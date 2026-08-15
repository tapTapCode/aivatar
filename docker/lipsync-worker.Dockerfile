# syntax=docker/dockerfile:1.7
ARG CUDA_IMAGE=nvidia/cuda:12.9.1-cudnn-devel-ubuntu24.04
FROM ${CUDA_IMAGE}
ARG MODEL_ADAPTER=""
ARG MODEL_REVISION="PIN_REQUIRED"
ARG MUSETALK_REPOSITORY=https://github.com/TMElyralab/MuseTalk.git
LABEL org.opencontainers.image.description="Isolated MuseTalk lip-sync worker" \
      ai.pipeline.model_revision="${MODEL_REVISION}"
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    WORKER_KIND=lipsync PORT=8080 MODEL_ADAPTER=${MODEL_ADAPTER}
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3.12 python3-pip python3-venv ffmpeg curl ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app
WORKDIR /app
COPY requirements/control-plane.txt requirements/lipsync-worker.txt ./requirements/
RUN --mount=type=cache,target=/root/.cache/pip python3.12 -m pip install --break-system-packages -r requirements/control-plane.txt -r requirements/lipsync-worker.txt
RUN test "${MODEL_REVISION}" != "PIN_REQUIRED" \
    && git clone --filter=blob:none --no-checkout "${MUSETALK_REPOSITORY}" /opt/MuseTalk \
    && git -C /opt/MuseTalk fetch --depth 1 origin "${MODEL_REVISION}" \
    && git -C /opt/MuseTalk checkout --detach FETCH_HEAD \
    && python3.12 -m pip install --break-system-packages -r /opt/MuseTalk/requirements.txt \
    && rm -rf /opt/MuseTalk/.git
COPY --chown=app:app src ./src
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=5 CMD curl -fsS http://127.0.0.1:8080/health || exit 1
CMD ["python3.12", "-m", "src.workers.main"]
