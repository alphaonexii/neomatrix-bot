FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY step2_bot.py .

CMD ["python", "step2_bot.py"]