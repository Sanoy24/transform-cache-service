import io
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from transform_cache.cli import parse_args, read_body

BODY = json.dumps({"list_1": ["a"], "list_2": ["b"]})


def test_defaults() -> None:
    args = parse_args(["--json", BODY])

    assert str(args.host) == "http://127.0.0.1:8000/"
    assert args.repeat == 1
    assert args.output == "-"


def test_short_flags() -> None:
    args = parse_args(
        ["-h", "http://example.com:9000", "-r", "3", "-i", "-", "-o", "x"]
    )

    assert str(args.host) == "http://example.com:9000/"
    assert args.repeat == 3
    assert args.input == "-"
    assert args.output == "x"


def test_json_short_flag() -> None:
    assert parse_args(["-j", BODY]).json_input == BODY


def test_help_is_long_flag_only(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        parse_args(["--help"])

    assert exit_info.value.code == 0
    assert "--host, -h" in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--json", BODY, "--input", "-"],
        ["--json", BODY, "--repeat", "0"],
        ["--json", BODY, "--host", "not a url"],
        ["--json", BODY, "--host", "ftp://example.com"],
    ],
    ids=["no-body", "two-bodies", "zero-repeat", "malformed-host", "non-http-host"],
)
def test_rejects_invalid_arguments(argv: list[str]) -> None:
    with pytest.raises(ValidationError):
        parse_args(argv)


def test_ignores_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOST", "http://from-env:1")
    monkeypatch.setenv("REPEAT", "7")

    args = parse_args(["--json", BODY])

    assert str(args.host) == "http://127.0.0.1:8000/"
    assert args.repeat == 1


def test_reads_body_from_json_argument() -> None:
    body = read_body(parse_args(["--json", BODY]), io.StringIO())

    assert body.list_1 == ["a"]
    assert body.list_2 == ["b"]


def test_reads_body_from_stdin() -> None:
    body = read_body(parse_args(["--input", "-"]), io.StringIO(BODY))

    assert body.list_1 == ["a"]


def test_reads_body_from_file(tmp_path: Path) -> None:
    path = tmp_path / "body.json"
    path.write_text(BODY, encoding="utf-8")

    body = read_body(parse_args(["--input", str(path)]), io.StringIO())

    assert body.list_2 == ["b"]


@pytest.mark.parametrize(
    "raw",
    [
        '{"list_1": ["a"], "list_2": []}',
        '{"list_1": ["a"]}',
        "not json",
    ],
    ids=["unequal-lengths", "missing-list", "invalid-json"],
)
def test_rejects_invalid_body_before_sending(raw: str) -> None:
    with pytest.raises(ValidationError):
        read_body(parse_args(["--json", raw]), io.StringIO())
