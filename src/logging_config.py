# Файл: src/logging_config.py
import logging
import sys

def setup_logging():
    """
    Настраивает централизованное логирование для всего приложения.
    """
    # Определяем формат логов
    log_format = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    
    # Создаем обработчики
    stdout_handler = logging.StreamHandler(sys.stdout)
    file_handler = logging.FileHandler("bot_activity.log", mode='a', encoding='utf-8')
    
    # Устанавливаем базовую конфигурацию
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            stdout_handler,
            file_handler
        ]
    )
    
    # Устанавливаем более высокий уровень для "шумных" библиотек, если потребуется
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    logging.info("Logging configured successfully.")