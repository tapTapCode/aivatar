# Local AI presenter pipeline

## Architecture

```text
Presenter studio -> FastAPI -> queue -> Chatterbox worker -> MuseTalk worker
                 -> FFmpeg render worker -> owner-scoped MP4
```

The browser never receives model credentials. Uploads require an explicit rights confirmation,
are assigned randomized identifiers, are size limited, and are validated with `ffprobe` before
registration. FFmpeg and MuseTalk are invoked with argument arrays rather than shell strings.

## Selected models

| Stage | Model | Pinned source revision | License and use |
| --- | --- | --- | --- |
| TTS | Resemble AI Chatterbox 0.1.7 | `5de7a54aa4e5e2baadb0182dde554908b48b85c2` | MIT; upstream permits commercial self-hosting. Generated audio contains Chatterbox's imperceptible PerTh provenance watermark. |
| Lip sync | Tencent Music MuseTalk 1.5 | `0a89dec45a0192b824e3cf4daf96c239440c5ed8` | MIT code; upstream states its trained model may be used commercially. Every separately downloaded dependency/checkpoint must still be reviewed under its own license. |

MuseTalk was selected over LivePortrait as the production lip-sync default. LivePortrait's code
is MIT, but its upstream license warns that the bundled InsightFace models are non-commercial;
that makes the default distribution unsuitable for an unmodified commercial SaaS deployment.
LatentSync 1.6 remains an optional quality candidate but needs about 18 GB VRAM and is materially
slower than MuseTalk for long-form production.

Official references:

- <https://github.com/resemble-ai/chatterbox>
- <https://github.com/TMElyralab/MuseTalk>
- <https://github.com/bytedance/LatentSync>
- <https://github.com/KlingAIResearch/LivePortrait/blob/main/LICENSE>

## Runtime requirements

- Python 3.11 or 3.12 for the control plane and model workers
- FFmpeg/ffprobe
- NVIDIA CUDA GPU for production MuseTalk and Chatterbox inference
- Recommended: 24 GB VRAM, 32 GB system RAM, and 80 GB temporary/model disk
- Redis for durable multi-process queueing; local development can use the in-memory queue

MuseTalk's upstream reference reports 30 fps or better on a Tesla V100 and uses a 256x256 face
region. Actual throughput and quality must be benchmarked on the selected deployment GPU.

## Configuration

Copy `.env.example` to `.env` and set at minimum:

```dotenv
PROVIDER_MODE=workers
QUEUE_BACKEND=redis
CHATTERBOX_MODEL_ADAPTER=src.providers.local.chatterbox:create_chatterbox_provider
MUSETALK_MODEL_ADAPTER=src.providers.local.musetalk:create_musetalk_provider
CHATTERBOX_MODEL_REVISION=5de7a54aa4e5e2baadb0182dde554908b48b85c2
MUSETALK_MODEL_REVISION=0a89dec45a0192b824e3cf4daf96c239440c5ed8
VOICE_REGISTRY_ROOT=/data/voices
AVATAR_REGISTRY_ROOT=/data/avatars
MUSETALK_SOURCE_ROOT=/opt/MuseTalk
MUSETALK_MODELS_ROOT=/models
```

Install the official MuseTalk checkout at exactly the configured revision and download its
documented model tree beneath `MUSETALK_MODELS_ROOT`. Do not substitute unreviewed mirrors.

## Local verification

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
uvicorn src.api.main:app --host 127.0.0.1 --port 8001

# second terminal
cd frontend && npm install && npm run dev
```

Open <http://localhost:3000>, select **Create**, upload authorized media, and submit a
job. `PROVIDER_MODE=mock` produces a deterministic contract test. It does not exercise or claim
the visual quality of Chatterbox or MuseTalk.

## Supported output

- Aspect ratios: 16:9, 9:16, 1:1, 4:3 through the API, and 4:5
- Studio presets: 720p and 1080p
- Container: MP4
- Video/audio: H.264 and AAC by default
- Captions: burned-in SRT-derived captions or none

## Known limitations

- A single still presenter image can be prepared as a video input, but natural head, shoulder,
  and hand movement requires a user-owned motion clip. MuseTalk changes the face/lips; it does
  not invent full-body gestures.
- Uploaded backgrounds are validated and registered, but the current studio form does not yet
  route them into the scene compositor. Template solid backgrounds and the existing split/full
  visual contracts remain available through the project API.
- Production GPU inference was not run on this Mac. Only CPU/mock, API, FFmpeg, and adapter
  contract tests can be verified locally.
- The development media registry is in memory; production must replace it with persistent
  metadata and object storage before multi-instance deployment.
