from actions.computer_settings import _detect_action_locally, _normalize_action_name


def test_local_settings_detector_handles_russian_system_settings():
    assert _detect_action_locally("открой системные настройки") == {
        "action": "open_settings",
        "value": None,
    }


def test_local_settings_detector_handles_volume_percent():
    assert _detect_action_locally("поставь громкость на 35%") == {
        "action": "volume_set",
        "value": 35,
    }


def test_local_settings_detector_handles_sound_on_without_gemini():
    assert _detect_action_locally("turn on sound") == {
        "action": "unmute",
        "value": None,
    }


def test_normalize_action_name_accepts_russian_aliases():
    assert _normalize_action_name("тёмная тема") == "dark_mode"
    assert _normalize_action_name("вайфай") == "toggle_wifi"


def test_normalize_action_name_maps_volume_to_set_volume():
    assert _normalize_action_name("volume") == "volume_set"
    assert _normalize_action_name("turn on sound") == "unmute"
