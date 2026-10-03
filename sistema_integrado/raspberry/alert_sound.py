"""
alert_sound.py - Gestión de reproducción de audios desde la carpeta 'Audios'
en la raíz del proyecto para la Raspberry Pi, con reconexión Bluetooth.
"""
import os
import sys
import subprocess

# Dirección MAC del parlante Bluetooth vinculado
MAC_PARLANTE = "41:42:34:98:75:BE"

def obtener_carpeta_audios():
    """
    Retorna la ruta absoluta de la carpeta 'Audios' ubicada en la raíz del proyecto.
    Soporta la estructura habitual en la Raspberry Pi y entornos de ejecución.
    """
    return os.path.expanduser("~/sketches/Proyecto-de-titulo-Robotica/Audios")

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
    except Exception:
        pass

def buscar_archivo_audio(nombre_archivo):
    """
    Busca un archivo de audio dentro de la carpeta 'Audios'.
    Soporta búsqueda exacta o sin distinción de mayúsculas/minúsculas.
    """
    carpeta = obtener_carpeta_audios()
    if not os.path.isdir(carpeta):
        return None

    # 1. Coincidencia directa
    ruta_directa = os.path.join(carpeta, nombre_archivo)
    if os.path.isfile(ruta_directa):
        return ruta_directa

    # 2. Búsqueda insensible a mayúsculas/minúsculas y sin extensión
    nombre_lower = nombre_archivo.lower()
    try:
        for f in os.listdir(carpeta):
            if f.lower() == nombre_lower:
                return os.path.join(carpeta, f)
            if os.path.splitext(f.lower())[0] == nombre_lower:
                return os.path.join(carpeta, f)
    except Exception:
        pass

    return None

def reproducir_audio(nombre_archivo, fallback_texto=None):
    """
    Reproduce un archivo de audio ubicado en la carpeta 'Audios' mediante mpv.
    Si no se encuentra o falla, emite un aviso sonoro alternativo.
    """
    asegurar_conexion_bluetooth()

    archivo = buscar_archivo_audio(nombre_archivo)
    if archivo and os.path.isfile(archivo):
        print(f"🔊 [AUDIO] Reproduciendo: {archivo}")
        ret = os.system(f'mpv --no-video "{archivo}" 2>/dev/null')
        if ret == 0:
            return True

    print(f"⚠️ [AUDIO] No se encontró '{nombre_archivo}' en '{obtener_carpeta_audios()}'.")
    if fallback_texto:
        os.system(f'aplay /usr/share/sounds/alsa/Front_Center.wav 2>/dev/null || espeak -v es "{fallback_texto}" 2>/dev/null')
    sys.stdout.write('\a')
    sys.stdout.flush()
    return False

def sonar_conexion():
    """Reproduce el audio 'conectado.mp3' de la carpeta Audios al pedir buscar la mochila."""
    print("\n🔊 [ALTAVOZ] Reproduciendo sonido de conexión (conectado.mp3)...")
    reproducir_audio("conectado.mp3", fallback_texto="Iniciando búsqueda")

def sonar_alerta():
    """
    Reproduce el sonido de llegada al objetivo desde la carpeta Audios.
    Permite reproducir alerta.mp3, mochila.mp3, o cualquier otro audio que agregues a futuro.
    """
    print("\n🔔 [ALTAVOZ] ¡MOCHILA ALCANZADA!")
    asegurar_conexion_bluetooth()

    # Prioridades de nombres para la alerta de llegada
    posibles_nombres = ["alerta.mp3", "mochila.mp3", "llegada.mp3", "objetivo.mp3"]
    archivo_encontrado = None

    for nombre in posibles_nombres:
        ruta = buscar_archivo_audio(nombre)
        if ruta:
            archivo_encontrado = ruta
            break

    # Si no tiene esos nombres, busca cualquier otro audio en Audios/ que no sea conectado.mp3
    if not archivo_encontrado:
        carpeta = obtener_carpeta_audios()
        if os.path.isdir(carpeta):
            try:
                for f in sorted(os.listdir(carpeta)):
                    if f.lower().endswith(('.mp3', '.wav', '.opus', '.ogg', '.m4a')) and "conectado" not in f.lower():
                        archivo_encontrado = os.path.join(carpeta, f)
                        break
            except Exception:
                pass

    if archivo_encontrado:
        print(f"🔊 [AUDIO] Reproduciendo audio de llegada: {archivo_encontrado}")
        ret = os.system(f'mpv --no-video "{archivo_encontrado}" 2>/dev/null')
        if ret == 0:
            return

    # Fallback si aún no hay un segundo audio en Audios
    print(">> [AUDIO] No se encontró audio de llegada en 'Audios/'. Emitiendo señal acústica...")
    os.system('aplay /usr/share/sounds/alsa/Front_Center.wav 2>/dev/null || espeak -v es "Mochila alcanzada" 2>/dev/null')
    sys.stdout.write('\a\a\a')
    sys.stdout.flush()

if __name__ == "__main__":
    print(f"Carpeta de audios detectada: {obtener_carpeta_audios()}")
    print("Probando sonido de conexión (conectado.mp3)...")
    sonar_conexion()
