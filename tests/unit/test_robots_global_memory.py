import pytest

from agents.governance.rules.robots_checker import RobotsChecker
from shared.memory import GlobalMemory
from tests.unit.test_memory_tiers import FakeRedis


@pytest.mark.asyncio
async def test_robots_checker_syncs_fetched_robots_into_global_memory() -> None:
    redis = FakeRedis()
    memory = GlobalMemory(redis)
    checker = RobotsChecker(redis, global_memory=memory)
    robots_url = "https://www.jumia.ma/robots.txt"
    robots_txt = "User-agent: *\nDisallow: /admin"

    redis.values[f"robots:{robots_url}"] = robots_txt

    fetched = await checker._get_robots_txt(robots_url)

    assert fetched == robots_txt
    assert await memory.get_robots_txt("www.jumia.ma") == robots_txt
