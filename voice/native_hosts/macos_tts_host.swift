import AppKit
import Foundation

private let backendName = "macos_native"

private struct VoiceDescriptor {
    let id: String
    let displayName: String
    let locale: String?
    let genderHint: String?
    let qualityHint: String?
    let source: String
    let isDefault: Bool

    var payload: [String: Any] {
        [
            "id": id,
            "display_name": displayName,
            "locale": locale as Any,
            "gender_hint": genderHint as Any,
            "quality_hint": qualityHint as Any,
            "source": source,
            "is_default": isDefault,
        ]
    }
}

private final class SpeechDelegate: NSObject, NSSpeechSynthesizerDelegate {
    var completed = false
    var finishedSpeaking = false

    func speechSynthesizer(_ sender: NSSpeechSynthesizer, didFinishSpeaking finishedSpeaking: Bool) {
        self.finishedSpeaking = finishedSpeaking
        self.completed = true
    }
}

private func emit(_ payload: [String: Any], exitCode: Int32 = 0) -> Never {
    let data: Data
    do {
        data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    } catch {
        let fallback = "{\"ok\":false,\"backend_name\":\"\(backendName)\",\"error_code\":\"HOST_JSON_FAILED\",\"error_message\":\"\(error.localizedDescription)\"}"
        FileHandle.standardOutput.write(Data(fallback.utf8))
        exit(1)
    }
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
    exit(exitCode)
}

private func requestPayload() throws -> [String: Any] {
    let data = FileHandle.standardInput.readDataToEndOfFile()
    guard !data.isEmpty else {
        throw NSError(domain: backendName, code: 1, userInfo: [NSLocalizedDescriptionKey: "Empty request payload."])
    }
    let object = try JSONSerialization.jsonObject(with: data)
    guard let payload = object as? [String: Any] else {
        throw NSError(domain: backendName, code: 2, userInfo: [NSLocalizedDescriptionKey: "Request payload must be a JSON object."])
    }
    return payload
}

private func normalizedLocale(_ rawValue: String?) -> String? {
    let locale = (rawValue ?? "").trimmingCharacters(in: .whitespacesAndNewlines).replacingOccurrences(of: "_", with: "-")
    return locale.isEmpty ? nil : locale
}

private func matchesLocale(_ candidate: String?, localeHint: String?) -> Bool {
    guard let hint = normalizedLocale(localeHint)?.lowercased(), !hint.isEmpty else {
        return true
    }
    let locale = normalizedLocale(candidate)?.lowercased() ?? ""
    if locale == hint {
        return true
    }
    return locale.split(separator: "-", maxSplits: 1).first == hint.split(separator: "-", maxSplits: 1).first
}

private func qualityHint(for id: String, displayName: String) -> String {
    let haystack = "\(id) \(displayName)".lowercased()
    if haystack.contains("assistant") || haystack.contains("siri") {
        return "assistant"
    }
    if haystack.contains("premium") || haystack.contains("enhanced") {
        return "premium"
    }
    if haystack.contains("compact") {
        return "compact"
    }
    return "default"
}

private func genderHint(from rawValue: Any?, id: String, displayName: String) -> String? {
    let attrText = String(describing: rawValue ?? "").lowercased()
    if attrText.contains("male") {
        return "male"
    }
    if attrText.contains("female") {
        return "female"
    }
    let haystack = "\(id) \(displayName)".lowercased()
    if haystack.contains(" female") || haystack.hasSuffix("female") {
        return "female"
    }
    if haystack.contains(" male") || haystack.hasSuffix("male") {
        return "male"
    }
    return nil
}

