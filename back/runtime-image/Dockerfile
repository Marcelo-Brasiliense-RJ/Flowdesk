FROM python:3.11-slim

# I2: LibreOffice headless para converter .xls fora do padrão sem Excel COM (portável,
# roda em Linux). Substitui o acoplamento a Windows+Office do read_table legado.
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-calc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# flowdesk_sdk e o script do projeto são montados em /src em runtime.
WORKDIR /run
USER 65534:65534
