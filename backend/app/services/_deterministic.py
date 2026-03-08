from __future__ import annotations

import hashlib


def stable_score(seed: str, *, floor: float = 0.0, ceiling: float = 1.0) -> float:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    ratio = int(digest[:8], 16) / 0xFFFFFFFF
    return floor + (ceiling - floor) * ratio

