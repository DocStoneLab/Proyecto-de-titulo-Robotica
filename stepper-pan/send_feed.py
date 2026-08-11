import cv2
import requests
import time

SERVER_URL = 'http://100.64.158.87:5000/detect'

cap = cv2.VideoCapture(0)  # 0 = first USB webcam
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

print("Camera started, sending frames...")

frame_count = 0

while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to grab frame")
        break

    frame_count += 1
    if frame_count % 5 != 0:  # send every 5th frame
        continue

    _, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])

    try:
        response = requests.post(
            SERVER_URL,
            files={'image': ('frame.jpg', encoded.tobytes(), 'image/jpeg')},
            timeout=5
        )
        detections = response.json()
        if detections:
            print(f"Detections: {detections}")
    except Exception as e:
        print(f"Error sending frame: {e}")

    time.sleep(0.05)

cap.release()