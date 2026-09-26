# CUAVerifierBench

This lane tracks the Stage 1 verifier regression suite.

`stage1-manifest.json` records the pinning and evidence requirements before CI enforcement. Target dependency: `microsoft/fara` CUAVerifierBench, pinned to a reviewed commit before scoring. The harness verifier adapter boundary is already in `controller/app/harness/verifier/uv.py`.
