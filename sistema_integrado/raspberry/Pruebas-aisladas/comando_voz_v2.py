"""
comando_voz_v2.py - Interacción por voz integrada con Arduino Cerebro

Funcionalidad:
1. Escucha por el micrófono USB de la Raspberry Pi.
2. Si escucha "busca el bastón":
   - Lanza el script send_feed.py para activar la cámara y el paneo YOLO.
3. Si escucha "para", "detente", "listo" o "volver":
   - Detiene send_feed.py.
   - Envía el comando 'r' al Arduino Cerebro para que el robot retroceda a la cinta y retome el circuito.
"""

import subprocess
import speech_recognition as sr
import serial
import time
import ctypes

# Silenciar mensajes y avisos internos de ALSA en C
ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p)
def py_error_handler(filename, line, function, err, fmt):
    pass
c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)
try:
    asound = ctypes.cdll.LoadLibrary('libasound.so.2')
    asound.snd_lib_error_set_handler(c_error_handler)
except Exception:
    pass

SEND_FEED_SCRIPT = "sistema_integrado/raspberry/send_feed.py"
PUERTO_CEREBRO   = "/dev/ttyACM0"  # Ajustar según 'ls /dev/tty*'
BAUD_CEREBRO     = 115200

TRIGGER_PHRASES = [
    "busca el baston",
    "busca el bastón",
    "buscar baston",
    "buscar bastón",
    "busca mi baston",
]

STOP_PHRASES = [
    "detente",
    "para",
    "detener busqueda",
    "detener búsqueda",
    "listo",
    "volver",
    "regresa",
    "regresar",
]

proceso_busqueda = None


def enviar_retorno_a_cerebro():
    """Envía el comando 'r' por Serial a Cerebro para iniciar la maniobra de regreso."""
    print(">> [VOZ] Enviando orden de RETORNO ('r') al Arduino Cerebro...")
    try:
        ser = serial.Serial(PUERTO_CEREBRO, BAUD_CEREBRO, timeout=1)
        time.sleep(1.5)  # Breve espera de sincronización UART
        ser.write(b'r\n')
        ser.close()
        print("[OK] Orden 'r' transmitida con éxito a Cerebro.")
    except Exception as e:
        print(f"[AVISO] No se pudo abrir Cerebro en {PUERTO_CEREBRO} ({e}). Simulación completada.")


def escuchar_comando(recognizer, mic):
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        print("\nEscuchando... di 'busca el bastón' o 'listo / para'")
        audio = recognizer.listen(source, phrase_time_limit=5)

    try:
        texto = recognizer.recognize_google(audio, language="es-CL")
        print(f"Escuché: \"{texto}\"")
        return texto.lower()
    except sr.UnknownValueError:
        print("No entendí, intenta de nuevo.")
        return ""
    except sr.RequestError as e:
        print(f"Error con el servicio de reconocimiento: {e}")
        return ""


def iniciar_busqueda():
    global proceso_busqueda
    if proceso_busqueda is not None and proceso_busqueda.poll() is None:
        print(">> Ya hay una búsqueda en curso, ignorando comando.")
        return
    print(">> Comando detectado. Iniciando send_feed.py...")
    proceso_busqueda = subprocess.Popen(["python3", SEND_FEED_SCRIPT])


def detener_y_retornar():
    global proceso_busqueda
    if proceso_busqueda is not None and proceso_busqueda.poll() is None:
        print(">> Deteniendo proceso de cámara...")
        proceso_busqueda.terminate()
        proceso_busqueda = None

    # Enviar la señal de retorno al chasis
    enviar_retorno_a_cerebro()


def main():
    recognizer = sr.Recognizer()
    mic = sr.Microphone()

    print("\n==============================================")
    print("   SISTEMA DE CONTROL POR VOZ INTEGRADO       ")
    print("==============================================")
    print("Comandos disponibles:")
    print(" - 'busca el bastón' : Inicia cámara y paneo")
    print(" - 'listo' / 'para'  : Regresa a la cinta")
    print("Presiona Ctrl+C para salir.\n")

    try:
        while True:
            texto = escuchar_comando(recognizer, mic)
            if any(frase in texto for frase in TRIGGER_PHRASES):
                iniciar_busqueda()
            elif any(frase in texto for frase in STOP_PHRASES):
                detener_y_retornar()
    except KeyboardInterrupt:
        print("\nCerrando...")
        if proceso_busqueda is not None and proceso_busqueda.poll() is None:
            proceso_busqueda.terminate()


if __name__ == "__main__":
    main()
