"""Load and validate application configuration."""

from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel

ConfigT = TypeVar(
    "ConfigT",
    bound=BaseModel,
)

# The config package owns where its own files live, mirroring
# DEFAULT_TRADES_CSV in the CSV repository, so no caller needs to know the
# package layout.
CONFIG_DIR = Path(__file__).resolve().parent

AREAS_YAML = CONFIG_DIR / "areas.yaml"
TRADE_TYPES_YAML = CONFIG_DIR / "trade_types.yaml"
LOAD_PROFILES_YAML = CONFIG_DIR / "load_profiles.yaml"


def load_yaml[ConfigT: BaseModel](
    path: Path,
    schema: type[ConfigT],
) -> ConfigT:
    """Load a YAML file and validate it against a Pydantic schema."""

    with path.open(
        encoding="utf-8",
    ) as file:
        raw_config = yaml.safe_load(file)

    return schema.model_validate(
        raw_config
    )