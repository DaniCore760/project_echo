from ursina import *
import json
import os
from functools import partial

# Отключаем VSync для плавности, если нужно
app = Ursina(vsync=False)

# --- НАСТРОЙКИ ---
window.title = "Project Echo - Map Editor (Smooth)"
window.borderless = True
window.fullscreen = False
window.exit_button.visible = False

# Путь к папке с текстурами
TEXTURES_DIR = 'assets/textures'
if not os.path.exists(TEXTURES_DIR):
    os.makedirs(TEXTURES_DIR)

# Списки объектов
placed_blocks = []
ct_spawns = []
t_spawns = []

# Текущее состояние
current_texture = 'brick'
selected_block = None
current_tool = 'block' 
dragging_block = None  

# --- ЗАГОЛОВОК ---
Text(text='Map Editor TINTool', origin=(0,0), y=0.45, scale=2, color=color.cyan, background=True)

# --- НОВАЯ ПЛАВНАЯ КАМЕРА ---
class SmoothFreeCamera(Entity):
    def __init__(self):
        super().__init__()
        self.speed = 20
        self.smoothness = 8  # Насколько быстро камера разгоняется/тормозит (меньше = плавнее)
        self.velocity = Vec3(0,0,0) # Текущая скорость для инерции
        
        camera.parent = self
        camera.position = (0,0,0)
        camera.rotation = (0,0,0)
        
        self.position = (0, 10, -20)
        self.rotation_x = 30

    def update(self):
        # Игнорируем управление, если мышь на UI
        if mouse.hovered_entity and isinstance(mouse.hovered_entity, (Slider, Button)):
            pass
        
        # Вращение (Средняя кнопка мыши)
        elif mouse.middle: 
            self.rotation_y += mouse.velocity[0] * 150
            self.rotation_x -= mouse.velocity[1] * 150
            self.rotation_x = clamp(self.rotation_x, -90, 90)

        # Ввод движения
        # W/S - Вперед/Назад (по направлению взгляда)
        # D/A - Вправо/Влево (стейф)
        # E/Q - Вверх/Вниз (вертикальный взлет относительно камеры)
        
        input_move = Vec3(
            held_keys['d'] - held_keys['a'],      # X
            held_keys['e'] - held_keys['q'],      # Y
            held_keys['w'] - held_keys['s']       # Z
        )

        # Вычисляем направление относительно поворота камеры
        # self.forward - это вектор "куда я смотрю"
        # self.right - это вектор "направо от меня"
        # self.up - это вектор "вверх относительно меня"
        
        direction = (self.forward * input_move.z) + \
                    (self.right * input_move.x) + \
                    (self.up * input_move.y)

        if direction.length() > 0:
            direction = direction.normalized()

        # Целевая скорость
        target_velocity = direction * self.speed
        
        # Плавное изменение текущей скорости к целевой (Lerp)
        self.velocity = lerp(self.velocity, target_velocity, time.dt * self.smoothness)
        
        # Применяем движение
        self.position += self.velocity * time.dt

editor_cam = SmoothFreeCamera()

# --- UPDATE (Перемещение блоков) ---
def update():
    global dragging_block
    
    if dragging_block:
        if mouse.world_point:
            new_x = round(mouse.world_point.x)
            new_z = round(mouse.world_point.z)
            new_y = dragging_block.y 
            dragging_block.position = Vec3(new_x, new_y, new_z)

# --- UI: ИНСТРУМЕНТЫ ---
tools_bg = Entity(parent=camera.ui, model='quad', color=color.rgba(0,0,0,0.8), 
                  scale=(0.25, 0.4), position=(-0.75, 0.2))
Text(parent=tools_bg, text="TOOLS", origin=(0, 0), y=0.4, scale=1.5)

def set_tool(tool_name):
    global current_tool
    current_tool = tool_name
    
    btn_block_mode.color = color.green if tool_name == 'block' else color.gray
    btn_ct_spawn.color = color.blue if tool_name == 'ct' else color.gray
    btn_t_spawn.color = color.red if tool_name == 't' else color.gray
    
    if tool_name != 'block':
        deselect_block()

btn_block_mode = Button(parent=tools_bg, text='Add Blocks', scale=(0.8, 0.2), y=0.15, color=color.green)
btn_block_mode.on_click = partial(set_tool, 'block')
btn_ct_spawn = Button(parent=tools_bg, text='Add CT Spawn', scale=(0.8, 0.2), y=-0.05, color=color.gray)
btn_ct_spawn.on_click = partial(set_tool, 'ct')
btn_t_spawn = Button(parent=tools_bg, text='Add T Spawn', scale=(0.8, 0.2), y=-0.25, color=color.gray)
btn_t_spawn.on_click = partial(set_tool, 't')

