from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

# --- AUTH СХЕМИ (Лаб 2) ---
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=72)

class UserOut(BaseModel):
    id: int
    username: str
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}

class Token(BaseModel):
    access_token: str
    token_type: str

# --- ORDER СХЕМИ (Лаб 3) ---
class OrderCreate(BaseModel):
    client_name: str = Field(min_length=2, max_length=120)
    gr_liv_area: float = Field(gt=0, le=10_000)
    total_bsmt_sf: float = Field(ge=0, le=10_000)
    garage_area: float = Field(ge=0, le=2_000)
    year_built: int = Field(ge=1872, le=2010)
    overall_qual: int = Field(ge=1, le=10)
    ms_zoning: str = Field(min_length=1, max_length=10)

class OrderUpdate(BaseModel):
    client_name: str | None = Field(default=None, min_length=2, max_length=120)
    gr_liv_area: float | None = Field(default=None, gt=0, le=10_000)
    total_bsmt_sf: float | None = Field(default=None, ge=0, le=10_000)
    garage_area: float | None = Field(default=None, ge=0, le=2_000)
    year_built: int | None = Field(default=None, ge=1872, le=2010)
    overall_qual: int | None = Field(default=None, ge=1, le=10)
    ms_zoning: str | None = Field(default=None, min_length=1, max_length=10)

class OrderRead(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    client_name: str
    gr_liv_area: float
    total_bsmt_sf: float
    garage_area: float
    year_built: int
    overall_qual: int
    ms_zoning: str
    predicted_price: float | None
    status: str
    created_at: datetime

class BatchResult(BaseModel):
    index: int
    order_id: Optional[int] = None
    status: str
    predicted_price: Optional[float] = None
    error: Optional[str] = None

class BatchResponse(BaseModel):
    total: int
    results: List[BatchResult]