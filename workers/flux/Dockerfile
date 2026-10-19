FROM python:3.12-slim

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/tmp/huggingface \
    TRANSFORMERS_CACHE=/tmp/huggingface

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg git ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /worker
COPY requirements.txt .
RUN python -m pip install --upgrade pip && \
    python -m pip install torch==2.12.1 torchvision==0.27.1 --index-url https://download.pytorch.org/whl/cu130 && \
    python -m pip install -r requirements.txt
COPY worker.py .
CMD ["python", "-u", "worker.py"]
