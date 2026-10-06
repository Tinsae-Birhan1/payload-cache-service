from payload_cache.domain.transformer import UppercaseTransformer


async def test_uppercase_transformer() -> None:
    transformer = UppercaseTransformer()

    assert await transformer("first string") == "FIRST STRING"
