from __future__ import annotations

import hashlib
import os
import pickle
import platform
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

_FACE_ENCODINGS_MEMORY_CACHE: dict[tuple[str, str], tuple[str, list, list]] = {}
_YOLO_MODEL_CACHE: dict[str, object] = {}


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _coerce_camera_index(index: int | str | None) -> int | None:
    if index in (None, ""):
        return None
    try:
        return int(index)
    except (TypeError, ValueError):
        return None


def _open_camera(index: int | None) -> cv2.VideoCapture:
    system = platform.system()
    index = _coerce_camera_index(index)
    if index is None:
        index = 2 if system == "Darwin" else 0
    if system == "Darwin":
        cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
    elif system == "Windows":
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(index, cv2.CAP_V4L2)

    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def _camera_warmup(cap: cv2.VideoCapture, frames: int = 3) -> None:
    for _ in range(max(0, frames)):
        cap.read()


def run_face_detect(camera_index: int | None = None, duration: int = 5) -> dict:
    """Detect faces via Haar cascade for `duration` seconds.

    Returns:
        {"max_faces": int, "duration": int}
    """
    cap = _open_camera(camera_index)
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    max_faces = 0
    deadline = time.time() + duration

    while time.time() < deadline:
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
        if len(faces) > max_faces:
            max_faces = len(faces)

    cap.release()
    return {"max_faces": max_faces, "duration": duration}


def run_object_detect(
    camera_index: int | None = None,
    duration: int = 5,
    model_path: str | None = None,
    conf_threshold: float = 0.6,
) -> dict:
    """Detect objects with YOLOv8 for `duration` seconds.

    Returns:
        {"objects": {label: confidence}, "duration": int}
    """
    from ultralytics import YOLO

    if model_path is None:
        base = _base_dir()
        for candidate in ("yolov8n.pt", "yolov8s.pt", "yolov8l.pt"):
            p = base / candidate
            if p.exists():
                model_path = str(p)
                break
        if model_path is None:
            model_path = "yolov8n.pt"

    model = _YOLO_MODEL_CACHE.get(model_path)
    if model is None:
        model = YOLO(model_path)
        _YOLO_MODEL_CACHE[model_path] = model
    cap = _open_camera(camera_index)
    _camera_warmup(cap)

    best: dict[str, float] = {}
    frame_count = 0
    analyzing = False
    lock = threading.Lock()
    deadline = time.time() + duration

    def _analyze(frame_copy):
        nonlocal analyzing
        try:
            results = model(frame_copy, verbose=False)[0]
            with lock:
                for box in results.boxes:
                    conf = float(box.conf[0])
                    if conf < conf_threshold:
                        continue
                    label = model.names[int(box.cls[0])]
                    if label not in best or conf > best[label]:
                        best[label] = round(conf, 2)
        finally:
            analyzing = False

    while time.time() < deadline:
        ret, frame = cap.read()
        if not ret:
            break
        frame_count += 1
        if frame_count % 5 == 0 and not analyzing:
            analyzing = True
            t = threading.Thread(target=_analyze, args=(frame.copy(),), daemon=True)
            t.start()

    cap.release()
    with lock:
        return {"objects": dict(best), "duration": duration}


def _load_face_encodings(db_path: Path, cache_path: Path):
    import face_recognition

    if not db_path.exists():
        return [], []

    def _db_hash() -> str:
        parts = []
        for person in sorted(os.listdir(db_path)):
            person_dir = db_path / person
            if not person_dir.is_dir():
                continue
            for photo in sorted(os.listdir(person_dir)):
                p = person_dir / photo
                parts.append(f"{p}_{p.stat().st_mtime}")
        return hashlib.md5("|".join(parts).encode()).hexdigest()

    current_hash = _db_hash()
    memory_key = (str(db_path.resolve()), str(cache_path.resolve()))
    memory_cache = _FACE_ENCODINGS_MEMORY_CACHE.get(memory_key)
    if memory_cache and memory_cache[0] == current_hash:
        return memory_cache[1], memory_cache[2]

    if cache_path.exists():
        with open(cache_path, "rb") as f:
            cache = pickle.load(f)
        if cache.get("hash") == current_hash:
            encodings, names = cache["encodings"], cache["names"]
            _FACE_ENCODINGS_MEMORY_CACHE[memory_key] = (current_hash, encodings, names)
            return encodings, names

    encodings, names = [], []
    for person in os.listdir(db_path):
        person_dir = db_path / person
        if not person_dir.is_dir():
            continue
        for photo in os.listdir(person_dir):
            if not photo.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            img = face_recognition.load_image_file(str(person_dir / photo))
            embs = face_recognition.face_encodings(img)
            if embs:
                encodings.append(embs[0])
                names.append(person)

    with open(cache_path, "wb") as f:
        pickle.dump({"hash": current_hash, "encodings": encodings, "names": names}, f)

    _FACE_ENCODINGS_MEMORY_CACHE[memory_key] = (current_hash, encodings, names)
    return encodings, names


def _identify_face(
    known_encodings,
    known_names,
    encoding,
    distance_threshold: float,
) -> str | None:
    if not known_encodings:
        return None
    distances = np.linalg.norm(np.asarray(known_encodings) - encoding, axis=1)
    best_idx = int(np.argmin(distances))
    if distances[best_idx] < distance_threshold:
        return known_names[best_idx]
    return None


def run_face_id(
    camera_index: int | None = None,
    duration: int = 5,
    db_path: str | None = None,
    cache_path: str | None = None,
    distance_threshold: float = 0.5,
    min_identified_hits: int = 1,
    frame_interval: int = 5,
) -> dict:
    """Identify known faces for `duration` seconds.

    Returns:
        {"identified": {name: count}, "unknown": int, "no_face": int, "duration": int}
    """
    import face_recognition

    base = _base_dir()
    _db = Path(db_path) if db_path else base / "aria" / "known_faces"
    _cache = Path(cache_path) if cache_path else base / "aria" / "face_cache.pkl"

    known_encodings, known_names = _load_face_encodings(_db, _cache)

    cap = _open_camera(camera_index)
    _camera_warmup(cap)

    identified: dict[str, int] = {}
    unknown = 0
    no_face = 0
    frame_count = 0
    analyzed_frames = 0
    deadline = time.time() + duration
    started_at = time.time()

    while time.time() < deadline:
        ret, frame = cap.read()
        if not ret:
            break
        frame_count += 1
        if frame_count % max(1, frame_interval) != 0:
            continue

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        small = cv2.resize(rgb, (0, 0), fx=0.5, fy=0.5)
        locations = face_recognition.face_locations(small, model="hog")
        encodings = face_recognition.face_encodings(small, locations)
        analyzed_frames += 1

        if not encodings:
            no_face += 1
            continue

        name = _identify_face(
            known_encodings,
            known_names,
            encodings[0],
            distance_threshold,
        )
        if name:
            identified[name] = identified.get(name, 0) + 1
            if identified[name] >= max(1, min_identified_hits):
                break
        else:
            unknown += 1

    cap.release()
    return {
        "identified": dict(identified),
        "unknown": unknown,
        "no_face": no_face,
        "duration": duration,
        "elapsed": round(time.time() - started_at, 2),
        "frames": frame_count,
        "analyzed_frames": analyzed_frames,
    }
