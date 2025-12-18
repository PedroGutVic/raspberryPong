from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306 
from luma.core.render import canvas
from PIL import ImageFont
import time
import sys

# --- CONFIGURACIÓN DE 4 PANTALLAS ---
# Pines evitados: 6, 16 (botones)

# PANTALLA 1: I2C-1 (bus hardware estándar)
# SDA: GPIO 2 → Pin físico 3
# SCL: GPIO 3 → Pin físico 5
I2C_PORT_1 = 1
ADDR_1 = 0x3C

# PANTALLA 2: I2C-3 (bus configurado)
# SDA: GPIO 4 → Pin físico 7
# SCL: GPIO 5 → Pin físico 29
I2C_PORT_2 = 3
ADDR_2 = 0x3C

# PANTALLA 3: I2C-13 (bus disponible)
# SDA: GPIO 22 → Pin físico 15
# SCL: GPIO 17 → Pin físico 11
I2C_PORT_3 = 13
ADDR_3 = 0x3C

# PANTALLA 4: I2C-14 (bus disponible)
# SDA: GPIO 10 → Pin físico 19
# SCL: GPIO 11 → Pin físico 23
I2C_PORT_4 = 14
ADDR_4 = 0x3C

# --- Configuración de Fuente ---
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 9)
    big_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 14)
except IOError:
    font = ImageFont.load_default()
    big_font = ImageFont.load_default()

# ==============================================================================
# INICIALIZACIÓN DE LAS 4 PANTALLAS
# ==============================================================================

devices = []

try:
    # Pantalla 1
    serial_1 = i2c(port=I2C_PORT_1, address=ADDR_1)
    device_1 = ssd1306(serial_1)
    devices.append(('Pantalla 1', device_1))
    print(f"✓ Pantalla 1 (I2C-{I2C_PORT_1}) inicializada.")

    # Pantalla 2
    serial_2 = i2c(port=I2C_PORT_2, address=ADDR_2)
    device_2 = ssd1306(serial_2)
    devices.append(('Pantalla 2', device_2))
    print(f"✓ Pantalla 2 (I2C-{I2C_PORT_2}) inicializada.")

    # Pantalla 3
    serial_3 = i2c(port=I2C_PORT_3, address=ADDR_3)
    device_3 = ssd1306(serial_3, rotate=2)
    devices.append(('Pantalla 3', device_3))
    print(f"✓ Pantalla 3 (I2C-{I2C_PORT_3}) inicializada.")

    # Pantalla 4
    serial_4 = i2c(port=I2C_PORT_4, address=ADDR_4)
    device_4 = ssd1306(serial_4, rotate=2)
    devices.append(('Pantalla 4', device_4))
    print(f"✓ Pantalla 4 (I2C-{I2C_PORT_4}) inicializada.")

except Exception as e:
    print(f"Error al inicializar dispositivos: {e}")
    print("Asegúrese de que los pines estén correctamente cableados y ejecute con 'sudo'.")
    sys.exit(1)


# ==============================================================================
# 2. FUNCIÓN DE DIBUJO Y BUCLE
# ==============================================================================

print("Iniciando prueba de 4 pantallas...")
contador = 0
try:
    while True:
        tiempo_actual = time.strftime('%H:%M:%S')
        
        # Actualizar Pantalla 1
        with canvas(device_1) as draw:
            draw.text((20, 10), "PANTALLA 1", font=big_font, fill="white")
            draw.text((10, 30), f"Count: {contador}", font=font, fill="white")
            
        # Actualizar Pantalla 2
        with canvas(device_2) as draw:
            draw.text((20, 10), "PANTALLA 2", font=big_font, fill="white")
            draw.text((10, 30), f"Hora: {tiempo_actual}", font=font, fill="white")
        
        # Actualizar Pantalla 3
        with canvas(device_3) as draw:
            draw.text((20, 10), "PANTALLA 3", font=big_font, fill="white")
            draw.text((10, 30), f"Test: OK", font=font, fill="white")
            
        # Actualizar Pantalla 4
        with canvas(device_4) as draw:
            draw.text((20, 10), "PANTALLA 4", font=big_font, fill="white")
            draw.text((10, 30), f"Valor: {contador % 100}", font=font, fill="white")
        
        contador += 1
        time.sleep(0.5)

except KeyboardInterrupt:
    print("\nPrueba terminada.")
    for name, dev in devices:
        dev.clear()
