# FlowDesk backend — FastAPI + runtime de scripts em subprocesso
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Dependencias de sistema:
# - libgl1 / libglib2.0-0: exigidas pelo opencv usado por rapidocr-onnxruntime (OCR)
# - curl: usado pelo healthcheck do compose
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

# Persistencia: o SQLite (flowdesk.db) vive dentro de storage/ via symlink, de modo
# que um unico volume montado em /app/storage guarda banco, uploads e outputs.
# O config aponta DB_PATH para /app/flowdesk.db; o symlink redireciona pro volume.
RUN ln -sf storage/flowdesk.db flowdesk.db

EXPOSE 8000

# Sem --reload em producao: o watcher do reload reiniciaria o servidor ao ver os
# scripts .py regravados pelo runtime a cada execucao (ver README).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
