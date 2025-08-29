from __future__ import annotations

"""Deterministic synthetic validation metrics for demo/offline mode.

Seeded by alarm ID so screenshots / tests are stable across runs and platforms.
"""

import hashlib
import random
from typing import Dict, Any


def synth_metrics(alarm_id: str) -> Dict[str, Any]:
    seed = int(hashlib.sha256(alarm_id.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    ok = rng.random() < 0.8  # 80% pass
    ping_loss = 0.0 if ok else rng.choice([0.25, 1.0])
    rtt_ms = round(rng.uniform(2, 60), 1) if ok else None
    hop_count = rng.randint(2, 6)
    hops = [f"198.51.{i}.{rng.randint(1,254)}" for i in range(hop_count)]
    last_hop = hops[-1]
    return {
        "ping_loss": ping_loss,
        "rtt_ms": rtt_ms,
        "traceroute_hops": hops,
        "traceroute_last_hop": last_hop,
        "status": "ok" if ok else "fail",
    }


__all__ = ["synth_metrics"]
