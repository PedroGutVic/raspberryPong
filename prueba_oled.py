from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from luma.core.render import canvas
import time

# Asegúrese de que la dirección I2C sea la correcta (0x3C o 0x3D)
serial = i2c(port=1, address=0x3C)
device = ssd1306(serial)

# Inicia el dibujo
with canvas(device) as draw:
    # Dibuja un rectángulo en el borde
    draw.rectangle(device.bounding_box, outline="white", fill="black")

    # Escribe un texto
    draw.text((10, 20), "RPi 5 Test OK!", fill="white")
    draw.text((10, 40), "NFP1315-61AY", fill="white")

# Espera 5 segundos y luego borra la pantalla
time.sleep(5)
device.clear()
