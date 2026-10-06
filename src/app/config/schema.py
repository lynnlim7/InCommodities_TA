"""
Configuration schema for power position tool.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

WeekdayName = Literal[
    "Monday", 
    "Tuesday",
    "Wednesday", 
    "Thursday", 
    "Friday"
]

class ContinuousProfileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["continuous"]

class HourlyWindowProfileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["hourly_window"]

    start_hour: int = Field(ge=0, le=23)
    end_hour: int = Field(ge=1, le=24)
    weekdays: list[WeekdayName] = Field(min_length=1)


ProfileConfig = Annotated[
    ContinuousProfileConfig | HourlyWindowProfileConfig,
    Field(discriminator="type"),
]


class LoadProfilesConfig(BaseModel):
    """Root configuration for load profiles."""

    model_config = ConfigDict(extra="forbid")

    load_profiles: dict[str, ProfileConfig]
    