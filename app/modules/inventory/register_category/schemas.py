from pydantic import BaseModel, Field


class CreateCategoryRequest(BaseModel):
    name: str = Field(min_length=3, max_length=100)


class CategoryResponse(BaseModel):
    id: int
    name: str