"""Backend bridge between the desktop shell and the existing JARVIS core."""

from desktop.backend.engine_facade import EngineFacade, build_default_engine_facade
from desktop.backend.speech_service import DesktopSpeechService, SpeechState

__all__ = ["DesktopSpeechService", "EngineFacade", "SpeechState", "build_default_engine_facade"]
