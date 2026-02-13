import flet as ft
import google.generativeai as genai
import random
import json
import os
import time
import asyncio
import re
from dotenv import load_dotenv


# ตรวจสอบ SDK
try:
    import google.generativeai as genai
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False

# ==============================================================================
# 1. CONFIGURATION & DATA LOADING
# ==============================================================================

# สั่งให้โหลดค่าจากไฟล์ .env ทันทีที่รัน
load_dotenv()

def get_api_keys():
    # 1. ลองดึงจากระบบปกติ (กรณีรันบนคอมพิวเตอร์)
    raw_keys = os.getenv("GEMINI_API_KEYS", "")
    
    # 2. ถ้าไม่เจอ (กรณีรันบนมือถือ) ให้เปิดไฟล์ api.env อ่านตรงๆ
    if not raw_keys and os.path.exists("api.env"):
        try:
            with open("api.env", "r") as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEYS="):
                        # แยกค่าหลังเครื่องหมายเท่ากับออกมา
                        raw_keys = line.split("=")[1].strip().strip('"').strip("'")
                        break
        except: 
            pass

    if raw_keys:
        return [k.strip() for k in raw_keys.split(",") if k.strip()]
    return []

# นำคีย์มาใช้ในโปรแกรม
API_KEYS = get_api_keys()
AI_MODEL_NAME = 'gemini-flash-latest' 

def load_json_file(filename):
    """โหลดไฟล์ JSON จาก Path"""
    base_path = os.path.dirname(__file__)
    paths_to_check = [filename, os.path.join(base_path, filename), os.path.join(base_path, "assets", filename)]
    
    for path in paths_to_check:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f: return json.load(f)
            except: continue
    return {}

def json_to_text(data):
    return json.dumps(data, ensure_ascii=False, indent=2)

def load_the_7th_sense_data():
    """โหลดข้อมูลอัตโนมัติจากไฟล์ JSON ทั้งหมด (Natural Sort)"""
    titles, contexts = {}, {}
    episodic_data = load_json_file("Episodic_Arc.json")
    
    if "episodic_arc" in episodic_data:
        blocks = episodic_data["episodic_arc"]
        
        def natural_sort_key(s):
            return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

        try:
            sorted_blocks = sorted(blocks.keys(), key=natural_sort_key)
        except:
            sorted_blocks = sorted(blocks.keys())

        chapter_index = 0
        for block_key in sorted_blocks:
            episodes = blocks[block_key].get("episodes", {})
            try:
                sorted_eps = sorted(episodes.keys(), key=natural_sort_key)
            except:
                sorted_eps = sorted(episodes.keys())
            
            for ep_key in sorted_eps:
                ep_data = episodes[ep_key]
                titles[chapter_index] = ep_data.get("title", f"Episode {chapter_index+1}")
                evt = ep_data.get('event', '-')
                kp = ep_data.get('key_point', '-')
                contexts[chapter_index] = f"Event: {evt}\nKey Point: {kp}"
                chapter_index += 1
                
    total_chapters = len(titles) if titles else 50
    
    info_world = json_to_text(load_json_file("World_Building.json"))
    info_chars = json_to_text(load_json_file("Characters.json"))
    info_protocols = json_to_text(load_json_file("Protocols.json"))
    info_basic = json_to_text(load_json_file("Basic_Story_Info.json"))
    info_storymap = json_to_text(load_json_file("Story_Map.json"))

    info_core = f"--- BASIC INFO ---\n{info_basic}\n\n--- STORY MAP ---\n{info_storymap}"
    info_write = f"--- PROTOCOLS & RULES ---\n{info_protocols}"

    return titles, contexts, total_chapters, info_core, info_world, info_chars, info_write

(MASTER_TITLES, MASTER_CONTEXTS, TOTAL_CHAPTERS, INFO_CORE, INFO_WORLD, INFO_CHARS, INFO_WRITE) = load_the_7th_sense_data()

def get_db_path():
    data_dir = os.getenv("FLET_APP_STORAGE_DATA") or os.getcwd()
    return os.path.join(data_dir, "story_db_7th_sense.json")

DB_FILENAME = get_db_path() 
story_data = {}

# ==============================================================================
# 2. DATABASE SYSTEM
# ==============================================================================

def save_db_to_file():
    try:
        with open(DB_FILENAME, "w", encoding="utf-8") as f:
            json.dump(story_data, f, ensure_ascii=False, indent=4)
    except: pass

