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
import unicodedata
import select
import termios
import tty
import atexit
import speech_recognition as sr
from alert_sound import sonar_alerta, sonar_conexion, MAC_PARLANTE

# ==========================================
# GESTIÓN Y RESTAURACIÓN DE TERMINAL SSH
# ==========================================
old_term_settings = None
if sys.stdin.isatty():
    try:
        old_term_settings = termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        old_term_settings = None

def restaurar_terminal():
    global old_term_settings
    if old_term_settings is not None:
        try:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_term_settings)
        except Exception:
            pass
        old_term_settings = None
    try:
        sys.stdout.write("\033[?25h\n")
        sys.stdout.flush()
    except Exception:
        pass

atexit.register(restaurar_terminal)

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
LIMITE_PAN_PASOS        = 450
estado_switch_hardware  = "Desconocido"
dir_stepper_barrido     = 1
t_ultimo_barrido        = 0
PASO_BARRIDO            = 20
LIMITE_BARRIDO_PASOS    = 240
info_mochila            = {'detectada': False, 'center_x': 0, 'error_x': 0, 'conf': 0.0}
ultimo_evento_teclado   = "Esperando tecla..."
ultimo_evento_sistema   = "Sistema iniciado en REPOSO"

def log_evento(msg):
    global ultimo_evento_sistema
    ultimo_evento_sistema = msg

# Variables de maniobra
direccion_giro_inicial = ' '
tiempo_giro_ms         = 450
tiempo_avance_inicio   = 0
tiempo_avance_total    = 0

# Puertos seriales y control
ser_sensores = None
ser_motores  = None
puerto_sensores_asignado = "No detectado"
puerto_motores_asignado  = "No detectado"
running = True

# Banderas de estado de hardware
hw_mic_ok       = False
hw_parlante_ok  = False
hw_camara_ok    = False
hw_sensores_ok  = False
hw_motores_ok   = False
hw_servidor_ok  = False

# Mensajes detallados de autodiagnóstico para el panel permanente
msg_mic          = "Comprobando..."
msg_parlante     = "Comprobando..."
msg_camara       = "Comprobando..."
msg_sensores     = "Comprobando..."
msg_motores      = "Comprobando..."
msg_servidor     = "Comprobando..."

# Métricas de flujo de datos de sensores
paquetes_sensores = 0
t_ultimo_tlm      = 0

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
    global ser_sensores, ser_motores, puerto_sensores_asignado, puerto_motores_asignado
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
    puerto_motores  = None

    # 1. Probar puertos a 115200 buscando Arduino Sensores (transmite "TLM:" autónomamente)
    for p in puertos:
        try:
            s = serial.Serial(p, BAUD_SENSORES, timeout=0.3)
            t_inicio = time.time()
            encontrado = False
            # Esperar hasta 2.3s para superar el reseteo del bootloader de Arduino Uno
            while time.time() - t_inicio < 2.3:
                linea = s.readline().decode('utf-8', errors='ignore').strip()
                if "TLM:" in linea or "Arduino Sensores" in linea:
                    encontrado = True
                    break
            if encontrado:
                ser_sensores = s
                puerto_sensores = p
                puerto_sensores_asignado = p
                ok_sensores = True
                msg_sensores = f"Detectado en {p} (115200 baud, TLM activo)"
                break
            else:
                s.close()
        except Exception:
            pass

    # 2. Probar puertos restantes a 9600 buscando Arduino Motores
    puertos_restantes = [p for p in puertos if p != puerto_sensores]
    for p in puertos_restantes:
        try:
            s = serial.Serial(p, BAUD_MOTORES, timeout=0.3)
            time.sleep(0.2)
            s.write(b"\nK\nQ\n")
            s.flush()
            t_inicio = time.time()
            encontrado = False
            while time.time() - t_inicio < 2.3:
                linea = s.readline().decode('utf-8', errors='ignore').strip()
                if any(tag in linea for tag in ["SWITCH:", "POS:", "Motores", "Homing", "Listo", "Switch", "STEP:"]):
                    encontrado = True
                    break
            if encontrado:
                ser_motores = s
                puerto_motores = p
                puerto_motores_asignado = p
                ok_motores = True
                msg_motores = f"Detectado en {p} (9600 baud, control motores activo)"
                break
            else:
                s.close()
        except Exception:
            pass

    # 3. Asignación por descarte si solo uno respondió activamente
    puertos_libres = [p for p in puertos if p != puerto_sensores and p != puerto_motores]

    if ok_sensores and not ok_motores and puertos_libres:
        p_cand = puertos_libres[0]
        try:
            ser_motores = serial.Serial(p_cand, BAUD_MOTORES, timeout=0.1)
            ok_motores = True
            puerto_motores_asignado = p_cand
            msg_motores = f"Asignado en {p_cand} (9600 baud, por descarte)"
        except Exception as e:
            msg_motores = f"Error al abrir {p_cand}: {e}"

    elif ok_motores and not ok_sensores and puertos_libres:
        p_cand = puertos_libres[0]
        try:
            ser_sensores = serial.Serial(p_cand, BAUD_SENSORES, timeout=0.1)
            ok_sensores = True
            puerto_sensores_asignado = p_cand
            msg_sensores = f"Asignado en {p_cand} (115200 baud, por descarte)"
        except Exception as e:
            msg_sensores = f"Error al abrir {p_cand}: {e}"

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
    global msg_mic, msg_parlante, msg_camara, msg_sensores, msg_motores, msg_servidor

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
            ser_motores.flush()
            alerta_motores_mostrada = False
        except Exception:
            if not alerta_motores_mostrada:
                alerta_motores_mostrada = True

