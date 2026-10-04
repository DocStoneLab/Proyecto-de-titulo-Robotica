"""
controlador_central.py - Cerebro Maestro en Raspberry Pi (Con Autodiagnóstico Modular)

Funcionalidad:
1. Autodiagnóstico modular de inicio: prueba individualmente micrófono, parlante, cámara,
   Arduinos y servidor YOLO. Muestra un dashboard claro en la terminal SSH.
2. Silencia 100% las advertencias internas de ALSA y JACK a nivel de C.
3. Alerta 1 sola vez si un componente no es detectado o se desconecta en caliente.
4. Modo tolerante a fallos: permite probar el sistema aunque no todos los periféricos estén conectados.
5. Coordina:
   - Búsqueda por voz ("¿Dónde está la mochila?") o teclado ('b').
   - Seguimiento de línea por cinta con Arduino Sensores.
   - Detección de 'mochila' vía servidor Flask remoto (192.168.100.89:5000).
   - Centrado con motor de pasos (T<steps>) y alineación de chasis ('a'/'d').
   - Aproximación hasta 10 cm con ultrasonido y frenado en seco (' ').
   - Alerta sonora por parlante Bluetooth (meme del pájaro gritando).
   - Retorno por voz ("listo"/"para") en reversa recta ('s') y realineación.
"""

import cv2
import requests
import serial
import time
import threading
import subprocess
import os
import sys
import ctypes
import contextlib
import glob
import speech_recognition as sr
from alert_sound import sonar_alerta, sonar_conexion, MAC_PARLANTE

