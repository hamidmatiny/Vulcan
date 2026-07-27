# Ray Train CPU backend (ADR-009 / ADR-010).

Ray version pin matches `serving/ray-serve`: **`ray[train]>=2.52.0,<2.53`** (same CVE floor; do not introduce a second Ray pin).

```bash
pip install 'ray[train]>=2.52.0,<2.53' torch
PYTHONPATH=. python training/ray-train/train.py
make test-ray-train
```

Optional status port: **9011** (`VULCAN_RAY_TRAIN_PORT`).
