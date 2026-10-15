FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m bot && mkdir -p /data /app/logs && chown -R bot /data /app/logs
USER bot
ENV DB_PATH=/data/qcine.db
CMD ["python", "bot.py"]
