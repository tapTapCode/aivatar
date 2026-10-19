# Aivatar Production Activation

The next milestone is not another architecture phase. It is **Real Reference Test #1**: one 60–90 second video using authorized real providers and the reference-documentary production profile.

## Security gate first

The supplied WhatsApp archive contained credentials. Do not copy those historical values into `.env`.

1. Rotate the exposed AI33/HeyGen/account credentials at the providers.
2. Create fresh least-privilege credentials for Aivatar.
3. Copy `.env.example` to `.env` and enter only the fresh values.
4. Set `AIVATAR_ARCHIVE_CREDENTIALS_ROTATED=true` only after rotation is complete.

Aivatar's activation checker intentionally treats this as a blocking production requirement.

## Mac bootstrap

From the source directory on macOS:

```bash
./scripts/bootstrap_macos.sh
cp .env.example .env
```

Configure the fresh provider values in `.env`, then run:

```bash
python3 scripts/production_activation_check.py
```

The first real run should not start until all required checks report `READY`.

## Required production services

- AI33 Pro or 69Labs: authoritative narration
- Authorized HeyGen: primary presenter
- Cloudflare R2: persistent project media
- RunPod Serverless FLUX endpoint
- RunPod Serverless LTX endpoint
- Hugging Face token for worker model acquisition where required

MuseTalk remains an optional fallback and is not a blocker for the first real HeyGen test.

## Create the reference-test project

With the provider setup complete:

```bash
python3 scripts/create_reference_test_project.py \
  --channel "Reference Channel 01" \
  --avatar-name "Presenter 01" \
  --provider-avatar-id "<AUTHORIZED_HEYGEN_AVATAR_ID>" \
  --reference-image "/absolute/path/to/presenter-reference.png" \
  --duration 75 \
  --voice-provider ai33
```

Use `--script-file /path/to/test-script.txt` when a specific reference-test script is available.

## Reference profile

`reference_documentary_v1` encodes the currently agreed production format:

- 30% presenter target
- PRESENTER / SPLIT / FULL_VISUAL core formats
- 40/60 default split with 50/50 and 35/65 available
- PIP support
- cache -> motion graphic -> FLUX + local motion -> selective LTX
- one authoritative master narration timeline
- 1080p 16:9 default

This profile is deliberately marked as a **baseline**, not a claim of exact reference matching. The first real output must be reviewed side-by-side against one selected reference video, then the profile/Director should be tuned from that evidence.

## Build the desktop app locally

```bash
./scripts/build_macos_app.sh
```

The production package bundles the Python API as a sidecar. An unsigned local build is enough for the first internal test. Apple Developer ID signing/notarization is a release step after the real provider workflow is validated.

## Real Reference Test #1 acceptance gate

The 60–90 second test is accepted only if all of these are true:

- master narration remains continuous and authoritative
- presenter appears close to the 30% target
- only exact presenter audio segments are sent to HeyGen
- presenter-returned audio is not used in the final mix
- B-roll actually supports the spoken content
- FLUX stills use local motion where that is sufficient
- LTX is used selectively when real motion adds value
- SPLIT/PIP feel intentional rather than decorative
- captions are synchronized
- no gaps/overlaps/corrupt scenes
- final MP4 passes QC
- actual provider/GPU costs are recorded

After that passes, scale the **real provider** test through 5 -> 10 -> 30–40 minutes.
