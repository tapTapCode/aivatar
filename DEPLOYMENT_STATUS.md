# Deployment status

The React/Vite desktop UI can be previewed on Vercel as a static frontend. The Python
FastAPI renderer, FFmpeg workers, local database, and provider credentials remain
server-side and are not bundled into the frontend deployment.

For a fully functional hosted production deployment, point `VITE_AIVATAR_API` at a
separately deployed API with persistent storage, FFmpeg, and fresh provider secrets.
The Vercel preview is therefore a UI/product walkthrough, not a claim that cloud
rendering works without that backend.
