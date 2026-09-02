import cv2
import requests
import serial
import time

SERVER_URL = 'http://100.64.158.87:5000/detect'

# ── ARDUINO SERIAL (stepper/motor controller) ──
ARDUINO_PORT = '/dev/ttyUSB0'   # if this doesn't work, check with `ls /dev/tty*`
ARDUINO_BAUD = 9600

arduino = None
try:
    arduino = serial.Serial(ARDUINO_PORT, ARDUINO_BAUD, timeout=1)
    time.sleep(2)  # let the Arduino reset after the serial port opens
    print(f"Connected to Arduino on {ARDUINO_PORT}")
except Exception as e:
    print(f"Could not open Arduino serial port ({e}). Tracking commands will be skipped.")

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
        data = response.json()
        detections = data.get('detections', [])
        pan_steps = data.get('pan_steps', 0)

        if detections:
            print(f"Detections: {detections}")

        if pan_steps != 0:
            if arduino is not None:
                print(f"Sending T{pan_steps} to Arduino")
                try:
                    arduino.write(f"T{pan_steps}\n".encode())
                except Exception as e:
                    print(f"Error sending to Arduino: {e}")
            else:
                print(f"pan_steps={pan_steps} but Arduino is not connected - command NOT sent")

    except Exception as e:
        print(f"Error sending frame: {e}")

    time.sleep(0.05)

cap.release()
if arduino is not None:
    arduino.close()