from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
from ursina.shaders import lit_with_shadows_shader, basic_lighting_shader
import socket
import threading
import json
import time
import random
import json
import os #

app = Ursina()
GAME_NAME = 'PROJECT: ECHO'
SUBTITLE = "GLOBAL CONFLICT" 
VERSION = "0.1.2"
STATUS = 'PRE-ALPHA'
window.title = "Project: Echo - Global Conflict v.0.1.2 Pre-Alpha"
window.borderless = False
window.fullscreen = False
window.vsync = False
window.color = color.black # <--- ДОБАВИТЬ ЭТУ СТРОКУ (уберет белый фон окна)

# --- НАСТРОЙКИ СЕТИ ---
DEFAULT_IP = '26.69.138.152'
PORT = 5555

# --- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ---
game_state = "menu"
my_player = None
enemy_entity = None
score_ct = 0
score_t = 0
map_spawns_ct = []
map_spawns_t = []

# Инициализируем сокет
socket_obj = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
target_address = None
is_server = False
my_nickname = "Player"
enemy_nickname_str = "Enemy"
network_queue = [] 

settings = {
    'volume': 0.3,
    'sensitivity': 8,
}

# --- ЦВЕТА ИГРОКОВ ---
# CT - Спецназ (Темно-синий)
CT_COLOR = color.rgb(40, 60, 150)
CT_VEST_COLOR = color.rgb(20, 30, 80)

# T - Террористы (Коричневый/Хаки)
T_COLOR = color.rgb(130, 100, 60)
T_VEST_COLOR = color.rgb(80, 60, 40)

# --- КОНФИГУРАЦИЯ ОРУЖИЯ ---
weapon_config = {
    'knife':  {'dmg': 35, 'rate': 0.5, 'range': 4.0,  'clip': 0,  'reserve': 0,   'reload': 0,   'type': 'melee', 'price': 0},
    'pistol': {'dmg': 25, 'rate': 0.2, 'range': 50,   'clip': 12, 'reserve': 48,  'reload': 1.5, 'type': 'gun',   'price': 200},
    'ak47':  {'dmg': 35, 'rate': 0.1, 'range': 100,  'clip': 30, 'reserve': 90,  'reload': 2.5, 'type': 'gun',   'price': 2500},
    'awp':    {'dmg': 105,'rate': 1.5, 'range': 300,  'clip': 10, 'reserve': 30,  'reload': 3.5, 'type': 'gun',   'price': 10000}
}

# --- МОДЕЛИ ОРУЖИЯ ---
def create_gun_model(weapon_type):
    # Оружие рендерится поверх (без теней от мира)
    parent = Entity(parent=camera, scale=1.0, position=(0.7, -0.6, 1.5), rotation=(-5, -5, 0))
    
    if weapon_type == 'knife':
        gun_entity = Entity(
            parent=parent, 
            model='knife.obj',
            texture='crate',
            scale=(0.4, 0.4, 0.4),               
            rotation=(50, -185, 50),
            position=(0.18, -0.08, -1.3),
            shader=lit_with_shadows_shader 
        )

    elif weapon_type == 'pistol':
        # Вместо нагромождения Entity(model='cube'...) пишем одну строку:
        gun_entity = Entity(
            parent=parent, 
            model='Pistol.obj',      # Имя твоего файла
            texture='crate',
            color=color.dark_gray,  # Добавь эту строку, чтобы модель не была белой
            scale=(0.1, 0.1, 0.2),               # Подбери нужный размер
            rotation=(0, -183, 0),
            position=(0, 0.2, 0),
            shader=lit_with_shadows_shader # Чтобы на пушку падали тени
        )
    
    elif weapon_type == 'ak47':
        # Вместо нагромождения Entity(model='cube'...) пишем одну строку:
        gun_entity = Entity(
            parent=parent, 
            model='ak47.obj',      # Имя твоего файла
            texture='crate',
            color=color.dark_gray,  # Добавь эту строку, чтобы модель не была белой
            scale=(0.6, 0.5, 0.5),               # Подбери нужный размер
            rotation=(0, -186, 0),
            position=(-0.1, 0.3, 0),
            shader=lit_with_shadows_shader # Чтобы на пушку падали тени
        )
    
    elif weapon_type == 'awp':
        # Вместо нагромождения Entity(model='cube'...) пишем одну строку:
        gun_entity = Entity(
            parent=parent, 
            model='awp.obj',      # Имя твоего файла
            texture='crate',
            scale=(0.6, 0.5, 0.5),               # Подбери нужный размер
            rotation=(0, -270, 0),
            position=(-0.2, 0.3, 0),
            shader=lit_with_shadows_shader # Чтобы на пушку падали тени
        )

    return parent

