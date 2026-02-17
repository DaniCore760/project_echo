from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
from ursina.shaders import lit_with_shadows_shader
import socket
import threading
import json
import time
import random
import os
import hashlib

app = Ursina()
GAME_NAME = 'PROJECT: ECHO'
SUBTITLE = "GLOBAL CONFLICT" 
VERSION = "2.0.0"
STATUS = 'PRE-ALPHA'
window.title = f"Project: Echo - Global Conflict v.{VERSION} {STATUS}"
window.borderless = False
window.fullscreen = False
window.vsync = False
window.color = color.black

# --- НАСТРОЙКИ СЕТИ ---
DEFAULT_IP = '26.69.138.152'
PORT = 5555

# --- СЕТЕВЫЕ ТИКИ ---
tick_rate = 1 / 15
last_send_time = 0

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
    'volume': 0.4,
    'sensitivity': 8,
}

# --- ЦВЕТА ИГРОКОВ ---
CT_COLOR = color.rgb(40, 60, 150)       # Синий
CT_VEST_COLOR = color.rgb(20, 30, 80)
T_COLOR = color.rgb(130, 100, 60)       # Коричневый
T_VEST_COLOR = color.rgb(80, 60, 40)

# --- КОНФИГУРАЦИЯ ОРУЖИЯ (ОБНОВЛЕННАЯ) ---
weapon_config = {
    'knife':  {
        'dmg': 35, 'rate': 0.5, 'range': 4.0,  
        'clip': 0, 'reserve': 0, 'reload': 0,   
        'type': 'melee', 'price': 0
    },
    'pistol': {
        'dmg': 25, 'rate': 0.2, 'range': 50,   
        'clip': 7, 'reserve': 28, 'reload': 1.5, # <--- 7/28, 1.5s
        'type': 'gun',   'price': 200
    },
    'ak47':  {
        'dmg': 35, 'rate': 0.1, 'range': 100,  
        'clip': 30, 'reserve': 90, 'reload': 2.4, # <--- 30/90, 2.4s
        'type': 'gun',   'price': 2500
    },
    'awp':    {
        'dmg': 105,'rate': 1.5, 'range': 300,  
        'clip': 3, 'reserve': 12, 'reload': 4.2,  # <--- 3/12, 4.2s
        'type': 'gun',   'price': 10000
    }
}

# --- МОДЕЛИ ОРУЖИЯ ---
def create_gun_model(weapon_type):
    # Родительский объект для оружия (привязан к камере)
    parent = Entity(parent=camera, scale=1.0, position=(0.7, -0.6, 1.5), rotation=(-5, -5, 0))
    
    if weapon_type == 'knife':
        gun_entity = Entity(
            parent=parent, 
            model='knife.obj',
            texture='crate',
            scale=(0.4, 0.4, 0.4),               
            # ИСПРАВЛЕНА ПОЗИЦИЯ - теперь нож виден сразу
            position=(0.3, -0.1, 0.8), 
            rotation=(-10, -40, -10),
            shader=lit_with_shadows_shader 
        )

    elif weapon_type == 'pistol':
        gun_entity = Entity(
            parent=parent, 
            model='Pistol.obj',
            texture='crate',
            color=color.dark_gray,
            scale=(0.1, 0.1, 0.2),
            rotation=(0, -183, 0),
            position=(0, 0.2, 0),
            shader=lit_with_shadows_shader
        )
    
    elif weapon_type == 'ak47':
        gun_entity = Entity(
            parent=parent, 
            model='ak47.obj',
            texture='crate',
            color=color.dark_gray,
            scale=(0.6, 0.5, 0.5),
            rotation=(0, -186, 0),
            position=(-0.1, 0.3, 0),
            shader=lit_with_shadows_shader
        )
    
    elif weapon_type == 'awp':
        gun_entity = Entity(
            parent=parent, 
            model='awp.obj',
            texture='crate',
            scale=(0.6, 0.5, 0.5),
            rotation=(0, -270, 0),
            position=(-0.2, 0.3, 0),
            shader=lit_with_shadows_shader
        )

    return parent
    
