"""
Pydantic schema for validating trade CSV rows.

Defines the external data contract for trades loaded from CSV.
Parses raw CSV strings into typed values before they enter the core module. 
"""

from datetime import date
from decimal import Decimal 

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CsvTradeRow(BaseModel):

    model_config = ConfigDict(str_strip_whitespace=True)

    trade_id: str = Field(min_length=1)
    trade_date: date

    counterparty: str = Field(min_length=1)
    area: str = Field(min_length=1)
    trade_type: str = Field(min_length=1)

    buy_sell: str = Field(min_length=1)
    product: str = Field(min_length=1)
    load_profile: str = Field(min_length=1)

    start_date: date
    end_date: date

    volume_mw: Decimal = Field(gt=0)
    price_jpy_kwh: Decimal = Field(gt=0)

    @model_validator(mode="after")
    def validate_delivery_period(self) -> "CsvTradeRow":
        """Require a positive delivery interval."""
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date")

        return self


CSV_HEADERS = tuple(CsvTradeRow.model_fields)




