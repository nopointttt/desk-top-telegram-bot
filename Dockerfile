# Файл: Dockerfile

# --- ЭТАП 1: Установка зависимостей ---
# Используем официальный, легковесный образ Python
FROM python:3.11-slim as builder

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем только файл с зависимостями
COPY requirements.txt .

# Устанавливаем зависимости в отдельный слой, чтобы Docker кэшировал их
# Это ускорит последующие сборки, если зависимости не менялись
RUN pip install --no-cache-dir -r requirements.txt

# --- ЭТАП 2: Сборка финального образа ---
# Используем тот же базовый образ для чистоты
FROM python:3.11-slim

WORKDIR /app

# Копируем установленные зависимости из этапа 'builder'
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Копируем исходный код нашего приложения
COPY src/ ./src/
COPY run.py .

# Указываем команду, которая будет выполняться при запуске контейнера
CMD ["python", "run.py"]