def get_map_hash(filename='level_data.json'):
    if not os.path.exists(filename):
        return "none" 
    with open(filename, "rb") as f:
        bytes = f.read()
        return hashlib.md5(bytes).hexdigest()

# ================= КЛАСС ИГРОКА =================
class Player(FirstPersonController):
    def __init__(self, position=(0,1,0), team='ct'):
        super().__init__(position=position)
        self.hp = 100
        self.money = 0 # Стартовые деньги (как в CS)
        self.base_speed = settings['sensitivity']
        self.speed = self.base_speed
        self.mouse_sensitivity = Vec2(40, 40)
        self.team = team
        self.cursor.enabled = False 
        
        self.original_height = self.camera_pivot.y
        self.crouch_height = self.original_height / 2
        self.is_crouching = False
        
        # Инвентарь: только нож на старте
        self.inventory = {
            'knife': {'clip': 0, 'reserve': 0}
        }
        self.current_weapon_name = 'knife'
        self.last_shot = 0
        self.is_reloading = False
        
        self.is_dead = False
        
        self.weapon_pivot = Entity(parent=camera.ui)
        self.switch_weapon('knife')
        
        self.crosshair = Entity(parent=camera.ui, model='quad', scale=0.004, color=color.red)

    def switch_weapon(self, name):
        if self.is_reloading or self.is_dead: return
        self.current_weapon_name = name
        for child in self.weapon_pivot.children: destroy(child)
        self.gun_model = create_gun_model(name)
        self.gun_model.parent = self.weapon_pivot
        
        if name == 'knife':
             self.gun_model.position = (0.5, -0.4)
             self.gun_model.rotation = (0, -5, 0)
        update_hud()

    def update(self):
        if game_state != "game" or self.is_dead: return
        super().update()
        
        if held_keys['left mouse'] and self.current_weapon_name == 'ak47':
            if not self.is_reloading:
                self.try_shoot()
        
        # === МЕХАНИКА ПЕРЕДВИЖЕНИЯ ===
        if self.is_reloading:
            # При перезарядке скорость сильно падает
            self.speed = 3.0
            # Если пытаемся присесть во время перезарядки - еще медленнее
            if held_keys['control'] or held_keys['left control']:
                 self.camera_pivot.y = lerp(self.camera_pivot.y, self.crouch_height, time.dt * 10)
                 self.speed = 1.5
            else:
                 self.camera_pivot.y = lerp(self.camera_pivot.y, self.original_height, time.dt * 10)

        elif held_keys['control'] or held_keys['left control']:
            # Приседаем
            self.speed = 2.5
            self.camera_pivot.y = lerp(self.camera_pivot.y, self.crouch_height, time.dt * 10)
        else:
            # Встаем
            self.camera_pivot.y = lerp(self.camera_pivot.y, self.original_height, time.dt * 10)
            
            if held_keys['shift'] or held_keys['left shift']:
                self.speed = 4 # Ходьба (тихо)
            else:
                self.speed = 7 # Бег

    def input(self, key):
        if game_state != "game" or self.is_dead: return
        super().input(key)
        
        if key == 'left mouse down':
            # Стреляем одиночными только если это НЕ калаш (он теперь в update)
            if self.current_weapon_name != 'ak47':
                if not self.is_reloading:
                    self.try_shoot()
        
        if key == 'r': self.reload()
        
        # --- НОВАЯ СИСТЕМА СЛОТОВ ---
        if key == '1': self.switch_weapon('knife')
        if key == '2' and 'pistol' in self.inventory: self.switch_weapon('pistol')
        if key == '3' and 'ak47' in self.inventory: self.switch_weapon('ak47')
        if key == '4' and 'awp' in self.inventory: self.switch_weapon('awp')
        
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
        
        vol = settings['volume']
        w_name = self.current_weapon_name
        
        if w_name == 'knife':
             Audio('knife_slash.mp3', volume=vol, pitch=random.uniform(0.8,1.2), loop=False)
        elif w_name == 'pistol':
             Audio('pistol.mp3', volume=vol, pitch=random.uniform(0.95,1.05), loop=False)
        elif w_name == 'ak47':
             Audio('ak47.mp3', volume=vol, pitch=random.uniform(0.95,1.05), loop=False)
        elif w_name == 'awp':
             Audio('awp.mp3', volume=vol, pitch=1.0, loop=False)
        else:
             Audio('ursina/assets/sounds/shoot.wav', volume=vol, pitch=random.uniform(0.9,1.1), loop=False)

        hit_info = raycast(camera.world_position, camera.forward, distance=conf['range'], ignore=[self])
        
        if hit_info.hit:
            if conf['type'] == 'gun':
                BulletTrail(camera.world_position + camera.forward*0.5 + camera.right*0.2, hit_info.world_point)
            
            if hit_info.entity in enemy_parts:
                send_data({'type': 'hit', 'dmg': conf['dmg']})
                crosshair_hit()

    def shoot_anim(self, w_type):
        if w_type == 'melee':
            # Анимация удара ножом
            self.gun_model.animate_position(Vec3(0.5, -0.4, 1.5), duration=0.1, curve=curve.linear)
            self.gun_model.animate_rotation(Vec3(20, -20, 0), duration=0.1)
            invoke(self.reset_anim, delay=0.2)
        else:
            # Отдача оружия
            self.gun_model.animate_position(self.gun_model.position - Vec3(0, 0, 0.2), duration=0.05)
            self.gun_model.animate_rotation(self.gun_model.rotation + Vec3(-5, 0, 0), duration=0.05)
            invoke(self.reset_anim, delay=0.06)

    def reset_anim(self):
        if self.is_reloading: return # Если идет перезарядка, не сбрасываем анимацию в дефолт
        
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
        duration = conf['reload'] # 1.5, 2.4, или 4.2
        
        # --- АНИМАЦИЯ ПЕРЕЗАРЯДКИ ---
        # 1. Опускаем оружие
        self.gun_model.animate_position((0.4, -0.8, -0.5), duration=duration*0.3, curve=curve.in_expo)
        self.gun_model.animate_rotation((60, -30, 30), duration=duration*0.3)

        # 2. Имитация смены магазина (тряска)
        invoke(self.gun_model.animate_rotation, (65, -35, 30), duration=0.1, delay=duration*0.5)
        invoke(self.gun_model.animate_rotation, (60, -30, 30), duration=0.1, delay=duration*0.6)

        # 3. Возврат оружия
        return_time = duration * 0.8
        invoke(self.gun_model.animate_position, (0.7, -0.6), duration=duration*0.2, delay=return_time)
        invoke(self.gun_model.animate_rotation, (-5, -5, 0), duration=duration*0.2, delay=return_time)

        # Завершение
        invoke(self.finish_reload, delay=duration)

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

    # --- ЛОГИКА ПОЛУЧЕНИЯ УРОНА ---
    def take_damage(self, amount):
        # Если мертв или под щитом - урон не проходит
        if self.is_dead or self.is_invulnerable:
            return

        self.hp -= amount
        update_hud()
        
        # Эффект крови
        damage_vignette.alpha = 100
        damage_vignette.animate('alpha', 0, duration=1)

        if self.hp <= 0:
            die()

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
        self.current_team_color = T_COLOR # По дефолту
        self.create_body_parts()

    def create_body_parts(self):
        # Очистка старых частей если есть
        for c in self.children: destroy(c)
        enemy_parts.clear()

        # Создаем части тела
        self.body = Entity(parent=self, model='cube', color=T_VEST_COLOR, scale=(0.6, 0.8, 0.35), position=(0, 1.3, 0), collider='box', shader=lit_with_shadows_shader)
        self.head = Entity(parent=self, model='cube', color=color.rgb(255, 200, 150), scale=(0.3, 0.35, 0.3), position=(0, 1.9, 0), collider='box', shader=lit_with_shadows_shader)
        self.leg_l = Entity(parent=self, model='cube', color=self.current_team_color, scale=(0.25, 0.9, 0.25), position=(-0.2, 0.45, 0), shader=lit_with_shadows_shader)
        self.leg_r = Entity(parent=self, model='cube', color=self.current_team_color, scale=(0.25, 0.9, 0.25), position=(0.2, 0.45, 0), shader=lit_with_shadows_shader)
        self.arm_l = Entity(parent=self.body, model='cube', color=self.current_team_color, scale=(0.25, 1.0, 0.25), position=(-0.65, 0.1, 0), shader=lit_with_shadows_shader)
        self.arm_r = Entity(parent=self.body, model='cube', color=self.current_team_color, scale=(0.25, 1.0, 0.25), position=(0.65, 0.1, 0), shader=lit_with_shadows_shader)
        
        enemy_parts.append(self.body)
        enemy_parts.append(self.head)
        
        self.name_tag = Text(text=enemy_nickname_str, parent=self, y=2.3, billboard=True, scale=5, color=color.white, background=True)

    def set_team_color(self, team_str):
        new_skin = CT_COLOR if team_str == 'ct' else T_COLOR
        new_vest = CT_VEST_COLOR if team_str == 'ct' else T_VEST_COLOR
        
        if new_skin != self.current_team_color:
            self.current_team_color = new_skin
            self.leg_l.color = new_skin
            self.leg_r.color = new_skin
            self.arm_l.color = new_skin
            self.arm_r.color = new_skin
            self.body.color = new_vest

