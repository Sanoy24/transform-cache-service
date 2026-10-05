import pytest
from pydantic import ValidationError

from transform_cache.config import Settings


def test_reads_prefixed_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CACHE_TRANSFORMER_LATENCY_SECONDS", "0.1")

    assert Settings().transformer_latency_seconds == 0.1


def test_rejects_negative_latency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CACHE_TRANSFORMER_LATENCY_SECONDS", "-1")

    with pytest.raises(ValidationError):
        Settings()
