"""
send_feed.py - Sistema Integrado de Visión, Paneo y Notificación a Cerebro

Funcionalidad:
1. Captura frames de la webcam USB y los envía al servidor YOLO.
2. Controla el motor de pasos de la cámara (Arduino Motores/Stepper) con T<steps>.
3. Cuando detecta el bastón/objeto, envía la orientación ('i', 'd' o 'f') al Arduino Cerebro.
4. Escucha a Cerebro: cuando recibe 'EVT:OBJETIVO_10CM', reproduce el sonido de alerta.
"""

import cv2
import requests
import serial
import time
import os
import threading

SERVER_URL = 'http://100.64.158.87:5000/detect'

# ── PUERTOS SERIALES ARDUINOS ──
# Arduino de Motores / Stepper
PUERTO_STEPPER = '/dev/ttyUSB0'
BAUD_STEPPER   = 9600

# Arduino Cerebro (Navegación / Sensores)
PUERTO_CEREBRO = '/dev/ttyACM0'  # Si no conecta, verificar con 'ls /dev/tty*'
BAUD_CEREBRO   = 115200

arduino_stepper = None
arduino_cerebro = None

# Conexión Stepper / Motores
try:
    arduino_stepper = serial.Serial(PUERTO_STEPPER, BAUD_STEPPER, timeout=1)
    time.sleep(2)
    print(f"[OK] Conectado a Arduino Stepper en {PUERTO_STEPPER}")
except Exception as e:
    print(f"[AVISO] No se pudo abrir {PUERTO_STEPPER} ({e}). Comandos de paneo omitidos.")

# Conexión Cerebro
try:
    arduino_cerebro = serial.Serial(PUERTO_CEREBRO, BAUD_CEREBRO, timeout=0.1)
    time.sleep(2)
    print(f"[OK] Conectado a Arduino Cerebro en {PUERTO_CEREBRO}")
except Exception as e:
    print(f"[AVISO] No se pudo abrir {PUERTO_CEREBRO} ({e}). Triggers a Cerebro omitidos.")


def reproducir_sonido():
    """Genera sonido de alerta cuando el robot frena a 10 cm del objeto."""
    print("\n🔔 [SONIDO] ¡OBJETIVO ALCANZADO A 10 CM! Reproduciendo señal sonora...")
    # Intenta reproducir con aplay/paplay o emite campana de terminal
    try:
        os.system("paplay /usr/share/sounds/freedesktop/stereo/complete.oga 2>/dev/null || aplay /usr/share/sounds/alsa/Front_Center.wav 2>/dev/null || printf '\\a'")
    except Exception:
        print("\a")


def hilo_escucha_cerebro():
    """Monitorea eventos emitidos por el Arduino Cerebro."""
    global objeto_notificado
    while True:
        if arduino_cerebro is not None and arduino_cerebro.is_open:
            try:
                linea = arduino_cerebro.readline().decode('utf-8', errors='ignore').strip()
                if linea:
                    if "EVT:OBJETIVO_10CM" in linea:
                        reproducir_sonido()
                    elif "EVT:EN_PISTA" in linea:
                        print(">> [CEREBRO] Robot de regreso en la pista. Listo para nueva detección.")
                        objeto_notificado = False
            except Exception:
                pass
        time.sleep(0.05)


# Iniciar hilo de escucha en segundo plano
threading.Thread(target=hilo_escucha_cerebro, daemon=True).start()

# ── CAPTURA DE VÍDEO ──
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

print("\nCámara iniciada. Enviando frames al servidor YOLO...")

frame_count = 0
objeto_notificado = False

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error al leer frame de la cámara")
            break

        frame_count += 1
        if frame_count % 5 != 0:  # Enviar cada 5to frame
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

            # 1. Mover motor de pasos para centrar el objeto
            if pan_steps != 0 and arduino_stepper is not None:
                try:
                    arduino_stepper.write(f"T{pan_steps}\n".encode())
                except Exception as e:
                    print(f"Error enviando comando a Stepper: {e}")

            # 2. Si detecta el objeto y no lo ha notificado, avisar a Cerebro
            if detections and not objeto_notificado:
                print(f"\n🎯 [DETECCIÓN] ¡Objeto encontrado!: {detections}")
                
                # Evaluar dirección según el paneo actual
                if pan_steps < -5:
                    cmd_cerebro = 'i' # Girar a la izquierda
                    print(">> Disparando orden a Cerebro: Girar IZQUIERDA ('i') y avanzar.")
                elif pan_steps > 5:
                    cmd_cerebro = 'd' # Girar a la derecha
                    print(">> Disparando orden a Cerebro: Girar DERECHA ('d') y avanzar.")
                else:
                    cmd_cerebro = 'f' # Directo al frente
                    print(">> Disparando orden a Cerebro: Avanzar al FRENTE ('f').")

                if arduino_cerebro is not None:
                    try:
                        arduino_cerebro.write(cmd_cerebro.encode())
                        objeto_notificado = True
                    except Exception as e:
                        print(f"Error notificando a Cerebro: {e}")
                else:
                    print("[SIMULACIÓN] Comando que se enviaría a Cerebro:", cmd_cerebro)
                    objeto_notificado = True

        except Exception as e:
            print(f"Error procesando frame con servidor: {e}")

        time.sleep(0.05)

finally:
    cap.release()
    if arduino_stepper is not None: arduino_stepper.close()
    if arduino_cerebro is not None: arduino_cerebro.close()
