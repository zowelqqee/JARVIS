"""Contract tests for the experimental native macOS TTS backend."""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import ANY, MagicMock, patch

from voice.backends import macos_native
from voice.backends.macos_native import MacOSNativeTTSBackend
from voice.tts_provider import SpeechUtterance


class MacOSNativeTTSBackendTests(unittest.TestCase):
    """Protect native-host request/response handling and interruption hooks."""

    def test_is_available_uses_ping_response(self) -> None:
        backend = MacOSNativeTTSBackend(host_command=["xcrun", "swift", "/tmp/macos_tts_host.swift"])
        ping_process = MagicMock()
        ping_process.stdout = '{"ok": true, "backend_name": "macos_native"}'
        ping_process.stderr = ""
        ping_process.returncode = 0

        with patch("voice.backends.macos_native.sys.platform", "darwin"), patch(
            "voice.backends.macos_native.subprocess.run",
            return_value=ping_process,
        ) as run_mock:
            self.assertTrue(backend.is_available())
            self.assertTrue(backend.is_available())

        run_mock.assert_called_once()

    def test_default_host_command_uses_writable_module_cache_for_ping(self) -> None:
        backend = MacOSNativeTTSBackend(host_path="/tmp/macos_tts_host.swift")
        ping_process = MagicMock()
        ping_process.stdout = '{"ok": true, "backend_name": "macos_native"}'
        ping_process.stderr = ""
        ping_process.returncode = 0

        with patch("voice.backends.macos_native.sys.platform", "darwin"), patch(
            "pathlib.Path.exists",
            return_value=True,
        ), patch(
            "pathlib.Path.mkdir",
        ) as mkdir_mock, patch(
            "voice.backends.macos_native.subprocess.run",
            return_value=ping_process,
        ) as run_mock:
            self.assertTrue(backend.is_available())

        mkdir_mock.assert_called_once_with(parents=True, exist_ok=True)
        run_mock.assert_called_once_with(
            [
                "xcrun",
                "swift",
                "-module-cache-path",
                str(macos_native._HOST_MODULE_CACHE_PATH),
                "/tmp/macos_tts_host.swift",
            ],
            input='{"op": "ping"}\n',
            stdout=ANY,
            stderr=ANY,
            text=True,
            check=False,
            timeout=15.0,
        )

    def test_is_available_records_host_missing_reason(self) -> None:
        backend = MacOSNativeTTSBackend(host_path="/tmp/does-not-exist.swift")

        with patch("voice.backends.macos_native.sys.platform", "darwin"):
            self.assertFalse(backend.is_available())

        self.assertEqual(
            backend.availability_diagnostic(),
            ("HOST_MISSING", "Native macOS TTS host not found at /tmp/does-not-exist.swift."),
        )

    def test_is_available_classifies_missing_swift_toolchain(self) -> None:
        backend = MacOSNativeTTSBackend(host_command=["xcrun", "swift", "/tmp/macos_tts_host.swift"])

        with patch("voice.backends.macos_native.sys.platform", "darwin"), patch(
            "voice.backends.macos_native.subprocess.run",
            side_effect=OSError("[Errno 2] No such file or directory: 'xcrun'"),
        ):
            self.assertFalse(backend.is_available())

        self.assertEqual(
            backend.availability_diagnostic(),
            (
                "HOST_TOOLCHAIN_MISSING",
                "Native macOS Swift toolchain is unavailable; check `xcrun`, `swift`, and Command Line Tools.",
            ),
        )

    def test_is_available_classifies_swift_sdk_mismatch(self) -> None:
        backend = MacOSNativeTTSBackend(host_command=["xcrun", "swift", "/tmp/macos_tts_host.swift"])
        ping_process = MagicMock()
        ping_process.stdout = ""
        ping_process.stderr = (
            "error: failed to build module 'CoreFoundation'; this SDK is not supported by the compiler "
            "(the SDK is built with 'Apple Swift version 6.0 effective-5.10', while this compiler is "
            "'Apple Swift version 5.9')."
        )
        ping_process.returncode = 1
        developer_dir_process = MagicMock()
        developer_dir_process.stdout = "/Library/Developer/CommandLineTools\n"
        developer_dir_process.stderr = ""
        developer_dir_process.returncode = 0
        swiftc_path_process = MagicMock()
        swiftc_path_process.stdout = "/Library/Developer/CommandLineTools/usr/bin/swiftc\n"
        swiftc_path_process.stderr = ""
        swiftc_path_process.returncode = 0

        with patch("voice.backends.macos_native.sys.platform", "darwin"), patch(
            "voice.backends.macos_native.subprocess.run",
            side_effect=[ping_process, developer_dir_process, swiftc_path_process],
        ):
            self.assertFalse(backend.is_available())

        self.assertEqual(
            backend.availability_diagnostic(),
            (
                "HOST_SDK_MISMATCH",
                "Native macOS Swift compiler and SDK appear mismatched; align Xcode and Command Line Tools.",
            ),
        )
        self.assertEqual(
            backend.availability_detail_lines(),
            (
                "sdk toolchain: Apple Swift version 6.0 effective-5.10",
                "active compiler: Apple Swift version 5.9",
                "active developer dir: /Library/Developer/CommandLineTools",
                "active swiftc: /Library/Developer/CommandLineTools/usr/bin/swiftc",
            ),
        )

    def test_is_available_reports_developer_dir_override_when_set(self) -> None:
        backend = MacOSNativeTTSBackend(host_command=["xcrun", "swift", "/tmp/macos_tts_host.swift"])
        ping_process = MagicMock()
        ping_process.stdout = ""
        ping_process.stderr = (
            "error: failed to build module 'CoreFoundation'; this SDK is not supported by the compiler "
            "(the SDK is built with 'Apple Swift version 6.0 effective-5.10', while this compiler is "
            "'Apple Swift version 5.9')."
        )
        ping_process.returncode = 1
        developer_dir_process = MagicMock()
        developer_dir_process.stdout = "/Applications/Xcode.app/Contents/Developer\n"
        developer_dir_process.stderr = ""
        developer_dir_process.returncode = 0
        swiftc_path_process = MagicMock()
        swiftc_path_process.stdout = "/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc\n"
        swiftc_path_process.stderr = ""
        swiftc_path_process.returncode = 0

        with patch.dict(
            "voice.backends.macos_native.os.environ",
            {"DEVELOPER_DIR": "/Applications/Xcode.app/Contents/Developer"},
            clear=False,
        ), patch("voice.backends.macos_native.sys.platform", "darwin"), patch(
            "voice.backends.macos_native.subprocess.run",
            side_effect=[ping_process, developer_dir_process, swiftc_path_process],
        ):
            self.assertFalse(backend.is_available())

        self.assertEqual(
            backend.availability_detail_lines(),
            (
                "sdk toolchain: Apple Swift version 6.0 effective-5.10",
                "active compiler: Apple Swift version 5.9",
                "developer dir override: /Applications/Xcode.app/Contents/Developer",
                "active developer dir: /Applications/Xcode.app/Contents/Developer",
                "active swiftc: /Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc",
            ),
        )

    def test_is_available_classifies_swift_bridging_conflict(self) -> None:
        backend = MacOSNativeTTSBackend(host_command=["xcrun", "swift", "/tmp/macos_tts_host.swift"])
        ping_process = MagicMock()
        ping_process.stdout = ""
        ping_process.stderr = "error: duplicate module 'SwiftBridging' found while compiling host."
        ping_process.returncode = 1

        with patch("voice.backends.macos_native.sys.platform", "darwin"), patch(
            "voice.backends.macos_native.subprocess.run",
            return_value=ping_process,
        ):
            self.assertFalse(backend.is_available())

        self.assertEqual(
            backend.availability_diagnostic(),
            (
                "HOST_SWIFT_BRIDGING_CONFLICT",
                "Native macOS Swift toolchain reported a SwiftBridging module conflict.",
            ),
        )

    def test_is_available_timeout_reports_runtime_toolchain_detail_lines(self) -> None:
        backend = MacOSNativeTTSBackend(host_command=["xcrun", "swift", "/tmp/macos_tts_host.swift"])
        developer_dir_process = MagicMock()
        developer_dir_process.stdout = "/Library/Developer/CommandLineTools\n"
        developer_dir_process.stderr = ""
        developer_dir_process.returncode = 0
        swiftc_path_process = MagicMock()
        swiftc_path_process.stdout = "/Library/Developer/CommandLineTools/usr/bin/swiftc\n"
        swiftc_path_process.stderr = ""
        swiftc_path_process.returncode = 0

        with patch("voice.backends.macos_native.sys.platform", "darwin"), patch(
            "voice.backends.macos_native.subprocess.run",
            side_effect=[
                subprocess.TimeoutExpired(cmd=["xcrun", "swift", "/tmp/macos_tts_host.swift"], timeout=15.0),
                developer_dir_process,
                swiftc_path_process,
            ],
        ):
            self.assertFalse(backend.is_available())

        self.assertEqual(
            backend.availability_diagnostic(),
            (
                "HOST_TIMEOUT",
                "Native macOS TTS host ping timed out.",
            ),
        )
        self.assertEqual(
            backend.availability_detail_lines(),
            (
                "active developer dir: /Library/Developer/CommandLineTools",
                "active swiftc: /Library/Developer/CommandLineTools/usr/bin/swiftc",
            ),
        )

    def test_is_available_refines_ping_failure_with_typecheck_result(self) -> None:
        backend = MacOSNativeTTSBackend()
        ping_process = MagicMock()
        ping_process.stdout = ""
        ping_process.stderr = (
            "error: failed to build module 'CoreFoundation'; this SDK is not supported by the compiler."
        )
        ping_process.returncode = 1
        typecheck_process = MagicMock()
        typecheck_process.stdout = ""
        typecheck_process.stderr = "error: duplicate module 'SwiftBridging' found while compiling host."
        typecheck_process.returncode = 1

        with patch("voice.backends.macos_native.sys.platform", "darwin"), patch(
            "voice.backends.macos_native.subprocess.run",
            side_effect=[ping_process, typecheck_process],
        ) as run_mock:
            self.assertFalse(backend.is_available())

        self.assertEqual(run_mock.call_count, 2)
        self.assertEqual(
            backend.availability_diagnostic(),
            (
                "HOST_SWIFT_BRIDGING_CONFLICT",
                "Native macOS Swift toolchain reported a SwiftBridging module conflict.",
            ),
        )

    def test_is_available_compile_failed_reports_runtime_toolchain_context(self) -> None:
        backend = MacOSNativeTTSBackend(host_command=["xcrun", "swift", "/tmp/macos_tts_host.swift"])
        ping_process = MagicMock()
        ping_process.stdout = ""
        ping_process.stderr = "error: link command failed with exit code 1"
        ping_process.returncode = 1
        developer_dir_process = MagicMock()
        developer_dir_process.stdout = "/tmp/jarvis-invalid-developer-dir\n"
        developer_dir_process.stderr = ""
        developer_dir_process.returncode = 0
        swiftc_path_process = MagicMock()
        swiftc_path_process.stdout = "/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc\n"
        swiftc_path_process.stderr = ""
        swiftc_path_process.returncode = 0

        with patch.dict(
            "voice.backends.macos_native.os.environ",
            {"DEVELOPER_DIR": "/tmp/jarvis-invalid-developer-dir"},
            clear=False,
        ), patch("voice.backends.macos_native.sys.platform", "darwin"), patch(
            "voice.backends.macos_native.subprocess.run",
            side_effect=[ping_process, developer_dir_process, swiftc_path_process],
        ):
            self.assertFalse(backend.is_available())

        self.assertEqual(
            backend.availability_diagnostic(),
            (
                "HOST_COMPILE_FAILED",
                "Native macOS TTS host failed to compile or start. First error: error: link command failed with exit code 1",
            ),
        )
        self.assertEqual(
            backend.availability_detail_lines(),
            (
                "developer dir override: /tmp/jarvis-invalid-developer-dir",
                "active developer dir: /tmp/jarvis-invalid-developer-dir",
                "active swiftc: /Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc",
            ),
        )

    def test_list_voices_parses_host_descriptors(self) -> None:
        backend = MacOSNativeTTSBackend(host_command=["xcrun", "swift", "/tmp/macos_tts_host.swift"])
        list_process = MagicMock()
        list_process.stdout = (
            '{"ok": true, "backend_name": "macos_native", "voices": '
            '[{"id": "com.apple.voice.yuri", "display_name": "Yuri", "locale": "ru-RU", "gender_hint": "male", '
            '"quality_hint": "assistant", "source": "macos_native", "is_default": true}]}'
        )
        list_process.stderr = ""
        list_process.returncode = 0

        with patch("voice.backends.macos_native.sys.platform", "darwin"), patch(
            "voice.backends.macos_native.subprocess.run",
            return_value=list_process,
        ):
            voices = backend.list_voices(locale_hint="ru-RU")

        self.assertEqual(len(voices), 1)
        self.assertEqual(voices[0].id, "com.apple.voice.yuri")
        self.assertEqual(voices[0].display_name, "Yuri")
        self.assertEqual(voices[0].locale, "ru-RU")
        self.assertEqual(voices[0].quality_hint, "assistant")
        self.assertTrue(voices[0].is_default)

    def test_resolve_voice_returns_descriptor_from_host_payload(self) -> None:
        backend = MacOSNativeTTSBackend(host_command=["xcrun", "swift", "/tmp/macos_tts_host.swift"])
        resolve_process = MagicMock()
        resolve_process.stdout = (
            '{"ok": true, "backend_name": "macos_native", "voice": '
            '{"id": "com.apple.voice.ru.assistant.male", "display_name": "Russian Assistant", '
            '"locale": "ru-RU", "gender_hint": "male", "quality_hint": "assistant", '
            '"source": "macos_native", "is_default": false}}'
        )
        resolve_process.stderr = ""
        resolve_process.returncode = 0

        with patch("voice.backends.macos_native.sys.platform", "darwin"), patch(
            "voice.backends.macos_native.subprocess.run",
            return_value=resolve_process,
        ):
            voice = backend.resolve_voice("ru_assistant_male", "ru-RU")

        self.assertIsNotNone(voice)
        self.assertEqual(voice.id, "com.apple.voice.ru.assistant.male")
        self.assertEqual(voice.gender_hint, "male")

    def test_speak_returns_host_result_and_voice_id(self) -> None:
        backend = MacOSNativeTTSBackend(host_command=["xcrun", "swift", "/tmp/macos_tts_host.swift"])
        process = MagicMock()
        process.communicate.return_value = (
            '{"ok": true, "backend_name": "macos_native", "voice_id": "com.apple.voice.ru.assistant.male"}',
            "",
        )
        process.returncode = 0

        with patch("voice.backends.macos_native.sys.platform", "darwin"), patch(
            "voice.backends.macos_native.subprocess.Popen",
            return_value=process,
        ) as popen_mock:
            result = backend.speak(
                SpeechUtterance(
                    text="Привет",
                    locale="ru-RU",
                    voice_profile="ru_assistant_male",
                )
            )

        self.assertTrue(result.ok)
        self.assertEqual(result.backend_name, "macos_native")
        self.assertEqual(result.voice_id, "com.apple.voice.ru.assistant.male")
        popen_mock.assert_called_once_with(
            ["xcrun", "swift", "/tmp/macos_tts_host.swift"],
            stdin=ANY,
            stdout=ANY,
            stderr=ANY,
            text=True,
        )

    def test_stop_terminates_active_host_process(self) -> None:
        backend = MacOSNativeTTSBackend(host_command=["xcrun", "swift", "/tmp/macos_tts_host.swift"])
        process = MagicMock()
        process.poll.return_value = None
        backend._current_process = process

        stopped = backend.stop()

        self.assertTrue(stopped)
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=0.2)


if __name__ == "__main__":
    unittest.main()
