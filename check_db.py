# Файл: C:\desk_top\check_db.py
import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в пути, чтобы найти src.config
root_dir = Path(__file__).parent
sys.path.append(str(root_dir))

from sqlalchemy.ext.asyncio import create_async_engine
from src.config import DATABASE_URL

async def check_connection():
    """Пытается установить соединение с базой данных."""
    print("--- Database Connection Test ---")
    if not DATABASE_URL or "None" in DATABASE_URL:
        print("ERROR: Database URL is not configured correctly in .env file.")
        return

    try:
        user_part, host_part = DATABASE_URL.split('@')
        user, _ = user_part.split('//')[1].split(':')
        masked_url = f"{user}@{host_part}"
        print(f"Attempting to connect to: {masked_url}")
    except Exception:
        print(f"Attempting to connect to an incorrectly formatted URL.")

    try:
        engine = create_async_engine(DATABASE_URL)
        async with engine.connect() as connection:
            print("\nSUCCESS: Connection to the database was successful!")
    except Exception as e:
        print("\nERROR: Failed to connect to the database.")
        print("-------")
        print(f"Details: {e}")
        print("-------")
        print("Possible reasons:")
        print("1. Is the PostgreSQL server running? (Check services.msc)")
        print("2. Are DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_NAME in your .env file correct?")
        print("3. Is a firewall blocking the connection on the specified port?")

    print("\n--- Test Finished ---")

if __name__ == "__main__":
    asyncio.run(check_connection())