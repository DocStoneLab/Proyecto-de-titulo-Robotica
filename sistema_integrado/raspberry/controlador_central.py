"""
controlador_central.py - Cerebro Maestro en Raspberry Pi

Este script coordina todo el sistema según los requerimientos:
1. Escucha por micrófono el comando de voz "¿Dónde está la mochila?" para iniciar la búsqueda.
2. Sigue el circuito de cinta leyendo el Arduino de Sensores (Línea + Ultrasonido).
3. Envía frames de la cámara al servidor remoto Flask (remote_yolo_script.py / yolo8n_mochilas.pt).
4. Cuando YOLO detecta una 'mochila':
   - Centra la cámara con el motor de pasos (T<steps>).
   - Gira el chasis ('a' o 'd') para alinearse de frente a la mochila.
   - Avanza ('w') hacia la mochila.
5. Monitorea el sensor ultrasónico desde el Arduino de Sensores:
   - Al confirmar distancia <= 10 cm:
     - Frena los motores (' ').
     - Emite el sonido de alerta por el altavoz conectado a la Raspberry Pi.
6. Espera la confirmación por voz ("listo" o "para"):
   - Retrocede ('s') hasta que los sensores de línea detecten la cinta predefinida.
   - Realiza contragiro para recuperar la orientación del circuito y continúa.
"""

import cv2
import requests
import serial
import time
import threading
import sys
import speech_recognition as sr
from alert_sound import sonar_alerta

# ==========================================
# CONFIGURACIÓN GENERAL
# ==========================================
SERVER_URL = 'http://100.64.158.87:5000/detect'  # Servidor Flask con yolo8n_mochilas.pt

# Puertos Seriales USB de la Raspberry Pi hacia los 2 Arduinos
PUERTO_SENSORES = '/dev/ttyACM0'  # Arduino Sensores (Línea + Ultrasonido)
BAUD_SENSORES   = 115200

PUERTO_MOTORES  = '/dev/ttyUSB0'  # Arduino Motores + Stepper Cámara
BAUD_MOTORES    = 9600

# Parámetros de detección y alineación
CLASE_OBJETIVO        = 'mochila' # o 'backpack'
ANCHO_IMAGEN          = 640
CENTRO_X_OBJETIVO     = 320
MARGEN_CENTRO_PX      = 45        # Tolerancia en píxeles para considerar centrado
DISTANCIA_OBJETIVO_CM = 10        # Distancia de frenado ultrasónico

# Frases de activación y detención
TRIGGER_VOZ_BUSCAR = [
    "donde esta la mochila",
    "dónde está la mochila",
    "busca la mochila",
    "buscar mochila",
    "donde esta mi mochila",
    "dónde está mi mochila",
    "encuentra la mochila",
]

TRIGGER_VOZ_RETORNO = [
    "listo",
    "para",
    "detente",
    "volver",
    "regresa",
    "detener",
]

# ==========================================
# VARIABLES GLOBALES DE ESTADO
# ==========================================
class EstadoSistema:
    REPOSO               = "REPOSO"
    SEGUIR_PISTA         = "SEGUIR_PISTA"
    ALINEANDO_MOCHILA    = "ALINEANDO_MOCHILA"
    AVANZANDO_A_MOCHILA  = "AVANZANDO_A_MOCHILA"
    EN_OBJETIVO_SONIDO   = "EN_OBJETIVO_SONIDO"
    RETORNO_A_PISTA      = "RETORNO_A_PISTA"

estado_actual = EstadoSistema.REPOSO

# Telemetría de sensores (Arduino Sensores)
distancia_frente = 999
linea_izq        = 0
linea_cen        = 0
linea_der        = 0

# Memoria de maniobra para retorno
direccion_giro_inicial = ' '
tiempo_giro_ms         = 450
tiempo_avance_inicio   = 0
tiempo_avance_total    = 0

# Conexiones seriales
ser_sensores = None
ser_motores  = None
running = True

# ==========================================
# INICIALIZACIÓN DE CONEXIONES SERIALES
# ==========================================
def conectar_arduinos():
    global ser_sensores, ser_motores
    try:
        ser_sensores = serial.Serial(PUERTO_SENSORES, BAUD_SENSORES, timeout=0.1)
        print(f"[OK] Conectado a Arduino Sensores en {PUERTO_SENSORES}")
    except Exception as e:
        print(f"[AVISO] No se pudo conectar a Arduino Sensores ({e}).")

    try:
        ser_motores = serial.Serial(PUERTO_MOTORES, BAUD_MOTORES, timeout=0.1)
        print(f"[OK] Conectado a Arduino Motores en {PUERTO_MOTORES}")
    except Exception as e:
        print(f"[AVISO] No se pudo conectar a Arduino Motores ({e}).")

def enviar_motor(cmd):
    """Envía un comando de movimiento ('w','s','a','d',' ') al Arduino de motores."""
    if ser_motores and ser_motores.is_open:
        try:
            ser_motores.write(cmd.encode())
        except Exception as e:
            print(f"Error enviando comando '{cmd}' a motores: {e}")

