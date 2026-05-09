
import cv2
import face_recognition
import numpy as np
import os
import threading
import pickle
import hashlib
import platform

DB_PATH = "aria/known_faces"
CACHE_PATH = "aria/face_cache.pkl"

def get_db_hash():
    files = []
    for person in sorted(os.listdir(DB_PATH)):
        person_dir = os.path.join(DB_PATH, person)
        if not os.path.isdir(person_dir):
            continue
        for photo in sorted(os.listdir(person_dir)):
            path = os.path.join(person_dir, photo)
            files.append(f"{path}_{os.path.getmtime(path)}")
    return hashlib.md5("|".join(files).encode()).hexdigest()

def load_encodings():
    current_hash = get_db_hash()
    
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "rb") as f:
            cache = pickle.load(f)
        if cache["hash"] == current_hash:
            print(f"Кэш актуален: {len(cache['encodings'])} encodings")
            return cache["encodings"], cache["names"]
    
    print("База изменилась, пересчитываю embeddings...")
    encodings, names = [], []
    for person in os.listdir(DB_PATH):
        person_dir = os.path.join(DB_PATH, person)
        if not os.path.isdir(person_dir):
            continue
        for photo in os.listdir(person_dir):
            if not photo.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            img = face_recognition.load_image_file(os.path.join(person_dir, photo))
            emb = face_recognition.face_encodings(img)
            if emb:
                encodings.append(emb[0])
                names.append(person)
    
    with open(CACHE_PATH, "wb") as f:
        pickle.dump({"hash": current_hash, "encodings": encodings, "names": names}, f)
    
    print(f"Готово: {len(encodings)} encodings, кэш сохранён")
    return encodings, names

known_encodings, known_names = load_encodings()

system = platform.system()
 
if system == "Darwin":
    cap = cv2.VideoCapture(2, cv2.CAP_AVFOUNDATION)
elif system == "Windows":
    cap = cv2.VideoCapture(0, cv2.CAP_DHSOW)
elif system == "Linux":
    cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
else:
    cap = cv2.VideoCapture(0, cv2.CAP_ANY)

last_label = "..."
last_color = (128, 128, 128)
analyzing = False

def analyze_frame(frame):
    global last_label, last_color, analyzing
    try:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        small = cv2.resize(rgb, (0, 0), fx=0.5, fy=0.5)
        locations = face_recognition.face_locations(small)
        encodings = face_recognition.face_encodings(small, locations)

        if encodings:
            distances = face_recognition.face_distance(known_encodings, encodings[0])
            best_idx = np.argmin(distances)
            if distances[best_idx] < 0.5:
                last_label = known_names[best_idx]
                last_color = (0, 255, 0)
            else:
                last_label = "Unknown"
                last_color = (0, 0, 255)
        else:
            last_label = "No face"
            last_color = (128, 128, 128)
    except Exception as e:
        print(e)
        last_label = "Error"
        last_color = (0, 0, 255)
    finally:
        analyzing = False

frame_count = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1

    if frame_count % 15 == 0 and not analyzing:
        analyzing = True
        t = threading.Thread(target=analyze_frame, args=(frame.copy(),))
        t.daemon = True
        t.start()

    cv2.putText(frame, last_label, (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, last_color, 2)
    cv2.imshow("ARIA - Face ID", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()