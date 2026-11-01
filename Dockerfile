FROM python:3.11-slim

# Устанавливаем переменные окружения для корректной работы Python в Docker
# (чтобы логи выводились сразу, а не копились в буфере)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем файл с Python-зависимостями
COPY requirements.txt .

# Устанавливаем Python-библиотеки
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем браузер Chromium и ВСЕ необходимые системные библиотеки для него
# Флаг --with-deps автоматически подтянет нужные пакеты Linux
RUN playwright install --with-deps chromium

# Копируем все остальные файлы проекта (bot.py, json файлы и т.д.)
COPY . .

# Команда для запуска бота
CMD ["python", "bot.py"]