# --- UI: НАСТРОЙКИ БЛОКА ---
edit_panel = Entity(parent=camera.ui, position=(-0.85, -0.25), enabled=False)
edit_bg = Entity(parent=edit_panel, model='quad', color=color.rgba(0,0,0,0.8), scale=(0.4, 0.5), x=0.15)
Text(parent=edit_panel, text="BLOCK SETTINGS", position=(0, 0.2), scale=1.5)

def update_scale_x():
    if selected_block: selected_block.scale_x = slider_x.value
def update_scale_y():
    if selected_block: selected_block.scale_y = slider_y.value
def update_scale_z():
    if selected_block: selected_block.scale_z = slider_z.value

slider_x = Slider(parent=edit_panel, min=1, max=10, default=1, text='Size X', y=0.1, step=1, dynamic=True, on_value_changed=update_scale_x)
slider_y = Slider(parent=edit_panel, min=1, max=10, default=1, text='Size Y', y=0.0, step=1, dynamic=True, on_value_changed=update_scale_y)
slider_z = Slider(parent=edit_panel, min=1, max=10, default=1, text='Size Z', y=-0.1, step=1, dynamic=True, on_value_changed=update_scale_z)
lbl_selected_tex = Text(parent=edit_panel, text="Texture: None", position=(0, -0.2), scale=1)

# --- ВЫДЕЛЕНИЕ ---
def select_block(entity):
    global selected_block
    if entity in ct_spawns or entity in t_spawns:
        return

    if selected_block: selected_block.color = color.white

    selected_block = entity
    selected_block.color = color.lime 
    edit_panel.enabled = True
    
    slider_x.value = entity.scale_x
    slider_y.value = entity.scale_y
    slider_z.value = entity.scale_z
    
    tex_name = getattr(entity, 'my_texture_name', 'Unknown')
    lbl_selected_tex.text = f"Texture: {os.path.basename(tex_name)}"

def deselect_block():
    global selected_block
    if selected_block:
        selected_block.color = color.white 
        selected_block = None
    edit_panel.enabled = False

# --- ТЕКСТУРЫ ---
assets_bg = Entity(parent=camera.ui, model='quad', color=color.rgba(0,0,0,0.8), 
                   scale=(0.3, 1.5), position=(0.75, 0), z=1)
Text(parent=assets_bg, text="TEXTURES", origin=(0, 0), position=(0, 0.45), scale=2, color=color.white)
texture_buttons = []

def set_current_texture(tex_path):
    global current_texture
    if selected_block:
        apply_texture_safely(selected_block, tex_path)
        lbl_selected_tex.text = f"Texture:\n{os.path.basename(tex_path)}"
        current_texture = tex_path 
    else:
        current_texture = tex_path
    
    for btn in texture_buttons:
        btn.color = color.green if hasattr(btn, 'my_tex_path') and btn.my_tex_path == tex_path else color.white

def refresh_asset_panel():
    for btn in texture_buttons: destroy(btn)
    texture_buttons.clear()
    files = []
    if os.path.exists(TEXTURES_DIR):
        files = [f for f in os.listdir(TEXTURES_DIR) if f.lower().endswith('.png')]
    
    start_x = 0.65; start_y = 0.35; x_offset = 0; y_offset = 0
    for i, file_name in enumerate(files):
        full_path = f'{TEXTURES_DIR}/{file_name}'
        btn = Button(parent=camera.ui, model='quad', texture=full_path, scale=(0.09, 0.09), position=(start_x + x_offset, start_y - y_offset), color=color.white, highlight_color=color.lime)
        btn.my_tex_path = full_path
        btn.on_click = partial(set_current_texture, full_path)
        btn.tooltip = Tooltip(file_name)
        texture_buttons.append(btn)
        x_offset += 0.1
        if (i + 1) % 2 == 0: x_offset = 0; y_offset += 0.11

refresh_btn = Button(parent=camera.ui, text='REFRESH', scale=(0.2, 0.05), position=(0.75, 0.42), color=color.azure)
refresh_btn.on_click = refresh_asset_panel
refresh_asset_panel()

# --- ФУНКЦИИ СОЗДАНИЯ ---
def apply_texture_safely(entity, tex_path):
    entity.my_texture_name = tex_path 
    entity.texture = tex_path

def create_block(position, texture_name):
    b = Entity(model='cube', position=position, collider='box')
    apply_texture_safely(b, texture_name)
    placed_blocks.append(b)
    return b

