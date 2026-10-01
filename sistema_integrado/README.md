# Rama de Sistema Integrado (Staging / Branch)

Esta carpeta reúne la solución completa integrada lista para probar en el hardware físico:

```
sistema_integrado/
├── README.md                      <-- Este manual de uso y pruebas
├── diagrama_conexiones.md         <-- Mapa de pines y cables
├── cerebro/                       <-- Firmware de navegación FSM (Arduino Cerebro)
├── motores_stepper/               <-- Firmware de tracción y paneo (Arduino Motores/Stepper)
└── raspberry/                     <-- Scripts de visión y voz (Raspberry Pi)
    ├── send_feed.py               <-- Paneo YOLO + trigger a Cerebro + sonido
    └── comando_voz_v2.py          <-- Detección por voz + comando de retorno ('r')
```

---

## 1. Paso a paso para cargar el Firmware en los Arduinos

### Paso 1: Cargar en el Arduino de Motores y Stepper
Conecta el Arduino de motores por cable USB a tu PC y corre:
```bash
pio run -d sistema_integrado/motores_stepper --target upload
```

### Paso 2: Cargar en el Arduino Cerebro (Sensores)
Conecta el Arduino de sensores por cable USB a tu PC y corre:
```bash
pio run -d sistema_integrado/cerebro --target upload
```

---

## 2. Paso a paso para correr en la Raspberry Pi

Una vez conectados ambos Arduinos por USB a la Raspberry Pi:

### Paso 1: Verificar puertos USB
```bash
ls /dev/ttyUSB* /dev/ttyACM*
```
*(Por defecto `stepper` usa `/dev/ttyUSB0` y `cerebro` usa `/dev/ttyACM0`).*

### Paso 2: Lanzar el sistema por comando de voz
```bash
python3 sistema_integrado/raspberry/comando_voz_v2.py
```

---

## 3. Secuencia de Prueba Completa

1. **Inicio en pista:** El robot sigue el circuito de cinta normalmente (`SEGUIR_LINEA`).
2. **Búsqueda por voz:** Di al micrófono *"busca el bastón"*. El script `send_feed.py` se activará y la cámara empezará a panear.
3. **Detección visual:** Cuando YOLO detecta el bastón:
   - El stepper centra la cámara sobre el objeto.
   - `send_feed.py` envía la orientación (`'i'`, `'d'` o `'f'`) a `cerebro`.
4. **Salida y avance:** El robot gira hacia el objeto y avanza de frente (`'w'`).
5. **Frenado ultrasónico a 10 cm:** Al confirmar $\le 10\text{ cm}$ con el HC-SR04, el robot frena en seco y emite `EVT:OBJETIVO_10CM`.
6. **Alerta sonora:** La Raspberry Pi escucha el evento y reproduce automáticamente el sonido de alerta.
7. **Retorno por voz:** Cuando le digas al robot *"listo"* o *"para"*:
   - `comando_voz_v2.py` envía `'r'` a `cerebro`.
   - El robot retrocede recto (`'s'`) hasta que sus sensores de línea tocan la cinta.
   - Realiza el contragiro opuesto para alinearse con la pista.
   - Continúa avanzando hacia adelante por el circuito.