# ================= КЛАСС ИГРОКА =================
class Player(FirstPersonController):
    def __init__(self, position=(0,1,0), team='ct'):
        super().__init__(position=position)
        self.hp = 100
        self.money = 10000
        self.base_speed = settings['sensitivity']
        self.speed = self.base_speed
        self.mouse_sensitivity = Vec2(40, 40)
        self.team = team
        self.cursor.enabled = False 
        
        self.original_height = self.camera_pivot.y
        self.crouch_height = self.original_height / 2
        self.is_crouching = False
        
        self.inventory = {
            'knife': {'clip': 0, 'reserve': 0}
        }
        self.current_weapon_name = 'knife'
        self.last_shot = 0
        self.is_reloading = False
        
        self.weapon_pivot = Entity(parent=camera.ui)
        self.switch_weapon('knife')
        
        self.crosshair = Entity(parent=camera.ui, model='quad', scale=0.003, color=color.green)

    def switch_weapon(self, name):
        if self.is_reloading: return
        self.current_weapon_name = name
        for child in self.weapon_pivot.children: destroy(child)
        self.gun_model = create_gun_model(name)
        self.gun_model.parent = self.weapon_pivot
        update_hud()

    def update(self):
        if game_state != "game": return
        super().update()
        
        # === МЕХАНИКА ПЕРЕДВИЖЕНИЯ И ПРИСЕДАНИЯ ===
        if held_keys['control'] or held_keys['left control']:
            # Приседаем
            self.speed = 2.5
            # Плавное опускание камеры
            self.camera_pivot.y = lerp(self.camera_pivot.y, self.crouch_height, time.dt * 10)
        else:
            # Встаем
            # Плавный подъем камеры
            self.camera_pivot.y = lerp(self.camera_pivot.y, self.original_height, time.dt * 10)
            
            if held_keys['shift'] or held_keys['left shift']:
                self.speed = 4 # Ходьба (тихо)
            else:
                self.speed = 7 # Бег

    def input(self, key):
        if game_state != "game": return
        super().input(key)
        
        if key == 'left mouse down':
            if not self.is_reloading:
                self.try_shoot()
        
        if key == 'r': self.reload()
        if key == '1' and 'ak47' in self.inventory: self.switch_weapon('ak47')
        if key == '1' and 'awp' in self.inventory: self.switch_weapon('awp')
        if key == '2' and 'pistol' in self.inventory: self.switch_weapon('pistol')
        if key == '3': self.switch_weapon('knife')
        if key == 'b': toggle_buy_menu()
        if key == 'escape': toggle_pause_menu()

    def try_shoot(self):
        if time.time() - self.last_shot < weapon_config[self.current_weapon_name]['rate']:
            return

        conf = weapon_config[self.current_weapon_name]
        
        if conf['type'] == 'gun':
            current_ammo = self.inventory[self.current_weapon_name]['clip']
            if current_ammo <= 0:
                self.reload()
                return
            self.inventory[self.current_weapon_name]['clip'] -= 1
            update_hud()

        self.last_shot = time.time()
        self.shoot_anim(conf['type'])
        
        # === ИЗМЕНЕННАЯ ЛОГИКА ЗВУКОВ ===
        vol = settings['volume']
        w_name = self.current_weapon_name
        
        if w_name == 'knife':
             Audio('ursina/assets/sounds/swing.wav', volume=vol, pitch=random.uniform(0.8,1.2), loop=False)
        elif w_name == 'pistol':
             # Воспроизводим pistol.mp3
             Audio('pistol.mp3', volume=vol, pitch=random.uniform(0.95,1.05), loop=False)
        elif w_name == 'ak47':
             # Воспроизводим ak47.mp3
             Audio('ak47.mp3', volume=vol, pitch=random.uniform(0.95,1.05), loop=False)
        elif w_name == 'awp':
             # Воспроизводим awp.mp3
             Audio('awp.mp3', volume=vol, pitch=1.0, loop=False)
        else:
             # На всякий случай дефолтный звук, если добавится новое оружие без звука
             Audio('ursina/assets/sounds/shoot.wav', volume=vol, pitch=random.uniform(0.9,1.1), loop=False)

        hit_info = raycast(camera.world_position, camera.forward, distance=conf['range'], ignore=[self])
        
        if hit_info.hit:
            if conf['type'] == 'gun':
                BulletTrail(camera.world_position + camera.forward*0.5 + camera.right*0.2, hit_info.world_point)
            
            if hit_info.entity in enemy_parts:
                print(f"Hit enemy! -{conf['dmg']}")
                send_data({'type': 'hit', 'dmg': conf['dmg']})
                crosshair_hit()

    def shoot_anim(self, w_type):
        if w_type == 'melee':
            self.gun_model.animate_position(Vec3(0.5, -0.4, 0.8), duration=0.05, curve=curve.linear)
            self.gun_model.animate_rotation(Vec3(10, -5, 0), duration=0.05)
            invoke(self.reset_anim, delay=0.15)
        else:
            self.gun_model.animate_position(self.gun_model.position - Vec3(0, 0, 0.2), duration=0.05)
            self.gun_model.animate_rotation(self.gun_model.rotation + Vec3(-5, 0, 0), duration=0.05)
            invoke(self.reset_anim, delay=0.06)

    def reset_anim(self):
        if self.current_weapon_name == 'knife':
             self.gun_model.animate_position((0.5, -0.4), duration=0.2, curve=curve.out_sine)
             self.gun_model.animate_rotation((0, -5, 0), duration=0.2)
        else:
             self.gun_model.animate_position((0.7, -0.6), duration=0.1)
             self.gun_model.animate_rotation((-5, -5, 0), duration=0.1)

    def reload(self):
        name = self.current_weapon_name
        conf = weapon_config[name]
        
        if conf['type'] == 'melee' or self.is_reloading: return
        
        current_clip = self.inventory[name]['clip']
        reserve = self.inventory[name]['reserve']
        if current_clip >= conf['clip'] or reserve <= 0: return

        self.is_reloading = True
        
        # --- ЭТАП 1: Опускаем оружие и чуть поворачиваем (0.0 - 0.3 сек) ---
        # Используем curve.in_expo для резкого начала ухода
        self.gun_model.animate_position((0.4, -0.6, -1.0), duration=0.3, curve=curve.in_expo)
        self.gun_model.animate_rotation((40, -20, 15), duration=0.3)

        # --- ЭТАП 2: Имитируем вставку магазина (через delay) ---
        # Небольшой "толчок" вверх через некоторое время
        invoke(self.gun_model.animate_position, (0.4, -0.55, -1.0), duration=0.1, delay=conf['reload'] * 0.4)
        invoke(self.gun_model.animate_position, (0.4, -0.6, -1.0), duration=0.1, delay=conf['reload'] * 0.5)

        # --- ЭТАП 3: Возврат и рывок затвора (перед самым концом) ---
        # Возвращаем в исходную позицию (допустим, это 0.18, -0.08, -1.3)
        return_delay = conf['reload'] - 0.3
        invoke(self.gun_model.animate_position, (0.18, -0.08, -1.3), duration=0.2, delay=return_delay)
        invoke(self.gun_model.animate_rotation, (50, -185, 50), duration=0.2, delay=return_delay)

        # Завершаем логику
        invoke(self.finish_reload, delay=conf['reload'])

    def finish_reload(self):
        name = self.current_weapon_name
        conf = weapon_config[name]
        needed = conf['clip'] - self.inventory[name]['clip']
        amount = min(needed, self.inventory[name]['reserve'])
        
        self.inventory[name]['clip'] += amount
        self.inventory[name]['reserve'] -= amount
        self.is_reloading = False
        self.reset_anim()
        update_hud()

    def take_damage(self, amount):
        self.hp -= amount
        update_hud()
        damage_vignette.alpha = 150
        damage_vignette.animate('alpha', 0, duration=1)
        if self.hp <= 0: die()

