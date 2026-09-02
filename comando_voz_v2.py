"""
Script de interacción por voz — versión intermedia (sin Arduino todavía).

Escucha continuamente por el micrófono USB. Cuando detecta el comando
("busca el bastón"), lanza el script send_feed.py, que empieza a mandar
frames de la cámara al servidor Flask (donde corre YOLO) para detección.

Requisitos previos (correr en la Raspberry Pi):
    sudo apt update
    sudo apt install portaudio19-dev flac -y
    pip3 install SpeechRecognition pyaudio --break-system-packages
"""

import subprocess
import speech_recognition as sr

# --- Configuración ---
# Ruta al script que manda el video al servidor de detección.
# Ajusta la ruta si send_feed.py está en otra carpeta.
SEND_FEED_SCRIPT = "sketches/Proyecto-de-titulo-Robotica/stepper-pan/send_feed.py"

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
]

proceso_busqueda = None  # referencia al proceso send_feed.py mientras corre


def listar_microfonos():
    print("Micrófonos disponibles:")
    for i, nombre in enumerate(sr.Microphone.list_microphone_names()):
        print(f"  [{i}] {nombre}")


def escuchar_comando(recognizer, mic):
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        print("\nEscuchando... di 'busca el bastón'")
        audio = recognizer.listen(source, phrase_time_limit=5)

    try:
        texto = recognizer.recognize_google(audio, language="es-CL")
        print(f"Escuché: \"{texto}\"")
        return texto.lower()
    except sr.UnknownValueError:
        print("No entendí, intenta de nuevo.")
        return ""
    except sr.RequestError as e:
        print(f"Error con el servicio de reconocimiento (revisa tu internet): {e}")
        return ""


def iniciar_busqueda():
    global proceso_busqueda
    if proceso_busqueda is not None and proceso_busqueda.poll() is None:
        print(">> Ya hay una búsqueda en curso, ignorando comando.")
        return
    print(">> Comando detectado. Iniciando send_feed.py...")
    proceso_busqueda = subprocess.Popen(["python3", SEND_FEED_SCRIPT])


def detener_busqueda():
    global proceso_busqueda
    if proceso_busqueda is not None and proceso_busqueda.poll() is None:
        print(">> Deteniendo búsqueda...")
        proceso_busqueda.terminate()
        proceso_busqueda = None
    else:
        print(">> No hay ninguna búsqueda en curso.")


def main():
    listar_microfonos()

    recognizer = sr.Recognizer()
    # Si tu micrófono USB no queda seleccionado por defecto, especifica su índice:
    # mic = sr.Microphone(device_index=1)
    mic = sr.Microphone()

    print("\nSistema listo. Presiona Ctrl+C para salir.\n")

    try:
        while True:
            texto = escuchar_comando(recognizer, mic)
            if any(frase in texto for frase in TRIGGER_PHRASES):
                iniciar_busqueda()
            elif any(frase in texto for frase in STOP_PHRASES):
                detener_busqueda()
    except KeyboardInterrupt:
        print("\nCerrando...")
        detener_busqueda()


if __name__ == "__main__":
    main()
