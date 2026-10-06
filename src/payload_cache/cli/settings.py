import json
import sys
from pathlib import Path
from typing import Self

from pydantic import AliasChoices, AnyHttpUrl, Field, PositiveInt, ValidationError, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from payload_cache.api.schemas import PayloadCreate

STDIO = "-"


# The spec assigns "-h" to both --host and --help, which argparse cannot express;
# "-h" keeps its universal meaning (help) and --host gets "-H".
class CliSettings(BaseSettings):
    """Create a payload on the cache service and read it back, optionally repeatedly."""

    model_config = SettingsConfigDict(
        cli_prog_name="cache-cli",
        # Case-sensitive so "-H" (host) and "-h" (help) stay distinct.
        case_sensitive=True,
        cli_hide_none_type=True,
    )

    host: AnyHttpUrl = Field(
        default=AnyHttpUrl("http://localhost:8000"),
        validation_alias=AliasChoices("H", "host"),
        description="base URL of the payload service",
    )
    repeat: PositiveInt = Field(
        default=1,
        validation_alias=AliasChoices("r", "repeat"),
        description="number of iterations; later iterations should hit the cache",
    )
    input: str | None = Field(
        default=None,
        validation_alias=AliasChoices("i", "input"),
        description='JSON input file, "-" for stdin',
    )
    json_input: str | None = Field(
        default=None,
        validation_alias=AliasChoices("j", "json"),
        description="JSON input given inline",
    )
    output: str = Field(
        default=STDIO,
        validation_alias=AliasChoices("o", "output"),
        description='output file, "-" for stdout',
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Command line only. With environment sources enabled, an unrelated variable such
        # as HOST (set by many shells and CI runners) would silently override defaults.
        return (init_settings,)

    @model_validator(mode="after")
    def _exactly_one_input_source(self) -> Self:
        if (self.input is None) == (self.json_input is None):
            raise ValueError("provide exactly one of --input or --json")
        if self.input not in (None, STDIO) and not Path(self.input).is_file():
            raise ValueError(f"input file not found: {self.input}")
        return self

    def load_payload(self) -> PayloadCreate:
        """Read and validate the payload with the server's own schema, so malformed input
        fails locally with a clear message instead of as a 422 from the server."""
        if self.json_input is not None:
            raw = self.json_input
        elif self.input == STDIO:
            raw = sys.stdin.read()
        else:
            raw = Path(str(self.input)).read_text(encoding="utf-8")
        try:
            return PayloadCreate.model_validate(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise InputError(f"input is not valid JSON: {exc}") from exc
        except ValidationError as exc:
            raise InputError(f"invalid payload:\n{exc}") from exc


class InputError(Exception):
    """The payload given to the CLI is unreadable or invalid."""