class BulletTrail(Entity):
    def __init__(self, start, end):
        dist = distance(start, end)
        super().__init__(model='cube', color=color.rgba(255, 200, 0, 150), scale=(0.02, 0.02, dist), position=lerp(start, end, 0.5), shader=None)
        self.look_at(end)
        destroy(self, delay=0.05)

enemy_parts = []

class EnemyModel(Entity):
    def __init__(self, pos=(0, -50, 0)):
        super().__init__(position=pos)
        
        # Определение цвета врага
        # Если я Сервер (CT), то враг T. Если я Клиент (T), то враг CT.
        if is_server: 
            # Враг - Террорист
            skin_color = T_COLOR
            vest_color = T_VEST_COLOR
        else:
            # Враг - CT
            skin_color = CT_COLOR
            vest_color = CT_VEST_COLOR
        
        # Ноги (две отдельные)
        self.leg_l = Entity(parent=self, model='cube', color=skin_color, scale=(0.25, 0.9, 0.25), position=(-0.2, 0.45, 0), shader=lit_with_shadows_shader)
        self.leg_r = Entity(parent=self, model='cube', color=skin_color, scale=(0.25, 0.9, 0.25), position=(0.2, 0.45, 0), shader=lit_with_shadows_shader)
        
        # Туловище
        self.body = Entity(parent=self, model='cube', color=vest_color, scale=(0.6, 0.8, 0.35), position=(0, 1.3, 0), collider='box', shader=lit_with_shadows_shader)
        enemy_parts.append(self.body)
        
        # Голова
        self.head = Entity(parent=self, model='cube', color=color.rgb(255, 200, 150), scale=(0.3, 0.35, 0.3), position=(0, 1.9, 0), collider='box', shader=lit_with_shadows_shader)
        enemy_parts.append(self.head)
        
        # Руки
        self.arm_l = Entity(parent=self.body, model='cube', color=skin_color, scale=(0.25, 1.0, 0.25), position=(-0.65, 0.1, 0), shader=lit_with_shadows_shader)
        self.arm_r = Entity(parent=self.body, model='cube', color=skin_color, scale=(0.25, 1.0, 0.25), position=(0.65, 0.1, 0), shader=lit_with_shadows_shader)
        
        self.name_tag = Text(text=enemy_nickname_str, parent=self, y=2.3, billboard=True, scale=5, color=color.white, background=True)

