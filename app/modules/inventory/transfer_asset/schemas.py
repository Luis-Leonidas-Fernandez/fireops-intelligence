from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class TransferAssetRequest(BaseModel):
    destination_location_id: int | None = Field(default=None, gt=0)
    destination_vehicle_asset_id: int | None = Field(default=None, gt=0)
    reason: str | None = Field(default=None, max_length=1000)
    observations: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_one_destination_source(self) -> Self:
        if (self.destination_location_id is None) == (
            self.destination_vehicle_asset_id is None
        ):
            raise ValueError(
                "Provide either destination_location_id or destination_vehicle_asset_id."
            )
        return self


class TransferAssetResponse(BaseModel):
    id: int
    asset_id: int
    user_id: int
    movement_type: Literal["TRASLADO"]
    occurred_at: datetime
    origin_location_id: int | None
    destination_location_id: int
    reason: str | None
    observations: str | None


class MovementItemResponse(BaseModel):
    id: int
    asset_id: int
    asset_code: str
    asset_name: str
    user_id: int
    user_email: str | None = None
    movement_type: str
    occurred_at: datetime
    origin_location_id: int | None = None
    origin_location_name: str | None = None
    destination_location_id: int | None = None
    destination_location_name: str | None = None
    reason: str | None = None
    observations: str | None = None