def create_ct_spawn(position):
    s = Entity(model='cube', position=position, collider='box', color=color.rgba(0, 0, 255, 128), texture='white_cube')
    ct_spawns.append(s)
    return s

def create_t_spawn(position):
    s = Entity(model='cube', position=position, collider='box', color=color.rgba(255, 0, 0, 128), texture='white_cube')
    t_spawns.append(s)
    return s

# --- СОХРАНЕНИЕ И ЗАГРУЗКА ---
def save_map():
    blocks_data = []
    for b in placed_blocks:
        tex_name = getattr(b, 'my_texture_name', 'brick')
        blocks_data.append({'pos': (b.x, b.y, b.z), 'scale': (b.scale_x, b.scale_y, b.scale_z), 'tex': tex_name})
    
    with open('level_data.json', 'w') as f:
        json.dump({
            "blocks": blocks_data, 
            "spawns_ct": [(s.x, s.y, s.z) for s in ct_spawns], 
            "spawns_t": [(s.x, s.y, s.z) for s in t_spawns]
        }, f, indent=4)
    print_on_screen("Map Saved!", position=(0,0), scale=2, duration=2)

def load_map():
    if not os.path.exists('level_data.json'):
        print_on_screen("File not found!", position=(0,0), scale=2, duration=2, color=color.red)
        return

    deselect_block()
    for b in placed_blocks: destroy(b)
    for s in ct_spawns: destroy(s)
    for s in t_spawns: destroy(s)
    placed_blocks.clear()
    ct_spawns.clear()
    t_spawns.clear()

    with open('level_data.json', 'r') as f:
        data = json.load(f)

    for b_data in data.get("blocks", []):
        pos = b_data.get('pos', [0,0,0])
        tex = b_data.get('tex', 'brick')
        scale = b_data.get('scale', [1,1,1])
        new_block = create_block(pos, tex)
        new_block.scale = scale
    
    for pos in data.get("spawns_ct", []):
        create_ct_spawn(pos)
    
    for pos in data.get("spawns_t", []):
        create_t_spawn(pos)

    print_on_screen("Map Loaded!", position=(0,0), scale=2, duration=2)

save_btn = Button(text='SAVE MAP', scale=(0.2, 0.05), position=(0.7, -0.4), color=color.azure)
save_btn.on_click = save_map
load_btn = Button(text='LOAD MAP', scale=(0.2, 0.05), position=(0.7, -0.46), color=color.orange)
load_btn.on_click = load_map

# --- INPUT ---
def input(key):
    global current_texture, dragging_block
    
    if key == 'left mouse down':
        if mouse.hovered_entity and isinstance(mouse.hovered_entity, (Button, Tooltip, Slider)):
            return

        if mouse.hovered_entity and mouse.hovered_entity == selected_block:
             dragging_block = mouse.hovered_entity
             dragging_block.collision = False 
             dragging_block.alpha = 0.5       
             return 

        if mouse.hovered_entity:
            build_position = (0,0,0)
            if mouse.hovered_entity == base_floor:
                x = round(mouse.world_point.x)
                z = round(mouse.world_point.z)
                build_position = (x, 0.5, z)
            else:
                build_position = mouse.hovered_entity.position + mouse.normal

            if current_tool == 'block':
                create_block(build_position, current_texture)
            elif current_tool == 'ct':
                create_ct_spawn(build_position)
            elif current_tool == 't':
                create_t_spawn(build_position)

    if key == 'left mouse up':
        if dragging_block:
            dragging_block.collision = True
            dragging_block.alpha = 1
            if dragging_block == selected_block: dragging_block.color = color.lime
            dragging_block = None

    if key == 'delete':
        target = selected_block if selected_block else mouse.hovered_entity
        if target:
            if target in placed_blocks: placed_blocks.remove(target); destroy(target)
            elif target in ct_spawns: ct_spawns.remove(target); destroy(target)
            elif target in t_spawns: t_spawns.remove(target); destroy(target)
            if target == selected_block: deselect_block()

    if key == 'right mouse down':
        if mouse.hovered_entity and mouse.hovered_entity in placed_blocks:
            if current_tool == 'block':
                select_block(mouse.hovered_entity)
                Audio('ursina/assets/sounds/button_click.wav', volume=0.5, pitch=1.5)
        elif not mouse.hovered_entity or mouse.hovered_entity == base_floor:
            deselect_block()

# --- СЦЕНА ---
base_floor = Entity(model='plane', scale=100, texture='white_cube', texture_scale=(100,100), collider='box', color=color.gray)
DirectionalLight(parent=editor_cam, y=2, z=3, shadows=False, rotation=(45, -45, 45))

app.run()
