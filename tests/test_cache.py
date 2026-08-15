from src.orchestration.cache import generation_cache_key


def key(**updates: object) -> str:
    arguments = {
        "provider": "image",
        "model": "flux",
        "model_revision": "abc123",
        "prompt": "Ocean",
        "negative_prompt": None,
        "seed": 1,
        "width": 1024,
        "height": 1024,
        "steps": 4,
        "guidance": 1.0,
        "quantization": None,
        "settings": {"attention": "sdpa"},
    }
    arguments.update(updates)
    return generation_cache_key(**arguments)


def test_cache_key_is_deterministic() -> None:
    assert key() == key()


def test_cache_key_includes_model_settings() -> None:
    assert key(model_revision="rev2") != key()
    assert key(seed=2) != key()
    assert key(quantization="fp8") != key()
