"""
Configuration schema for power position tool.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

DayOfWeek = Literal[
    "Monday", 
    "Tuesday",
    "Wednesday", 
    "Thursday", 
    "Friday", 
    "Saturday",
    "Sunday",
]

class ContinuousProfileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["continuous"]

class HourlyWindowProfileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["hourly_window"]

    start_hour: int = Field(ge=0, le=23)
    end_hour: int = Field(ge=1, le=24)
    weekdays: list[DayOfWeek] = Field(min_length=1)


ProfileConfig = Annotated[
    ContinuousProfileConfig | HourlyWindowProfileConfig,
    Field(discriminator="type"),
]


class LoadProfilesConfig(BaseModel):
    """Root configuration for load profiles."""

    model_config = ConfigDict(extra="forbid")

    load_profiles: dict[str, ProfileConfig]

class AreasConfig(BaseModel):
    """Configuration for supported trading areas."""

    model_config = ConfigDict(extra="forbid")

    areas: list[str] = Field(min_length=1)


class TradeTypesConfig(BaseModel):
    """Configuration for supported trade types."""

    model_config = ConfigDict(extra="forbid")

    trade_types: list[str] = Field(min_length=1)
    