from __future__ import annotations


ASSISTANT_NAME = "F.R.I.D.A.Y."
ASSISTANT_PLAIN_NAME = "Friday"
ASSISTANT_SYSTEM_NAME = "FRIDAY"
ASSISTANT_VOICE_NAME = "Aoede"

PRIMARY_WAKE_WORDS = [
    "Friday",
    "Hey Friday",
    "Okay Friday",
    "F.R.I.D.A.Y.",
]

LEGACY_WAKE_WORDS = [
    "Jarvis",
    "Hey Jarvis",
    "Okay Jarvis",
    "Джарвис",
    "Окей Джарвис",
]


def build_wake_word_instruction() -> str:
    primary = ", ".join(f'"{word}"' for word in PRIMARY_WAKE_WORDS)
    legacy = ", ".join(f'"{word}"' for word in LEGACY_WAKE_WORDS)
    return f"""
        [WAKE WORD RULE]
        You MUST respond ONLY if the user's message begins with one of the primary wake words: {primary}.
        Legacy aliases {legacy} should also still work for backward compatibility.
        Exception: the stop word "стоп" / "stop" is always allowed and must interrupt the current process.
        If the message does NOT start with one of these triggers — stay completely silent.
        Do not respond, do not acknowledge, do not make any sound.
        """