# ================= UI & HUD (НОВЫЙ CS-STYLE) =================
hud_parent = None
hud_hp_txt = None
hud_ammo_txt = None
hud_money_txt = None
hud_score_txt = None 
damage_vignette = None
crosshair_marker = None

def create_ui():
    global hud_parent, hud_hp_txt, hud_ammo_txt, hud_money_txt, damage_vignette, crosshair_marker, hud_score_txt
    
    if hud_parent: destroy(hud_parent)
    
    hud_parent = Entity(parent=camera.ui)
    
    damage_vignette = Entity(parent=camera.ui, model='quad', scale=2, color=color.red, alpha=0)
    crosshair_marker = Text(text='X', scale=2, color=color.red, enabled=False, origin=(0,0))
    death_screen_txt = Text(text='YOU DIED', scale=5, color=color.red, origin=(0,0), enabled=False)
    
    # --- СЧЕТ ---
    hud_score_txt = Text(parent=hud_parent, text="CT: 0 | T: 0", origin=(0,0), position=(0, 0.45), scale=2, color=color.white)
    hud_score_txt.create_background(padding=0.1, radius=0.1, color=color.rgba(0,0,0,100))

    # --- ГЛАВНАЯ ПАНЕЛЬ СТАТИСТИКИ ---
    # Оставляем панель как фон
    panel_bg = Entity(parent=hud_parent, model='quad', scale=(1.2, 0.12), position=(0, -0.44), color=color.rgba(0, 0, 0, 180))
    
    # ДЕНЬГИ (Слева)
    Text(parent=hud_parent, text="$", position=(-0.48, -0.44), scale=4, origin=(0,0), color=color.green, z=-1)
    hud_money_txt = Text(parent=hud_parent, text="0", position=(-0.3, -0.44), scale=4, origin=(0,0), color=color.white, z=-1)
    
    # ЗДОРОВЬЕ (Центр)
    Text(parent=hud_parent, text="+", position=(-0.06, -0.44), scale=4, origin=(0,0), color=color.red, z=-1)
    hud_hp_txt = Text(parent=hud_parent, text="100", position=(0.06, -0.44), scale=4, origin=(0,0), color=color.white, z=-1)

    # ПАТРОНЫ (Справа)
    # Иконка патрона
    Text(parent=hud_parent, text="I", position=(0.3, -0.44), scale=2.5, origin=(0,0), color=color.yellow, rotation=(0,0,90), z=-1)
    hud_ammo_txt = Text(parent=hud_parent, text="---", position=(0.48, -0.44), scale=4, origin=(0,0), color=color.white, z=-1)