# ================= UI & HUD (ОБНОВЛЕННЫЙ) =================
hud_parent = None
hud_hp_txt = None
hud_ammo_txt = None
hud_money_txt = None
hud_score_txt = None 
damage_vignette = None
crosshair_marker = None

def create_ui():
    global hud_parent, hud_hp_txt, hud_ammo_txt, hud_money_txt, damage_vignette, crosshair_marker, hud_score_txt
    
    hud_parent = Entity(parent=camera.ui)
    damage_vignette = Entity(parent=camera.ui, model='quad', scale=2, color=color.red, alpha=0)
    crosshair_marker = Text(text='X', scale=2, color=color.red, enabled=False, origin=(0,0))
    
    # --- СЧЕТ (СВЕРХУ) ---
    hud_score_txt = Text(parent=hud_parent, text="CT: 0 | T: 0", origin=(0,0), position=(0, 0.45), scale=2, color=color.white)
    hud_score_txt.create_background(padding=0.1, radius=0.1, color=color.rgba(0,0,0,100))

    # --- ЗДОРОВЬЕ (СНИЗУ СЛЕВА) ---
    hud_hp_txt = Text(parent=hud_parent, text="+ 100", position=(-0.85, -0.45), scale=3, color=color.red)

    # --- БОЕЗАПАС (СНИЗУ СПРАВА) ---
    hud_ammo_txt = Text(parent=hud_parent, text="30 / 90", position=(0.65, -0.45), scale=3, color=color.yellow)

    # --- ДЕНЬГИ (СЛЕВА ЧУТЬ ВЫШЕ) ---
    hud_money_txt = Text(parent=hud_parent, text="$ 0", position=(-0.85, -0.38), scale=2, color=color.green)


