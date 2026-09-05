from pydantic import BaseModel, Field

class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")

class TenantOut(BaseModel):
    id: str
    name: str
    slug: str
    status: str
