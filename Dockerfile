FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/storage/recibos && chmod +x start.sh
EXPOSE 8181
# En Railway el puerto real lo define $PORT (ver start.sh). start.sh corre
# migraciones antes de levantar uvicorn.
CMD ["sh", "start.sh"]