def update_hud():
    if not my_player: return
    hud_hp_txt.text = f"+ {my_player.hp}"
    hud_money_txt.text = f"$ {my_player.money}"
    w_name = my_player.current_weapon_name
    if weapon_config[w_name]['type'] == 'melee':
        hud_ammo_txt.text = "---"
    else:
        c = my_player.inventory[w_name]['clip']
        r = my_player.inventory[w_name]['reserve']
        hud_ammo_txt.text = f"{c} / {r}"

def update_score_ui():
    global hud_score_txt
    if hud_score_txt:
        hud_score_txt.text = f"CT: {score_ct} | T: {score_t}"

def crosshair_hit():
    crosshair_marker.enabled = True
    invoke(setattr, crosshair_marker, 'enabled', False, delay=0.1)

# --- МЕНЮ ПОКУПКИ (БЕЛЫЙ СТИЛЬ) ---
buy_menu_panel = None

def toggle_buy_menu():
    global buy_menu_panel
    if game_state != "game": return
    
    if not buy_menu_panel:
        buy_menu_panel = Entity(parent=camera.ui, enabled=False)
        
        # 1. ФОН ПАНЕЛИ
        # ВАЖНО: z=1 отодвигает фон назад, чтобы он не перекрывал кнопки
        Entity(parent=buy_menu_panel, model='quad', scale=(0.9, 0.9), 
               color=color.rgb(30, 30, 30), z=1)
        
        # Заголовок
        Text(text="WEAPON SHOP", parent=buy_menu_panel, y=0.38, x=0, 
             origin=(0,0), scale=2, color=color.black, z=-1)
        
        y_pos = 0.25
        for name, stats in weapon_config.items():
            # Убрали проверку цены, чтобы отображались все (включая нож)
            
            price_text = f"${stats['price']}" if stats['price'] > 0 else "FREE"
            
            # 2. КНОПКИ ОРУЖИЯ
            # highlight_color делает кнопку светлее при наведении
            # z=-1 гарантирует, что кнопка будет ПОВЕРХ фона
            btn = Button(parent=buy_menu_panel, 
                         text=f"{name.upper()}  [{price_text}]", 
                         scale=(0.6, 0.08), 
                         y=y_pos, 
                         color=color.black,
                         text_color=color.white,
                         highlight_color=color.dark_gray,
                         z=-1) 
            
            btn.on_click = Func(buy_weapon, name, stats['price'])
            y_pos -= 0.12 
            
        # 3. КНОПКА ЗАКРЫТЬ
        Button(parent=buy_menu_panel, text="CLOSE MENU", scale=(0.3, 0.08), y=-0.35, 
               color=color.red, text_color=color.black, highlight_color=color.pink, z=-1,
               on_click=toggle_buy_menu)

    buy_menu_panel.enabled = not buy_menu_panel.enabled
    
    # Блокируем камеру и включаем курсор
    mouse.locked = not buy_menu_panel.enabled
    my_player.enabled = not buy_menu_panel.enabled

