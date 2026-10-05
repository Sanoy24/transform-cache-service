from transform_cache.transformer import SimulatedTransformer


async def test_uppercases_input() -> None:
    transformer = SimulatedTransformer(latency_seconds=0)

    assert await transformer.transform("first string") == "FIRST STRING"