private func voiceDescriptor(from voice: NSSpeechSynthesizer.VoiceName) -> VoiceDescriptor? {
    let voiceID = voice.rawValue
    guard !voiceID.isEmpty else {
        return nil
    }
    let attributes = NSSpeechSynthesizer.attributes(forVoice: voice)
    let displayName = (attributes[.name] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
    let locale = normalizedLocale(String(describing: attributes[.localeIdentifier] ?? ""))
    let resolvedDisplayName = (displayName?.isEmpty == false ? displayName! : voiceID)
    return VoiceDescriptor(
        id: voiceID,
        displayName: resolvedDisplayName,
        locale: locale,
        genderHint: genderHint(from: attributes[.gender], id: voiceID, displayName: resolvedDisplayName),
        qualityHint: qualityHint(for: voiceID, displayName: resolvedDisplayName),
        source: backendName,
        isDefault: NSSpeechSynthesizer.defaultVoice.rawValue == voiceID
    )
}

private func allVoices() -> [VoiceDescriptor] {
    NSSpeechSynthesizer.availableVoices.compactMap { voiceDescriptor(from: $0) }
}

private func profileLanguage(_ profile: String?, locale: String?) -> String? {
    let normalizedProfile = (profile ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    if normalizedProfile.hasPrefix("ru_") {
        return "ru"
    }
    if normalizedProfile.hasPrefix("en_") {
        return "en"
    }
    return normalizedLocale(locale)?.split(separator: "-", maxSplits: 1).first.map(String.init)
}

private func profileGender(_ profile: String?) -> String? {
    let normalizedProfile = (profile ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    if normalizedProfile.hasSuffix("_male") {
        return "male"
    }
    if normalizedProfile.hasSuffix("_female") {
        return "female"
    }
    return nil
}

private func resolveVoice(profile: String?, locale: String?) -> VoiceDescriptor? {
    let voices = allVoices()
    guard !voices.isEmpty else {
        return nil
    }
    let targetLocale = normalizedLocale(locale)?.lowercased()
    let targetLanguage = profileLanguage(profile, locale: locale)?.lowercased()
    let targetGender = profileGender(profile)

    func score(_ voice: VoiceDescriptor) -> Int {
        var total = 0
        let locale = normalizedLocale(voice.locale)?.lowercased()
        let language = locale?.split(separator: "-", maxSplits: 1).first.map(String.init)
        if locale == targetLocale, targetLocale != nil {
            total += 100
        } else if language == targetLanguage, targetLanguage != nil {
            total += 40
        }
        if voice.genderHint == targetGender, targetGender != nil {
            total += 20
        }
        if voice.qualityHint == "assistant" {
            total += 10
        } else if voice.qualityHint == "premium" {
            total += 6
        }
        if voice.isDefault {
            total += 2
        }
        return total
    }

    return voices.sorted {
        let leftScore = score($0)
        let rightScore = score($1)
        if leftScore != rightScore {
            return leftScore > rightScore
        }
        return $0.displayName.localizedCaseInsensitiveCompare($1.displayName) == .orderedAscending
    }.first
}

private func selectedVoice(explicitVoiceID: String?, profile: String?, locale: String?) -> (NSSpeechSynthesizer.VoiceName?, VoiceDescriptor?) {
    if let explicitVoiceID, !explicitVoiceID.isEmpty {
        for voice in NSSpeechSynthesizer.availableVoices where voice.rawValue == explicitVoiceID {
            return (voice, voiceDescriptor(from: voice))
        }
    }
    guard let descriptor = resolveVoice(profile: profile, locale: locale) else {
        return (nil, nil)
    }
    let voice = NSSpeechSynthesizer.availableVoices.first { $0.rawValue == descriptor.id }
    return (voice, descriptor)
}

private func listVoices(localeHint: String?) -> [VoiceDescriptor] {
    allVoices().filter { matchesLocale($0.locale, localeHint: localeHint) }.sorted {
        if $0.locale != $1.locale {
            return ($0.locale ?? "") < ($1.locale ?? "")
        }
        return $0.displayName.localizedCaseInsensitiveCompare($1.displayName) == .orderedAscending
    }
}

private func handleSpeak(request: [String: Any]) -> Never {
    let text = String(describing: request["text"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    if text.isEmpty {
        emit([
            "ok": true,
            "attempted": false,
            "backend_name": backendName,
        ])
    }

    let locale = normalizedLocale(request["locale"] as? String)
    let voiceProfile = request["voice_profile"] as? String
    let explicitVoiceID = (request["voice_id"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
    let resolved = selectedVoice(explicitVoiceID: explicitVoiceID, profile: voiceProfile, locale: locale)
    let synthesizer = resolved.0.flatMap { NSSpeechSynthesizer(voice: $0) } ?? NSSpeechSynthesizer()
    let delegate = SpeechDelegate()
    synthesizer.delegate = delegate

    if let rate = request["rate"] as? Double {
        synthesizer.rate = max(120.0, min(320.0, Float(rate) * 180.0))
    }
    if let volume = request["volume"] as? Double {
        synthesizer.volume = max(0.0, min(1.0, Float(volume)))
    }

    guard synthesizer.startSpeaking(text) else {
        emit([
            "ok": false,
            "backend_name": backendName,
            "voice_id": resolved.1?.id as Any,
            "error_code": "TTS_FAILED",
            "error_message": "Native macOS speech synthesis did not start.",
        ], exitCode: 1)
    }

    while !delegate.completed {
        RunLoop.current.run(mode: .default, before: Date(timeIntervalSinceNow: 0.05))
    }

    if delegate.finishedSpeaking {
        emit([
            "ok": true,
            "backend_name": backendName,
            "voice_id": resolved.1?.id as Any,
        ])
    }
    emit([
        "ok": false,
        "backend_name": backendName,
        "voice_id": resolved.1?.id as Any,
        "error_code": "TTS_FAILED",
        "error_message": "Speech stopped before completion.",
    ], exitCode: 1)
}

let request: [String: Any]
do {
    request = try requestPayload()
} catch {
    emit([
        "ok": false,
        "backend_name": backendName,
        "error_code": "HOST_REQUEST_INVALID",
        "error_message": error.localizedDescription,
    ], exitCode: 1)
}

let operation = String(describing: request["op"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)

switch operation {
case "ping":
    emit([
        "ok": true,
        "backend_name": backendName,
    ])
case "list_voices":
    emit([
        "ok": true,
        "backend_name": backendName,
        "voices": listVoices(localeHint: request["locale_hint"] as? String).map(\.payload),
    ])
case "resolve_voice":
    emit([
        "ok": true,
        "backend_name": backendName,
        "voice": resolveVoice(
            profile: request["voice_profile"] as? String,
            locale: request["locale"] as? String
        )?.payload as Any,
    ])
case "stop":
    emit([
        "ok": true,
        "backend_name": backendName,
    ])
case "speak":
    handleSpeak(request: request)
default:
    emit([
        "ok": false,
        "backend_name": backendName,
        "error_code": "HOST_UNSUPPORTED_OPERATION",
        "error_message": "Unsupported operation: \(operation)",
    ], exitCode: 1)
}
