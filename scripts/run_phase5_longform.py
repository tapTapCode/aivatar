from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.production.longform import assemble_longform_proof

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=int, default=30)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "workspace" / "phase5-longform")
    args = parser.parse_args()
    print(json.dumps(assemble_longform_proof(args.output_dir, args.minutes), indent=2))
