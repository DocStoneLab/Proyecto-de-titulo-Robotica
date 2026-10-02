# Robot Móvil Autónomo Buscador de Mochilas
*Proyecto de Título - Ingeniería en Robótica*

Sistema robótico autónomo con tracción 4WD, visión artificial remota basada en YOLOv8, interacción por voz y navegación híbrida (seguimiento de línea por infrarrojos y aproximación ultrasónica).

---

## 1. Descripción General del Sistema

El robot navega autónomamente sobre un circuito delimitado por cinta. A través de comandos de voz, inicia la búsqueda de una mochila específica utilizando una cámara montada sobre un mecanismo de paneo con motor paso a paso.

Las imágenes se transmiten a un servidor remoto que ejecuta un modelo **YOLOv8** personalizado (`yolo8n_mochilas.pt`). Al detectar la mochila:
1. La cámara y el chasis se alinean con el objetivo.
2. El robot sale del camino predefinido y avanza hacia la mochila.
3. Se detiene con precisión a **10 cm** usando el sensor de ultrasonido.
4. Emite una alerta sonora a través de un parlante Bluetooth.
5. Al recibir la confirmación por voz (*"listo"* o *"para"*), retrocede en reversa recta hasta reenganchar la cinta predefinida, contragira para orientarse y continúa su recorrido por el circuito.

---

## 2. Arquitectura de Hardware y Comunicación

La **Raspberry Pi** actúa como el cerebro central del robot, conectada por puertos USB independientes a dos microcontroladores Arduino Uno, sin requerir cables puente entre ellos.

```
                             ┌────────────────────────────────────────┐
                             │       SERVIDOR REMOTO (GPU / Flask)    │
                             │  - remote_yolo_script.py (Puerto 5000) │
                             │  - yolo8n_mochilas.pt                  │
                             └───────────────────▲────────────────────┘
                                                 │ Wi-Fi (HTTP POST)
                                                 │
                             ┌───────────────────▼────────────────────┐
                             │       RASPBERRY PI (Cerebro Central)   │
                             │  - controlador_central.py              │
                             │  - alert_sound.py                      │
                             └───────┬────────────────────────┬───────┘
                                     │ USB                    │ USB
                                     │ (/dev/ttyACM0)         │ (/dev/ttyUSB0)
                                     │ 115200 baud            │ 9600 baud
                                     ▼                        ▼
                   ┌───────────────────────────┐    ┌───────────────────────────┐
                   │    ARDUINO 1: SENSORES    │    │    ARDUINO 2: MOTORES     │
                   │    (Ultrasonido + Línea)  │    │   (Tracción 4WD + Paneo)  │
                   └─────────────┬─────────────┘    └─────────────┬─────────────┘
                                 │                                │
                                 ▼                                ▼
                        [SENSORES EN CHASIS]             [ACTUADORES Y MOTORES]
                        - HC-SR04 (Pines 8, 9)           - 4WD Puentes H L298N (2 al 9)
                        - 3x TCRT5000 (A0, A1, A2)       - Stepper 28BYJ-48 (10 al 13)
                                                         - Final de Carrera (Pin A5)
```

### Componentes Utilizados:
* **Procesamiento Central y Audio:**
  * 1x Raspberry Pi con Raspberry Pi OS
  * 1x Cámara Web USB
  * 1x Micrófono USB
  * 1x Parlante de audio Bluetooth
* **Microcontroladores:**
  * 2x Arduino Uno
* **Sensores:**
  * 1x Sensor de distancia por ultrasonido HC-SR04
  * 3x Sensores infrarrojos de línea TCRT5000
  * 1x Final de carrera (Microswitch homing para el paneo)
* **Actuadores y Potencia:**
  * 4x Motoreductores DC con ruedas
  * 2x Controladores de motor Puente H L298N
  * 1x Motor paso a paso 28BYJ-48 con placa controladora ULN2003 (mecanismo de paneo)

---

## 3. Estructura del Repositorio

```
Proyecto-de-titulo-Robotica/
├── README.md                              <-- Documentación principal
│
├── sistema_integrado/                     <-- Solución completa y unificada
│   ├── README.md                          <-- Manual de carga y puesta en marcha
│   ├── diagrama_conexiones.md             <-- Mapa de pines y cableado detallado
│   ├── cerebro/                           <-- Firmware PlatformIO para Arduino 1 (Sensores)
│   │   ├── platformio.ini
│   │   └── src/main.cpp
│   ├── motores_stepper/                   <-- Firmware PlatformIO para Arduino 2 (Motores + Stepper)
│   │   ├── platformio.ini
│   │   └── src/main.cpp
│   └── raspberry/                         <-- Software principal para la Raspberry Pi
│       ├── controlador_central.py         <-- Cerebro maestro: coordina voz, visión, motores y altavoz
│       ├── alert_sound.py                 <-- Módulo de alerta sonora Bluetooth (meme del pájaro)
│       ├── pajaro.opus                    <-- Archivo de audio de alerta
│       └── Pruebas-aisladas/              <-- Scripts de diagnóstico modular
│
└── Yolo remote, Proyecto de titulo/       <-- Servidor de detección visual
    ├── remote_yolo_script.py              <-- API Flask que procesa las imágenes
    └── yolo8n_mochilas.pt                 <-- Modelo entrenado para detección de mochilas
```

---

## 4. Guía de Puesta en Marcha

### Paso 1: Levantar el Servidor YOLO (PC / Servidor con GPU)
En la máquina que ejecutará el procesamiento de imágenes:
```bash
cd "Yolo remote, Proyecto de titulo"
python3 remote_yolo_script.py
```

### Paso 2: Flashear los Arduinos desde PC (PlatformIO)
Conecta cada Arduino mediante cable USB a tu PC y carga el código respectivo:
```bash
# Cargar en Arduino 2 (Motores y Stepper):
pio run -d sistema_integrado/motores_stepper --target upload

# Cargar en Arduino 1 (Sensores Ultrasonido y Línea):
pio run -d sistema_integrado/cerebro --target upload
```

### Paso 3: Conectar Dispositivos a la Raspberry Pi
1. Conecta ambos Arduinos a los puertos USB de la Raspberry Pi.
2. Conecta la cámara USB y el micrófono USB.
3. Enciende el parlante Bluetooth (se reconectará automáticamente con la Raspberry Pi).

### Paso 4: Ejecutar el Controlador Central en la Raspberry Pi
```bash
python3 sistema_integrado/raspberry/controlador_central.py
```

---

## 5. Comandos de Voz y Flujo de Interacción

| Comando de Voz | Acción del Robot |
| :--- | :--- |
| **"¿Dónde está la mochila?"** / *"Busca la mochila"* | El robot arranca el seguimiento de pista por cinta y activa la cámara con el paneo de búsqueda. |
| **Detección Automática (YOLO)** | Centra la mochila con el stepper, gira el chasis hacia el objetivo, sale de la cinta y avanza. |
| **Llegada a 10 cm (Ultrasonido)** | Frena de inmediato en seco y reproduce el audio de alerta por el parlante Bluetooth. |
| **"Listo"** / *"Para"* / *"Volver"* | El robot retrocede recto en reversa hasta detectar la cinta, se realinea y continúa el recorrido por el circuito. |
