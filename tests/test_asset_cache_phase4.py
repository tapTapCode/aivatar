from pathlib import Path

from pipeline.cache.assets import AssetCache, cache_key


def test_content_addressed_cache_reuses_identical_generation(tmp_path: Path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"same asset")
    cache = AssetCache(tmp_path / "cache")
    key1 = cache_key(kind="image", provider="flux", model="m", prompt="same prompt", parameters={"seed": 1})
    key2 = cache_key(kind="image", provider="flux", model="m", prompt=" same   prompt ", parameters={"seed": 1})
    assert key1 == key2
    cache.put(key1, source, {"provider": "flux"})
    hit = cache.get(key2)
    assert hit is not None
    destination = tmp_path / "project" / "asset.bin"
    cache.materialize(hit, destination)
    assert destination.read_bytes() == b"same asset"
    assert cache.peek(key1).metadata["hits"] == 1