def update_hud():
    if not my_player: return
    hud_hp_txt.text = f"{my_player.hp}"
    hud_money_txt.text = f"{my_player.money}"
    
    w_name = my_player.current_weapon_name
    if weapon_config[w_name]['type'] == 'melee':
        hud_ammo_txt.text = "---"
        hud_ammo_txt.color = color.gray
    else:
        c = my_player.inventory[w_name]['clip']
        r = my_player.inventory[w_name]['reserve']
        hud_ammo_txt.text = f"{c} / {r}"
        
        # Красим красным если мало патронов
        if c <= 3: hud_ammo_txt.color = color.red
        else: hud_ammo_txt.color = color.white

def update_score_ui():
    global hud_score_txt
    if hud_score_txt:
        hud_score_txt.text = f"CT: {score_ct} | T: {score_t}"

def crosshair_hit():
    crosshair_marker.enabled = True
    invoke(setattr, crosshair_marker, 'enabled', False, delay=0.1)

# --- МЕНЮ ПОКУПКИ ---
buy_menu_panel = None

def toggle_buy_menu():
    global buy_menu_panel
    if game_state != "game": return
    
    if not buy_menu_panel:
        buy_menu_panel = Entity(parent=camera.ui, enabled=False)
        Entity(parent=buy_menu_panel, model='quad', scale=(0.9, 0.9), 
               color=color.rgb(30, 30, 30), z=1)
        Text(text="WEAPON SHOP", parent=buy_menu_panel, y=0.38, x=0, 
             origin=(0,0), scale=2, color=color.black, z=-1)
        
        y_pos = 0.25
        # Фильтруем нож из магазина, он бесплатен и всегда есть
        shop_items = {k:v for k,v in weapon_config.items() if v['price'] > 0}
        
        for name, stats in shop_items.items():
            price_text = f"${stats['price']}"
            btn = Button(parent=buy_menu_panel, 
                         text=f"{name.upper()}  [{price_text}]", 
                         scale=(0.6, 0.08), y=y_pos, color=color.black,
                         text_color=color.white, highlight_color=color.dark_gray, z=-1) 
            btn.on_click = Func(buy_weapon, name, stats['price'])
            y_pos -= 0.12 
            
        Button(parent=buy_menu_panel, text="CLOSE", scale=(0.3, 0.08), y=-0.35, 
               color=color.red, text_color=color.black, highlight_color=color.pink, z=-1,
               on_click=toggle_buy_menu)

    buy_menu_panel.enabled = not buy_menu_panel.enabled
    mouse.locked = not buy_menu_panel.enabled
    my_player.enabled = not buy_menu_panel.enabled

