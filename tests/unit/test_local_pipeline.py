import pytest

from scripts.run_local_pipeline import run_pipeline


@pytest.mark.asyncio
async def test_local_pipeline_returns_addressable_response() -> None:
    result = await run_pipeline("Bghit Samsung phone b 3000 dh", user_id="telegram_123")

    assert result.products_count == 3
    assert result.top_score > 0
    assert result.outbound.user_id == "telegram_123"
    assert result.outbound.channel == "telegram"
    assert "Samsung" in result.outbound.message
    assert "Score:" in result.outbound.message
