FROM nvidia/cuda:12.8.1-runtime-ubuntu24.04
ENV DEBIAN_FRONTEND=noninteractive PIP_BREAK_SYSTEM_PACKAGES=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip git ffmpeg wget ca-certificates && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 https://github.com/TMElyralab/MuseTalk.git /opt/MuseTalk
WORKDIR /opt/MuseTalk
RUN python3 -m pip install --no-cache-dir -r requirements.txt && python3 -m pip install --no-cache-dir runpod==1.11.0 boto3
COPY worker.py /worker/worker.py
ENV MUSETALK_REPO=/opt/MuseTalk
CMD ["python3", "/worker/worker.py"]