# ==========================================
# SUPRESOR DE MENSAJES C (ALSA / JACK / PyAudio)
# ==========================================
@contextlib.contextmanager
def suprimir_salida_c():
    """Redirige temporalmente stderr (descriptor 2) a /dev/null para silenciar JACK y ALSA."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        old_stderr = os.dup(2)
        sys.stderr.flush()
        os.dup2(devnull, 2)
        os.close(devnull)
        yield
    except Exception:
        yield
    finally:
        try:
            sys.stderr.flush()
            os.dup2(old_stderr, 2)
            os.close(old_stderr)
        except Exception:
            pass

# Silenciador auxiliar de ALSA
try:
    ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p)
    def py_error_handler(filename, line, function, err, fmt): pass
    c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)
    asound = ctypes.cdll.LoadLibrary('libasound.so.2')
    asound.snd_lib_error_set_handler(c_error_handler)
except Exception:
    pass

# ==========================================
# CONFIGURACIÓN GENERAL
# ==========================================
# IP de tu PC donde corre remote_yolo_script.py
SERVER_URL = 'http://192.168.100.89:5000/detect'

PUERTO_SENSORES = '/dev/ttyACM0'  # Arduino Sensores (Línea + Ultrasonido)
BAUD_SENSORES   = 115200

PUERTO_MOTORES  = '/dev/ttyUSB0'  # Arduino Motores + Stepper Cámara
BAUD_MOTORES    = 9600

CLASE_OBJETIVO        = 'mochila'
ANCHO_IMAGEN          = 640
CENTRO_X_OBJETIVO     = 320
MARGEN_CENTRO_PX      = 45
DISTANCIA_OBJETIVO_CM = 10

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

TRIGGER_VOZ_PARAR = [
    "stop",
    "alto",
    "frena",
    "cancela",
    "cancelar",
]

# ==========================================
# ESTADOS DEL SISTEMA
# ==========================================
class EstadoSistema:
    REPOSO               = "REPOSO"
    SEGUIR_PISTA         = "SEGUIR_PISTA"
    ALINEANDO_MOCHILA    = "ALINEANDO_MOCHILA"
    AVANZANDO_A_MOCHILA  = "AVANZANDO_A_MOCHILA"
    EN_OBJETIVO_SONIDO   = "EN_OBJETIVO_SONIDO"
    RETORNO_A_PISTA      = "RETORNO_A_PISTA"

estado_actual = EstadoSistema.REPOSO

# Telemetría de sensores
distancia_frente = 999
linea_izq        = 0
linea_cen        = 0
linea_der        = 0

# Variables para interfaz en vivo (Dashboard)
ultima_voz_escuchada    = "(esperando comando...)"
ultimo_comando_chasis   = ' '
ultimo_comando_stepper  = "Centrado (0)"
pos_stepper_actual      = 0
dir_stepper_barrido     = 1
t_ultimo_barrido        = 0
PASO_BARRIDO            = 20
LIMITE_BARRIDO_PASOS    = 240
info_mochila            = {'detectada': False, 'center_x': 0, 'error_x': 0, 'conf': 0.0}

# Variables de maniobra
direccion_giro_inicial = ' '
tiempo_giro_ms         = 450
tiempo_avance_inicio   = 0
tiempo_avance_total    = 0

# Puertos seriales y control
ser_sensores = None
ser_motores  = None
running = True

# Banderas de estado de hardware
hw_mic_ok       = False
hw_parlante_ok  = False
hw_camara_ok    = False
hw_sensores_ok  = False
hw_motores_ok   = False
hw_servidor_ok  = False

# Banderas para avisar 1 sola vez en desconexión
alerta_camara_mostrada   = False
alerta_servidor_mostrada = False
alerta_motores_mostrada  = False
alerta_sensores_mostrada = False

# ==========================================
# DIAGNÓSTICO MODULAR DE HARDWARE
# ==========================================
def test_microfono():
    with suprimir_salida_c():
        try:
            mics = sr.Microphone.list_microphone_names()
            if mics:
                return True, f"Conectado ({len(mics)} disp.)"
            return False, "No detectado"
        except Exception as e:
            return False, f"Error: {e}"

def test_parlante():
    try:
        res = subprocess.run(["bluetoothctl", "info", MAC_PARLANTE], capture_output=True, text=True, timeout=2)
        if "Connected: yes" in res.stdout:
            return True, f"Conectado ({MAC_PARLANTE})"
        subprocess.run(["bluetoothctl", "connect", MAC_PARLANTE], capture_output=True, timeout=3)
        res2 = subprocess.run(["bluetoothctl", "info", MAC_PARLANTE], capture_output=True, text=True, timeout=2)
        if "Connected: yes" in res2.stdout:
            return True, f"Reconectado ({MAC_PARLANTE})"
        return False, f"Desconectado ({MAC_PARLANTE})"
    except Exception as e:
        return False, f"Error: {e}"

def test_camara():
    try:
        cap_test = cv2.VideoCapture(0)
        if cap_test.isOpened():
            ret, _ = cap_test.read()
            cap_test.release()
            if ret:
                return True, "Conectada (/dev/video0)"
            return False, "Detectada pero sin señal de video"
        return False, "No detectada (/dev/video0)"
    except Exception as e:
        return False, f"Error: {e}"

def detectar_arduinos():
    global ser_sensores, ser_motores
    # Buscar en todos los puertos seriales USB posibles
    puertos = sorted(list(set(glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyUSB*'))))
    if not puertos:
        return (False, "No hay puertos /dev/ttyACM* ni /dev/ttyUSB*"), \
               (False, "No hay puertos /dev/ttyACM* ni /dev/ttyUSB*")

    msg_sensores = "No detectado"
    msg_motores  = "No detectado"
    ok_sensores  = False
    ok_motores   = False
    puerto_sensores = None

    # 1. Identificar Arduino Sensores (transmite "TLM:" a 115200 baudios)
    for p in puertos:
        try:
            s = serial.Serial(p, BAUD_SENSORES, timeout=0.25)
            time.sleep(0.1)
            lineas = [s.readline().decode('utf-8', errors='ignore') for _ in range(4)]
            if any("TLM:" in l for l in lineas):
                ser_sensores = s
                puerto_sensores = p
                ok_sensores = True
                msg_sensores = f"Conectado en {p} (telemetría TLM activa)"
                break
            else:
                s.close()
        except Exception:
            pass

    # Puertos disponibles para el Arduino de Motores
    puertos_restantes = [p for p in puertos if p != puerto_sensores]

    # Si no detectó TLM pero hay puertos, intentar conectar el puerto preferido
    if not ok_sensores and puertos_restantes:
        p = PUERTO_SENSORES if PUERTO_SENSORES in puertos_restantes else puertos_restantes[0]
        try:
            ser_sensores = serial.Serial(p, BAUD_SENSORES, timeout=0.1)
            ok_sensores = True
            puerto_sensores = p
            msg_sensores = f"Conectado en {p}"
            puertos_restantes.remove(p)
        except Exception as e:
            msg_sensores = f"Error al abrir {p}: {e}"

    # 2. Conectar Arduino Motores en el puerto restante a 9600 baudios
    for p in puertos_restantes:
        try:
            ser_motores = serial.Serial(p, BAUD_MOTORES, timeout=0.1)
            ok_motores = True
            msg_motores = f"Conectado en {p}"
            break
        except Exception as e:
            msg_motores = f"Error al abrir {p}: {e}"

    if not ok_motores and not ser_motores:
        msg_motores = f"No detectado (puertos libres: {puertos_restantes})"

    return (ok_sensores, msg_sensores), (ok_motores, msg_motores)

def test_servidor_yolo():
    try:
        # Intentar conectar con la ruta raíz o /detect con timeout corto
        res = requests.get('http://192.168.100.89:5000/', timeout=1.5)
        if res.status_code in [200, 404]:
            return True, f"En línea (http://192.168.100.89:5000)"
    except Exception:
        pass
    try:
        res = requests.post(SERVER_URL, timeout=1.5)
        return True, f"En línea ({SERVER_URL})"
    except Exception:
        return False, f"Sin respuesta ({SERVER_URL})"

def autodiagnostico_hardware():
    global hw_mic_ok, hw_parlante_ok, hw_camara_ok, hw_sensores_ok, hw_motores_ok, hw_servidor_ok

    print("\n" + "="*62)
    print("         AUTODIAGNÓSTICO MODULAR DEL SISTEMA (NAVBOT)         ")
    print("="*62)

    hw_mic_ok, msg_mic           = test_microfono()
    hw_parlante_ok, msg_parlante = test_parlante()
    hw_camara_ok, msg_camara     = test_camara()
    (hw_sensores_ok, msg_sensores), (hw_motores_ok, msg_motores) = detectar_arduinos()
    hw_servidor_ok, msg_servidor = test_servidor_yolo()

    print(f" [{'✅' if hw_mic_ok else '❌'}] MICRÓFONO USB       : {msg_mic}")
    print(f" [{'✅' if hw_parlante_ok else '❌'}] PARLANTE BLUETOOTH  : {msg_parlante}")
    print(f" [{'✅' if hw_camara_ok else '❌'}] CÁMARA USB          : {msg_camara}")
    print(f" [{'✅' if hw_sensores_ok else '❌'}] ARDUINO SENSORES    : {msg_sensores}")
    print(f" [{'✅' if hw_motores_ok else '❌'}] ARDUINO MOTORES     : {msg_motores}")
    print(f" [{'✅' if hw_servidor_ok else '⚠️'}] SERVIDOR YOLO       : {msg_servidor}")
    print("="*62)

    if not hw_mic_ok:
        print(">> [AVISO] Micrófono no disponible. Usa comandos por teclado.")
    if not hw_camara_ok:
        print(">> [AVISO] Cámara no detectada. La detección visual esperará conexión.")
    if not hw_sensores_ok or not hw_motores_ok:
        print(">> [AVISO] Arduinos no conectados. Órdenes se ejecutarán en modo simulación.")
    print(">> Sistema listo. Presiona 'b' para buscar, 'r' para retornar, 'q' para salir.\n")

# ==========================================
# ENVÍO SEGURO DE COMANDOS A MOTORES
# ==========================================
def enviar_motor(cmd):
    global ultimo_comando_chasis, alerta_motores_mostrada
    ultimo_comando_chasis = cmd
    if ser_motores and ser_motores.is_open:
        try:
            ser_motores.write(cmd.encode())
            alerta_motores_mostrada = False
        except Exception:
            if not alerta_motores_mostrada:
                alerta_motores_mostrada = True

def mover_stepper(steps):
    global ultimo_comando_stepper
    if ser_motores and ser_motores.is_open and steps != 0:
        try:
            ser_motores.write(f"T{steps}\n".encode())
            ultimo_comando_stepper = f"T{steps:+d} pasos"
        except Exception:
            pass

def centrar_camara():
    global pos_stepper_actual, ultimo_comando_stepper
    if pos_stepper_actual != 0:
        mover_stepper(-pos_stepper_actual)
        pos_stepper_actual = 0
        ultimo_comando_stepper = "Centrado (0)"

# ==========================================
# HILO 1: LECTURA DE ARDUINO SENSORES
# ==========================================
def hilo_lectura_sensores():
    global distancia_frente, linea_izq, linea_cen, linea_der, running, alerta_sensores_mostrada
    while running:
        if ser_sensores and ser_sensores.is_open:
            try:
                linea = ser_sensores.readline().decode('utf-8', errors='ignore').strip()
                if linea.startswith("TLM:"):
                    partes = linea[4:].split(',')
                    if len(partes) == 4:
                        distancia_frente = int(partes[0])
                        linea_izq        = int(partes[1])
                        linea_cen        = int(partes[2])
                        linea_der        = int(partes[3])
                elif "EVT:OBJETIVO_10CM" in linea and estado_actual != EstadoSistema.EN_OBJETIVO_SONIDO:
                    notificar_llegada_mochila()
                alerta_sensores_mostrada = False
            except Exception:
                if not alerta_sensores_mostrada:
                    print("⚠️ [ALERTA] Se interrumpió la lectura de Arduino Sensores.")
                    alerta_sensores_mostrada = True
        time.sleep(0.02)

# ==========================================
# HILO 2: RECONOCIMIENTO DE VOZ
def iniciar_busqueda():
    global estado_actual
    print("\n🚀 [INICIO] Iniciando búsqueda de la mochila y reproduciendo sonido de conexión...")
    threading.Thread(target=sonar_conexion, daemon=True).start()
    estado_actual = EstadoSistema.SEGUIR_PISTA

# ==========================================
# HILO 2: RECONOCIMIENTO DE VOZ CONTINUO
# ==========================================
def hilo_reconocimiento_voz():
    global estado_actual, running
    if not hw_mic_ok:
        return

    with suprimir_salida_c():
        recognizer = sr.Recognizer()
        recognizer.dynamic_energy_threshold = True
        try:
            mic = sr.Microphone()
            with mic as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.8)
        except Exception:
            return

    print(">> [VOZ] Escuchando continuamente por el micrófono...")

    while running:
        # Durante la maniobra de retorno a la cinta se pausa brevemente la escucha
        if estado_actual == EstadoSistema.RETORNO_A_PISTA:
            time.sleep(0.3)
            continue

        try:
            with suprimir_salida_c():
                with mic as source:
                    audio = recognizer.listen(source, timeout=2.5, phrase_time_limit=3.5)
                texto = recognizer.recognize_google(audio, language="es-CL").lower()
            
            ultima_voz_escuchada = f"\"{texto}\""

            # 1. En reposo: escuchar orden para iniciar la búsqueda
            if estado_actual == EstadoSistema.REPOSO:
                if any(frase in texto for frase in TRIGGER_VOZ_BUSCAR):
                    print("\n🚀 [VOZ] Comando de búsqueda recibido.")
                    iniciar_busqueda()

            # 2. En cualquier momento de la búsqueda o en el objetivo: escuchar 'listo', 'para', 'stop'
            elif estado_actual in [
                EstadoSistema.SEGUIR_PISTA,
                EstadoSistema.ALINEANDO_MOCHILA,
                EstadoSistema.AVANZANDO_A_MOCHILA,
                EstadoSistema.EN_OBJETIVO_SONIDO
            ]:
                if any(frase in texto for frase in TRIGGER_VOZ_PARAR):
                    print("\n🛑 [VOZ] Comando de parada ('stop/alto') recibido. Frenando robot...")
                    enviar_motor(' ')
                    estado_actual = EstadoSistema.REPOSO
                elif any(frase in texto for frase in TRIGGER_VOZ_RETORNO):
                    print("\n🔄 [VOZ] Comando 'Listo/Retorno' recibido. Iniciando retorno a la pista...")
                    iniciar_retorno_a_pista()

        except sr.WaitTimeoutError:
            pass
        except sr.UnknownValueError:
            pass
        except Exception:
            pass

# ==========================================
# HILO 3: ENTRADA POR TECLADO (FALLBACK SSH)
# ==========================================
def hilo_teclado():
    global estado_actual, running
    while running:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            cmd = line.strip().lower()
            if cmd == 'b':
                print("\n⌨️ [TECLADO] Comando 'b' recibido.")
                iniciar_busqueda()
            elif cmd == 'r':
                print("\n⌨️ [TECLADO] Comando 'r': Iniciando retorno a la pista...")
                iniciar_retorno_a_pista()
            elif cmd == 'h':
                print("\n⌨️ [TECLADO] Comando 'h': Calibrando/Centrando cámara...")
                enviar_motor('H')
            elif cmd == 'k':
                print("\n⌨️ [TECLADO] Comando 'k': Consultando estado del switch A5...")
                enviar_motor('K')
            elif cmd == ' ':
                print("\n⌨️ [TECLADO] Freno manual activado.")
                enviar_motor(' ')
                estado_actual = EstadoSistema.REPOSO
            elif cmd == 'q':
                print("\n⌨️ [TECLADO] Cerrando sistema...")
                running = False
                break
        except Exception:
            break

# ==========================================
# LÓGICA DE NAVEGACIÓN Y SONIDO
# ==========================================
def notificar_llegada_mochila():
    global estado_actual, tiempo_avance_total
    enviar_motor(' ')
    centrar_camara()
    estado_actual = EstadoSistema.EN_OBJETIVO_SONIDO
    tiempo_avance_total = time.time() - tiempo_avance_inicio
    sonar_alerta()

def iniciar_retorno_a_pista():
    global estado_actual
    centrar_camara()
    estado_actual = EstadoSistema.RETORNO_A_PISTA
    threading.Thread(target=ejecutar_maniobra_retorno, daemon=True).start()

def ejecutar_maniobra_retorno():
    global estado_actual
    print(">> [RETORNO] Retrocediendo hacia la cinta predefinida...")
    enviar_motor('s')

    t_inicio_rev = time.time()
    tiempo_max_rev = (tiempo_avance_total if tiempo_avance_total > 0 else 3.0) + 2.0

    while time.time() - t_inicio_rev < tiempo_max_rev:
        if linea_izq or linea_cen or linea_der:
            print(">> [RETORNO] ¡Cinta detectada! Frenando reversa.")
            enviar_motor(' ')
            break
        time.sleep(0.02)

    enviar_motor(' ')
    time.sleep(0.2)

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
# INTERFAZ EN VIVO: DASHBOARD EN TERMINAL
# ==========================================
def hilo_dashboard_terminal():
    global running
    # Dejar pasar el autodiagnóstico inicial
    time.sleep(2.0)
    while running:
        try:
            renderizar_dashboard()
            time.sleep(0.25)
        except Exception:
            pass

def renderizar_dashboard():
    # 1. Sensores de línea (TCRT5000)
    izq_sym = "⬛" if linea_izq else "⬜"
    cen_sym = "⬛" if linea_cen else "⬜"
    der_sym = "⬛" if linea_der else "⬜"
    linea_str = f"[{izq_sym} IZQ] [{cen_sym} CEN] [{der_sym} DER]  ({linea_izq},{linea_cen},{linea_der})"

    # 2. Sensor Ultrasonido
    if distancia_frente < 400:
        dist_str = f"{distancia_frente} cm"
    else:
        dist_str = "> 100 cm (Libre)"

    # 3. Motores Chasis
    motor_desc = {
        'w': "AVANZAR (Adelante)",
        's': "RETROCEDER (Reversa)",
        'a': "GIRAR A LA IZQUIERDA",
        'd': "GIRAR A LA DERECHA",
        ' ': "DETENIDO / FRENO"
    }.get(ultimo_comando_chasis, f"Comando '{ultimo_comando_chasis}'")

    # 4. Stepper Cámara
    grados_aprox = int(pos_stepper_actual * 360 / 2048)
    stepper_str = f"{pos_stepper_actual:+d} pasos ({grados_aprox:+d}°) | {ultimo_comando_stepper}"

    # 5. Visión YOLO
    if info_mochila['detectada']:
        dir_err = "IZQUIERDA" if info_mochila['error_x'] < 0 else "DERECHA" if info_mochila['error_x'] > 0 else "CENTRADA"
        vision_str = f"🎯 ENCONTRADA | X={info_mochila['center_x']}px | Error={info_mochila['error_x']:+d}px ({dir_err}) | Conf={info_mochila['conf']*100:.0f}%"
    else:
        if estado_actual == EstadoSistema.SEGUIR_PISTA:
            vision_str = "🔍 Buscando... (Barrido de cámara activo)"
        elif estado_actual == EstadoSistema.REPOSO:
            vision_str = "⏸️ Sistema en reposo (esperando orden)"
        else:
            vision_str = "❌ No visible en este fotograma"

    panel = (
        "\033[H\033[2J"
        "╔══════════════════════════════════════════════════════════════════════════════╗\n"
        "║                🤖 NAVBOT - PANEL DE MONITOREO EN TIEMPO REAL                 ║\n"
        f"║  ESTADO DEL ROBOT : [ {estado_actual.center(22)} ]                             ║\n"
        "╠══════════════════════════════════════════════════════════════════════════════╣\n"
        f"║ 🎤 VOZ ESCUCHADA  : {ultima_voz_escuchada[:53].ljust(55)}║\n"
        f"║ 📡 LÍNEA (TCRT)   : {linea_str[:53].ljust(55)}║\n"
        f"║ 📏 ULTRASONIDO    : {dist_str[:53].ljust(55)}║\n"
        f"║ ⚙️ MOTORES CHASIS : {motor_desc[:53].ljust(55)}║\n"
        f"║ 🎥 CÁMARA (PAN)   : {stepper_str[:53].ljust(55)}║\n"
        f"║ 🎯 VISIÓN YOLO    : {vision_str[:53].ljust(55)}║\n"
        "╠══════════════════════════════════════════════════════════════════════════════╣\n"
        "║ ⌨️ TECLAS: [b] Buscar | [r] Retorno | [h] Centrar cámara | [ ] Parar | [q] Salir  ║\n"
        "╚══════════════════════════════════════════════════════════════════════════════╝\n"
    )
    sys.stdout.write(panel)
    sys.stdout.flush()

# ==========================================
# BUCLE PRINCIPAL (CÁMARA + YOLO + CONTROL)
# ==========================================
def main():
    global estado_actual, running, direccion_giro_inicial, tiempo_avance_inicio
    global alerta_camara_mostrada, alerta_servidor_mostrada
    global t_ultimo_barrido, dir_stepper_barrido, pos_stepper_actual, info_mochila

    # 1. Autodiagnóstico modular de inicio
    autodiagnostico_hardware()

    # 2. Iniciar hilos auxiliares
    threading.Thread(target=hilo_lectura_sensores, daemon=True).start()
    threading.Thread(target=hilo_reconocimiento_voz, daemon=True).start()
    threading.Thread(target=hilo_teclado, daemon=True).start()
    threading.Thread(target=hilo_dashboard_terminal, daemon=True).start()

    cap = None
    frame_counter = 0

    try:
        while running:
            # En reposo: espera inicio por voz o teclado
            if estado_actual == EstadoSistema.REPOSO:
                enviar_motor(' ')
                time.sleep(0.1)
                continue

            # Gestión de apertura de cámara bajo demanda
            if cap is None or not cap.isOpened():
                cap = cv2.VideoCapture(0)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, ANCHO_IMAGEN)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                if not cap.isOpened():
                    if not alerta_camara_mostrada:
                        print("❌ [ALERTA] No se detecta cámara conectada. Reintentando...")
                        alerta_camara_mostrada = True
                    time.sleep(1.0)
                    continue
                else:
                    if alerta_camara_mostrada:
                        print("✅ [INFO] Cámara USB conectada y activa.")
                        alerta_camara_mostrada = False

            ret, frame = cap.read()
            if not ret:
                if not alerta_camara_mostrada:
                    print("❌ [ALERTA] La cámara no entregó imagen. Reintentando...")
                    alerta_camara_mostrada = True
                time.sleep(0.5)
                continue
            else:
                alerta_camara_mostrada = False

            frame_counter += 1

            if estado_actual == EstadoSistema.SEGUIR_PISTA:
                ejecutar_seguimiento_linea()

            # Procesamiento con servidor YOLO (1 de cada 4 frames)
            if frame_counter % 4 == 0 and estado_actual in [EstadoSistema.SEGUIR_PISTA, EstadoSistema.ALINEANDO_MOCHILA, EstadoSistema.AVANZANDO_A_MOCHILA]:
                _, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])

                try:
                    res = requests.post(
                        SERVER_URL,
                        files={'image': ('frame.jpg', encoded.tobytes(), 'image/jpeg')},
                        timeout=2.5
                    )
                    data = res.json()
                    alerta_servidor_mostrada = False

                    detecciones = data if isinstance(data, list) else data.get('detections', [])

                    mochila = None
                    for d in detecciones:
                        label = d.get('label', '').lower()
                        if 'mochila' in label or 'backpack' in label:
                            mochila = d
                            break

                    if mochila is not None:
                        center_x = mochila.get('center_x', CENTRO_X_OBJETIVO)
                        conf = mochila.get('confidence', 0.0)
                        error_x  = center_x - CENTRO_X_OBJETIVO

                        info_mochila = {
                            'detectada': True,
                            'center_x': center_x,
                            'error_x': error_x,
                            'conf': conf
                        }

                        # Centrar cámara en la mochila detectada
                        steps_stepper = int(error_x * 0.12)
                        if steps_stepper != 0:
                            mover_stepper(steps_stepper)
                            pos_stepper_actual += steps_stepper

                        if abs(error_x) > MARGEN_CENTRO_PX:
                            estado_actual = EstadoSistema.ALINEANDO_MOCHILA
                            if error_x < 0:
                                enviar_motor('a')
                                direccion_giro_inicial = 'a'
                            else:
                                enviar_motor('d')
                                direccion_giro_inicial = 'd'
                        else:
                            if estado_actual != EstadoSistema.AVANZANDO_A_MOCHILA:
                                estado_actual = EstadoSistema.AVANZANDO_A_MOCHILA
                                tiempo_avance_inicio = time.time()
                            enviar_motor('w')
                    else:
                        info_mochila = {'detectada': False, 'center_x': 0, 'error_x': 0, 'conf': 0.0}

                        # Paneo activo de cámara durante la búsqueda en pista
                        if estado_actual == EstadoSistema.SEGUIR_PISTA:
                            if time.time() - t_ultimo_barrido > 0.15:
                                t_ultimo_barrido = time.time()
                                paso = PASO_BARRIDO * dir_stepper_barrido
                                mover_stepper(paso)
                                pos_stepper_actual += paso
                                if pos_stepper_actual >= LIMITE_BARRIDO_PASOS:
                                    dir_stepper_barrido = -1
                                elif pos_stepper_actual <= -LIMITE_BARRIDO_PASOS:
                                    dir_stepper_barrido = 1

                except Exception:
                    if not alerta_servidor_mostrada:
                        alerta_servidor_mostrada = True

            # Detección ultrasónica de proximidad
            if estado_actual == EstadoSistema.AVANZANDO_A_MOCHILA:
                if 0 < distancia_frente <= DISTANCIA_OBJETIVO_CM:
                    notificar_llegada_mochila()

            time.sleep(0.03)

    except KeyboardInterrupt:
        print("\nCerrando sistema...")
    finally:
        running = False
        enviar_motor(' ')
        if cap: cap.release()
        if ser_sensores: ser_sensores.close()
        if ser_motores: ser_motores.close()

if __name__ == '__main__':
    main()
