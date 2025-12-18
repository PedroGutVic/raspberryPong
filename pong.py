
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306 
from luma.core.render import canvas
from PIL import ImageFont, ImageDraw, Image
import json
import time
import math
import random
import sys
import os
import atexit
import threading

# --- INTEGRACIÓN GPIO ZERO ---
from gpiozero import Button, Device
from gpiozero.pins.lgpio import LGPIOFactory

# ==============================================================================
# 1. CONFIGURACIÓN DE HARDWARE (OLED y GPIO)
# ==============================================================================

# --- OLED - 1 PANTALLA PRINCIPAL ---
try:
    # Pantalla 1 (Principal)
    serial_1 = i2c(port=1, address=0x3C)
    device_1 = ssd1306(serial_1)
    
    devices = [device_1]
except Exception as e:
    print(f"Error al iniciar la pantalla OLED: {e}")
    sys.exit(1)
    
WHITE = "white"
BLACK = "black"
# Pantalla virtual: 1x1 = 128x64
WIDTH, HEIGHT = 128, 64
SCREEN_W, SCREEN_H = 128, 64  # Tamaño de cada pantalla física

# --- Fuentes ---
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 9)
    big_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 14)
except IOError:
    font = ImageFont.load_default()
    big_font = ImageFont.load_default()

# --- GPIO (Configuración Nativa) ---
# Cerrar pines previos y configurar factory
Device.pin_factory = LGPIOFactory()

def cleanup_gpio():
    """Limpiar recursos GPIO al salir"""
    try:
        Device.pin_factory.close()
    except:
        pass

atexit.register(cleanup_gpio)

# ---------------- HIGH LEVEL (Archivo simple) ----------------
HIGH_LEVEL_FILE = os.path.join(os.path.dirname(__file__), "highlevel.json")