def mover_stepper(steps):
    global ultimo_comando_stepper
    if ser_motores and ser_motores.is_open and steps != 0:
        try:
            if steps == -30:
                ser_motores.write(b"<\n")
            elif steps == 30:
                ser_motores.write(b">\n")
            else:
                ser_motores.write(f"T{steps}\n".encode())
            ser_motores.flush()
            ultimo_comando_stepper = f"T{steps:+d} pasos (enviado a {puerto_motores_asignado})"
        except Exception as e:
            ultimo_comando_stepper = f"Error stepper: {e}"
    else:
        if not ser_motores or not ser_motores.is_open:
            ultimo_comando_stepper = "FALLO: Motores NO conectado"

def centrar_camara():
    global pos_stepper_actual, ultimo_comando_stepper
    if ser_motores and ser_motores.is_open:
        try:
            ser_motores.write(b"C\n")
            ser_motores.flush()
        except Exception:
            pass
    pos_stepper_actual = 0
    ultimo_comando_stepper = f"Centrado (0) (enviado a {puerto_motores_asignado})"

# ==========================================
# HILO 1: LECTURA DE ARDUINO SENSORES
# ==========================================
def hilo_lectura_sensores():
    global distancia_frente, linea_izq, linea_cen, linea_der, running, alerta_sensores_mostrada
    global paquetes_sensores, t_ultimo_tlm
    while running:
        if ser_sensores and ser_sensores.is_open:
            try:
                linea = ser_sensores.readline().decode('utf-8', errors='ignore').strip()
                if "TLM:" in linea:
                    idx = linea.find("TLM:")
                    partes = linea[idx+4:].split(',')
                    if len(partes) >= 4:
                        try:
                            distancia_frente = int(partes[0].strip())
                            linea_izq        = int(partes[1].strip())
                            linea_cen        = int(partes[2].strip())
                            linea_der        = int(partes[3].strip())
                            paquetes_sensores += 1
                            t_ultimo_tlm = time.time()
                            alerta_sensores_mostrada = False
                        except ValueError:
                            pass
                elif "EVT:OBJETIVO_10CM" in linea and estado_actual != EstadoSistema.EN_OBJETIVO_SONIDO:
                    notificar_llegada_mochila()

                # Si hay líneas acumuladas en el búfer serial, vaciar para tener telemetría en tiempo real
                if ser_sensores.in_waiting > 120:
                    ser_sensores.reset_input_buffer()
            except Exception:
                if not alerta_sensores_mostrada:
                    alerta_sensores_mostrada = True
        time.sleep(0.01)

