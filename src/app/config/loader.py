"""Load and validate application configuration."""

from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel


ConfigT = TypeVar(
    "ConfigT",
    bound=BaseModel,
)


def load_yaml(
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