def buy_weapon(name, cost):
    if my_player.money >= cost:
        my_player.money -= cost
        if name in my_player.inventory:
             my_player.inventory[name]['reserve'] = weapon_config[name]['reserve']
        else:
             my_player.inventory[name] = {'clip': weapon_config[name]['clip'], 'reserve': weapon_config[name]['reserve']}
        my_player.switch_weapon(name)
        update_hud()
        Audio('ursina/assets/sounds/coin.wav', volume=settings['volume'], loop=False)

def die():
    global game_state, score_ct, score_t
    game_state = "dead"
    send_data({'type': 'kill_confirm'})
    
    if my_player.team == 'ct':
        score_t += 1
    else:
        score_ct += 1
    update_score_ui()

    my_player.position = (0, 50, 0)
    my_player.cursor.enabled = False
    msg = Text(text='YOU DIED', scale=4, origin=(0,0), color=color.red)
    destroy(msg, delay=3)
    invoke(respawn, delay=3)

def respawn():
    global game_state
    
    # ИСПОЛЬЗУЕМ НОВУЮ ФУНКЦИЮ
    spawn_pos = get_spawn_point(my_player.team)
    
    my_player.position = spawn_pos
    my_player.hp = 100
    if 'pistol' not in my_player.inventory:
        my_player.inventory['pistol'] = {'clip': 12, 'reserve': 24}
    my_player.switch_weapon('knife')
    game_state = "game"
    my_player.cursor.enabled = True
    update_hud()

# ================= МЕНЮ (БЕЛЫЙ СТИЛЬ) =================
menu_ui = None
settings_ui = None
nick_input = None
ip_input = None

def create_main_menu():
    global menu_ui, nick_input, ip_input
    menu_ui = Entity(parent=camera.ui)
    
    # Фон меню (Черный, чтобы перекрыть все белое)
    Entity(parent=menu_ui, model='quad', scale=(15, 10), color=color.black)
    
    # Название игры
    Text(parent=menu_ui, text=GAME_NAME, origin=(0,0), y=0.38, scale=5, color=color.white)
    Text(parent=menu_ui, text=SUBTITLE, origin=(0,0), y=0.31, scale=2, color=color.light_gray)
    Text(parent=menu_ui, text=f'{STATUS} v.{VERSION}', position=(0.6, -0.45), scale=1.2, color=color.gray)

    # --- ПОЛЯ ВВОДА ---
    Text(parent=menu_ui, text='NICKNAME', position=(-0.25, 0.05), scale=1.5, color=color.white)
    nick_input = InputField(parent=menu_ui, default_value='Player1', y=0.0, 
                            scale=(0.4, 0.05), color=color.dark_gray, text_color=color.white)
    
    Text(parent=menu_ui, text='SERVER IP', position=(-0.25, -0.1), scale=1.5, color=color.white)
    ip_input = InputField(parent=menu_ui, default_value=DEFAULT_IP, y=-0.15, 
                          scale=(0.4, 0.05), color=color.dark_gray, text_color=color.white)

    # --- КНОПКИ (ИСПРАВЛЕННЫЕ) ---
    # Кнопка HOST (Синяя)
    b_host = Button(parent=menu_ui, text='HOST GAME', y=-0.3, x=-0.2, 
                    scale=(0.3, 0.08), 
                    color=color.blue,           # <--- СИНИЙ ЦВЕТ
                    text_color=color.white,     # Белый текст
                    highlight_color=color.cyan) # При наведении светлее
    b_host.on_click = on_host
    
    # Кнопка JOIN (Зеленая)
    b_join = Button(parent=menu_ui, text='JOIN GAME', y=-0.3, x=0.2, 
                    scale=(0.3, 0.08), 
                    color=color.green,          # <--- ЗЕЛЕНЫЙ ЦВЕТ
                    text_color=color.white,     # Белый текст
                    highlight_color=color.lime) # При наведении светлее
    b_join.on_click = on_connect

