# Attention and Cache Investigation

Status: implementation-specific experiments `NOT TESTED` because pinned model source and GPU
environments are unavailable.

## Scientific boundary

Diffusion/flow denoising is not autoregressive token decoding. At each denoising step, latent-driven
queries/keys/values may change. A cache is valid only for tensors proven to depend solely on fixed
conditioning. Cached prompt embeddings or text-encoder outputs are distinct from reusable
cross-attention K/V, and all require output-equivalence tests.

The official FLUX.2 repository publicly identifies a specialized 9B KV variant and describes KV
caching for multi-reference image editing. That fact must not be generalized to the selected 4B
checkpoint or to LTX/MuseTalk. The pinned code for each candidate must be inspected module by module.

## Required inspection worksheet

For every attention module record:

1. module path and attention backend;
2. Q/K/V input dependencies (fixed text/reference versus changing latent);
3. tensor shape, dtype, device, and lifetime;
4. whether official code exposes a cache;
5. invalidation key and concurrency isolation;
6. baseline/cached output hashes and numeric difference;
7. recomputation avoided and cache bytes;
8. latency, allocated/reserved/NVML deltas; and
9. result: valid, invalid, unsupported, insignificant, or NOT TESTED.

## Configurations

The harness enumerates default attention, PyTorch SDPA, compatible FlashAttention, cached prompt
embeddings, cached text output, cross-attention K/V only when valid, `torch.compile`, CUDA graphs,
quantized weights, and CPU offload. Synchronize CUDA around timing and reset peaks for every run.

## PagedAttention

Current project result:

```text
Result: NOT APPLICABLE to a workload unless inspection finds an autoregressive,
request-growing token KV cache matching paged-token management assumptions.

Reason: installing vLLM does not make diffusion/flow attention a PagedAttention workload.
```

This is a workload-classification result, not a claim that all cache techniques are useless.
FLUX.2's specialized officially documented KV path must be evaluated on its own terms.

