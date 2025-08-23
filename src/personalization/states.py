# Файл: C:\desk_top\src\personalization\states.py
from aiogram.fsm.state import State, StatesGroup

class Personalization(StatesGroup):
    choosing_profile = State()
    coder_interview_q1 = State()
    product_manager_interview_q1 = State()
    personal_assistant_interview_q1 = State()

# --- НОВЫЙ КОД ---
class DataManagement(StatesGroup):
    confirming_deletion = State()
# --- КОНЕЦ НОВОГО КОДА ---

# --- НОВЫЙ КОД: Проекты (FSM /new_project) ---
class NewProject(StatesGroup):
    entering_name = State()
    entering_goal = State()
    entering_context = State()
    choosing_mode = State()
    confirming = State()
# --- КОНЕЦ НОВОГО КОДА ---