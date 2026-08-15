from __future__ import annotations

import threading
from collections import defaultdict


class MetricsRegistry:
    """Dependency-light Prometheus text exporter for core counters and gauges."""

    def __init__(self) -> None:
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()

    def increment(self, name: str, value: float = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def render(self) -> str:
        with self._lock:
            lines: list[str] = []
            for name, value in sorted(self._counters.items()):
                lines.extend((f"# TYPE {name} counter", f"{name} {value}"))
            for name, value in sorted(self._gauges.items()):
                lines.extend((f"# TYPE {name} gauge", f"{name} {value}"))
            return "\n".join(lines) + "\n"
