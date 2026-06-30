FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV SEEG_PROTECT_HOST=0.0.0.0
ENV SEEG_PROTECT_PORT=8000
ENV SEEG_PROTECT_DB=/app/data/seeg_protect.sqlite3
ENV SEEG_PROTECT_EVENT_LOG=/app/data/events.jsonl
ENV SEEG_PROTECT_SMS_OUTBOX=/app/data/sms_outbox.jsonl

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "-m", "seeg_protect.app"]
