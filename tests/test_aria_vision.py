import numpy as np
import pytest

pytest.importorskip("cv2")

from aria.vision import _coerce_camera_index, _identify_face


def test_coerce_camera_index_handles_model_values():
    assert _coerce_camera_index(None) is None
    assert _coerce_camera_index("") is None
    assert _coerce_camera_index("2") == 2
    assert _coerce_camera_index(3) == 3
    assert _coerce_camera_index("bad") is None


def test_identify_face_returns_nearest_match_under_threshold():
    known = [
        np.array([0.0, 0.0, 0.0]),
        np.array([1.0, 1.0, 1.0]),
    ]
    names = ["arseniy", "alice"]

    assert _identify_face(known, names, np.array([0.1, 0.1, 0.1]), 0.5) == "arseniy"
    assert _identify_face(known, names, np.array([0.6, 0.6, 0.6]), 0.5) is None
