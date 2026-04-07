import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request
from redis.asyncio import Redis

from app.config import settings


_WINDOWS: dict[str, deque[float]] = defaultdict(deque)
_redis_client: Redis | None = None


def _get_redis() -> Redis | None:
    global _redis_client
    if not settings.redis_url:
        return None
    if _redis_client is None:
        _redis_client = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    return _redis_client


def _allow(key: str, *, limit: int, window_sec: int) -> bool:
    now = time.time()
    q = _WINDOWS[key]
    while q and now - q[0] > window_sec:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


async def _allow_redis(key: str, *, limit: int, window_sec: int) -> bool:
    client = _get_redis()
    if client is None:
        return _allow(key, limit=limit, window_sec=window_sec)

    now_ms = int(time.time() * 1000)
    window_start = now_ms - (window_sec * 1000)
    member = f"{now_ms}:{key}"
    try:
        pipe = client.pipeline(transaction=True)
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zadd(key, {member: now_ms})
        pipe.zcard(key)
        pipe.expire(key, window_sec + 2)
        _, _, count, _ = await pipe.execute()
        return int(count) <= limit
    except Exception:
        if settings.rate_limit_fail_closed:
            return False
        # Fallback to in-memory limiter if Redis is temporarily unavailable.
        return _allow(key, limit=limit, window_sec=window_sec)


def rate_limit(*, limit: int, window_sec: int) -> Callable:
    async def _dep(req: Request) -> None:
        ip = req.client.host if req.client else "unknown"
        key = f"rl:{req.url.path}:{ip}"
        if not await _allow_redis(key, limit=limit, window_sec=window_sec):
            raise HTTPException(status_code=429, detail="Too many requests")

    return _dep
