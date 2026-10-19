#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This bootstrap script is for macOS." >&2
  exit 1
fi

if ! command -v brew >/dev/null; then
  echo "Homebrew is required. Install it from brew.sh, then rerun this script." >&2
  exit 1
fi

brew install git node pnpm rust python@3.12 ffmpeg sqlite
python3 -m pip install --upgrade "huggingface_hub[cli]"
python3 -m pip install --upgrade pip
python3 -m pip install -e '.[dev]'
echo "Aivatar macOS prerequisites installed. Docker Desktop is still installed separately if GPU-worker image development is needed."
