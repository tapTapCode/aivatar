# Free HeyGen proof workflow

HeyGen no longer includes free API credits. The supported zero-API-cost proof therefore uses
an operator-generated HeyGen web export and imports that MP4 into Exact Scene. The source
watermark is preserved; the application does not remove, crop, cover, or obscure it.

## Workflow

1. Generate a short proof in the authorized HeyGen web account.
2. Download the MP4 through HeyGen's normal export control.
3. Open **Presenter studio** in Exact Scene.
4. Upload the MP4 as **Presenter video** and confirm that its use is authorized.
5. Select **Use presenter video audio**.
6. Paste the matching transcript when captions are enabled.
7. Generate the Exact Scene output and download the resulting MP4.

Set the production worker configuration to:

```dotenv
PROVIDER_MODE=workers
AVATAR_VIDEO_PROVIDER=imported_video
```

The imported provider validates the video and embedded audio, records a checksum and private
provenance, extracts its audio for deterministic local FFmpeg composition, and preserves any
watermark in the source. No Docker model worker, RunPod GPU, or local avatar model is required
for this mode.

For clean production exports, switch `AVATAR_VIDEO_PROVIDER` to `heygen_api`, configure a
rotated server-side key and funded API wallet, and run a short paid canary before long-form use.