def buy_weapon(name, cost):
    if my_player.money >= cost:
        my_player.money -= cost
        # Добавляем в инвентарь или пополняем запас
        if name in my_player.inventory:
             my_player.inventory[name]['reserve'] = weapon_config[name]['reserve']
        else:
             my_player.inventory[name] = {'clip': weapon_config[name]['clip'], 'reserve': weapon_config[name]['reserve']}
        
        my_player.switch_weapon(name)
        update_hud()
        Audio('ursina/assets/sounds/coin.wav', volume=settings['volume'], loop=False)

# --- ЛОГИКА СМЕРТИ ---
def die():
    global score_ct, score_t
    if my_player.is_dead: return
    
    my_player.is_dead = True
    
    # Отправляем инфо о смерти убийце, чтобы он получил деньги и перестал видеть хитмаркеры
    send_data({'type': 'kill_confirm'})
    
    if my_player.team == 'ct': score_t += 1
    else: score_ct += 1
    update_score_ui()

    my_player.cursor.enabled = False
    my_player.position = (0, -100, 0) # Убираем под карту
    death_screen_txt.enabled = True
    
    # Спавн через 1 секунду + время щита
    invoke(respawn, delay=1.0)

def respawn():
    spawn_pos = get_spawn_point(my_player.team)
    my_player.position = spawn_pos
    my_player.hp = 100
    my_player.is_dead = False
    my_player.cursor.enabled = True
    death_screen_txt.enabled = False
    
    # Щит на спавне
    my_player.is_invulnerable = True
    
    # Сброс инвентаря
    my_player.inventory = {'knife': {'clip': 0, 'reserve': 0}}
    my_player.switch_weapon('knife') 
    
    update_hud()
    
    # Отключаем щит через 2 секунды
    invoke(disable_shield, delay=2.0)

