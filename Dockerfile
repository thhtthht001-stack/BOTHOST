FROM python:3.11-slim

# Устанавливаем переменные окружения
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Фиксируем путь для браузеров Playwright
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Копируем и устанавливаем Python-зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем браузер Chromium и ВСЕ необходимые системные библиотеки.
# Флаг --only-shell устанавливает только headless-версию, что экономит место.
RUN playwright install --with-deps --only-shell chromium

# Копируем остальной код
COPY . .

CMD ["python", "bot.py"]
