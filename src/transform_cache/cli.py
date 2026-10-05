"""cache-cli: send payloads to the service and report what came back."""

import argparse
import json
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Self, TextIO

import httpx2
from pydantic import AnyHttpUrl, Field, model_validator
from pydantic_settings import (
    BaseSettings,
    CliApp,
    CliSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from transform_cache.schemas import PayloadCreate

STDIO = "-"
# Generous: a large uncached payload costs many transformer calls on the server.
REQUEST_TIMEOUT_SECONDS = 60


class CliArgs(BaseSettings):
    """Send a payload to the caching service, read it back, and report the result."""

    model_config = SettingsConfigDict(
        cli_hide_none_type=True,
        # Keyed by flag name (the alias for "json"), as pydantic-settings expects.
        cli_shortcuts={
            "host": "h",
            "repeat": "r",
            "input": "i",
            "json": "j",
            "output": "o",
        },
    )

    host: AnyHttpUrl = Field(
        default=AnyHttpUrl("http://127.0.0.1:8000"), description="Service base URL"
    )
    repeat: int = Field(default=1, ge=1, description="Number of POST + GET iterations")
    input: str | None = Field(
        default=None, description='JSON request body file, or "-" for stdin'
    )
    json_input: str | None = Field(
        default=None, alias="json", description="JSON request body as an argument"
    )
    output: str = Field(default=STDIO, description='Result file, or "-" for stdout')

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Command line only: generic names like HOST or OUTPUT set in the
        # environment for something else must not change what the CLI does.
        return (init_settings,)

    @model_validator(mode="after")
    def check_one_body_source(self) -> Self:
        if (self.input is None) == (self.json_input is None):
            raise ValueError("provide exactly one of --input or --json")
        return self


def parse_args(argv: list[str]) -> CliArgs:
    # Our own parser because pydantic-settings' default one reserves -h for help,
    # while the required interface uses -h for --host; help stays on --help.
    parser = argparse.ArgumentParser(prog="cache-cli", add_help=False)
    parser.add_argument("--help", action="help", help="show this help and exit")
    source: CliSettingsSource[CliArgs] = CliSettingsSource(CliArgs, root_parser=parser)
    return CliApp.run(CliArgs, cli_args=argv, cli_settings_source=source)


def read_body(args: CliArgs, stdin: TextIO) -> PayloadCreate:
    """Validate the body locally so bad input fails before any request is sent."""
    if args.json_input is not None:
        raw = args.json_input
    elif args.input == STDIO:
        raw = stdin.read()
    elif args.input is not None:
        raw = Path(args.input).read_text(encoding="utf-8")
    else:  # unreachable: check_one_body_source requires one of them
        raise ValueError("no request body given")
    return PayloadCreate.model_validate_json(raw)


def run(body: PayloadCreate, repeat: int, client: httpx2.Client, out: TextIO) -> None:
    """POST then GET the payload `repeat` times, writing one JSON line per round.

    Timing each round makes the cache visible: after the first round no
    transformer calls are needed, so later rounds are much faster.
    """
    for iteration in range(1, repeat + 1):
        started = time.perf_counter()
        created = client.post("/payload", json=body.model_dump())
        created.raise_for_status()
        payload_id = created.json()["id"]
        read = client.get(f"/payload/{payload_id}")
        read.raise_for_status()
        record: dict[str, Any] = {
            "iteration": iteration,
            "id": payload_id,
            "status": created.status_code,
            "output": read.json()["output"],
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        }
        out.write(json.dumps(record) + "\n")


def main(argv: list[str] | None = None) -> int:
    with ExitStack() as stack:
        try:
            args = parse_args(sys.argv[1:] if argv is None else argv)
            body = read_body(args, sys.stdin)
            # Opened before any request, so a bad path fails fast.
            out = (
                sys.stdout
                if args.output == STDIO
                else stack.enter_context(open(args.output, "w", encoding="utf-8"))
            )
        except (ValueError, OSError) as error:  # ValidationError is a ValueError
            print(f"cache-cli: error: {error}", file=sys.stderr)
            return 2

        try:
            client = stack.enter_context(
                httpx2.Client(base_url=str(args.host), timeout=REQUEST_TIMEOUT_SECONDS)
            )
            run(body, args.repeat, client, out)
        except httpx2.HTTPError as error:
            print(f"cache-cli: request failed: {error}", file=sys.stderr)
            return 1
    return 0
