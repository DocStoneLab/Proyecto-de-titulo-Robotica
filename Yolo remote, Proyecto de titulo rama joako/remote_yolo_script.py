import threading
import time
import numpy as np
import cv2
from flask import Flask, request, jsonify, Response
from ultralytics import YOLO

app = Flask(__name__)
model = YOLO('yolo8n_mochilas.pt')

# Frame compartido para el streaming web
latest_frame = None
frame_lock = threading.Lock()

@app.route('/detect', methods=['POST'])
def detect():
    global latest_frame
    if 'image' not in request.files:
        return jsonify({'error': 'No se envió ninguna imagen'}), 400

    file = request.files['image']
    img = cv2.imdecode(np.frombuffer(file.read(), np.uint8), cv2.IMREAD_COLOR)

    if img is None:
        return jsonify({'error': 'Error decodificando imagen'}), 400

    results = model(img, imgsz=320, conf=0.6)

    # Dibujar las detecciones en la imagen
    annotated_frame = results[0].plot()

    # Guardar en memoria para transmitir a la página web
    with frame_lock:
        latest_frame = annotated_frame.copy()


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

def generar_streaming():
    # Frame de espera mientras la Raspberry no envíe imágenes
    placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(placeholder, "Servidor en espera de imagenes...", (40, 220),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    cv2.putText(placeholder, "Presiona 'b' o habla en la Raspberry para iniciar", (40, 270),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1)

    while True:
        with frame_lock:
            frame_actual = latest_frame if latest_frame is not None else placeholder
            ret, buffer = cv2.imencode('.jpg', frame_actual)

        if ret:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        time.sleep(0.04)

@app.route('/video_feed')
def video_feed():
    return Response(generar_streaming(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/', methods=['GET'])
def index():
    return """
    <!DOCTYPE html>
    <html lang="es">
        <head>
            <title>Panel de Monitoreo YOLO - Mochilas</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                    background-color: #0f172a;
                    color: #f8fafc;
                    margin: 0;
                    padding: 30px 15px;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                }
                .card {
                    background: #1e293b;
                    border: 1px solid #334155;
                    border-radius: 14px;
                    padding: 24px;
                    max-width: 720px;
                    width: 100%;
                    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.4);
                    text-align: center;
                }
                h1 {
                    font-size: 22px;
                    color: #38bdf8;
                    margin-top: 0;
                }
                .badge {
                    display: inline-block;
                    background: #15803d;
                    color: #fff;
                    font-weight: bold;
                    padding: 4px 12px;
                    border-radius: 20px;
                    font-size: 13px;
                    margin-bottom: 12px;
                }
                .video-container {
                    margin: 16px 0;
                    border-radius: 10px;
                    overflow: hidden;
                    border: 2px solid #475569;
                    background: #000;
                    line-height: 0;
                }
                img {
                    width: 100%;
                    max-width: 640px;
                    height: auto;
                    display: block;
                    margin: 0 auto;
                }
                p.info {
                    color: #94a3b8;
                    font-size: 14px;
                    margin: 8px 0 0 0;
                }
            </style>
        </head>
        <body>
            <div class="card">
                <span class="badge">● SERVIDOR ACTIVO</span>
                <h1>Cámara en Vivo & Detección YOLO</h1>
                <p class="info">Modelo <code>yolo8n_mochilas.pt</code> | Endpoint: <code>/detect</code></p>
                <div class="video-container">
                    <img src="/video_feed" alt="Transmisión en Vivo">
                </div>
                <p class="info">
                    💡 La imagen se actualiza en tiempo real cuando el robot pasa al estado de búsqueda.
                </p>
            </div>
        </body>
    </html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)