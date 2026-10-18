from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TransferAssetRequest(BaseModel):
    destination_location_id: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=1000)
    observations: str | None = Field(default=None, max_length=2000)


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
