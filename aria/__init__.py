# Makes aria a proper Python package so PyInstaller can bundle aria.vision reliably.
# The standalone scripts (face_detect.py, face_id.py, object_detect.py) are NOT
# imported by the main application and are excluded from the bundle.
