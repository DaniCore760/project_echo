from ursina import *
from ursina.shaders import lit_with_shadows_shader
import json
import os
from functools import partial

app = Ursina()

# --- НАСТРОЙКИ ---
window.title = "Project Echo - Map Editor"
window.borderless = True
window.fullscreen = False

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
current_tool = 'block' # 'block', 'ct', 't'

# --- ЗАГОЛОВОК ---
Text(text='Map Editor TINTool', origin=(0,0), y=0.45, scale=2, color=color.cyan, background=True)

# --- КАМЕРА ---
class FreeCamera(Entity):
    def __init__(self):
        super().__init__()
        self.speed = 20
        self.camera_pivot = Entity(parent=self)
        camera.parent = self.camera_pivot
        camera.position = (0,0,0)
        camera.rotation = (0,0,0)
        self.position = (0, 10, -20)
        self.rotation_x = 30

    def update(self):
        if mouse.hovered_entity and isinstance(mouse.hovered_entity, (Slider, Button)):
            return

        if mouse.middle: 
            self.rotation_y += mouse.velocity[0] * 100
            self.camera_pivot.rotation_x -= mouse.velocity[1] * 100
            self.camera_pivot.rotation_x = clamp(self.camera_pivot.rotation_x, -90, 90)

        direction = Vec3(
            self.forward * (held_keys['w'] - held_keys['s'])
            + self.right * (held_keys['d'] - held_keys['a'])
            + self.up * (held_keys['e'] - held_keys['q']) 
        ).normalized()

        self.position += direction * self.speed * time.dt

editor_cam = FreeCamera()

# --- UI: ВЫБОР ИНСТРУМЕНТА (ЛЕВАЯ ПАНЕЛЬ) ---
tools_bg = Entity(parent=camera.ui, model='quad', color=color.rgba(0,0,0,0.8), 
                  scale=(0.25, 0.4), position=(-0.75, 0.2))
Text(parent=tools_bg, text="TOOLS", origin=(0, 0), y=0.4, scale=1.5)

def set_tool(tool_name):
    global current_tool
    current_tool = tool_name
    
    # Визуальное обновление кнопок
    btn_block_mode.color = color.green if tool_name == 'block' else color.gray
    btn_ct_spawn.color = color.blue if tool_name == 'ct' else color.gray
    btn_t_spawn.color = color.red if tool_name == 't' else color.gray
    
    # Если перешли в режим спавнов, снимаем выделение с блока
    if tool_name != 'block':
        deselect_block()

btn_block_mode = Button(parent=tools_bg, text='Add Blocks', scale=(0.8, 0.2), y=0.15, color=color.green)
btn_block_mode.on_click = partial(set_tool, 'block')

btn_ct_spawn = Button(parent=tools_bg, text='Add CT Spawn', scale=(0.8, 0.2), y=-0.05, color=color.gray)
btn_ct_spawn.on_click = partial(set_tool, 'ct')

btn_t_spawn = Button(parent=tools_bg, text='Add T Spawn', scale=(0.8, 0.2), y=-0.25, color=color.gray)
btn_t_spawn.on_click = partial(set_tool, 't')


# --- МЕНЮ РЕДАКТИРОВАНИЯ БЛОКА ---
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
    # Если кликнули на спавн, не выделяем его как блок для растягивания
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

# --- ПАНЕЛЬ ТЕКСТУР ---
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
    
    # Визуальное выделение выбранной текстуры
    for btn in texture_buttons:
        btn.color = color.green if hasattr(btn, 'my_tex_path') and btn.my_tex_path == tex_path else color.white

def refresh_asset_panel():
    for btn in texture_buttons: destroy(btn)
    texture_buttons.clear()

    files = []
    if os.path.exists(TEXTURES_DIR):
        files = [f for f in os.listdir(TEXTURES_DIR) if f.lower().endswith('.png')]
    
    start_x = 0.65
    start_y = 0.35
    x_offset = 0
    y_offset = 0
    
    for i, file_name in enumerate(files):
        full_path = f'{TEXTURES_DIR}/{file_name}'
        btn = Button(
            parent=camera.ui,
            model='quad',
            texture=full_path,
            scale=(0.09, 0.09),
            position=(start_x + x_offset, start_y - y_offset),
            color=color.white,
            highlight_color=color.lime
        )
        btn.my_tex_path = full_path
        btn.on_click = partial(set_current_texture, full_path)
        btn.tooltip = Tooltip(file_name)
        texture_buttons.append(btn)
        
        x_offset += 0.1
        if (i + 1) % 2 == 0:
            x_offset = 0
            y_offset += 0.11

refresh_btn = Button(parent=camera.ui, text='REFRESH', scale=(0.2, 0.05), position=(0.75, 0.42), color=color.azure)
refresh_btn.on_click = refresh_asset_panel
refresh_asset_panel()

