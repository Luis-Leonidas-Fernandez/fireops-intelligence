from pydantic import BaseModel, Field


class RegisterAssetRequest(BaseModel):
    internal_code: str = Field(min_length=3, max_length=30)
    name: str = Field(min_length=3, max_length=150)
    category_id: int = Field(gt=0)


class RegisterAssetResponse(BaseModel):
    id: int
    internal_code: str
    name: str
    category_id: int