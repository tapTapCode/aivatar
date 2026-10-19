# Higgsfield presenter provider

Aivatar can use Higgsfield as its primary presenter provider. The renderer and scene timeline
remain provider-neutral; only the presenter adapter uploads the scene audio/reference image,
submits the Higgsfield job, polls it, downloads the MP4, and hands it back to FFmpeg.

## Configuration

Set these values in the server-side `.env` file. Never put the key in the desktop bundle or a
browser request:

```dotenv
HIGGSFIELD_API_KEY=key-id:secret
AIVATAR_PRESENTER_PROVIDER=authorized_higgsfield
HIGGSFIELD_MODEL=wan/v2.7/image-to-video
```

The default model is the documented Higgsfield image-to-video endpoint that accepts an
`audio_url`. The model path is configurable because the provider catalog changes. A reference
image is required on the selected avatar (`reference_image_path`).

The server uses Higgsfield's signed upload flow for the reference image and scene WAV, then polls
the returned request status URL. The API key is never returned by `/providers`, `/infrastructure`,
or the desktop app.

HeyGen remains registered as an explicit fallback/compatibility provider for existing avatars, but
new avatars default to `authorized_higgsfield`.

## Important limitation

Higgsfield's documented public API is model-specific. The default image-to-video model accepts
audio, but the public schema does not promise HeyGen-style phoneme-level lip synchronization. The
adapter therefore records the selected model in asset metadata and Aivatar's normal QC must verify
mouth motion, frame integrity, duration, and audio alignment before a production export is used.
