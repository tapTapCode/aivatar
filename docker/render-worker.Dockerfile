# syntax=docker/dockerfile:1.7
FROM python:3.12.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 WORKER_KIND=render PORT=8080 PROVIDER_MODE=configured
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app
WORKDIR /app
COPY requirements/control-plane.txt ./requirements/control-plane.txt
RUN --mount=type=cache,target=/root/.cache/pip python -m pip install -r requirements/control-plane.txt
COPY --chown=app:app src ./src
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD curl -fsS http://127.0.0.1:8080/health || exit 1
CMD ["python", "-m", "src.workers.main"]

