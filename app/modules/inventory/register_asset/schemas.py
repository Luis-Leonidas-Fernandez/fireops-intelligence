from typing import Self

from pydantic import BaseModel, Field, model_validator


class RegisterAssetRequest(BaseModel):
    internal_code: str = Field(min_length=3, max_length=30)
    name: str = Field(min_length=3, max_length=150)
    category_id: int | None = Field(default=None, gt=0)
    new_category_name: str | None = Field(default=None, min_length=3, max_length=100)
    location_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def require_one_category_source(self) -> Self:
        if (self.category_id is None) == (self.new_category_name is None):
            raise ValueError("Provide either category_id or new_category_name.")
        return self


class RegisterAssetResponse(BaseModel):
    id: int
    internal_code: str
    name: str
    category_id: int
    location_id: int | None
