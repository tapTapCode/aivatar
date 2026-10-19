from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.production.stress import run_three_project_concurrency

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=int, default=1)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "workspace" / "phase5-concurrency")
    args = parser.parse_args()
    print(json.dumps(run_three_project_concurrency(args.output_dir, minutes=args.minutes), indent=2))