# ================= МЕНЮ =================
menu_ui = None
team_ui = None
nick_input = None
ip_input = None

def create_main_menu():
    global menu_ui, nick_input, ip_input
    menu_ui = Entity(parent=camera.ui)
    
    Entity(parent=menu_ui, model='quad', scale=(15, 10), color=color.black, z=1)
    Text(parent=menu_ui, text=GAME_NAME, origin=(0,0), y=0.38, scale=5, color=color.white, z=-0.1)
    Text(parent=menu_ui, text=SUBTITLE, origin=(0,0), y=0.28, scale=2, color=color.light_gray, z=-0.1)
    Text(parent=menu_ui, text=f'{STATUS} v.{VERSION}', position=(0.6, -0.45), scale=1.2, color=color.gray, z=-0.1)

    Text(parent=menu_ui, text='NICKNAME', position=(-0.10, 0.07), scale=1.5, color=color.white, z=-0.1)
    nick_input = InputField(parent=menu_ui, default_value='Player1', y=0.0, 
                            scale=(0.4, 0.05), color=color.dark_gray, text_color=color.white, z=-0.1)
    
    Text(parent=menu_ui, text='SERVER IP', position=(-0.10, -0.07), scale=1.5, color=color.white, z=-0.1)
    ip_input = InputField(parent=menu_ui, default_value=DEFAULT_IP, y=-0.15, 
                          scale=(0.4, 0.05), color=color.dark_gray, text_color=color.white, z=-0.1)

    b_host = Button(parent=menu_ui, text='HOST GAME', y=-0.3, x=-0.2, scale=(0.3, 0.08), 
                    color=color.blue, text_color=color.white, highlight_color=color.cyan, z=-0.1)
    b_host.on_click = on_host
    
    b_join = Button(parent=menu_ui, text='JOIN GAME', y=-0.3, x=0.2, scale=(0.3, 0.08), 
                    color=color.green, text_color=color.white, highlight_color=color.lime, z=-0.1)
    b_join.on_click = on_connect

def create_team_menu():
    global team_ui
    if menu_ui: menu_ui.enabled = False
    
    team_ui = Entity(parent=camera.ui)
    Entity(parent=team_ui, model='quad', scale=(15, 10), color=color.black, z=1)
    Text(parent=team_ui, text="CHOOSE YOUR TEAM", origin=(0,0), y=0.3, scale=3, color=color.white, z=-0.1)
    
    # Кнопка CT
    btn_ct = Button(parent=team_ui, text="COUNTER-TERRORISTS", color=CT_COLOR, x=-0.3, scale=(0.5, 0.1), z=-0.1)
    btn_ct.on_click = Func(init_player, 'ct')
    
    # Кнопка T
    btn_t = Button(parent=team_ui, text="TERRORISTS", color=T_COLOR, x=0.3, scale=(0.5, 0.1), z=-0.1)
    btn_t.on_click = Func(init_player, 't')

def on_host():
    global is_server, my_nickname
    is_server = True
    my_nickname = nick_input.text
    try: socket_obj.bind(('0.0.0.0', PORT))
    except: pass
    threading.Thread(target=network_listener, args=('server',), daemon=True).start()
    create_team_menu()

def on_connect():
    global is_server, my_nickname, target_address
    is_server = False
    my_nickname = nick_input.text
    target_address = (ip_input.text, PORT)
    send_data({'type': 'check_map', 'hash': get_map_hash(), 'nickname': my_nickname})
    threading.Thread(target=network_listener, args=('client',), daemon=True).start()
    
    # Скрываем меню и ждем подтверждения карты
    menu_ui.enabled = False
    Text(text="Connecting...", origin=(0,0), id='sync_msg', scale=2)