def mover_stepper(steps):
    """Envía un comando de pasos T<steps> al motor de paneo de la cámara."""
    if ser_motores and ser_motores.is_open and steps != 0:
        try:
            ser_motores.write(f"T{steps}\n".encode())
        except Exception as e:
            print(f"Error enviando T{steps} a stepper: {e}")

# ==========================================
# HILO 1: LECTURA DE ARDUINO SENSORES
# ==========================================
def hilo_lectura_sensores():
    global distancia_frente, linea_izq, linea_cen, linea_der, running
    while running:
        if ser_sensores and ser_sensores.is_open:
            try:
                linea = ser_sensores.readline().decode('utf-8', errors='ignore').strip()
                if linea.startswith("TLM:"):
                    # Formato: TLM:<dist>,<I>,<C>,<D>
                    partes = linea[4:].split(',')
                    if len(partes) == 4:
                        distancia_frente = int(partes[0])
                        linea_izq        = int(partes[1])
                        linea_cen        = int(partes[2])
                        linea_der        = int(partes[3])
                elif "EVT:OBJETIVO_10CM" in linea and estado_actual != EstadoSistema.EN_OBJETIVO_SONIDO:
                    notificar_llegada_mochila()
            except Exception:
                pass
        time.sleep(0.02)

# ==========================================
# HILO 2: RECONOCIMIENTO DE VOZ
# ==========================================
def hilo_reconocimiento_voz():
    global estado_actual, running
    recognizer = sr.Recognizer()
    try:
        mic = sr.Microphone()
    except Exception as e:
        print(f"[AVISO] Micrófono no disponible ({e}). Usar comandos de teclado.")
        return

    print(">> [VOZ] Micrófono listo. Di '¿Dónde está la mochila?' para iniciar.")

    while running:
        if estado_actual in [EstadoSistema.REPOSO, EstadoSistema.EN_OBJETIVO_SONIDO]:
            try:
                with mic as source:
                    recognizer.adjust_for_ambient_noise(source, duration=0.3)
                    audio = recognizer.listen(source, phrase_time_limit=4)
                texto = recognizer.recognize_google(audio, language="es-CL").lower()
                print(f">> [VOZ ESCUCHADA]: \"{texto}\"")

                if estado_actual == EstadoSistema.REPOSO:
                    if any(frase in texto for frase in TRIGGER_VOZ_BUSCAR):
                        print("\n🚀 [VOZ] Comando recibido: Iniciando búsqueda de la mochila...")
                        estado_actual = EstadoSistema.SEGUIR_PISTA

                elif estado_actual == EstadoSistema.EN_OBJETIVO_SONIDO:
                    if any(frase in texto for frase in TRIGGER_VOZ_RETORNO):
                        print("\n🔄 [VOZ] Comando 'Listo/Para' recibido. Iniciando retorno a la pista...")
                        iniciar_retorno_a_pista()

            except sr.UnknownValueError:
                pass
            except Exception:
                pass
        else:
            time.sleep(0.5)

# ==========================================
# LÓGICA DE NAVEGACIÓN Y ACCIÓN
# ==========================================
def notificar_llegada_mochila():
    global estado_actual, tiempo_avance_total
    enviar_motor(' ')
    estado_actual = EstadoSistema.EN_OBJETIVO_SONIDO
    tiempo_avance_total = time.time() - tiempo_avance_inicio
    print(f"\n==========================================")
    print(f"🎯 ¡MOCHILA ALCANZADA! Distancia: {distancia_frente} cm")
    print(f"==========================================")
    sonar_alerta()
    print(">> Esperando comando de voz: 'listo' o 'para' para volver al circuito...")

def iniciar_retorno_a_pista():
    global estado_actual
    estado_actual = EstadoSistema.RETORNO_A_PISTA
    threading.Thread(target=ejecutar_maniobra_retorno, daemon=True).start()

def ejecutar_maniobra_retorno():
    global estado_actual
    print(">> [RETORNO] Retrocediendo hacia la cinta...")
    enviar_motor('s')  # Reversa recta

    t_inicio_rev = time.time()
    tiempo_max_rev = (tiempo_avance_total if tiempo_avance_total > 0 else 3.0) + 2.0

    # Esperar hasta que los sensores de línea toquen la cinta
    while time.time() - t_inicio_rev < tiempo_max_rev:
        if linea_izq or linea_cen or linea_der:
            print(">> [RETORNO] ¡Cinta detectada! Frenando reversa.")
            enviar_motor(' ')
            break
        time.sleep(0.02)

    enviar_motor(' ')
    time.sleep(0.2)

    # Contragiro opuesto para alinearse en el sentido de la pista
    if direccion_giro_inicial == 'a':
        print(">> [RETORNO] Contragiro a la DERECHA para alinearse con el circuito...")
        enviar_motor('d')
        time.sleep(tiempo_giro_ms / 1000.0)
    elif direccion_giro_inicial == 'd':
        print(">> [RETORNO] Contragiro a la IZQUIERDA para alinearse con el circuito...")
        enviar_motor('a')
        time.sleep(tiempo_giro_ms / 1000.0)

    enviar_motor(' ')
    print(">> [RETORNO] Reenganche completado. Reanudando circuito normal.")
    estado_actual = EstadoSistema.SEGUIR_PISTA