# ==========================================
# HILO 1B: LECTURA DE ARDUINO MOTORES Y STEPPER
# ==========================================
def hilo_lectura_motores():
    global running, pos_stepper_actual, estado_switch_hardware
    while running:
        if ser_motores and ser_motores.is_open:
            try:
                linea = ser_motores.readline().decode('utf-8', errors='ignore').strip()
                if linea:
                    if "POS:" in linea:
                        val = linea.split("POS:")[1].strip()
                        try:
                            pos_stepper_actual = int(val)
                        except ValueError:
                            pass
                    elif "SWITCH:" in linea:
                        raw = linea.split("SWITCH:")[1].strip()
                        if "PRESIONADO" in raw:
                            estado_switch_hardware = "PRESIONADO (Centro 90°)"
                        else:
                            estado_switch_hardware = "LIBRE"
                    elif any(k in linea for k in ["Homing", "Switch", "calibrado", "reestablecida", "centro"]):
                        log_evento(f"Stepper: {linea[:35]}")

                if ser_motores.in_waiting > 120:
                    ser_motores.reset_input_buffer()
            except Exception:
                pass
        time.sleep(0.01)

# ==========================================
# HILO 2: RECONOCIMIENTO DE VOZ
# ==========================================
def iniciar_busqueda():
    global estado_actual
    log_evento("🚀 Búsqueda de mochila iniciada")
    threading.Thread(target=sonar_conexion, daemon=True).start()
    estado_actual = EstadoSistema.SEGUIR_PISTA

def hilo_reconocimiento_voz():
    global estado_actual, running, ultima_voz_escuchada
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

    while running:
        if estado_actual == EstadoSistema.RETORNO_A_PISTA:
            time.sleep(0.3)
            continue

        try:
            with suprimir_salida_c():
                with mic as source:
                    audio = recognizer.listen(source, timeout=2.5, phrase_time_limit=3.5)
                texto = recognizer.recognize_google(audio, language="es-CL").lower()
            
            ultima_voz_escuchada = f"\"{texto}\""
            log_evento(f"Voz: \"{texto}\"")
            renderizar_dashboard()

            # 1. En reposo: escuchar orden para iniciar la búsqueda
            if estado_actual == EstadoSistema.REPOSO:
                if any(frase in texto for frase in TRIGGER_VOZ_BUSCAR):
                    iniciar_busqueda()

            # 2. En cualquier momento de la búsqueda o en el objetivo: escuchar 'listo', 'para', 'stop'
            elif estado_actual in [
                EstadoSistema.SEGUIR_PISTA,
                EstadoSistema.ALINEANDO_MOCHILA,
                EstadoSistema.AVANZANDO_A_MOCHILA,
                EstadoSistema.EN_OBJETIVO_SONIDO
            ]:
                if any(frase in texto for frase in TRIGGER_VOZ_PARAR):
                    enviar_motor(' ')
                    estado_actual = EstadoSistema.REPOSO
                    log_evento("🛑 Parada por voz (stop/alto)")
                    renderizar_dashboard()
                elif any(frase in texto for frase in TRIGGER_VOZ_RETORNO):
                    iniciar_retorno_a_pista()

        except sr.WaitTimeoutError:
            pass
        except sr.UnknownValueError:
            pass
        except Exception:
            pass

# ==========================================
# HILO 3: ENTRADA POR TECLADO EN VIVO (SSH DIRECTO)
# ==========================================
def leer_tecla_no_bloqueante(timeout=0.1):
    if not sys.stdin.isatty():
        time.sleep(timeout)
        return None
    try:
        rlist, _, _ = select.select([sys.stdin], [], [], timeout)
        if not rlist:
            return None
        ch = sys.stdin.read(1)
        if ch == '\x1b':
            rlist2, _, _ = select.select([sys.stdin], [], [], 0.04)
            if rlist2:
                ch2 = sys.stdin.read(1)
                if ch2 == '[':
                    rlist3, _, _ = select.select([sys.stdin], [], [], 0.04)
                    if rlist3:
                        ch3 = sys.stdin.read(1)
                        if ch3 == 'D': return 'left'
                        if ch3 == 'C': return 'right'
                        if ch3 == 'A': return 'up'
                        if ch3 == 'B': return 'down'
            return 'esc'
        return ch
    except Exception:
        return None

