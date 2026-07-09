# Imagem de runtime para o sandbox de execução (S1 parte 2).
# Build (a partir de back/):
#   docker build -f runtime.Dockerfile -t flowdesk-runtime:local .
FROM python:3.11-slim

# libs de sistema exigidas por opencv (rapidocr-onnxruntime) e afins
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# usuário não-root para rodar os scripts
RUN useradd --uid 1000 --create-home runner
WORKDIR /project
USER 1000:1000
