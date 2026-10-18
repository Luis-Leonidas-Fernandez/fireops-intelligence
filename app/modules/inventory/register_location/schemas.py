from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

LocationType = Literal["FISICA", "VEHICULO"]


class CreateLocationRequest(BaseModel):
    name: str = Field(min_length=3, max_length=150)
    location_type: LocationType
    container_asset_id: int | None = Field(default=None, gt=0)
    description: str | None = None
    active: bool = True

    @model_validator(mode="after")
    def validate_container(self) -> "CreateLocationRequest":
        if self.location_type == "VEHICULO" and self.container_asset_id is None:
            raise ValueError("A vehicle location requires a container asset.")
        if self.location_type == "FISICA" and self.container_asset_id is not None:
            raise ValueError("A physical location cannot have a container asset.")
        return self


class LocationResponse(BaseModel):
    id: int
    name: str
    location_type: LocationType
    container_asset_id: int | None
    description: str | None
    active: bool
    created_at: datetime
    updated_at: datetime