# --- ФУНКЦИИ СОЗДАНИЯ ОБЪЕКТОВ ---
def apply_texture_safely(entity, tex_path):
    entity.my_texture_name = tex_path 
    entity.texture = tex_path

def create_block(position, texture_name):
    b = Entity(model='cube', position=position, 
               collider='box', shader=lit_with_shadows_shader)
    apply_texture_safely(b, texture_name)
    placed_blocks.append(b)
    return b

def create_ct_spawn(position):
    # Полупрозрачный синий куб
    s = Entity(model='cube', position=position, collider='box',
               color=color.rgba(0, 0, 255, 128), texture='white_cube')
    ct_spawns.append(s)
    return s

def create_t_spawn(position):
    # Полупрозрачный красный куб
    s = Entity(model='cube', position=position, collider='box',
               color=color.rgba(255, 0, 0, 128), texture='white_cube')
    t_spawns.append(s)
    return s

# --- СОХРАНЕНИЕ ---
def save_map():
    # Собираем блоки
    blocks_data = []
    for b in placed_blocks:
        tex_name = getattr(b, 'my_texture_name', 'brick')
        blocks_data.append({
            'pos': (b.x, b.y, b.z),
            'scale': (b.scale_x, b.scale_y, b.scale_z),
            'tex': tex_name 
        })
    
    # Собираем спавны (только координаты)
    ct_data = [(s.x, s.y, s.z) for s in ct_spawns]
    t_data = [(s.x, s.y, s.z) for s in t_spawns]

    full_data = {
        "blocks": blocks_data,
        "spawns_ct": ct_data,
        "spawns_t": t_data
    }

    with open('level_data.json', 'w') as f:
        json.dump(full_data, f, indent=4)
    
    print_on_screen("Map Saved!", position=(0,0), scale=2, duration=2)

save_btn = Button(text='SAVE MAP', scale=(0.2, 0.05), position=(0.7, -0.4), color=color.azure)
save_btn.on_click = save_map

# --- INPUT (ЛОГИКА СЕТКИ И СТРОИТЕЛЬСТВА) ---
def input(key):
    global current_texture
    
    # УДАЛЕНИЕ (DELETE)
    if key == 'delete':
        target = None
        if selected_block:
            target = selected_block
            deselect_block()
        elif mouse.hovered_entity:
             target = mouse.hovered_entity

        if target:
            if target in placed_blocks:
                placed_blocks.remove(target)
                destroy(target)
            elif target in ct_spawns:
                ct_spawns.remove(target)
                destroy(target)
            elif target in t_spawns:
                t_spawns.remove(target)
                destroy(target)

    # ЛКМ - УСТАНОВКА
    if key == 'left mouse down':
        if mouse.hovered_entity and not isinstance(mouse.hovered_entity, (Button, Tooltip, Slider)):
             
             build_position = (0,0,0)
             
             # Если клик по ПОЛУ: округляем X/Z, Y ставим на 0.5 (первый слой)
             if mouse.hovered_entity == base_floor:
                 x = round(mouse.world_point.x)
                 z = round(mouse.world_point.z)
                 build_position = (x, 0.5, z)
             
             # Если клик по БЛОКУ или СПАВНУ: ставим ровно к соседней грани
             else:
                 # Позиция существующего блока + нормаль (направление грани)
                 # Это гарантирует идеальное примыкание без округления дробных координат удара
                 build_position = mouse.hovered_entity.position + mouse.normal

             # Создаем объект в зависимости от выбранного инструмента
             if current_tool == 'block':
                 create_block(build_position, current_texture)
             elif current_tool == 'ct':
                 create_ct_spawn(build_position)
             elif current_tool == 't':
                 create_t_spawn(build_position)

    # ПКМ - ВЫДЕЛЕНИЕ (Только для блоков)
    if key == 'right mouse down':
        if mouse.hovered_entity and mouse.hovered_entity in placed_blocks:
            # Если инструмент - спавн, мы не хотим выделять блоки, чтобы не сбивать фокус
            if current_tool == 'block':
                select_block(mouse.hovered_entity)
                Audio('ursina/assets/sounds/button_click.wav', volume=0.5, pitch=1.5)
        elif not mouse.hovered_entity or mouse.hovered_entity == base_floor:
            deselect_block()

# --- СЦЕНА ---
# Пол с сеткой
base_floor = Entity(
    model='plane', 
    scale=100, 
    texture='white_cube', 
    texture_scale=(100,100), 
    collider='box', 
    color=color.gray
)
DirectionalLight(parent=editor_cam, y=2, z=3, shadows=True, rotation=(45, -45, 45))

app.run()
