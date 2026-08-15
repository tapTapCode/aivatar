from __future__ import annotations

from typing import Any

CONFIGURATIONS = (
    "default_attention",
    "pytorch_sdpa",
    "flash_attention_compatible",
    "cached_prompt_embeddings",
    "cached_text_encoder_output",
    "cached_cross_attention_kv_when_valid",
    "torch_compile",
    "cuda_graphs",
    "quantized_weights",
    "cpu_offload",
)


def not_tested_result() -> dict[str, Any]:
    return {
        "status": "NOT TESTED",
        "configurations": list(CONFIGURATIONS),
        "paged_attention": {
            "result": (
                "NOT APPLICABLE unless a model implementation exposes a request-growing "
                "autoregressive KV cache"
            ),
            "reason": (
                "Do not equate diffusion/flow attention with vLLM token-KV paging. "
                "The pinned official "
                "implementation must be inspected and output equivalence tested first."
            ),
        },
    }
