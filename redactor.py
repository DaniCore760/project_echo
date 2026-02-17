from ursina import *
import json

app = Ursina()
window.title = "CS: Ursina Map Editor"
window.borderless = False
window.exit_button.visible = False

# --- КОНФИГУРАЦИЯ ---
available_textures = ['brick', 'grass', 'dirt', 'stone', 'crate', 'white_cube']
default_texture = 'brick'

# Список всех блоков сцены
map_blocks = []
selected_block = None

# --- UI ЭЛЕМЕНТЫ (Ссылки) ---
prop_panel = None
pos_inputs = []
rot_inputs = []
scale_inputs = []
texture_buttons = []

# ================= КЛАСС СВОБОДНОЙ КАМЕРЫ =================
class FreeCamera(Entity):
    def __init__(self):
        super().__init__()
        self.speed = 10
        self.sensitivity = 40
        camera.parent = self
        camera.position = (0,0,0)
        camera.rotation = (0,0,0)
        self.position = (0, 10, -20)
        self.rotation_x = 30
        
        # Состояние мыши
        self.rotating = False

    def update(self):
        # Вращение камеры (только если зажата ПКМ)
        if held_keys['right mouse']:
            if not self.rotating:
                self.rotating = True
                mouse.locked = True
            
            self.rotation_y += mouse.velocity[0] * self.sensitivity
            self.rotation_x -= mouse.velocity[1] * self.sensitivity
        else:
            if self.rotating:
                self.rotating = False
                mouse.locked = False

        # Перемещение (WASD + QE)
        direction = Vec3(
            self.forward * (held_keys['w'] - held_keys['s'])
            + self.right * (held_keys['d'] - held_keys['a'])
            + self.up * (held_keys['e'] - held_keys['q'])
        ).normalized()

        # Ускорение на Shift
        move_speed = self.speed * (2 if held_keys['shift'] else 1)
        self.position += direction * move_speed * time.dt

    def input(self, key):
        # Зум / Скорость колесиком
        if key == 'scroll up':
            self.speed += 2
        if key == 'scroll down':
            self.speed = max(1, self.speed - 2)

editor_cam = FreeCamera()

# ================= УПРАВЛЕНИЕ БЛОКАМИ =================

def create_block(position=(0,0,0), scale=(1,1,1), rotation=(0,0,0), texture_name='brick', color_val=color.white):
    e = Entity(
        model='cube',
        position=position,
        scale=scale,
        rotation=rotation,
        texture=texture_name,
        color=color_val,
        collider='box',
        shader=None # В редакторе используем простой шейдер для четкости
    )
    e.texture_name = texture_name # Запоминаем имя текстуры для сохранения
    map_blocks.append(e)
    return e

def add_new_block():
    # Создаем блок перед камерой
    pos = editor_cam.position + editor_cam.forward * 5
    pos = Vec3(round(pos.x), round(pos.y), round(pos.z)) # Округляем для удобства
    select_block(create_block(position=pos))

def delete_selected():
    global selected_block
    if selected_block:
        map_blocks.remove(selected_block)
        destroy(selected_block)
        selected_block = None
        update_ui_values()
        print("Block deleted")

def duplicate_selected():
    if selected_block:
        new_b = create_block(
            position=selected_block.position + Vec3(1,1,1),
            scale=selected_block.scale,
            rotation=selected_block.rotation,
            texture_name=selected_block.texture_name,
            color_val=selected_block.color
        )
        select_block(new_b)

def select_block(entity):
    global selected_block
    
    # Сброс подсветки предыдущего
    if selected_block:
        selected_block.color = color.white 

    selected_block = entity
    selected_block.color = color.lime # Подсветка выделения
    update_ui_values()

# ================= UI ПАНЕЛЬ =================