def ejecutar_seguimiento_linea():
    """Lógica estándar de seguimiento con 3 sensores TCRT5000."""
    if linea_cen and not linea_izq and not linea_der:
        enviar_motor('w')
    elif linea_izq and not linea_der:
        enviar_motor('a')
    elif linea_der and not linea_izq:
        enviar_motor('d')
    elif linea_izq and linea_cen and linea_der:
        enviar_motor('w')
    else:
        enviar_motor('w')

# ==========================================
# BUCLE PRINCIPAL (CÁMARA + YOLO + CONTROL)
# ==========================================
def main():
    global estado_actual, running, direccion_giro_inicial, tiempo_avance_inicio

    conectar_arduinos()

    # Iniciar hilos auxiliares
    threading.Thread(target=hilo_lectura_sensores, daemon=True).start()
    threading.Thread(target=hilo_reconocimiento_voz, daemon=True).start()

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, ANCHO_IMAGEN)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    print("\n==============================================")
    print("   CONTROLADOR CENTRAL NAVBOT (RASPBERRY PI)  ")
    print("==============================================")
    print("Estado inicial: REPOSO.")
    print("Para iniciar, di '¿Dónde está la mochila?' o presiona 'b' en consola.\n")

    frame_counter = 0

    try:
        while running:
            # 1. Modo Reposo: espera activación
            if estado_actual == EstadoSistema.REPOSO:
                enviar_motor(' ')
                time.sleep(0.1)
                continue

            # 2. Captura de frame de la webcam
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            frame_counter += 1

            # 3. Modo Seguimiento normal de pista (busca mientras avanza por cinta)
            if estado_actual == EstadoSistema.SEGUIR_PISTA:
                ejecutar_seguimiento_linea()

            # Enviar 1 de cada 4 frames al servidor YOLO para no saturar la red
            if frame_counter % 4 == 0 and estado_actual in [EstadoSistema.SEGUIR_PISTA, EstadoSistema.ALINEANDO_MOCHILA, EstadoSistema.AVANZANDO_A_MOCHILA]:
                _, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])

                try:
                    res = requests.post(
                        SERVER_URL,
                        files={'image': ('frame.jpg', encoded.tobytes(), 'image/jpeg')},
                        timeout=3
                    )
                    data = res.json()

                    # Compatibilidad con lista directa [{'label':..., 'center_x':...}] o dict
                    detecciones = data if isinstance(data, list) else data.get('detections', [])

                    # Buscar mochila en las detecciones
                    mochila = None
                    for d in detecciones:
                        label = d.get('label', '').lower()
                        if 'mochila' in label or 'backpack' in label:
                            mochila = d
                            break

                    if mochila is not None:
                        center_x = mochila.get('center_x', CENTRO_X_OBJETIVO)
                        error_x  = center_x - CENTRO_X_OBJETIVO

                        print(f"🎯 Mochila detectada en x={center_x} (Error={error_x}px)")

                        # Mover stepper de cámara para mantenerla centrada
                        steps_stepper = int(error_x * 0.12)
                        mover_stepper(steps_stepper)

                        # ALINEACIÓN Y APROXIMACIÓN DEL ROBOT
                        if abs(error_x) > MARGEN_CENTRO_PX:
                            estado_actual = EstadoSistema.ALINEANDO_MOCHILA
                            if error_x < 0:
                                print(">> Girando chasis a la IZQUIERDA ('a')...")
                                enviar_motor('a')
                                direccion_giro_inicial = 'a'
                            else:
                                print(">> Girando chasis a la DERECHA ('d')...")
                                enviar_motor('d')
                                direccion_giro_inicial = 'd'
                        else:
                            # Mochila centrada: avanzar directamente hacia ella
                            if estado_actual != EstadoSistema.AVANZANDO_A_MOCHILA:
                                estado_actual = EstadoSistema.AVANZANDO_A_MOCHILA
                                tiempo_avance_inicio = time.time()
                                print(">> Mochila centrada. Avanzando de frente ('w')...")
                            
                            enviar_motor('w')

                except Exception as e:
                    # En caso de caída de conexión con el servidor YOLO, mantener seguimiento
                    pass

            # 4. Verificación de proximidad ultrasónica cuando va hacia la mochila
            if estado_actual == EstadoSistema.AVANZANDO_A_MOCHILA:
                if 0 < distancia_frente <= DISTANCIA_OBJETIVO_CM:
                    notificar_llegada_mochila()

            time.sleep(0.03)

    except KeyboardInterrupt:
        print("\nCerrando sistema...")
    finally:
        running = False
        enviar_motor(' ')
        cap.release()
        if ser_sensores: ser_sensores.close()
        if ser_motores: ser_motores.close()

if __name__ == '__main__':
    main()
