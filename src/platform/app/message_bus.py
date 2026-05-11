from redis.asyncio import Redis

from app.config import settings

_redis: Redis | None = None


async def init_bus() -> None:
    global _redis
    _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    await _redis.ping()


async def close_bus() -> None:
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None


def bus() -> Redis:
    if _redis is None:
        raise RuntimeError("message bus not initialised")
    return _redis
