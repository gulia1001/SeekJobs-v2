FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# collect once at start, then every COLLECT_EVERY_SECONDS (default: 24 hours)
CMD ["sh", "-c", "while true; do python run_daily.py; sleep ${COLLECT_EVERY_SECONDS:-86400}; done"]
