"""
alert_sound.py - Módulo para reproducir el meme del pájaro gritando
y asegurar reconexión automática Bluetooth con el parlante.
"""
import os
import sys
import subprocess

# Dirección MAC del parlante Bluetooth vinculado
MAC_PARLANTE = "41:42:34:98:75:BE"

# Rutas posibles donde puede estar el archivo pajaro.opus
RUTAS_AUDIO = [
    os.path.expanduser("~/Projects/Proyecto-de-titulo-Robotica/sistema_integrado/raspberry/pajaro.opus"),
    os.path.expanduser("~/sketches/Proyecto-de-titulo-Robotica/pajaro.opus"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "pajaro.opus"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "sonidos", "pajaro.opus"),
    os.path.expanduser("~/sketches/Proyecto-de-titulo-Robotica/sonidos/pajaro.opus"),
    os.path.expanduser("~/sonidos/pajaro.opus"),
]

def asegurar_conexion_bluetooth():
    """Verifica si el parlante está conectado y, si no lo está, lo conecta automáticamente."""
    try:
        check = subprocess.run(
            ["bluetoothctl", "info", MAC_PARLANTE],
            capture_output=True,
            text=True,
            timeout=2
        )
        if "Connected: yes" not in check.stdout:
            print(f">> [BLUETOOTH] Reconectando parlante {MAC_PARLANTE}...")
            subprocess.run(["bluetoothctl", "connect", MAC_PARLANTE], timeout=5)
    except Exception as e:
        pass

def buscar_sonido_conexion():
    """Busca el archivo de sonido de conexión en las carpetas de sonidos de la Raspberry."""
    directorios = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "sonidos"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sonidos"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "sonidos"),
        os.path.expanduser("~/sketches/Proyecto-de-titulo-Robotica/sonidos"),
        os.path.expanduser("~/sketches/Proyecto-de-titulo-Robotica/sistema_integrado/raspberry/sonidos"),
        os.path.expanduser("~/sketches/Proyecto-de-titulo-Robotica/sistema_integrado/sonidos"),
        os.path.expanduser("~/Projects/Proyecto-de-titulo-Robotica/sonidos"),
        os.path.expanduser("~/Projects/Proyecto-de-titulo-Robotica/sistema_integrado/raspberry/sonidos"),
        os.path.expanduser("~/sonidos"),
        os.path.expanduser("~/sketches/sonidos"),
    ]

    extensiones = ('.mp3', '.wav', '.opus', '.ogg', '.m4a', '.flac')

    # 1. Prioridad: Buscar archivos que tengan 'conex', 'conect' o 'connect' en el nombre
    for d in directorios:
        if os.path.isdir(d):
            try:
                for f in os.listdir(d):
                    if f.lower().endswith(extensiones) and any(w in f.lower() for w in ["conex", "conect", "connect"]):
                        return os.path.join(d, f)
            except Exception:
                pass

    # 2. Si no tiene ese nombre específico, buscar cualquier archivo de audio en la carpeta sonidos (que no sea pajaro)
    for d in directorios:
        if os.path.isdir(d):
            try:
                for f in os.listdir(d):
                    if f.lower().endswith(extensiones) and "pajaro" not in f.lower():
                        return os.path.join(d, f)
            except Exception:
                pass

    # 3. Rutas directas alternativas
    rutas_directas = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "conexion.opus"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "conexion.mp3"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "conexion.wav"),
        os.path.expanduser("~/sketches/Proyecto-de-titulo-Robotica/conexion.opus"),
        os.path.expanduser("~/sketches/Proyecto-de-titulo-Robotica/conexion.mp3"),
        os.path.expanduser("~/sketches/Proyecto-de-titulo-Robotica/conexion.wav"),
    ]
    for r in rutas_directas:
        if os.path.exists(r):
            return r

    return None

def sonar_conexion():
    """Reproduce el sonido de conexión cuando se inicia la búsqueda de la mochila."""
    print("\n🔊 [ALTAVOZ] Reproduciendo sonido de conexión...")
    
    # 1. Asegurar parlante bluetooth conectado
    asegurar_conexion_bluetooth()

    # 2. Buscar archivo de sonido
    archivo = buscar_sonido_conexion()
    if archivo:
        print(f">> [AUDIO] Reproduciendo archivo: {archivo}")
        ret = os.system(f'mpv --no-video "{archivo}" 2>/dev/null')
        if ret == 0:
            return

    # Fallback si no encuentra el archivo o falla mpv
    print(">> [AUDIO] Archivo de conexión no encontrado en carpeta 'sonidos/'. Tono alternativo...")
    os.system('aplay /usr/share/sounds/alsa/Front_Center.wav 2>/dev/null || espeak -v es "Iniciando búsqueda" 2>/dev/null')
    sys.stdout.write('\a')
    sys.stdout.flush()

def sonar_alerta():
    """Reproduce el audio del pájaro gritando cuando el robot llega a la mochila."""
    print("\n🔔 [ALTAVOZ] ¡MOCHILA DETECTADA A 10 CM! Reproduciendo meme del pájaro...")
    
    # 1. Asegurar que el parlante siga conectado
    asegurar_conexion_bluetooth()

    # 2. Buscar el archivo pajaro.opus
    archivo_encontrado = None
    for ruta in RUTAS_AUDIO:
        if os.path.exists(ruta):
            archivo_encontrado = ruta
            break

    # 3. Reproducir con mpv
    if archivo_encontrado:
        ret = os.system(f'mpv --no-video "{archivo_encontrado}" 2>/dev/null')
        if ret == 0:
            return

    # Fallback si no encuentra el archivo o falla mpv
    os.system('espeak -v es "Mochila encontrada" 2>/dev/null || aplay /usr/share/sounds/alsa/Front_Center.wav 2>/dev/null')
    sys.stdout.write('\a\a\a')
    sys.stdout.flush()

if __name__ == "__main__":
    print("Probando sonido de conexión...")
    sonar_conexion()
    print("Probando sonido de alerta...")
    sonar_alerta()