def init_player(team_choice):
    global my_player, game_state, enemy_entity, team_ui
    if team_ui: team_ui.enabled = False
    
    game_state = "game"
    create_map() 
    create_ui()
    update_score_ui()
    
    # Спавним игрока за выбранную команду
    my_player = Player(position=get_spawn_point(team_choice), team=team_choice)
    enemy_entity = EnemyModel(pos=(0, -50, 0))

# ================= КАРТА И ОСВЕЩЕНИЕ =================
def create_map():
    global map_spawns_ct, map_spawns_t
    sun = DirectionalLight(shadows=True)
    sun.look_at(Vec3(1, -1, -0.5)) 
    sun.shadow_map_resolution = Vec2(4096, 4096) 
    AmbientLight(color=color.rgb(30, 30, 35))
    Sky(color=color.rgb(50, 50, 70))
    Entity(model='plane', scale=200, texture='floor', texture_scale=(40,40), collider='box', shader=lit_with_shadows_shader, position=(0,0,0)) 

    if os.path.exists('level_data.json'):
        with open('level_data.json', 'r') as f:
            data = json.load(f)
            blocks_to_load = []
            if isinstance(data, dict):
                blocks_to_load = data.get('blocks', [])
                map_spawns_ct[:] = data.get('spawns_ct', [])
                map_spawns_t[:] = data.get('spawns_t', [])
            elif isinstance(data, list):
                blocks_to_load = data
            for block in blocks_to_load:
                Entity(model='cube', position=block['pos'], scale=block.get('scale', (1,1,1)), 
                       texture=block['tex'], collider='box', shader=lit_with_shadows_shader)
    else:
        create_default_map()

def create_default_map():
    walls = [
        {'pos': (0, 5, 60), 'scale': (120, 10, 2)},
        {'pos': (0, 5, -60), 'scale': (120, 10, 2)},
        {'pos': (60, 5, 0), 'scale': (2, 10, 120)},
        {'pos': (-60, 5, 0), 'scale': (2, 10, 120)},
        {'pos': (0, 5, 0), 'scale': (2, 10, 40)},
        {'pos': (30, 5, 20), 'scale': (40, 10, 2)},
        {'pos': (30, 5, -20), 'scale': (40, 10, 2)},
    ]
    for w in walls:
        Entity(model='cube', position=w['pos'], scale=w['scale'], texture='brick', 
               texture_scale=(w['scale'][0]/2, w['scale'][1]/2), collider='box', shader=lit_with_shadows_shader)
    boxes = [(10, 1, 10), (10, 2, 12), (35, 1, -15), (-30, 1, 5), (-40, 1, -20), (5, 1, 40), (45, 1, 40)]
    for b in boxes:
        Entity(model='cube', position=b, scale=2, texture='crate', collider='box', shader=lit_with_shadows_shader)

def get_spawn_point(team):
    if team == 'ct' and map_spawns_ct: return random.choice(map_spawns_ct)
    elif team == 't' and map_spawns_t: return random.choice(map_spawns_t)
    return (-40, 2, 0) if team == 'ct' else (40, 2, 0)

# ================= ИГРОВОЙ ЦИКЛ =================
def start_game(mode, ip_addr, nick):
    global my_player, game_state, enemy_entity, is_server, my_nickname, target_address
    my_nickname = nick
    menu_ui.enabled = False
    game_state = "game"
    is_server = (mode == 'server')
    create_map() 
    create_ui()
    update_score_ui()
    
    team = 'ct' if is_server else 't'
    my_player = Player(position=get_spawn_point(team), team=team)
    enemy_entity = EnemyModel(pos=(0, -50, 0))
    
    if mode == 'server':
        try: socket_obj.bind(('0.0.0.0', PORT))
        except: print("Port busy or error")
    else:
        target_address = (ip_addr, PORT)
    threading.Thread(target=network_listener, args=(mode,), daemon=True).start()

