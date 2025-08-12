# Файл: C:\desk_top\check_env.py
import os
from dotenv import load_dotenv

print("--- Environment Variable Check ---")

# Пытаемся загрузить .env файл из текущей директории
was_loaded = load_dotenv()
print(f"Was .env file found and loaded? -> {was_loaded}\n")

# Список переменных, которые мы ожидаем найти
vars_to_check = [
    "TELEGRAM_TOKEN",
    "OPENAI_API_KEY",
    "PINECONE_API_KEY",
    "DB_USER",
    "DB_PASS",
    "DB_HOST",
    "DB_PORT",
    "DB_NAME"
]

for var in vars_to_check:
    value = os.getenv(var)
    print(f"{var}: {value}")

print("--- End of Report ---")