def create_ui():
    global prop_panel, pos_inputs, rot_inputs, scale_inputs
    
    # Правая панель
    prop_panel = WindowPanel(
        title='Block Properties',
        content=[],
        position=(0.6, 0.45), # Сдвинем чуть левее, чтобы влезало
        scale=(0.3, 0.6),     # Чуть увеличим высоту
        color=color.rgba(0,0,0,150) # Полупрозрачный фон
    )
    
    # --- Кнопки действий ---
    # ВАЖНО: Добавляем текст в content, чтобы он занимал место
    prop_panel.content.append(Text(text="Actions:", scale=0.8, color=color.light_gray))
    
    action_row = Entity(parent=prop_panel, scale_y=0.05)
    # Кнопки делаем чуть меньше и аккуратнее
    Button(text='ADD', color=color.azure, scale=(0.25, 0.05), position=(-0.26, 0), parent=action_row, on_click=add_new_block)
    Button(text='DUP', color=color.orange, scale=(0.25, 0.05), position=(0.0, 0), parent=action_row, on_click=duplicate_selected)
    Button(text='DEL', color=color.red, scale=(0.25, 0.05), position=(0.26, 0), parent=action_row, on_click=delete_selected)
    prop_panel.content.append(action_row)

    # Отступ
    prop_panel.content.append(Entity(scale_y=0.01))

    # --- Поля ввода (Transform) ---
    def create_xyz_input(label):
        # Добавляем заголовок в контент
        prop_panel.content.append(Text(text=label, scale=0.8, color=color.light_gray))
        
        row = Entity(parent=prop_panel, scale_y=0.05)
        inputs = []
        for i, axis in enumerate(['x', 'y', 'z']):
            # Расставляем поля шире
            inp = InputField(default_value='0', limit_content_to='0123456789.-', 
                             position=((i-1)*0.28, 0), scale=(0.25, 0.05), parent=row)
            inp.text_entity.scale = 0.7 # Уменьшаем текст внутри поля, чтобы влезал
            inp.on_submit = apply_transform 
            inputs.append(inp)
        prop_panel.content.append(row)
        return inputs

    pos_inputs = create_xyz_input("Position (X, Y, Z)")
    rot_inputs = create_xyz_input("Rotation (X, Y, Z)")
    scale_inputs = create_xyz_input("Scale (X, Y, Z)")
    
    # Отступ
    prop_panel.content.append(Entity(scale_y=0.02))
    
    # Кнопка применения изменений (ИСПРАВЛЕНА ГИГАНТСКАЯ КНОПКА)
    # Оборачиваем кнопку в Entity-контейнер или задаем ей scale внутри списка, 
    # но надежнее просто добавить её как отдельный элемент с четким размером
    apply_btn = Button(text='Apply Transform', color=color.dark_gray, scale_y=0.05, height=0.05)
    apply_btn.on_click = apply_transform
    prop_panel.content.append(apply_btn)

    # --- Текстуры ---
    prop_panel.content.append(Entity(scale_y=0.02))
    prop_panel.content.append(Text(text="Textures:", scale=0.8, color=color.light_gray))
    
    tex_row = Entity(parent=prop_panel, scale_y=0.12) # Увеличим высоту контейнера текстур
    x_off = -0.3
    y_off = 0.02
    for i, tex in enumerate(available_textures):
        b = Button(parent=tex_row, text=tex, scale=(0.2, 0.04), position=(x_off, y_off), color=color.gray)
        b.text_entity.scale = 0.6
        b.on_click = Func(apply_texture, tex)
        x_off += 0.22
        if i == 2: # Перенос строки
            x_off = -0.3
            y_off = -0.05
    prop_panel.content.append(tex_row)

    # --- Save / Load ---
    prop_panel.content.append(Text(text="System:", scale=0.8, color=color.light_gray))
    sys_row = Entity(parent=prop_panel, scale_y=0.05)
    Button(text='SAVE', color=color.green, scale=(0.4, 0.05), position=(-0.22, 0), parent=sys_row, on_click=save_map)
    Button(text='LOAD', color=color.yellow, scale=(0.4, 0.05), position=(0.22, 0), parent=sys_row, on_click=load_map)
    prop_panel.content.append(sys_row)

