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
    sonar_alerta()