def load_highlevel():
    try:
        with open(HIGH_LEVEL_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return int(data.get('highlevel', 0))
    except Exception:
        return 0

def save_highlevel(level:int):
    try:
        with open(HIGH_LEVEL_FILE, 'w', encoding='utf-8') as f:
            json.dump({'highlevel': int(level)}, f)
    except Exception:
        pass

# Valor cargado en memoria
highlevel = load_highlevel()
# Flag para indicar que se consiguió un nuevo highlevel en la ronda pasada
new_highlevel_flag = False

# Variables para mensaje de compra
purchase_message = ""
purchase_message_time = 0

# ---------------- SISTEMA DE MONEDAS Y MEJORAS PERMANENTES ----------------
UPGRADES_FILE = os.path.join(os.path.dirname(__file__), "upgrades.json")

def load_upgrades():
    """Carga monedas y mejoras permanentes"""
    try:
        with open(UPGRADES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {
            'coins': 0,
            'permanent_upgrades': {
                'extra_lives': 0,      # +1 vida por nivel
                'faster_paddle': 0,    # +0.5 velocidad por nivel
                'score_multiplier': 0, # +10% puntos por nivel
                'ball_slowdown': 0     # -5% velocidad bola por nivel
            }
        }

def save_upgrades(data):
    """Guarda monedas y mejoras permanentes"""
    try:
        with open(UPGRADES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

# Cargar datos de mejoras
upgrades_data = load_upgrades()
coins = upgrades_data.get('coins', 0)
permanent_upgrades = upgrades_data.get('permanent_upgrades', {
    'extra_lives': 0, 'faster_paddle': 0, 'score_multiplier': 0, 'ball_slowdown': 0
})

# Mejoras temporales de la partida actual
temp_upgrades = {
    'shield': 0,           # Escudo que absorbe 1 muerte
    'slow_motion': 0,      # Ralentiza todo por 10s
    'extra_life': 0,       # +1 vida inmediata
    'speed_boost': 0       # +2 velocidad paleta por 15s
}
temp_upgrade_timers = {}  # Para manejar duraciones

# Pines BCM 23 (Arriba), 24 (Abajo), 25 (Aceptar/Seleccionar).
try:
    btn_up = Button(23)
    btn_down = Button(24)
    btn_select = Button(25)
except Exception as e:
    print(f"Error configurando botones GPIO: {e}")
    print("Intentando limpiar y reintentar...")
    cleanup_gpio()
    Device.pin_factory = LGPIOFactory()
    btn_up = Button(23)
    btn_down = Button(24)
    btn_select = Button(25)

FPS = 60
last_time = time.time()

# Velocidad inicial de las bolas (ajusta aquí el rango inicial)
BALL_SPEED_MIN = 4.0
BALL_SPEED_MAX = 6.0

# Aceleración por gravedad aplicada por el modificador (unidades por frame)
GRAVITY_ACCEL = 0.9
# Velocidad mínima de rebote bajo gravedad (no dejar la bola en reposo absoluto)
MIN_BOUNCE_V = 4.0

# Margen superior para el HUD (área reservada para puntos, vidas, nivel)
HUD_HEIGHT = 11


# ==============================================================================
# 2. CLASES Y ESTRUCTURAS DE JUEGO
# ==============================================================================

class SimpleRect:
    """Clase simplificada para simular pygame.Rect."""
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h
        
    @property
    def left(self): return self.x
    @left.setter
    def left(self, val): self.x = val
        
    @property
    def right(self): return self.x + self.w
    
    @property
    def top(self): return self.y
    @top.setter
    def top(self, val): self.y = val

    @property
    def bottom(self): return self.y + self.h

    @property
    def centerx(self): return self.x + self.w // 2
    @property
    def centery(self): return self.y + self.h // 2
    @centerx.setter
    def centerx(self, val): self.x = val - self.w // 2
    @centery.setter
    def centery(self, val): self.y = val - self.h // 2
    
    @property
    def center(self): return (self.centerx, self.centery)
    @center.setter
    def center(self, val): self.x = val[0] - self.w // 2; self.y = val[1] - self.h // 2
    
    def inflate(self, dx, dy):
        return SimpleRect(self.x - dx // 2, self.y - dy // 2, self.w + dx, self.h + dy)

# ---------------- CONFIGURACIÓN DE PONG ----------------
paddle_w, paddle_h = 2, 13
# Calcular el centro del área jugable (excluyendo el HUD)
playable_center = HUD_HEIGHT + (HEIGHT - HUD_HEIGHT) // 2
player = SimpleRect(2, playable_center - paddle_h//2, paddle_w, paddle_h) 
ai = SimpleRect(WIDTH - 4, playable_center - paddle_h//2, paddle_w, paddle_h) 

paddle_base_speed = 3.0 
ai_base_speed = 2.5  # IA más lenta al inicio
paddle_speed = paddle_base_speed
ai_speed = ai_base_speed


# ---------------- GAME STATS (Variables Globales Inicializadas) ----------------
lives = 3
score = 0
level = 1
game_over = False

state = 'menu'
menu_selected = 0
menu_options = ['Jugar', 'Tienda', 'Highscore', 'Salir']
last_score = None
last_menu_press_time = time.time() 

# Variables para menús de tiendas
shop_menu_selected = 0
shop_menu_options = []  # Se llenará dinámicamente
shop_game_selected = 0
shop_game_active = False  # Flag para pausar el juego
game_paused = False 

# IA balanceada: inicia más torpe pero mejora progresivamente
ai_error_chance = 0.45  # 45% de errores al inicio (más fácil)
ai_reaction_delay = 10  # Reacciona cada 10 frames (más lento)
ai_timer = 0
ai_target_y = ai.centery

# Menu específico para la pantalla de highscore (solo 1 opción: volver)
highscore_menu_selected = 0

modifier_timer = 0
MODIFIER_INTERVAL = 10 * 1000 

modifier_pickups = [] 
active_modifiers = [] 
balls = [] 

level_target_points = 3  
score_in_level = 0


# ---------------- CLASE BALL ----------------
class Ball:
    def __init__(self, direction=1, offset_y=0, x=None, y=None, vx=None, vy=None):
        # Radio base (puedes ajustar para tamaño visual)
        self.base_radius = 1.5
        self.radius = self.base_radius
        cx = WIDTH // 2 if x is None else int(x)
        # Centro del área jugable (excluyendo HUD)
        playable_center = HUD_HEIGHT + (HEIGHT - HUD_HEIGHT) // 2
        cy = playable_center + offset_y if y is None else int(y)
        self.rect = SimpleRect(int(cx - self.radius), int(cy - self.radius), int(self.radius * 2), int(self.radius * 2))

        # Posiciones en punto flotante para movimiento subpixel (necesario para gravedad)
        self.x = float(self.rect.x)
        self.y = float(self.rect.y)

        speed = random.uniform(BALL_SPEED_MIN, BALL_SPEED_MAX) if vx is None else (vx**2 + vy**2)**0.5
        angle = random.uniform(-0.6, 0.6)
        self.vx = speed * direction * math.cos(angle) if vx is None else vx
        self.vy = speed * math.sin(angle) if vy is None else vy
        
    def update(self, modifiers, slow_factor=1.0, ball_slowdown_levels=0):
        
        # 1. Aplicar Modificadores
        self.radius = self.base_radius
        for m in modifiers: m.apply_ball(self)
        centerx, centery = self.rect.centerx, self.rect.centery
        self.rect.w, self.rect.h = int(self.radius * 2), int(self.radius * 2)
        self.rect.center = (centerx, centery)

        # Sincronizar float positions con rect (tras posible cambio de tamaño)
        self.x = float(self.rect.x)
        self.y = float(self.rect.y)

        # 2. Aplicar reducción de velocidad por mejoras permanentes
        permanent_slow = 1.0 - (ball_slowdown_levels * 0.05)
        permanent_slow = max(0.5, permanent_slow)  # No más del 50% de reducción
        
        # 3. Movimiento: usar posiciones en punto flotante para que acumulen pequeñas aceleraciones
        effective_vx = self.vx * slow_factor * permanent_slow
        effective_vy = self.vy * slow_factor * permanent_slow
        
        self.x += effective_vx
        self.y += effective_vy
        self.rect.x = int(self.x)
        self.rect.y = int(self.y)

        # 4. Rebote en Paredes (Arriba/Abajo) - Respetando el margen del HUD
        gravity_active = any(isinstance(m, Gravity) for m in modifiers)

        # Techo (límite del HUD)
        if self.rect.top < HUD_HEIGHT:
            if gravity_active:
                # rebote más enérgico bajo gravedad
                self.y = float(HUD_HEIGHT)
                self.rect.y = HUD_HEIGHT
                self.vy = -self.vy * 0.75
                # asegurar rebote mínimo hacia abajo
                if abs(self.vy) < MIN_BOUNCE_V:
                    self.vy = MIN_BOUNCE_V
            else:
                self.y = float(HUD_HEIGHT)
                self.rect.y = HUD_HEIGHT
                self.vy = abs(self.vy)  # Asegurar que vaya hacia abajo

        # Suelo
        if self.rect.bottom > HEIGHT:
            if gravity_active:
                # colocar en el suelo y aplicar rebote más enérgico
                self.y = float(HEIGHT - self.rect.h)
                self.rect.y = int(self.y)
                new_vy = -abs(self.vy) * 0.8
                # asegurar rebote mínimo (no dejar la bola quieta)
                if abs(new_vy) < MIN_BOUNCE_V:
                    new_vy = -MIN_BOUNCE_V
                self.vy = new_vy
            else:
                self.rect.y = HEIGHT - self.rect.h
                self.vy *= -1

        # 4. Colisión con Paletas (Detección y Corrección)
        for m in modifiers:
            if not m.allow_paddle_collision(): 
                break 
        else:
            for paddle in (player, ai):
                # Detección de colisión robusta:
                if (self.rect.right >= paddle.left and self.rect.left <= paddle.right and
                    self.rect.bottom >= paddle.top and self.rect.top <= paddle.bottom):
                    
                    self.bounce_off_paddle(paddle)
                    
                    # Corrección de posición inmediata: Saca la bola del área de la paleta.
                    if paddle is player:
                        # Paleta Izquierda (sale a la derecha de la paleta)
                        self.rect.left = paddle.right + 1
                    else:
                        # Paleta Derecha (AI) (sale a la izquierda de la paleta)
                        self.rect.x = paddle.left - self.rect.w - 1 

    def draw(self, draw):
        # Dibujar la bola como una elipse que coincide con la hitbox
        draw.ellipse((self.rect.left, self.rect.top, self.rect.right, self.rect.bottom), outline=WHITE, fill=WHITE)

    def bounce_off_paddle(self, paddle):
        relative_y = max(-1.0, min(1.0, (self.rect.centery - paddle.centery) / (paddle.h / 2)))
        curve_power = 1.1; sign = 1 if relative_y >= 0 else -1
        progressive = sign * (abs(relative_y) ** curve_power)
        max_angle = math.radians(55)
        angle = progressive * max_angle
        speed = min(max(1.0, (self.vx ** 2 + self.vy ** 2) ** 0.5) * 1.12, 20.0)

        self.vx = abs(speed * math.cos(angle)) if paddle.centerx < WIDTH / 2 else -abs(speed * math.cos(angle))
        self.vy = speed * math.sin(angle)
        
        # NOTA: La corrección de posición se ha movido a Ball.update para evitar conflictos.

# ---------------- MODIFICADORES Y LÓGICA DE JUEGO ----------------

class Modifier:
    def __init__(self, name, symbol, duration):
        self.name, self.symbol, self.duration = name, symbol, duration
        self.start_time = int(time.time() * 1000)
    def expired(self): return (int(time.time() * 1000) - self.start_time) / 1000 >= self.duration
    def remaining(self): return max(0, int(self.duration - (int(time.time() * 1000) - self.start_time) / 1000))
    def apply_ball(self, ball): pass
    def allow_paddle_collision(self): return True
    def control_inverted(self): return False

class DoubleBall(Modifier):
    def __init__(self): super().__init__("Doble Bola", '2', 10)
class Gravity(Modifier):
    def __init__(self): super().__init__("Gravedad", 'G', 12)
    def apply_ball(self, ball):
        # Aplicar aceleración hacia abajo por frame
        ball.vy += GRAVITY_ACCEL
        # Pequeño arrastre horizontal para simular resistencia del aire
        ball.vx *= 0.997
class FastBall(Modifier):
    def __init__(self): super().__init__("Velocidad Extrema", '>', 8)
    def apply_ball(self, ball): ball.vx *= 1.01; ball.vy *= 1.01
class GhostBall(Modifier):
    def __init__(self): super().__init__("Bola Fantasma", '?', 8)
    def allow_paddle_collision(self): return random.random() > 0.4
class InvertControls(Modifier):
    def __init__(self): super().__init__("Controles Invertidos", 'I', 6)
    def control_inverted(self): return True
class BigBalls(Modifier):
    def __init__(self): super().__init__("Bolas Grandes", 'B', 15)
    def apply_ball(self, ball): ball.radius += 1 

modifier_classes = [DoubleBall, Gravity, FastBall, GhostBall, InvertControls, BigBalls]

class ModifierPickup:
    def __init__(self, mod_class):
        self.mod_class = mod_class
        self.symbol = mod_class().symbol
        margin = 10 
        # Spawn en área jugable (debajo del HUD)
        self.x = random.randint(margin, WIDTH - margin)
        self.y = random.randint(HUD_HEIGHT + margin, HEIGHT - margin)
        self.radius = 3 

    def draw(self, draw):
        draw.rectangle((self.x - self.radius, self.y - self.radius, 
                        self.x + self.radius, self.y + self.radius), outline=WHITE)
        
        # Uso de textbbox (corregido)
        bbox = draw.textbbox((0, 0), self.symbol, font=font)
        w = bbox[2] - bbox[0] # Ancho
        h = bbox[3] - bbox[1] # Alto
        
        draw.text((self.x - w // 2, self.y - h // 2), self.symbol, font=font, fill=WHITE)

    def check_collision(self, ball_rect):
        dx, dy = ball_rect.centerx - self.x, ball_rect.centery - self.y
        dist2 = dx*dx + dy*dy
        return dist2 <= (self.radius + max(ball_rect.w, ball_rect.h)//2) ** 2

def add_random_modifier():
    mod_class = random.choice(modifier_classes)
    if len(modifier_pickups) < 3:
        modifier_pickups.append(ModifierPickup(mod_class))


def reset_round(direction=1):
    global balls
    balls.clear()
    if any(isinstance(m, DoubleBall) for m in active_modifiers):
        balls.append(Ball(direction=1, offset_y=-5))
        balls.append(Ball(direction=-1, offset_y=5))
    else:
        balls.append(Ball(direction=direction, offset_y=0))

def reset_game():
    global lives, score, level, game_over, ai_speed, ai_error_chance, modifier_timer
    global ai_reaction_delay, active_modifiers, modifier_pickups, level_target_points, score_in_level
    global new_highlevel_flag, temp_upgrades, temp_upgrade_timers, paddle_speed

    lives = 3; score = 0; level = 1; game_over = False
    
    # Aplicar mejoras permanentes
    lives += permanent_upgrades.get('extra_lives', 0)
    paddle_speed = paddle_base_speed + (permanent_upgrades.get('faster_paddle', 0) * 0.5)
    
    ai_speed = ai_base_speed
    ai_error_chance = 0.45  # 45% errores inicial (más fácil)
    ai_reaction_delay = 10  # Frames entre decisiones (más lento)
    modifier_timer = int(time.time() * 1000)
    
    active_modifiers.clear()
    modifier_pickups.clear()
    
    # Resetear mejoras temporales
    temp_upgrades = {
        'shield': 0, 'slow_motion': 0, 'extra_life': 0, 'speed_boost': 0
    }
    temp_upgrade_timers.clear()
    
    level_target_points = 3  
    score_in_level = 0
    reset_round(direction=1)
    # Limpiar indicador de nuevo highlevel al reiniciar juego
    new_highlevel_flag = False

# ---------------- CATÁLOGOS DE TIENDAS ----------------
# Tienda del menú (mejoras permanentes con coins)
PERMANENT_SHOP_ITEMS = [
    {'name': 'Vida Extra', 'key': 'extra_lives', 'cost': 100, 'desc': '+1 vida inicial'},
    {'name': 'Paleta Rápida', 'key': 'faster_paddle', 'cost': 150, 'desc': '+0.5 velocidad'},
    {'name': 'Multi Puntos', 'key': 'score_multiplier', 'cost': 200, 'desc': '+10% puntos'},
    {'name': 'Slow Ball', 'key': 'ball_slowdown', 'cost': 250, 'desc': '-5% vel. bola'},
    {'name': '--- RESETEAR ---', 'key': 'reset', 'cost': 0, 'desc': 'Devuelve coins'},
    {'name': 'Volver', 'key': 'back', 'cost': 0, 'desc': ''}
]

# Tienda en partida (mejoras temporales con score)
TEMP_SHOP_ITEMS = [
    {'name': 'Escudo', 'key': 'shield', 'cost': 3, 'desc': 'Absorbe 1 muerte'},
    {'name': 'Slow-Mo', 'key': 'slow_motion', 'cost': 5, 'desc': 'Lento 10s'},
    {'name': '+1 Vida', 'key': 'extra_life', 'cost': 7, 'desc': 'Vida inmediata'},
    {'name': 'Speed Up', 'key': 'speed_boost', 'cost': 4, 'desc': '+2 vel 15s'},
    {'name': 'Volver', 'key': 'back', 'cost': 0, 'desc': ''}
]

# ---------------- FUNCIONES DE DIBUJO ----------------
def draw_on_oled(draw_function):
    # Crear imagen virtual
    virtual_img = Image.new('1', (WIDTH, HEIGHT), 0)
    virtual_draw = ImageDraw.Draw(virtual_img)
    
    # Dibujar todo el juego
    draw_function(virtual_draw)
    
    # Enviar a la pantalla principal
    with canvas(device_1) as draw:
        draw.bitmap((0, 0), virtual_img, fill=WHITE)

def game_draw(draw):
    global score, lives, level, coins, permanent_upgrades, temp_upgrades, shop_menu_selected
    global purchase_message, purchase_message_time
    
    # Mostrar mensaje de compra si existe y no ha pasado 1 segundo
    if purchase_message and time.time() - purchase_message_time < 1.0:
        # Limpiar pantalla
        draw.rectangle((0, 0, WIDTH, HEIGHT), fill=BLACK)
        # Mostrar mensaje centrado
        try:
            bbox = draw.textbbox((0, 0), purchase_message, font=font)
            w = bbox[2] - bbox[0]
            draw.text(((WIDTH - w)//2, HEIGHT//2 - 5), purchase_message, font=font, fill=WHITE)
        except Exception:
            draw.text((10, HEIGHT//2 - 5), purchase_message, font=font, fill=WHITE)
        return
    elif purchase_message and time.time() - purchase_message_time >= 1.0:
        purchase_message = ""
    
    if state == 'menu':
        # Título fijo
        title = "PONG ROUGE"
        title_x, title_y = 30, 10
        draw.text((title_x, title_y), title, font=big_font, fill=WHITE)

        # Calcular área del título para evitar solapamientos usando métricas de fuente
        try:
            ascent, descent = big_font.getmetrics()
            title_height = ascent + descent
            title_bottom = title_y + title_height
        except Exception:
            try:
                tb = draw.textbbox((title_x, title_y), title, font=big_font)
                title_bottom = tb[3]
            except Exception:
                title_bottom = title_y + 18

        # Mostrar último score si existe, justo debajo del título
        if last_score is not None:
            draw.text((30, title_bottom + 4), f"Score: {last_score}", font=font, fill=WHITE)

        # Parámetros de menú
        MENU_START_Y = title_bottom + 14
        ITEM_SPACING = 12

        # Calcular cuántos items caben en pantalla
        available_height = HEIGHT - MENU_START_Y - 5
        max_visible = int(available_height / ITEM_SPACING)
        
        # Calcular scroll offset solo cuando sea necesario
        scroll_offset = 0
        if len(menu_options) > max_visible:
            # Hacer scroll para mantener la selección visible
            if menu_selected >= max_visible:
                scroll_offset = -(menu_selected - max_visible + 1) * ITEM_SPACING

        # Dibujar las opciones aplicando el desplazamiento
        for i, opt in enumerate(menu_options):
            y = MENU_START_Y + i * ITEM_SPACING + scroll_offset
            # Solo dibujar si está en el área visible
            if y < MENU_START_Y or y > HEIGHT - 10:
                continue
            txt = f"{'>' if i == menu_selected else ' '} {opt}"
            draw.text((10, int(y)), txt, font=font, fill=WHITE)
        
    elif state == 'highscore':
        # Pantalla de nivel máximo
        # Título
        draw.text((15, 6), "NIVEL MAXIMO", font=big_font, fill=WHITE)
        # Valor central
        try:
            txt = f"Nivel {highlevel}"
            bbox = draw.textbbox((0,0), txt, font=font)
            w = bbox[2] - bbox[0]
            draw.text(((WIDTH - w)//2, 30), txt, font=font, fill=WHITE)
        except Exception:
            draw.text((30, 30), f"Nivel {highlevel}", font=font, fill=WHITE)

        # Menú simple: Volver
        for i, opt in enumerate(["Volver"]):
            txt = f"{'>' if i == highscore_menu_selected else ' '} {opt}"
            draw.text((10, HEIGHT - 14 + i * 10), txt, font=font, fill=WHITE)

    elif state == 'shop_menu':
        # Tienda del menú principal (mejoras permanentes)
        draw.text((20, 2), "TIENDA", font=big_font, fill=WHITE)
        draw.text((2, 16), f"Monedas: {coins}", font=font, fill=WHITE)
        
        y_start = 26
        item_spacing = 9
        visible_items = 4  # Número máximo de items visibles
        
        # Calcular scroll offset
        scroll_offset = -shop_menu_selected * item_spacing
        # Limitar scroll para mantener items visibles
        max_scroll = -(len(PERMANENT_SHOP_ITEMS) - visible_items) * item_spacing
        if len(PERMANENT_SHOP_ITEMS) > visible_items:
            scroll_offset = max(max_scroll, min(0, scroll_offset))
        
        for i, item in enumerate(PERMANENT_SHOP_ITEMS):
            y = y_start + i * item_spacing + scroll_offset
            # Solo dibujar si está en el área visible
            if y < y_start - item_spacing or y > HEIGHT - 10:
                continue
            
            marker = '>' if i == shop_menu_selected else ' '
            if item['key'] == 'reset' or item['key'] == 'back':
                txt = f"{marker} {item['name']}"
            else:
                upgrade_level = permanent_upgrades.get(item['key'], 0)
                txt = f"{marker} {item['name']}[{upgrade_level}]:{item['cost']}c"
            draw.text((2, int(y)), txt, font=font, fill=WHITE)

    elif state == 'shop_game':
        # Tienda durante la partida (mejoras temporales)
        draw.text((18, 2), "PAUSA - TIENDA", font=font, fill=WHITE)
        draw.text((2, 12), f"Puntos: {score}", font=font, fill=WHITE)
        
        y_start = 22
        item_spacing = 10
        visible_items = 4  # Número máximo de items visibles
        
        # Calcular scroll offset
        scroll_offset = -shop_game_selected * item_spacing
        # Limitar scroll para mantener items visibles
        max_scroll = -(len(TEMP_SHOP_ITEMS) - visible_items) * item_spacing
        if len(TEMP_SHOP_ITEMS) > visible_items:
            scroll_offset = max(max_scroll, min(0, scroll_offset))
        
        for i, item in enumerate(TEMP_SHOP_ITEMS):
            y = y_start + i * item_spacing + scroll_offset
            # Solo dibujar si está en el área visible
            if y < y_start - item_spacing or y > HEIGHT - 10:
                continue
            
            marker = '>' if i == shop_game_selected else ' '
            if item['key'] == 'back':
                txt = f"{marker} {item['name']}"
            else:
                txt = f"{marker} {item['name']}:{item['cost']}pts"
            draw.text((2, int(y)), txt, font=font, fill=WHITE)

    elif state == 'playing': 
        # Línea divisoria superior para el HUD
        HUD_HEIGHT = 11
        draw.line([(0, HUD_HEIGHT), (WIDTH, HUD_HEIGHT)], fill=WHITE)
        
        # Línea central del campo
        for i in range(HUD_HEIGHT + 2, HEIGHT, 4): 
            draw.line([(WIDTH // 2, i), (WIDTH // 2, i + 2)], fill=WHITE)
        
        draw.rectangle((player.left, player.top, player.right, player.bottom), outline=WHITE, fill=WHITE)
        draw.rectangle((ai.left, ai.top, ai.right, ai.bottom), outline=WHITE, fill=WHITE)
        for pu in modifier_pickups: pu.draw(draw)
        for ball in balls: ball.draw(draw)

        hud_text = f"P:{score} ♥:{lives} N:{level}"
        draw.text((1, 1), hud_text, font=font, fill=WHITE)
        
        # Indicador de escudo activo
        if temp_upgrades.get('shield', 0) > 0:
            draw.text((WIDTH - 15, 1), f"S:{temp_upgrades['shield']}", font=font, fill=WHITE)
        
        progress = score_in_level / level_target_points if level_target_points > 0 else 0
        max_w = WIDTH - 80
        draw_w = int(max_w * progress)
        draw.rectangle((WIDTH - max_w - 5, 1, WIDTH - 5, 2), outline=WHITE)
        draw.rectangle((WIDTH - max_w - 5, 1, WIDTH - max_w - 5 + draw_w, 2), fill=WHITE)

        y = 55
        for m in active_modifiers:
            txt = f"{m.symbol} ({m.remaining()}s)"
            draw.text((2, y), txt, font=font, fill=WHITE)
            y += 8
            if y > HEIGHT - 5: break 

        if game_over:
            draw.text((25, 20), "GAME OVER", font=big_font, fill=WHITE)
            final = f"Puntos: {last_score}"
            draw.text((35, 40), final, font=font, fill=WHITE)
            
            # Mostrar monedas ganadas
            try:
                base_c = max(1, last_score // 3) if last_score else 0
                lv_bonus = level if 'level' in dir() else 0
                coins_earned = base_c + lv_bonus
                draw.text((28, 48), f"+{coins_earned} monedas", font=font, fill=WHITE)
            except Exception:
                pass
            
            try:
                if new_highlevel_flag:
                    draw.text((15, 56), "¡Nuevo Nivel Max!", font=font, fill=WHITE)
            except Exception:
                pass


# ==============================================================================
# 4. BUCLE PRINCIPAL CON LECTURA GPIO
# ==============================================================================

reset_game() 

while True:
    now = time.time()
    dt = now - last_time
    last_time = now
    
    time.sleep(max(0, 1/FPS - dt)) 
    current_time_ms = int(now * 1000)
    
    # --- Lectura de Botones y Debounce ---
    current_time = time.time()
    menu_direction = 0
    select_pressed = False

    if current_time - last_menu_press_time > 0.2: 
        if btn_up.is_pressed:
            menu_direction = -1
            last_menu_press_time = current_time
        elif btn_down.is_pressed:
            menu_direction = 1
            last_menu_press_time = current_time
        
        if btn_select.is_pressed:
            select_pressed = True
            last_menu_press_time = current_time

    # --- Gestión de Estado ---
    if state == 'menu':
        menu_selected = (menu_selected + menu_direction) % len(menu_options)
        
        if select_pressed:
            choice = menu_options[menu_selected]
            if choice == 'Jugar':
                state = 'playing'
                reset_game()
                last_score = None
                game_paused = False
            elif choice == 'Tienda':
                state = 'shop_menu'
                shop_menu_selected = 0
                last_menu_press_time = current_time
            elif choice == 'Highscore':
                state = 'highscore'
                highscore_menu_selected = 0
                last_menu_press_time = current_time
            elif choice == 'Salir':
                sys.exit()
                
    elif state == 'shop_menu':
        # Navegación tienda del menú
        shop_menu_selected = (shop_menu_selected + menu_direction) % len(PERMANENT_SHOP_ITEMS)
        
        if select_pressed:
            item = PERMANENT_SHOP_ITEMS[shop_menu_selected]
            if item['key'] == 'back':
                state = 'menu'
                # Guardar cambios
                upgrades_data['coins'] = coins
                upgrades_data['permanent_upgrades'] = permanent_upgrades
                save_upgrades(upgrades_data)
            elif item['key'] == 'reset':
                # Resetear mejoras y devolver monedas gastadas
                coins_to_refund = 0
                for key in ['extra_lives', 'faster_paddle', 'score_multiplier', 'ball_slowdown']:
                    level_bought = permanent_upgrades.get(key, 0)
                    if level_bought > 0:
                        # Encontrar el costo del item
                        for shop_item in PERMANENT_SHOP_ITEMS:
                            if shop_item['key'] == key:
                                coins_to_refund += level_bought * shop_item['cost']
                                break
                
                coins += coins_to_refund
                permanent_upgrades = {
                    'extra_lives': 0, 'faster_paddle': 0, 'score_multiplier': 0, 'ball_slowdown': 0
                }
                
                # Guardar inmediatamente
                upgrades_data['coins'] = coins
                upgrades_data['permanent_upgrades'] = permanent_upgrades
                save_upgrades(upgrades_data)
                
                # Mostrar mensaje
                purchase_message = "Mejoras Reseteadas"
                purchase_message_time = time.time()
            else:
                # Comprar mejora
                if coins >= item['cost']:
                    coins -= item['cost']
                    permanent_upgrades[item['key']] = permanent_upgrades.get(item['key'], 0) + 1
                    
                    # Mostrar mensaje
                    purchase_message = f"Comprado: {item['name']}"
                    purchase_message_time = time.time()
                    
    elif state == 'shop_game':
        # Navegación tienda en partida
        shop_game_selected = (shop_game_selected + menu_direction) % len(TEMP_SHOP_ITEMS)
        
        if select_pressed:
            item = TEMP_SHOP_ITEMS[shop_game_selected]
            if item['key'] == 'back':
                state = 'playing'
                game_paused = False
            else:
                # Comprar mejora temporal
                if score >= item['cost']:
                    score -= item['cost']
                    temp_upgrades[item['key']] += 1
                    
                    # Aplicar efectos inmediatos
                    if item['key'] == 'extra_life':
                        lives += 1
                    elif item['key'] in ['slow_motion', 'speed_boost']:
                        temp_upgrade_timers[item['key']] = time.time()
                    
                    # Mostrar mensaje
                    purchase_message = f"Comprado: {item['name']}"
                    purchase_message_time = time.time()
                        
    elif state == 'highscore':
        # el submenú de highscore sólo tiene una opción: Volver
        highscore_menu_selected = (highscore_menu_selected + menu_direction) % 1
        if select_pressed:
            # volver al menú principal
            state = 'menu'
            last_menu_press_time = current_time
    
    # --- Lógica de Juego ---
    elif state == 'playing' and not game_over:
        
        if not game_paused:
            # 1. Input de Juego (Arriba/Abajo)
            direction = 0
            if btn_up.is_pressed: direction -= 1
            if btn_down.is_pressed: direction += 1

            inverted = any(m.control_inverted() for m in active_modifiers)
            if inverted: direction *= -1
                
            # 2. Movimiento del Jugador, AI y Bolas
            if balls:
                ball_speed = max(((b.vx ** 2 + b.vy ** 2) ** 0.5) for b in balls)
            else:
                ball_speed = 1.0 

            speed_bonus = max(0.0, ball_speed - 1.0)
            
            # Aplicar mejora de velocidad temporal si está activa
            temp_speed_bonus = 0
            if temp_upgrades.get('speed_boost', 0) > 0:
                if 'speed_boost' in temp_upgrade_timers:
                    elapsed = time.time() - temp_upgrade_timers['speed_boost']
                    if elapsed < 15:  # 15 segundos de duración
                        temp_speed_bonus = 2
                    else:
                        temp_upgrades['speed_boost'] = 0
                        del temp_upgrade_timers['speed_boost']
            
            player_effective_speed = paddle_speed + min(speed_bonus * 1.2, 15) + temp_speed_bonus
            ai_effective_speed = ai_speed + min(speed_bonus * 1.0, 12)

            player.y += direction * player_effective_speed
            player.y = max(HUD_HEIGHT, min(HEIGHT - player.h, player.y))

        ai_timer += 1
        # Seleccionar la bola más cercana a la IA
        main_ball = min(balls, key=lambda b: abs(b.rect.centerx - ai.centerx)) if balls else None

        if ai_timer >= ai_reaction_delay:
            ai_timer = 0
            if random.random() < ai_error_chance:
                # Error: apuntar a una posición aleatoria
                ai_target_y = random.randint(HUD_HEIGHT, HEIGHT)
            else:
                # IA mejorada: predecir posición futura de la bola
                if main_ball is not None:
                    # Si la bola se acerca a la IA, predecir dónde estará
                    if main_ball.vx > 0:  # Bola viene hacia la IA
                        # Calcular tiempo aproximado hasta llegar
                        distance_x = ai.centerx - main_ball.rect.centerx
                        if main_ball.vx > 0:
                            time_to_reach = distance_x / abs(main_ball.vx)
                            # Predecir posición Y futura (limitada)
                            predicted_y = main_ball.rect.centery + (main_ball.vy * time_to_reach)
                            predicted_y = max(HUD_HEIGHT, min(HEIGHT, predicted_y))
                            ai_target_y = predicted_y
                        else:
                            ai_target_y = main_ball.rect.centery
                    else:
                        # Bola se aleja, volver al centro del área jugable
                        ai_target_y = HUD_HEIGHT + (HEIGHT - HUD_HEIGHT) // 2
                else:
                    ai_target_y = ai.centery

        # Movimiento más suave de la IA
        if ai.centery < ai_target_y - 1: 
            ai.y += ai_effective_speed
        elif ai.centery > ai_target_y + 1: 
            ai.y -= ai_effective_speed
        ai.y = max(HUD_HEIGHT, min(HEIGHT - ai.h, ai.y))

        # 3. Actualización y Lógica de Ronda
        ball_to_remove = []
        should_reset_round = False
        reset_direction = 0
        
        # Calcular factor de slow motion si está activo
        slow_factor = 1.0
        if temp_upgrades.get('slow_motion', 0) > 0:
            if 'slow_motion' in temp_upgrade_timers:
                elapsed = time.time() - temp_upgrade_timers['slow_motion']
                if elapsed < 10:  # 10 segundos de duración
                    slow_factor = 0.5  # 50% velocidad
                else:
                    temp_upgrades['slow_motion'] = 0
                    del temp_upgrade_timers['slow_motion']
        
        ball_slowdown_levels = permanent_upgrades.get('ball_slowdown', 0)
        
        for ball in balls[:]:
            ball.update(active_modifiers, slow_factor, ball_slowdown_levels)
            
            # Puntuación (Pelota sale por la derecha -> Punto para el jugador)
            if ball.rect.right >= WIDTH:
                # Aplicar multiplicador de score permanente
                score_multiplier = 1.0 + (permanent_upgrades.get('score_multiplier', 0) * 0.1)
                score += int(1 * score_multiplier)
                score_in_level += 1
                should_reset_round = True
                reset_direction = -1 
                ball_to_remove.append(ball) 
            
            # Pérdida de vida (Pelota sale por la izquierda -> Punto para la IA)
            elif ball.rect.left <= 0:
                # Verificar si tiene escudo activo
                if temp_upgrades.get('shield', 0) > 0:
                    temp_upgrades['shield'] -= 1  # Consumir escudo
                    should_reset_round = True
                    reset_direction = 1
                else:
                    lives -= 1
                    should_reset_round = True
                    reset_direction = 1 
                ball_to_remove.append(ball) 
                
        # Limpiar las bolas que salieron de la pantalla
        for ball in ball_to_remove:
            if ball in balls:
                balls.remove(ball)

        # Lógica de Fin de Juego
        if lives <= 0:
            last_score = score
            # Verificar y actualizar nivel máximo alcanzado
            try:
                if level > highlevel:
                    highlevel = level
                    save_highlevel(highlevel)
                    new_highlevel_flag = True
                else:
                    new_highlevel_flag = False
                
                # Ganar monedas (mejorado: 1 moneda cada 3 puntos + bonus por nivel)
                base_coins = max(1, score // 3)
                level_bonus = level  # Bonus por nivel alcanzado
                coins_earned = base_coins + level_bonus
                coins += coins_earned
                
                # Guardar monedas
                upgrades_data['coins'] = coins
                save_upgrades(upgrades_data)
            except Exception:
                pass

            game_over = True 
            should_reset_round = False

        # Reinicio de Ronda / Nivelación
        elif should_reset_round and not balls: 
            if score_in_level >= level_target_points:
                level += 1; score_in_level = 0; level_target_points += 2
                
                # Progresión exponencial de dificultad pero con límites jugables
                # Velocidad: aumenta exponencialmente pero con tope
                ai_speed = min(ai_base_speed + (level - 1) * 0.5, ai_base_speed + 8.0)
                
                # Error: disminuye exponencialmente pero SIEMPRE mantiene 3-5% de error mínimo
                ai_error_chance = max(0.03, ai_error_chance * 0.65)
                
                # Reacción: mejora pero nunca es instantánea (mínimo 2 frames)
                ai_reaction_delay = max(2, ai_reaction_delay - 1)
                
                lives += 1
                
                # Abrir tienda automáticamente cada 2 niveles
                if level % 2 == 0:
                    state = 'shop_game'
                    game_paused = True
                    shop_game_selected = 0
                    
            reset_round(reset_direction) 
            
            
        # 4. Modificadores y Pickups
        if current_time_ms - modifier_timer >= MODIFIER_INTERVAL:
            add_random_modifier(); modifier_timer = current_time_ms

        before = len(active_modifiers)
        active_modifiers = [m for m in active_modifiers if not m.expired()]
        if before != len(active_modifiers) and not any(isinstance(m, DoubleBall) for m in active_modifiers) and not balls:
            reset_round(1) 
                
        for ball in balls[:]:
            for pu in modifier_pickups[:]:
                if pu.check_collision(ball.rect):
                    new_mod = pu.mod_class()
                    active_modifiers.append(new_mod)
                    
                    if isinstance(new_mod, DoubleBall):
                        bx, by = ball.rect.centerx, ball.rect.centery
                        speed = (ball.vx ** 2 + ball.vy ** 2) ** 0.5
                        angle = math.atan2(ball.vy, ball.vx)
                        delta = random.uniform(0.52, 1.22) * random.choice([-1, 1])
                        new_angle = angle + delta
                        nvx = speed * math.cos(new_angle)
                        nvy = speed * math.sin(new_angle)
                        balls.append(Ball(x=bx, y=by, vx=nvx, vy=nvy))
                        
                    modifier_pickups.remove(pu)
                    break 

    # Manejar transición de Game Over a Menú
    if game_over and state == 'playing':
        if current_time - last_menu_press_time > 3: 
             reset_game()
             state = 'menu'
             last_menu_press_time = current_time
        
    # ---------------- DRAW ----------------
    draw_on_oled(game_draw)
