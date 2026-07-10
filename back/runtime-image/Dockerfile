FROM python:3.11-slim

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# flowdesk_sdk e o script do projeto são montados em /src em runtime.
WORKDIR /run
USER 65534:65534