def init_db():
    global story_data
    raw_data = {}
    if os.path.exists(DB_FILENAME):
        try:
            with open(DB_FILENAME, "r", encoding="utf-8") as f: raw_data = json.load(f)
        except: pass

    for i in range(TOTAL_CHAPTERS):
        key = str(i)
        story_data[key] = raw_data.get(key, {"p1": "", "p2": "", "p3": ""})
        story_data[key]["t"] = MASTER_TITLES.get(i, f"Episode {i+1}")
        story_data[key]["ctx"] = MASTER_CONTEXTS.get(i, "")
    save_db_to_file()

def clean_narrative(text):
    if not text: return ""
    text = re.sub(r'^(#+|บทที่|ตอนที่|Chapter|Ch\.|PART|Episode|ตอน)\s*\d+.*$', '', text, flags=re.MULTILINE)
    text = text.replace('**', '').replace('*', '')
    return text.strip()

# ==============================================================================
# 3. UI APPLICATION
# ==============================================================================

async def main(page: ft.Page):
    init_db()
    page.title = "The 7th Sense: Editor 🔮"
    page.theme_mode = "dark" 
    page.scroll = "auto"
    page.window_width = 500
    page.window_height = 950
    page.padding = 20
    page.theme = ft.Theme(font_family="Sarabun")

    state = {"running": False, "start_time": 0, "is_loading": False, "current_key": 0}
    
    # --- ส่วนที่เพิ่มกลับมาตามคำขอ (Theme & Read Mode) ---
    btn_theme = ft.ElevatedButton(
        content=ft.Row([ft.Text("🌗"), ft.Text("Theme")], alignment="center"),
        on_click=lambda _: setattr(page, "theme_mode", "light" if page.theme_mode == "dark" else "dark") or page.update()
    )
    
    sw_read_mode = ft.Switch(label="Read Mode 📖", value=False)
    # --------------------------------------------------

    header_text = ft.Text("The 7th Sense: สัมผัสรัก สัมผัสลับ 🔮", size=24, weight="bold", color="purple200", text_align="center")
    sub_header = ft.Text("System: Aternium Interface ⚙️", size=14, color="grey")
    status_text = ft.Text("Ready", size=14, color="green")
    status_icon = ft.Text("✅", size=24)
    status_bar = ft.ProgressBar(width=400, color="purple", value=0)

    # Input Fields
    txt_title = ft.TextField(label="Episode Title 📌", read_only=True, filled=True, text_style=ft.TextStyle(weight="bold", color="amber200"))
    txt_extra_context = ft.TextField(label="Context / Plot Point (จาก Episodic Arc) 📝", multiline=True, min_lines=3, read_only=True, filled=True)
    
    txt_p1 = ft.TextField(label="PART 1: The Beginning 🎬", multiline=True, min_lines=8)
    txt_p2 = ft.TextField(label="PART 2: The Development ⚡", multiline=True, min_lines=8)
    txt_p3 = ft.TextField(label="PART 3: The Conclusion 🏁", multiline=True, min_lines=8)
    
    ui_inputs = [txt_p1, txt_p2, txt_p3]
    
    # ผูก Read Mode
    sw_read_mode.on_change = lambda e: [setattr(tf, "read_only", e.control.value) or tf.update() for tf in ui_inputs]

    def load_ui_from_memory(idx):
        state["is_loading"] = True
        key_str = str(idx)
        data = story_data[key_str]
        
        txt_title.value = f"EP.{idx+1}: {data['t']}"
        txt_extra_context.value = data['ctx']
        txt_p1.value = data.get('p1', '')
        txt_p2.value = data.get('p2', '')
        txt_p3.value = data.get('p3', '')
        
        txt_chap_num_display.value = str(idx + 1)
        state["current_key"] = idx
        state["is_loading"] = False
        page.update()

    txt_chap_num_display = ft.TextField(value="1", width=60, text_align="center", read_only=True)
    
    # ใช้ไอคอนแบบ String เพื่อความปลอดภัย
    chapter_controls = ft.Row([
        ft.ElevatedButton(" Prev", icon="arrow_back", on_click=lambda _: load_ui_from_memory(max(0, state["current_key"]-1))),
        txt_chap_num_display,
        ft.ElevatedButton("Next ", icon="arrow_forward", icon_color="white", on_click=lambda _: load_ui_from_memory(min(TOTAL_CHAPTERS-1, state["current_key"]+1)))
    ], alignment="center")

    def clear_screen_view():
        txt_p1.value = ""
        txt_p2.value = ""
        txt_p3.value = ""
        status_text.value = "ล้างหน้าจอแสดงผลแล้ว"; status_text.color = "amber"
        page.update()

    async def run_ai_task(part_idx):
        if not SDK_AVAILABLE or state["running"]: return
        if not API_KEYS:
            status_text.value = "Error: API Key missing"; status_text.color = "red"; page.update(); return
        
        state["running"] = True
        state["start_time"] = time.time()
        status_bar.value = None
        status_icon.value = "🔮"
        
        async def run_timer():
            while state["running"]:
                elapsed = time.time() - state["start_time"]
                status_text.value = f"กำลังเชื่อมต่อสัมผัสที่ 7... ({elapsed:.1f}s)"
                status_text.update(); await asyncio.sleep(0.1)
        
        timer_task = asyncio.create_task(run_timer())
        current_k = state["current_key"]
        
        prev_text = ""
        if part_idx == 2: prev_text = f"CONTINUE FROM PART 1: {txt_p1.value[-2500:]}"
        elif part_idx == 3: prev_text = f"CONTINUE FROM PART 2: {txt_p2.value[-2500:]}"

        try:
            prompt = (
                f"*** SYSTEM: THE 7TH SENSE NOVEL ENGINE ***\n"
                f"{INFO_WRITE}\n\n"
                f"*** DATABASE ***\n{INFO_CORE}\n{INFO_CHARS}\n{INFO_WORLD}\n"
                f"--------------------------------------------------\n"
                f"CURRENT EPISODE: {current_k+1} | TITLE: {txt_title.value}\n"
                f"SCENE EVENT: {txt_extra_context.value}\n"
                f"PREVIOUS CONTEXT: {prev_text}\n"
                f"--------------------------------------------------\n"
                f"TASK: เขียนเนื้อเรื่อง PART {part_idx}/3 โดยอ้างอิงข้อมูลจากฐานข้อมูลอย่างเคร่งครัด\n"
                f"เริ่มการบรรยาย:"
            )
            
            genai.configure(api_key=random.choice(API_KEYS))
            model = genai.GenerativeModel(AI_MODEL_NAME)
            res = await asyncio.to_thread(model.generate_content, prompt, 
                                          generation_config=genai.types.GenerationConfig(temperature=0.7, max_output_tokens=3500))
            
            final_text = clean_narrative(res.text)
            if part_idx == 1: txt_p1.value = final_text
            elif part_idx == 2: txt_p2.value = final_text
            elif part_idx == 3: txt_p3.value = final_text
            
            story_data[str(current_k)][f"p{part_idx}"] = final_text
            status_text.value = "บันทึกสัมผัสสำเร็จแล้ว ✨"; status_text.color = "purple"
        except Exception as e:
            status_text.value = f"Error: {e}"; status_text.color = "red"
        
        state["running"] = False
        status_bar.value = 0
        await timer_task
        save_db_to_file(); page.update()

    def create_block(title, ctrl, idx):
        return ft.Card(content=ft.Container(content=ft.Column([
            ft.Row([
                ft.Text(title, weight="bold", color="purple100"), 
                ft.ElevatedButton("⚡ เขียนเนื้อหา", icon="auto_awesome", on_click=lambda _: asyncio.create_task(run_ai_task(idx)))
            ], alignment="spaceBetween"),
            ctrl
        ]), padding=10))

    page.add(
        ft.Column([
            # แถวบนสุด (เพิ่มคืนมาให้แล้ว)
            ft.Row([sw_read_mode, btn_theme], alignment="spaceBetween"),
            
            header_text, 
            ft.Row([sub_header], alignment="center"),
            ft.Row([status_icon, status_text], alignment="center"),
            status_bar,
            ft.Divider(height=20, color="transparent"),
            
            ft.Card(content=ft.Container(content=ft.Column([
                chapter_controls, 
                ft.Row([
                    # ปุ่ม Clear และ Save ตามชื่อที่ระบุ
                    ft.ElevatedButton("🧹 Clear", bgcolor="orange800", color="white", expand=True, on_click=lambda _: clear_screen_view()),
                    ft.ElevatedButton("💾 Save", bgcolor="blue800", color="white", expand=True, on_click=lambda _: save_db_to_file())
                ]),
                txt_title, 
                txt_extra_context
            ]), padding=15)),
            
            create_block("PART 1: The Beginning", txt_p1, 1),
            create_block("PART 2: The Development", txt_p2, 2),
            create_block("PART 3: The Conclusion", txt_p3, 3),
            
            ft.Container(height=30)
        ], horizontal_alignment="center")
    )
    load_ui_from_memory(0)

if __name__ == "__main__":
    ft.app(target=main)