def update_ui_values():
    if not selected_block: return
    try:
        # Position
        pos_inputs[0].text = str(round(selected_block.x, 2))
        pos_inputs[1].text = str(round(selected_block.y, 2))
        pos_inputs[2].text = str(round(selected_block.z, 2))
        # Rotation
        rot_inputs[0].text = str(round(selected_block.rotation_x, 2))
        rot_inputs[1].text = str(round(selected_block.rotation_y, 2))
        rot_inputs[2].text = str(round(selected_block.rotation_z, 2))
        # Scale
        scale_inputs[0].text = str(round(selected_block.scale_x, 2))
        scale_inputs[1].text = str(round(selected_block.scale_y, 2))
        scale_inputs[2].text = str(round(selected_block.scale_z, 2))
    except:
        pass

def apply_transform():
    if not selected_block: return
    try:
        selected_block.position = (float(pos_inputs[0].text), float(pos_inputs[1].text), float(pos_inputs[2].text))
        selected_block.rotation = (float(rot_inputs[0].text), float(rot_inputs[1].text), float(rot_inputs[2].text))
        selected_block.scale = (float(scale_inputs[0].text), float(scale_inputs[1].text), float(scale_inputs[2].text))
    except ValueError:
        print("Invalid input")

def apply_texture(tex_name):
    if selected_block:
        selected_block.texture = tex_name
        selected_block.texture_name = tex_name

# ================= SAVE / LOAD =================

def save_map():
    data = []
    for b in map_blocks:
        block_data = {
            'pos': [b.x, b.y, b.z],
            'rot': [b.rotation_x, b.rotation_y, b.rotation_z],
            'scale': [b.scale_x, b.scale_y, b.scale_z],
            'texture': getattr(b, 'texture_name', 'brick'),
            'color': [b.color.r, b.color.g, b.color.b, b.color.a] # Сохраняем цвет на всякий случай
        }
        data.append(block_data)
    
    with open('level_data.json', 'w') as f:
        json.dump(data, f)
    
    print_on_screen("Map Saved to level_data.json!", duration=2)

def load_map():
    global map_blocks, selected_block
    
    if not os.path.exists('level_data.json'):
        print_on_screen("No level_data.json found!", color=color.red)
        return

    # Очистка текущей сцены
    for b in map_blocks:
        destroy(b)
    map_blocks = []
    selected_block = None

    with open('level_data.json', 'r') as f:
        data = json.load(f)

    for d in data:
        # Восстанавливаем цвет (если он не лаймовый от выделения)
        col = color.rgba(d['color'][0]*255, d['color'][1]*255, d['color'][2]*255, d['color'][3]*255)
        # При загрузке сбрасываем лайм на белый, так как объект не выделен
        col = color.white 

        create_block(
            position=tuple(d['pos']),
            rotation=tuple(d['rot']),
            scale=tuple(d['scale']),
            texture_name=d['texture'],
            color_val=col
        )
    print_on_screen("Map Loaded!", duration=2)

# ================= ВВОД МЫШИ (RAYCAST) =================
def input(key):
    if key == 'left mouse down':
        # Не выделяем блоки, если кликнули по UI
        if mouse.hovered_entity and mouse.hovered_entity.parent == prop_panel:
            return

        hit = raycast(camera.world_position, camera.forward, distance=100)
        if hit.hit:
            if hit.entity in map_blocks:
                select_block(hit.entity)
        else:
            # Клик в пустоту - снятие выделения
            if selected_block:
                selected_block.color = color.white
                selected_block = None

# --- Инициализация ---
# Небо и земля для ориентира
Sky(color=color.rgb(50, 50, 70))
Entity(model='plane', scale=200, texture='floor', texture_scale=(40,40), color=color.dark_gray, collider='box')

create_ui()
add_new_block() # Создать один блок для старта

app.run()