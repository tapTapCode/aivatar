FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/tmp/huggingface \
    AIVATAR_MODEL_CACHE=/tmp/aivatar-models \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3-pip python3-venv git ffmpeg ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

# Production deployments should override LTX_REF with a reviewed commit SHA. The default tracks the
# official repository because Lightricks has not published a stable package/release channel for this stack.
ARG LTX_REF=main
RUN git clone --filter=blob:none https://github.com/Lightricks/LTX-2.git /opt/LTX-2 && \
    cd /opt/LTX-2 && git checkout "$LTX_REF" && \
    python3.12 -m pip install --break-system-packages uv && \
    uv sync --frozen && \
    .venv/bin/python -m pip install runpod==1.11.0 boto3==1.43.55 huggingface-hub>=0.35,<1

WORKDIR /worker
COPY worker.py .
CMD ["/opt/LTX-2/.venv/bin/python", "-u", "/worker/worker.py"]
