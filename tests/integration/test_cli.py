import io
import json
from pathlib import Path

import httpx2
import pytest
from fastapi.testclient import TestClient

from tests.examples import SPEC_INPUT, SPEC_OUTPUT
from tests.fakes import CountingTransformer
from transform_cache import cli
from transform_cache.config import Settings
from transform_cache.main import create_app
from transform_cache.schemas import PayloadCreate


def test_repeated_runs_reuse_payload_and_cache(
    client: TestClient, transformer: CountingTransformer
) -> None:
    out = io.StringIO()

    cli.run(PayloadCreate.model_validate(SPEC_INPUT), 3, client, out)

    records = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [record["iteration"] for record in records] == [1, 2, 3]
    assert [record["status"] for record in records] == [201, 200, 200]
    assert len({record["id"] for record in records}) == 1
    assert all(record["output"] == SPEC_OUTPUT for record in records)
    assert len(transformer.calls) == 6


def test_main_end_to_end_writes_output_file(
    settings: Settings,
    transformer: CountingTransformer,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # main() builds and opens its own HTTP client; give it an unopened client
    # for the in-process app, so main() also runs the app's startup/shutdown.
    app = create_app(settings, transformer)
    monkeypatch.setattr(httpx2, "Client", lambda **_: TestClient(app))
    output = tmp_path / "result.jsonl"

    exit_code = cli.main(
        ["--json", json.dumps(SPEC_INPUT), "--repeat", "2", "--output", str(output)]
    )

    assert exit_code == 0
    lines = output.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["status"] for line in lines] == [201, 200]


def test_main_reports_invalid_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(["--repeat", "0", "--json", json.dumps(SPEC_INPUT)])

    assert exit_code == 2
    assert "cache-cli: error" in capsys.readouterr().err


def test_main_reports_unreadable_input(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    exit_code = cli.main(["--input", str(tmp_path / "missing.json")])

    assert exit_code == 2
    assert "cache-cli: error" in capsys.readouterr().err


def test_main_reports_connection_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused", request=request)

    real_client = httpx2.Client
    monkeypatch.setattr(
        httpx2,
        "Client",
        lambda **kwargs: real_client(transport=httpx2.MockTransport(refuse), **kwargs),
    )

    exit_code = cli.main(["--json", json.dumps(SPEC_INPUT)])

    assert exit_code == 1
    assert "cache-cli: request failed" in capsys.readouterr().err


def test_main_reads_stdin_and_writes_stdout(
    settings: Settings,
    transformer: CountingTransformer,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = create_app(settings, transformer)
    monkeypatch.setattr(httpx2, "Client", lambda **_: TestClient(app))
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(SPEC_INPUT)))

    exit_code = cli.main(["--input", "-", "--output", "-"])

    assert exit_code == 0
    [line] = capsys.readouterr().out.splitlines()
    assert json.loads(line)["output"] == SPEC_OUTPUT
