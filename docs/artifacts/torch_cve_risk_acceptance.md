# torch CVE Risk Acceptance

## Status: ACCEPTED — Platform Limitation

**Package:** `torch 2.2.2`
**Affected advisories:**

| ID | Fix version | Description |
|---|---|---|
| PYSEC-2025-41 | 2.6.0 | Pickle deserialization arbitrary code execution |
| PYSEC-2024-259 | 2.5.0 | Deserialization vulnerability |
| CVE-2025-2953 | 2.7.1rc1 | Out-of-bounds read in CUDA kernels |
| CVE-2025-3730 | 2.8.0 | Memory corruption in distributed operations |

## Why not upgraded

PyPI and the PyTorch CPU wheel index (`https://download.pytorch.org/whl/cpu`) only publish `torch 2.2.2` for **macOS x86_64** (Intel). No wheel for torch >= 2.5 exists for this target. Confirmed on both Python 3.10 and 3.12.

```
ERROR: No matching distribution found for torch>=2.6.0
```

## Mitigations in place

- torch is used only for local embedding inference (sentence-transformers); it is not exposed directly to untrusted network input.
- The pickle deserialization CVEs are exploitable only if loading model files from untrusted sources. openZero loads only locally-cached HuggingFace models.
- CUDA CVEs: non-applicable — deployment target is CPU-only (no GPU on VPS).

## Resolution path

Monitor PyPI for `torch >= 2.5` macOS x86_64 wheels. When available, upgrade with:

```bash
pip install --upgrade "torch>=2.5.0"
```

Then re-run `pip-audit --local` to confirm clearance.

## Date accepted

2026-04-17
