#!/usr/bin/env python3
"""Script simple para probar la pantalla OLED"""

from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from luma.core.render import canvas
from PIL import ImageFont, ImageDraw
import time

print("Iniciando test de OLED...")

try:
    # Intentar conectar
    serial = i2c(port=1, address=0x3C)
    device = ssd1306(serial)
    print(f"✓ OLED conectada: {device.width}x{device.height}")
    
    # Cargar fuente
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 12)
    except:
        font = ImageFont.load_default()
    
    # Test 1: Llenar pantalla de blanco
    print("Test 1: Pantalla blanca...")
    with canvas(device) as draw:
        draw.rectangle((0, 0, device.width-1, device.height-1), fill="white")
    time.sleep(2)
    
    # Test 2: Pantalla negra
    print("Test 2: Pantalla negra...")
    with canvas(device) as draw:
        pass  # Pantalla vacía = negra
    time.sleep(2)
    
    # Test 3: Texto
    print("Test 3: Mostrando texto...")
    with canvas(device) as draw:
        draw.text((10, 10), "HOLA MUNDO!", font=font, fill="white")
        draw.text((10, 30), "Test OLED", font=font, fill="white")
    time.sleep(2)
    
    # Test 4: Formas
    print("Test 4: Dibujando formas...")
    with canvas(device) as draw:
        draw.rectangle((5, 5, 60, 30), outline="white", fill="white")
        draw.rectangle((70, 5, 120, 30), outline="white")
        draw.ellipse((5, 35, 30, 60), outline="white", fill="white")
        draw.line([(40, 40), (120, 60)], fill="white", width=2)
    time.sleep(2)
    
    # Test 5: Animación simple
    print("Test 5: Animación...")
    for i in range(device.width + 20):
        with canvas(device) as draw:
            x = i - 10
            draw.rectangle((x, 20, x+10, 40), fill="white")
            draw.text((30, 5), f"Frame {i}", font=font, fill="white")
        time.sleep(0.05)
    
    print("\n✓ Todos los tests completados!")
    print("Si no viste nada en la pantalla, verifica:")
    print("  1. Conexión I2C (SDA, SCL)")
    print("  2. Alimentación de la pantalla (VCC, GND)")
    print("  3. Dirección I2C correcta")
    
except Exception as e:
    print(f"\n✗ Error: {e}")
    print("\nPosibles soluciones:")
    print("  - Verifica que I2C esté habilitado: sudo raspi-config")
    print("  - Verifica las conexiones físicas")
    print("  - Prueba detectar dispositivos I2C: i2cdetect -y 1")
