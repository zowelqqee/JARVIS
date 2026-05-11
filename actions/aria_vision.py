from __future__ import annotations


def aria_vision(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "object_detect").strip().lower()
    camera_index = parameters.get("camera_index")  # None = auto
    duration = int(parameters.get("duration") or 5)
    duration = max(2, min(duration, 30))

    try:
        if action == "face_detect":
            from aria.vision import run_face_detect
            result = run_face_detect(camera_index=camera_index, duration=duration)
            count = result["max_faces"]
            if count == 0:
                return "No faces detected in frame."
            return f"Detected up to {count} face(s) in the frame."

        elif action == "object_detect":
            from aria.vision import run_object_detect
            result = run_object_detect(camera_index=camera_index, duration=duration)
            objects = result["objects"]
            if not objects:
                return "No objects detected."
            items = ", ".join(
                f"{label} ({conf:.0%})"
                for label, conf in sorted(objects.items(), key=lambda x: -x[1])
            )
            return f"Detected: {items}."

        elif action == "face_id":
            from aria.vision import run_face_id
            result = run_face_id(camera_index=camera_index, duration=duration)
            identified = result["identified"]
            unknown = result["unknown"]
            if not identified and unknown == 0:
                return "No faces detected during identification."
            if not identified:
                return "Face detected but not recognized — unknown person."
            names = ", ".join(
                f"{name}"
                for name, _ in sorted(identified.items(), key=lambda x: -x[1])
            )
            suffix = f" (also {unknown} unrecognized frame(s))" if unknown else ""
            return f"Recognized: {names}{suffix}."

        else:
            return f"Unknown aria_vision action: {action}. Use face_detect, object_detect, or face_id."

    except Exception as e:
        return f"aria_vision error: {e}"
