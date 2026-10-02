# Rama de Sistema Integrado (Staging / Branch)

Esta carpeta reúne la solución completa para el robot autónomo buscador de **mochilas**, integrando visión remota YOLO, control de voz, sensores y tracción 4WD con paneo:

```
sistema_integrado/
├── README.md                      <-- Este manual de uso y pruebas
├── diagrama_conexiones.md         <-- Mapa de pines y cableado entre placas
├── cerebro/                       <-- Firmware de sensores (Ultrasonido + Línea) para Arduino 1
├── motores_stepper/               <-- Firmware de tracción 4WD y paneo para Arduino 2
└── raspberry/                     <-- Software principal que corre en la Raspberry Pi
    ├── controlador_central.py     <-- CEREBRO MAESTRO: coordina voz, YOLO, motores y altavoz
    ├── alert_sound.py             <-- Módulo reproductor de alerta sonora para el altavoz
    ├── send_feed.py               <-- Cliente de visión y paneo de cámara hacia servidor Flask
    └── comando_voz_v2.py          <-- Reconocimiento de voz para activación y retorno
```

---

## 1. Arquitectura del Sistema

* **Servidor Flask Remoto:**
  * Ubicación: `/home/drstone/Projects/Yolo remote, Proyecto de titulo/`
  * Script: `remote_yolo_script.py`
  * Modelo: `yolo8n_mochilas.pt` (Detección de mochilas)
  * Puerto: `http://<IP_SERVIDOR>:5000/detect`
* **Raspberry Pi (Cerebro Central):**
  * Conectada a Cámara USB, Micrófono USB y Altavoz.
  * Conectada por USB a 2 Arduinos:
    1. **Arduino Sensores (`/dev/ttyACM0`):** Lee HC-SR04 y 3 sensores de línea TCRT5000.
    2. **Arduino Motores (`/dev/ttyUSB0`):** Controla 4 motores DC con L298N y motor de pasos para paneo de cámara.

---

## 2. Paso a paso para la Puesta en Marcha

### Paso 1: Levantar el Servidor YOLO Remoto
En la máquina con GPU/servidor:
```bash
cd "/home/drstone/Projects/Yolo remote, Proyecto de titulo"
python3 remote_yolo_script.py
```

### Paso 2: Flashear los 2 Arduinos desde tu PC
```bash
# 1. Arduino Motores y Stepper
pio run -d sistema_integrado/motores_stepper --target upload

# 2. Arduino Sensores (Cerebro)
pio run -d sistema_integrado/cerebro --target upload
```

### Paso 3: Ejecutar el Controlador Maestro en la Raspberry Pi
Conecta ambos Arduinos por USB a la Raspberry Pi y ejecuta:
```bash
python3 sistema_integrado/raspberry/controlador_central.py
```

---

## 3. Secuencia de Funcionamiento Completa

1. **Estado de Reposo:** El robot permanece detenido sobre el circuito de cinta esperando el comando de voz.
2. **Activación por Voz:** Dices al micrófono:
   > *"¿Dónde está la mochila?"* o *"Busca la mochila"*
   * El robot inicia el recorrido por la pista de cinta y activa la cámara con el paneo de búsqueda.
3. **Detección de Mochila con YOLO:**
   * Al aparecer una mochila en el campo de visión, el servidor devuelve las coordenadas (`center_x`).
   * El motor de pasos centra la cámara en la mochila.
   * El chasis del robot gira (`'a'` o `'d'`) para encarar la mochila de frente y sale de la cinta.
4. **Aproximación y Frenado a 10 cm:**
   * El robot avanza de frente (`'w'`) hacia la mochila.
   * Monitorea continuamente la distancia con el sensor de ultrasonido.
   * Al confirmar distancia **$\le 10\text{ cm}$**, frena en seco (`' '`).
5. **Aviso por Altavoz:**
   * La Raspberry Pi emite automáticamente el sonido de alerta por el parlante avisando que la mochila fue encontrada.
6. **Comando de Retorno:**
   * Cuando dices *"listo"* o *"para"*:
   * El robot retrocede recto (`'s'`) hasta que sus sensores de línea detectan la cinta del circuito.
   * Realiza el contragiro opuesto para recuperar la orientación original y continúa por la pista.