def on_host():
    start_game('server', '0.0.0.0', nick_input.text)
def on_connect():
    start_game('client', ip_input.text, nick_input.text)

# ================= КАРТА И ОСВЕЩЕНИЕ =================
def create_map():
    global map_spawns_ct, map_spawns_t
    
    # 1. ОСВЕЩЕНИЕ И ОКРУЖЕНИЕ
    sun = DirectionalLight(shadows=True)
    sun.look_at(Vec3(1, -1, -0.5)) 
    sun.shadow_map_resolution = Vec2(4096, 4096) 
    AmbientLight(color=color.rgb(30, 30, 35))
    Sky(color=color.rgb(50, 50, 70))
    
    # Пол (чтобы не падать, если карта пустая)
    Entity(model='plane', scale=200, texture='floor', 
           texture_scale=(40,40), collider='box', 
           shader=lit_with_shadows_shader, position=(0,0,0)) 

    # 2. ЗАГРУЗКА ИЗ JSON
    if os.path.exists('level_data.json'):
        print("Загрузка карты из JSON...")
        with open('level_data.json', 'r') as f:
            data = json.load(f)
            
            blocks_to_load = []

            # Проверка формата (Новый словарь или Старый список)
            if isinstance(data, dict):
                # НОВЫЙ ФОРМАТ РЕДАКТОРА
                blocks_to_load = data.get('blocks', [])
                map_spawns_ct[:] = data.get('spawns_ct', []) # Копируем список
                map_spawns_t[:] = data.get('spawns_t', [])   # Копируем список
            elif isinstance(data, list):
                # СТАРЫЙ ФОРМАТ (только блоки)
                blocks_to_load = data
            
            # Создаем блоки
            for block in blocks_to_load:
                Entity(
                    model='cube',
                    position=block['pos'],
                    scale=block.get('scale', (1,1,1)), # Учитываем масштаб из редактора
                    texture=block['tex'],
                    collider='box',
                    shader=lit_with_shadows_shader
                )
    else:
        print("Файл карты не найден, загружаю дефолтную...")
        create_default_map()

def create_default_map():
    # Твой старый код создания стен, если файла нет
    # 1. ОСВЕЩЕНИЕ
    # Поворачиваем солнце, чтобы тени были длиннее и виднее
    sun = DirectionalLight(shadows=True)
    sun.look_at(Vec3(1, -1, -0.5)) 
    sun.shadow_map_resolution = Vec2(4096, 4096) 
    
    # Уменьшаем AmbientLight
    AmbientLight(color=color.rgb(30, 30, 35))

    # 2. Земля
    Entity(model='plane', scale=200, texture='floor', 
           texture_scale=(40,40), collider='box', 
           shader=lit_with_shadows_shader) 
    
    # Более темное небо для контраста
    Sky(color=color.rgb(50, 50, 70))
    
    walls = [
        {'pos': (0, 5, 60), 'scale': (120, 10, 2)},
        {'pos': (0, 5, -60), 'scale': (120, 10, 2)},
        {'pos': (60, 5, 0), 'scale': (2, 10, 120)},
        {'pos': (-60, 5, 0), 'scale': (2, 10, 120)},
        {'pos': (0, 5, 0), 'scale': (2, 10, 40)},
        {'pos': (30, 5, 20), 'scale': (40, 10, 2)},
        {'pos': (30, 5, -20), 'scale': (40, 10, 2)},
    ]
    
