FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 10001 app && mkdir /data && chown app /data
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
USER app
EXPOSE 9000
# Один процесс: очередь живёт в памяти процесса + SQLite. Для масштабирования см. README.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
