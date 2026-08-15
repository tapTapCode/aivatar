from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks import image_benchmark, lipsync_benchmark, video_benchmark
from benchmarks.attention_benchmark import not_tested_result
from benchmarks.common import load_adapter
from benchmarks.environment_capture import write_environment
from benchmarks.report_generator import generate_report


def parse_adapters(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        workload, separator, reference = value.partition("=")
        if not separator or workload not in {"image", "video", "lipsync"}:
            raise ValueError("--adapter must use image|video|lipsync=module:function")
        result[workload] = reference
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run reproducible GPU workload benchmarks")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--gpu-profile", default="rtx5090")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cold-runs", type=int, default=5)
    parser.add_argument("--warmup-runs", type=int, default=3)
    parser.add_argument("--measured-runs", type=int, default=30)
    parser.add_argument("--adapter", action="append", default=[])
    args = parser.parse_args()
    if min(args.cold_runs, args.warmup_runs, args.measured_runs) < 0:
        parser.error("run counts must not be negative")

    output_dir: Path = args.output_dir
    environment = write_environment(output_dir)
    adapters = parse_adapters(args.adapter)
    results: list[dict[str, object]] = []
    reasons: dict[str, str] = {}
    runners = {
        "image": image_benchmark.run,
        "video": video_benchmark.run,
        "lipsync": lipsync_benchmark.run,
    }
    for workload, runner in runners.items():
        reference = adapters.get(workload)
        if not environment.get("gpu_query"):
            reasons[workload] = "NVIDIA GPU/NVML environment was not observed on this host."
        elif not reference:
            reasons[workload] = "No pinned model benchmark adapter was provided."
        else:
            adapter = load_adapter(reference)
            results.extend(
                runner(
                    adapter,
                    device=args.device,
                    cold_runs=args.cold_runs,
                    warmup_runs=args.warmup_runs,
                    measured_runs=args.measured_runs,
                )
            )
    (output_dir / "attention-investigation.json").write_text(
        json.dumps(not_tested_result(), indent=2)
    )
    generate_report(
        output_dir,
        results,
        environment=environment,
        gpu_profile=args.gpu_profile,
        not_tested_reasons=reasons,
    )


if __name__ == "__main__":
    main()
