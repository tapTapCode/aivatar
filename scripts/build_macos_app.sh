#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

command -v rustc >/dev/null || { echo "Rust is required: https://rustup.rs" >&2; exit 1; }
command -v pnpm >/dev/null || { echo "pnpm is required (corepack enable && corepack prepare pnpm@latest --activate)" >&2; exit 1; }
command -v ffmpeg >/dev/null || { echo "FFmpeg is required" >&2; exit 1; }

python3 scripts/build_macos_sidecar.py
cd apps/desktop
pnpm install
pnpm tauri build --bundles app,dmg