def hilo_teclado():
    global estado_actual, running, pos_stepper_actual, ultimo_evento_teclado

    if sys.stdin.isatty():
        try:
            tty.setcbreak(sys.stdin.fileno())
            attrs = termios.tcgetattr(sys.stdin.fileno())
            attrs[3] &= ~termios.ECHO
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, attrs)
        except Exception:
            pass

    while running:
        try:
            if sys.stdin.isatty():
                tecla = leer_tecla_no_bloqueante(timeout=0.1)
                if not tecla:
                    continue
                cmd = tecla.lower()
            else:
                line = sys.stdin.readline()
                if not line:
                    time.sleep(0.2)
                    continue
                cmd = line.strip().lower()

            if cmd in ['j', 'left']:
                mover_stepper(-30)
                pos_stepper_actual = max(-LIMITE_PAN_PASOS, pos_stepper_actual - 30)
                ultimo_evento_teclado = "Cámara Izquierda (-30 pasos)"
                renderizar_dashboard()
            elif cmd in ['l', 'right']:
                mover_stepper(30)
                pos_stepper_actual = min(LIMITE_PAN_PASOS, pos_stepper_actual + 30)
                ultimo_evento_teclado = "Cámara Derecha (+30 pasos)"
                renderizar_dashboard()
            elif cmd in ['h', 'c']:
                centrar_camara()
                ultimo_evento_teclado = "Cámara Centrada al frente (0)"
                renderizar_dashboard()
            elif cmd == 'b':
                ultimo_evento_teclado = "Búsqueda Iniciada ('b')"
                iniciar_busqueda()
                renderizar_dashboard()
            elif cmd == 'r':
                ultimo_evento_teclado = "Retorno a pista Iniciado ('r')"
                iniciar_retorno_a_pista()
                renderizar_dashboard()
            elif cmd in [' ', 'stop']:
                enviar_motor(' ')
                estado_actual = EstadoSistema.REPOSO
                ultimo_evento_teclado = "Freno general (REPOSO)"
                renderizar_dashboard()
            elif cmd in ['w', 'up']:
                enviar_motor('w')
                ultimo_evento_teclado = "Avanzar chasis (w)"
                renderizar_dashboard()
            elif cmd in ['s', 'down']:
                enviar_motor('s')
                ultimo_evento_teclado = "Retroceder chasis (s)"
                renderizar_dashboard()
            elif cmd == 'a':
                enviar_motor('a')
                ultimo_evento_teclado = "Giro izquierda chasis (a)"
                renderizar_dashboard()
            elif cmd == 'd':
                enviar_motor('d')
                ultimo_evento_teclado = "Giro derecha chasis (d)"
                renderizar_dashboard()
            elif cmd == 'k':
                enviar_motor('K')
                ultimo_evento_teclado = "Diagnóstico switch (K)"
                renderizar_dashboard()
            elif cmd == 'z':
                enviar_motor('Z')
                ultimo_evento_teclado = "Test LEDs ULN2003 (Z: A->B->C->D)"
                renderizar_dashboard()
            elif cmd == 'q':
                ultimo_evento_teclado = "Saliendo..."
                running = False
                break
        except Exception:
            break

# ==========================================
# LÓGICA DE NAVEGACIÓN Y SONIDO
# ==========================================
def notificar_llegada_mochila():
    global estado_actual, tiempo_avance_total
    log_evento("🎯 Objetivo mochila alcanzado (<=10 cm)")
    enviar_motor(' ')
    centrar_camara()
    estado_actual = EstadoSistema.EN_OBJETIVO_SONIDO
    tiempo_avance_total = time.time() - tiempo_avance_inicio
    sonar_alerta()

def iniciar_retorno_a_pista():
    global estado_actual
    log_evento("🔄 Retorno a pista iniciado")
    centrar_camara()
    estado_actual = EstadoSistema.RETORNO_A_PISTA
    threading.Thread(target=ejecutar_maniobra_retorno, daemon=True).start()

