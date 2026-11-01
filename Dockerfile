# Базовый образ с Python 3.11
FROM python:3.11-slim

WORKDIR /app

# Ставим Python-библиотеки
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Скачиваем сам браузер Chromium и системные библиотеки для него
RUN playwright install --with-deps chromium

# Копируем код бота
COPY . .

CMD ["python", "bot.py"]
