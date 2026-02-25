FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все Python-скрипты
COPY *.py .

# Запускаем новый файл с PvP
CMD ["python", "step3_bot.py"]