from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class WordTimestamp:
    word: str
    start: float
    end: float


@dataclass(slots=True)
class CaptionSegment:
    text: str
    start: float
    end: float


_WORD_RE = re.compile(r"\S+")


def _weight(word: str) -> float:
    # Punctuation receives a little extra time so the deterministic fallback reads naturally.
    base = max(1.0, len(re.sub(r"[^\w]", "", word)) ** 0.45)
    if word.endswith((".", "!", "?")):
        base += 0.8
    elif word.endswith((",", ";", ":")):
        base += 0.35
    return base


def align_script_heuristic(script: str, duration: float) -> list[WordTimestamp]:
    """Create duration-correct word timestamps without an ML aligner.

    This is the mandatory offline fallback for mock/imported audio. Real providers may supply
    their own word timings, which should be preferred when available.
    """
    if duration <= 0:
        raise ValueError("duration must be positive")
    words = _WORD_RE.findall(script.strip())
    if not words:
        return []
    weights = [_weight(w) for w in words]
    scale = duration / sum(weights)
    out: list[WordTimestamp] = []
    cursor = 0.0
    for index, (word, weight) in enumerate(zip(words, weights, strict=True)):
        end = duration if index == len(words) - 1 else min(duration, cursor + weight * scale)
        out.append(WordTimestamp(word=word, start=round(cursor, 3), end=round(end, 3)))
        cursor = end
    return out


def normalize_provider_timestamps(items: list[dict], duration: float) -> list[WordTimestamp]:
    """Normalize provider timestamps into Aivatar's canonical seconds-based format."""
    normalized: list[WordTimestamp] = []
    for item in items:
        word = str(item.get("word") or item.get("text") or "").strip()
        if not word:
            continue
        start = float(item.get("start", item.get("start_time", 0.0)))
        end = float(item.get("end", item.get("end_time", start)))
        # Some APIs report milliseconds. Detect safely using the known narration duration.
        if duration > 0 and max(start, end) > duration * 10:
            start /= 1000.0
            end /= 1000.0
        normalized.append(WordTimestamp(word, round(max(0.0, start), 3), round(min(duration, end), 3)))
    if not normalized:
        return []
    normalized.sort(key=lambda x: (x.start, x.end))
    if normalized[-1].end > duration + 0.05:
        raise ValueError("provider timestamps exceed narration duration")
    return normalized


def caption_segments(words: list[WordTimestamp], max_words: int = 8, max_duration: float = 4.0) -> list[CaptionSegment]:
    if not words:
        return []
    segments: list[CaptionSegment] = []
    bucket: list[WordTimestamp] = []
    for word in words:
        bucket.append(word)
        duration = bucket[-1].end - bucket[0].start
        sentence_end = word.word.endswith((".", "!", "?"))
        if len(bucket) >= max_words or duration >= max_duration or sentence_end:
            segments.append(CaptionSegment(" ".join(w.word for w in bucket), bucket[0].start, bucket[-1].end))
            bucket = []
    if bucket:
        segments.append(CaptionSegment(" ".join(w.word for w in bucket), bucket[0].start, bucket[-1].end))
    return segments


def save_timestamps(path: Path, words: list[WordTimestamp], source: str, duration: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": source,
        "duration": duration,
        "words": [asdict(w) for w in words],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
