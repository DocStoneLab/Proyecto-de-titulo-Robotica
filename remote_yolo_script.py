from flask import Flask, request, jsonify
from ultralytics import YOLO
import numpy as np
import cv2

app = Flask(__name__)
model = YOLO('yolo8n_mochilas.pt')

@app.route('/detect', methods=['POST'])
def detect():
    file = request.files['image']
    img = cv2.imdecode(np.frombuffer(file.read(), np.uint8), cv2.IMREAD_COLOR)

    results = model(img, imgsz=320, conf=0.6)

    detections = []
    for box in results[0].boxes:
        cls = int(box.cls[0])
        conf = float(box.conf[0])
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        center_x = int((x1 + x2) / 2)
        detections.append({
            'label': model.names[cls],
            'confidence': conf,
            'center_x': center_x
        })

    return jsonify(detections)

@app.route('/', methods=['GET'])
def index():
    return jsonify({"status": "Servidor activo", "endpoint": "/detect"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)