import math
from datetime import datetime, timezone


def retention_probability(*, last_taught_at: datetime, stability: float, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    delta_days = max((now - last_taught_at).total_seconds() / 86400.0, 0.0)
    s = max(stability, 0.1)
    value = math.exp(-(delta_days / s))
    return max(0.0, min(1.0, value))

