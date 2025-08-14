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