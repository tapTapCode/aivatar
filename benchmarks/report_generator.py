from __future__ import annotations

import csv
import json
import struct
import zlib
from pathlib import Path
from typing import Any

from benchmarks.common import summarize


def generate_report(
    output_dir: str | Path,
    results: list[dict[str, Any]],
    *,
    environment: dict[str, Any],
    gpu_profile: str,
    not_tested_reasons: dict[str, str],
) -> dict[str, Any]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    phases = sorted({(str(row["workload"]), str(row["phase"])) for row in results})
    summaries = {
        f"{workload} / {phase}": summarize(
            [row for row in results if row["workload"] == workload and row["phase"] == phase]
        )
        for workload, phase in phases
    }
    for workload, reason in not_tested_reasons.items():
        summaries.setdefault(
            f"{workload} / all phases",
            {"status": "NOT TESTED", "sample_count": 0, "reason": reason},
        )
    summary = {
        "gpu_profile": gpu_profile,
        "environment_gpu_query": environment.get("gpu_query"),
        "workloads": summaries,
        "maximum_definition": "highest_observed_seconds is only the maximum completed sample",
    }
    (target / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    with (target / "raw-results.jsonl").open("w") as handle:
        for result in results:
            handle.write(json.dumps(result, sort_keys=True) + "\n")
    _write_csv(target / "summary.csv", summaries)
    (target / "gpu-profile.json").write_text(
        json.dumps(
            {
                "requested_profile": gpu_profile,
                "observed_gpu": environment.get("gpu_query"),
                "match_status": _profile_match(gpu_profile, environment.get("gpu_query")),
            },
            indent=2,
        )
    )
    (target / "benchmark-report.md").write_text(_markdown(summary))
    values = {
        name: data.get("p50_seconds", 0)
        for name, data in summaries.items()
        if data.get("status") == "MEASURED"
    }
    _simple_bar_png(target / "latency-chart.png", values, color=(44, 123, 229))
    _simple_bar_png(target / "memory-chart.png", {}, color=(229, 107, 44))
    return summary


def _profile_match(profile: str, gpu_query: Any) -> str:
    if not gpu_query:
        return "NOT TESTED"
    expected = profile.lower().replace("rtx", "rtx ")
    return "VERIFIED" if expected in str(gpu_query).lower() else "MISMATCH"


def _write_csv(path: Path, summaries: dict[str, dict[str, Any]]) -> None:
    fields = [
        "workload",
        "status",
        "sample_count",
        "mean_seconds",
        "p50_seconds",
        "p90_seconds",
        "p95_seconds",
        "p99_seconds",
        "highest_observed_seconds",
        "successful_workloads_per_hour",
        "reason",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for workload, data in summaries.items():
            writer.writerow({"workload": workload, **data})


def _markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Benchmark Report",
        "",
        f"Requested GPU profile: `{summary['gpu_profile']}`",
        "",
        "No number in this report is an estimate. `highest_observed_seconds` is the highest "
        "completed sample, not a universal maximum.",
        "",
        "| Workload / phase | Status | Samples | p50 | p95 | p99 | Highest observed |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, data in summary["workloads"].items():
        lines.append(
            f"| {name} | {data.get('status')} | {data.get('sample_count', 0)} | "
            f"{_fmt(data.get('p50_seconds'))} | {_fmt(data.get('p95_seconds'))} | "
            f"{_fmt(data.get('p99_seconds'))} | {_fmt(data.get('highest_observed_seconds'))} |"
        )
        if data.get("reason"):
            lines.extend(("", f"{name}: {data['reason']}", ""))
    return "\n".join(lines) + "\n"


def _fmt(value: Any) -> str:
    return "—" if value is None else f"{float(value):.4f}s"


def _simple_bar_png(path: Path, values: dict[str, float], *, color: tuple[int, int, int]) -> None:
    width, height = 640, 360
    pixels = [[(250, 250, 250) for _ in range(width)] for _ in range(height)]
    if values:
        maximum = max(values.values()) or 1
        bar_width = max(20, (width - 80) // len(values) - 20)
        for index, value in enumerate(values.values()):
            bar_height = int((height - 80) * value / maximum)
            left = 50 + index * (bar_width + 20)
            for y in range(height - 40 - bar_height, height - 40):
                for x in range(left, min(width, left + bar_width)):
                    pixels[y][x] = color
    raw = b"".join(b"\x00" + b"".join(bytes(pixel) for pixel in row) for row in pixels)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
