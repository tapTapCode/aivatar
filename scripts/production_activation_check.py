#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path as _BootstrapPath

ROOT = _BootstrapPath(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import argparse
import json

from pipeline.activation.readiness import activation_status
from pipeline.storage.migrate import migrate


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether Aivatar is ready for the first real reference test.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()
    migrate()
    status = activation_status()
    if args.json:
        print(json.dumps(status, indent=2, default=str))
    else:
        print(f"Aivatar production activation: {status['readiness_percent']}%")
        for check in status["checks"]:
            mark = "READY" if check["ready"] else ("OPTIONAL" if not check["required"] else "BLOCKED")
            print(f"[{mark:8}] {check['label']}: {check['detail']}")
            if check.get("action") and not check["ready"]:
                print(f"           -> {check['action']}")
        print(f"\nNext milestone: {status['next_milestone']}")
    return 0 if status["ready_for_real_reference_test"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
