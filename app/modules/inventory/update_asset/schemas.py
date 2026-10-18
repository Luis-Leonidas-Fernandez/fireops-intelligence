from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class UpdateAssetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    internal_code: str | None = Field(default=None, min_length=3, max_length=30)
    name: str | None = Field(default=None, min_length=3, max_length=150)
    category_id: int | None = Field(default=None, gt=0)
    reason: str = Field(max_length=1000)

    @field_validator("reason")
    @classmethod
    def require_reason(cls, value: str) -> str:
        reason = value.strip()
        if not reason:
            raise ValueError("A reason is required.")
        return reason

    @model_validator(mode="after")
    def require_changes(self) -> Self:
        changed_fields = self.model_fields_set & {
            "internal_code",
            "name",
            "category_id",
        }
        if not changed_fields:
            raise ValueError("Provide at least one asset field to update.")
        if any(getattr(self, field_name) is None for field_name in changed_fields):
            raise ValueError("Updated asset fields cannot be null.")
        return self