def ejecutar_maniobra_retorno():
    global estado_actual
    log_evento(">> [RETORNO] Retrocediendo hacia la cinta...")
    enviar_motor('s')

    t_inicio_rev = time.time()
    tiempo_max_rev = (tiempo_avance_total if tiempo_avance_total > 0 else 3.0) + 2.0

    while time.time() - t_inicio_rev < tiempo_max_rev:
        if linea_izq or linea_cen or linea_der:
            log_evento(">> [RETORNO] ¡Cinta detectada! Frenando.")
            enviar_motor(' ')
            break
        time.sleep(0.02)

    enviar_motor(' ')
    time.sleep(0.2)

    if direccion_giro_inicial == 'a':
        log_evento(">> [RETORNO] Contragiro a la DERECHA...")
        enviar_motor('d')
        time.sleep(tiempo_giro_ms / 1000.0)
    elif direccion_giro_inicial == 'd':
        log_evento(">> [RETORNO] Contragiro a la IZQUIERDA...")
        enviar_motor('a')
        time.sleep(tiempo_giro_ms / 1000.0)

    enviar_motor(' ')
    log_evento(">> [RETORNO] Reenganche completado. Reanudando pista.")
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
def display_width(s):
    w = 0
    for c in s:
        if unicodedata.category(c) == 'Mn' or c == '\ufe0f':
            continue
        eaw = unicodedata.east_asian_width(c)
        if eaw in ('W', 'F'):
            w += 2
        else:
            w += 1
    return w

def make_box_row(content, total_width=76):
    prefix = "║ "
    suffix = " ║"
    w_fixed = display_width(prefix) + display_width(suffix)
    avail = total_width - w_fixed
    t = ""
    w_t = 0
    for c in content:
        cw = 2 if unicodedata.east_asian_width(c) in ('W', 'F') else (0 if (unicodedata.category(c) == 'Mn' or c == '\ufe0f') else 1)
        if w_t + cw > avail:
            break
        t += c
        w_t += cw
    padding = " " * max(0, avail - w_t)
    return f"{prefix}{t}{padding}{suffix}"

def renderizar_dashboard():
    if not sys.stdin.isatty():
        return

    # 0. Símbolos de diagnóstico de hardware
    sim_mic = "✅" if hw_mic_ok else "❌"
    sim_par = "✅" if hw_parlante_ok else "❌"
    sim_cam = "✅" if hw_camara_ok else "❌"
    sim_sen = "✅" if hw_sensores_ok else "❌"
    sim_mot = "✅" if hw_motores_ok else "❌"
    sim_srv = "✅" if hw_servidor_ok else "⚠️"

    # 1. Sensores de línea (TCRT5000)
    izq_sym = "■" if linea_izq else "□"
    cen_sym = "■" if linea_cen else "□"
    der_sym = "■" if linea_der else "□"

    if paquetes_sensores > 0 and (time.time() - t_ultimo_tlm < 1.0):
        flujo_str = f"Activo ({paquetes_sensores} lecturas)"
    elif paquetes_sensores > 0:
        flujo_str = "⚠️ Pausado / Señal perdida"
    else:
        flujo_str = "❌ Sin datos (Verifica USB/puerto)"

    linea_str = f"[{izq_sym} IZQ] [{cen_sym} CEN] [{der_sym} DER]  ({linea_izq},{linea_cen},{linea_der}) | {flujo_str}"

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
    if estado_switch_hardware != "Desconocido":
        stepper_str += f" | Sw: {estado_switch_hardware}"

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

    top = "╔" + "═"*74 + "╗"
    div = "╠" + "═"*74 + "╣"
    bot = "╚" + "═"*74 + "╝"

    rows = [
        top,
        make_box_row("NAVBOT - PANEL DE MONITOREO EN TIEMPO REAL".center(72)),
        make_box_row(f"ESTADO DEL ROBOT : [ {estado_actual.center(22)} ]"),
        div,
        make_box_row("🛠️ DIAGNÓSTICO DE HARDWARE:"),
        make_box_row(f"   [{sim_mic}] MICRÓFONO USB    : {msg_mic}"),
        make_box_row(f"   [{sim_par}] PARLANTE BT      : {msg_parlante}"),
        make_box_row(f"   [{sim_cam}] CÁMARA USB       : {msg_camara}"),
        make_box_row(f"   [{sim_sen}] ARDUINO SENSORES : {msg_sensores}"),
        make_box_row(f"   [{sim_mot}] ARDUINO MOTORES  : {msg_motores}"),
        make_box_row(f"   [{sim_srv}] SERVIDOR YOLO    : {msg_servidor}"),
        div,
        make_box_row(f"📡 SENSORES LÍNEA : {linea_str}"),
        make_box_row(f"📏 ULTRASONIDO    : {dist_str}"),
        make_box_row(f"⚙️ MOTORES CHASIS : {motor_desc}"),
        make_box_row(f"🎥 CÁMARA (PAN)   : {stepper_str}"),
        make_box_row(f"🎯 VISIÓN YOLO    : {vision_str}"),
        make_box_row(f"🎤 VOZ ESCUCHADA  : {ultima_voz_escuchada}"),
        div,
        make_box_row(f"⌨️ ÚLTIMA ACCIÓN  : {ultimo_evento_teclado}"),
        make_box_row(f"📢 ESTADO / EVENTO: {ultimo_evento_sistema}"),
        div,
        make_box_row("⌨️ TECLAS DIRECTAS (Sin presionar Enter):"),
        make_box_row("   [j / ◄] Cámara Izq  | [l / ►] Cámara Der | [h] Centrar | [z] Test LEDs"),
        make_box_row("   [b] Buscar Mochila  | [r] Volver a Pista | [ESPACIO] Frenar | [q] Salir"),
        bot
    ]

    panel = "\033[H" + "\n".join(f"{r}\033[K" for r in rows) + "\n\033[K"
    sys.stdout.write(panel)
    sys.stdout.flush()