def send_data(data_dict):
    global socket_obj, target_address
    if not socket_obj: return
    try:
        msg = json.dumps(data_dict).encode()
        if target_address: socket_obj.sendto(msg, target_address)
    except: pass

def network_listener(mode):
    global socket_obj, target_address
    while True:
        try:
            data, addr = socket_obj.recvfrom(2048 * 32)
            if mode == 'server' and target_address is None: target_address = addr
            if target_address and addr != target_address: continue
            msg = json.loads(data.decode())
            network_queue.append(msg)
        except: pass
        
def start_client_game():
    global game_state, my_player, enemy_entity
    if game_state == "game": return
    game_state = "game"
    for e in scene.entities:
        if hasattr(e, 'id') and e.id == 'sync_msg': destroy(e)
    create_map() 
    create_ui()
    update_score_ui()
    my_player = Player(position=get_spawn_point('t'), team='t')
    enemy_entity = EnemyModel(pos=(0, -50, 0))
    
def process_important_packet(msg):
    global score_ct, score_t
    m_type = msg.get('type')
    
    if m_type == 'hit': 
        # Проверяем на клиенте, можем ли мы получить урон (жив ли я)
        # Если мертв или в щите, урон игнорируется локально
        my_player.take_damage(msg.get('dmg', 0))
        
    elif m_type == 'kill_confirm':
        # Подтверждение, что мы убили врага -> получаем деньги и показываем маркер
        my_player.money += 300
        crosshair_hit()
        if my_player.team == 'ct': score_ct += 1
        else: score_t += 1
        update_score_ui()
        update_hud()

def update():
    global score_ct, score_t, last_send_time
    
    # Отправка позиции
    if my_player and game_state == "game" and not my_player.is_dead:
        if time.time() - last_send_time > tick_rate:
            moving = held_keys['w'] or held_keys['a'] or held_keys['s'] or held_keys['d']
            looking = mouse.velocity != Vec3(0,0,0)
            if moving or looking or held_keys['left mouse']:
                pos_data = {
                    'type': 'move', 
                    'x': round(my_player.x, 2), 'y': round(my_player.y, 2), 'z': round(my_player.z, 2), 
                    'ry': round(my_player.rotation_y, 2), 
                    'name': my_nickname,
                    'team': my_player.team # Отправляем нашу команду, чтобы враг видел правильный скин
                }
                send_data(pos_data)
                last_send_time = time.time()

    # Обработка пакетов
    latest_move_packet = None 
    while len(network_queue) > 0:
        msg = network_queue.pop(0)
        m_type = msg.get('type')
        if m_type == 'check_map':
            if msg['hash'] == get_map_hash(): send_data({'type': 'map_ok'})
            else:
                if os.path.exists('level_data.json'):
                    with open('level_data.json', 'r') as f: send_data({'type': 'map_data', 'data': json.load(f)})
        elif m_type == 'map_ok': 
            for e in scene.entities:
                if hasattr(e, 'id') and e.id == 'sync_msg': destroy(e)
            create_team_menu() # После синхронизации открываем выбор команды
        elif m_type == 'map_data':
            with open('level_data.json', 'w') as f: json.dump(msg['data'], f)
            for e in scene.entities:
                if hasattr(e, 'id') and e.id == 'sync_msg': destroy(e)
            create_team_menu()
        elif m_type == 'move': latest_move_packet = msg 
        else: process_important_packet(msg)

    # Обновление врага
    if latest_move_packet and enemy_entity:
        enemy_entity.animate_position((latest_move_packet['x'], latest_move_packet['y'], latest_move_packet['z']), duration=0.05, curve=curve.linear)
        enemy_entity.rotation_y = latest_move_packet['ry']
        
        # Обновляем ник
        if enemy_entity.name_tag.text != latest_move_packet.get('name'): 
            enemy_entity.name_tag.text = latest_move_packet.get('name')
        
        # Обновляем цвет (скин) в зависимости от того, кого выбрал враг
        enemy_team = latest_move_packet.get('team', 't')
        enemy_entity.set_team_color(enemy_team)

create_main_menu()
app.run()
