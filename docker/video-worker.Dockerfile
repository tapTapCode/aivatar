# syntax=docker/dockerfile:1.7
ARG CUDA_IMAGE=nvidia/cuda:12.9.1-cudnn-devel-ubuntu24.04
FROM ${CUDA_IMAGE}
ARG MODEL_ADAPTER=""
ARG MODEL_REVISION="PIN_REQUIRED"
LABEL org.opencontainers.image.description="Isolated LTX video worker" \
      ai.pipeline.model_revision="${MODEL_REVISION}"
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    WORKER_KIND=video PORT=8080 MODEL_ADAPTER=${MODEL_ADAPTER}
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3.12 python3-pip python3-venv ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app
WORKDIR /app
COPY requirements/control-plane.txt requirements/video-worker.txt ./requirements/
RUN --mount=type=cache,target=/root/.cache/pip python3.12 -m pip install --break-system-packages -r requirements/control-plane.txt -r requirements/video-worker.txt
COPY --chown=app:app src ./src
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=5 CMD curl -fsS http://127.0.0.1:8080/health || exit 1
CMD ["python3.12", "-m", "src.workers.main"]

