# Файл: C:\desk_top\src\config.py
from dotenv import load_dotenv
import os
from pathlib import Path

env_path = Path(__file__).parent.parent / ".env"

if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    print(f"[Config] WARNING: .env file not found at: {env_path}")

# API Keys
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

# Database connection
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# --- НОВЫЙ КОД ---
# Encryption Key
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
# --- КОНЕЦ НОВОГО КОДА ---