def get_spawn_point(team):
        # Если команда CT и есть точки спавна для CT
    if team == 'ct' and map_spawns_ct:
        return random.choice(map_spawns_ct)
        
    # Если команда T и есть точки спавна для T
    elif team == 't' and map_spawns_t:
        return random.choice(map_spawns_t)
            
    # ДЕФОЛТНЫЕ ТОЧКИ (если в карте не расставили спавны)
    return (-40, 2, 0) if team == 'ct' else (40, 2, 0)
    
    for w in walls:
        Entity(model='cube', position=w['pos'], scale=w['scale'], 
               texture='brick', texture_scale=(w['scale'][0]/2, w['scale'][1]/2), 
               collider='box', shader=lit_with_shadows_shader)

    boxes = [(10, 1, 10), (10, 2, 12), (35, 1, -15), (-30, 1, 5), (-40, 1, -20), (5, 1, 40), (45, 1, 40)]
    for b in boxes:
        Entity(model='cube', position=b, scale=2, texture='crate', 
               collider='box', shader=lit_with_shadows_shader)

# ================= ИГРОВОЙ ЦИКЛ =================
def start_game(mode, ip_addr, nick):
    global my_player, game_state, enemy_entity, is_server, my_nickname, target_address
    
    my_nickname = nick
    menu_ui.enabled = False
    game_state = "game"
    is_server = (mode == 'server')
    
    create_map() # Сначала грузим карту, чтобы заполнились списки спавнов!
    create_ui()
    update_score_ui()
    
    # Определяем команду
    team = 'ct' if is_server else 't'
    
    # ИСПОЛЬЗУЕМ НОВУЮ ФУНКЦИЮ
    start_pos = get_spawn_point(team)
    
    my_player = Player(position=start_pos, team=team)
    
    enemy_entity = EnemyModel(pos=(0, -50, 0))
    
    if mode == 'server':
        try:
            socket_obj.bind(('0.0.0.0', PORT))
        except:
            print("Port busy or error")
    else:
        target_address = (ip_addr, PORT)
        
    threading.Thread(target=network_listener, args=(mode,), daemon=True).start()

def send_data(data_dict):
    global socket_obj, target_address
    if not socket_obj: return
    try:
        msg = json.dumps(data_dict).encode()
        if target_address:
            socket_obj.sendto(msg, target_address)
    except Exception as e:
        print(f"Send error: {e}")

def network_listener(mode):
    global socket_obj, target_address, score_ct, score_t
    while True:
        try:
            data, addr = socket_obj.recvfrom(2048)
            if mode == 'server' and target_address is None: 
                target_address = addr
            
            if target_address and addr != target_address: 
                continue
                
            network_queue.append(json.loads(data.decode()))
        except:
            pass

def update():
    global score_ct, score_t
    
    if my_player and game_state == "game":
        if held_keys['w'] or held_keys['a'] or held_keys['s'] or held_keys['d'] or mouse.velocity != Vec3(0,0,0):
             pos_data = {
                'type': 'move', 
                'x': round(my_player.x, 2), 'y': round(my_player.y, 2), 'z': round(my_player.z, 2), 
                'ry': round(my_player.rotation_y, 2),
                'name': my_nickname
            }
             send_data(pos_data)

    while len(network_queue) > 0:
        msg = network_queue.pop(0)
        m_type = msg.get('type')
        
        if m_type == 'move':
            if enemy_entity:
                enemy_entity.animate_position((msg['x'], msg['y'], msg['z']), duration=0.1)
                enemy_entity.rotation_y = msg['ry']
                if enemy_entity.name_tag.text != msg.get('name'):
                    enemy_entity.name_tag.text = msg.get('name')
        elif m_type == 'hit':
            my_player.take_damage(msg.get('dmg', 0))
        elif m_type == 'kill_confirm':
            my_player.money += 300
            if my_player.team == 'ct':
                score_ct += 1
            else:
                score_t += 1
            update_score_ui()
            
            update_hud()
            Audio('ursina/assets/sounds/coin.wav', volume=settings['volume'])

create_main_menu()
app.run()
