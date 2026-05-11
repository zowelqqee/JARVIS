import cv2
from ultralytics import YOLO
import threading

MODEL_PATH = "yolov8l.pt"  # скачается автоматически

model = YOLO(MODEL_PATH)
print("Модель загружена")

cap = cv2.VideoCapture(2, cv2.CAP_AVFOUNDATION)

last_results = []
analyzing = False
frame_count = 0

def analyze_frame(frame):
    global last_results, analyzing
    try:
        results = model(frame, verbose=False)[0]
        detections = []
        for box in results.boxes:
            cls = int(box.cls[0])
            conf = float(box.conf[0])
            if conf < 0.6:
                continue
            label = model.names[cls]
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            detections.append((label, conf, x1, y1, x2, y2))
        last_results = detections
    except Exception as e:
        print(e)
    finally:
        analyzing = False

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1

    if frame_count % 5 == 0 and not analyzing:
        analyzing = True
        t = threading.Thread(target=analyze_frame, args=(frame.copy(),))
        t.daemon = True
        t.start()

    for label, conf, x1, y1, x2, y2 in last_results:
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(frame, f"{label} {conf:.0%}", (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    cv2.imshow("ARIA - Object Detection", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()