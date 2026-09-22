FROM python:3.11-slim

# 巡检项依赖 procps（vmstat、free）和 coreutils（df、nproc），slim 镜像默认不带
RUN apt-get update \
    && apt-get install -y --no-install-recommends procps coreutils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV INSPECT_DB=/app/data/inspect.db
VOLUME ["/app/data"]

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