def hilo_dashboard_terminal():
    global running
    # Dejar pasar el autodiagnóstico inicial para que se pueda leer con calma
    time.sleep(2.5)

    if running and sys.stdin.isatty():
        sys.stdout.write("\033[2J\033[H\033[?25l")  # Limpiar pantalla 1 sola vez y ocultar cursor
        sys.stdout.flush()

    while running:
        try:
            renderizar_dashboard()
            time.sleep(0.5)
        except Exception:
            pass

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
    threading.Thread(target=hilo_lectura_motores, daemon=True).start()
    threading.Thread(target=hilo_reconocimiento_voz, daemon=True).start()
    threading.Thread(target=hilo_teclado, daemon=True).start()
    threading.Thread(target=hilo_dashboard_terminal, daemon=True).start()

    cap = None
    frame_counter = 0

    try:
        while running:
            # Gestión de apertura de cámara desde el inicio (transmisión continua)
            if cap is None or not cap.isOpened():
                cap = cv2.VideoCapture(0)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, ANCHO_IMAGEN)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                if not cap.isOpened():
                    if not alerta_camara_mostrada:
                        alerta_camara_mostrada = True
                    time.sleep(1.0)
                    continue
                else:
                    alerta_camara_mostrada = False

            ret, frame = cap.read()
            if not ret:
                if not alerta_camara_mostrada:
                    alerta_camara_mostrada = True
                time.sleep(0.2)
                continue
            else:
                alerta_camara_mostrada = False

            frame_counter += 1

            # Control de chasis según estado del sistema
            if estado_actual == EstadoSistema.REPOSO:
                enviar_motor(' ')
            elif estado_actual == EstadoSistema.SEGUIR_PISTA:
                ejecutar_seguimiento_linea()

            # Transmisión y procesamiento continuo con YOLO (1 de cada 3 frames en todo momento)
            if frame_counter % 3 == 0:
                _, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])

                try:
                    res = requests.post(
                        SERVER_URL,
                        files={'image': ('frame.jpg', encoded.tobytes(), 'image/jpeg')},
                        timeout=2.0
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

                        # En estados activos de búsqueda, guiar chasis y cámara hacia la mochila
                        if estado_actual in [EstadoSistema.SEGUIR_PISTA, EstadoSistema.ALINEANDO_MOCHILA, EstadoSistema.AVANZANDO_A_MOCHILA]:
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

                        # Paneo activo de cámara durante la búsqueda en pista si no hay mochila
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
        restaurar_terminal()
        if cap: cap.release()
        if ser_sensores: ser_sensores.close()
        if ser_motores: ser_motores.close()
        print("\n>> Sistema detenido correctamente.")

if __name__ == '__main__':
    main()
