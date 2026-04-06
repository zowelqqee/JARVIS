"""Product-level voice profiles and fallback helpers."""

from __future__ import annotations

from dataclasses import dataclass

VOICE_PROFILE_RU_ASSISTANT_MALE = "ru_assistant_male"
VOICE_PROFILE_RU_ASSISTANT_FEMALE = "ru_assistant_female"
VOICE_PROFILE_RU_ASSISTANT_ANY = "ru_assistant_any"
VOICE_PROFILE_EN_ASSISTANT_MALE = "en_assistant_male"
VOICE_PROFILE_EN_ASSISTANT_FEMALE = "en_assistant_female"
VOICE_PROFILE_EN_ASSISTANT_ANY = "en_assistant_any"


@dataclass(frozen=True, slots=True)
class VoiceProfile:
    """Stable product-level voice profile."""

    id: str
    language: str
    gender_hint: str | None = None


_VOICE_PROFILES = {
    VOICE_PROFILE_RU_ASSISTANT_MALE: VoiceProfile(
        id=VOICE_PROFILE_RU_ASSISTANT_MALE,
        language="ru",
        gender_hint="male",
    ),
    VOICE_PROFILE_RU_ASSISTANT_FEMALE: VoiceProfile(
        id=VOICE_PROFILE_RU_ASSISTANT_FEMALE,
        language="ru",
        gender_hint="female",
    ),
    VOICE_PROFILE_RU_ASSISTANT_ANY: VoiceProfile(
        id=VOICE_PROFILE_RU_ASSISTANT_ANY,
        language="ru",
        gender_hint=None,
    ),
    VOICE_PROFILE_EN_ASSISTANT_MALE: VoiceProfile(
        id=VOICE_PROFILE_EN_ASSISTANT_MALE,
        language="en",
        gender_hint="male",
    ),
    VOICE_PROFILE_EN_ASSISTANT_FEMALE: VoiceProfile(
        id=VOICE_PROFILE_EN_ASSISTANT_FEMALE,
        language="en",
        gender_hint="female",
    ),
    VOICE_PROFILE_EN_ASSISTANT_ANY: VoiceProfile(
        id=VOICE_PROFILE_EN_ASSISTANT_ANY,
        language="en",
        gender_hint=None,
    ),
}

_DEFAULT_PROFILE_BY_LANGUAGE = {
    "en": VOICE_PROFILE_EN_ASSISTANT_MALE,
    "ru": VOICE_PROFILE_RU_ASSISTANT_MALE,
}

_ANY_PROFILE_BY_LANGUAGE = {
    "en": VOICE_PROFILE_EN_ASSISTANT_ANY,
    "ru": VOICE_PROFILE_RU_ASSISTANT_ANY,
}


def get_voice_profile(profile_id: str | None) -> VoiceProfile | None:
    """Return one known voice profile by identifier."""
    key = str(profile_id or "").strip().lower()
    if not key:
        return None
    return _VOICE_PROFILES.get(key)


def default_voice_profile_for_locale(locale: str | None) -> str | None:
    """Return the default product profile for one spoken locale."""
    language = _language_from_locale(locale)
    if not language:
        return None
    return _DEFAULT_PROFILE_BY_LANGUAGE.get(language)


def fallback_voice_profile_ids(
    profile_id: str | None,
    locale: str | None = None,
) -> tuple[str, ...]:
    """Return ordered product-level fallback profiles for one request.

    Phase 1 keeps profiles language-scoped. Locale-specific ranking stays backend-local,
    while the shared layer handles stable profile fallback within a language family.
    """

    resolved_profile_id = _resolved_profile_id(profile_id, locale)
    profile = get_voice_profile(resolved_profile_id)
    if profile is None:
        return ()

    candidates = [profile.id]
    any_profile = _ANY_PROFILE_BY_LANGUAGE.get(profile.language)
    if any_profile and any_profile not in candidates:
        candidates.append(any_profile)
    return tuple(candidates)


def _resolved_profile_id(profile_id: str | None, locale: str | None) -> str | None:
    explicit = str(profile_id or "").strip().lower()
    if explicit in _VOICE_PROFILES:
        return explicit
    return default_voice_profile_for_locale(locale)


def _language_from_locale(locale: str | None) -> str:
    normalized_locale = str(locale or "").strip().lower().replace("_", "-")
    if not normalized_locale:
        return ""
    return normalized_locale.split("-", maxsplit=1)[0]
