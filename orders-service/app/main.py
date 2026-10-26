import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import List
from pathlib import Path
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from passlib.context import CryptContext

from . import crud, models, schemas
from .database import Base, SessionLocal, engine, get_db

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("orders-api")

# --- SECRETS & CONFIG (Лаб 2) ---
def read_secret(name: str) -> str:
    path = Path(f"/run/secrets/{name}")
    if not path.exists():
        logger.error(f"Secret {name} missing!")
        sys.exit(1)
    return path.read_text().strip()

# Зчитуємо тільки якщо ми в Docker (якщо є папка /run/secrets)
if Path("/run/secrets").exists():
    JWT_SECRET_KEY = read_secret("jwt_secret_key")
else:
    # Запасний варіант для локального запуску
    JWT_SECRET_KEY = "local_dev_key"

ALGORITHM = "HS256"
FORECAST_URL = os.getenv("FORECAST_URL", "http://forecast-api:8001")
FORECAST_TIMEOUT = float(os.getenv("FORECAST_TIMEOUT", "3.0"))

Base.metadata.create_all(bind=engine)

# --- ASYNC CLIENT (Лаб 3) ---
http_client: httpx.AsyncClient | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(timeout=FORECAST_TIMEOUT)
    yield
    await http_client.aclose()

app = FastAPI(title="Orders API (Auth + Async)", version="0.2.0", lifespan=lifespan)

# --- AUTH SETUP (Лаб 2) ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=30)
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise ValueError()
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token", headers={"WWW-Authenticate": "Bearer"})
    
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid user", headers={"WWW-Authenticate": "Bearer"})
    return user

# --- AUTH ENDPOINTS (Лаб 2) ---
@app.post("/auth/register", response_model=schemas.UserOut, status_code=201)
def register(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    hashed_pw = pwd_context.hash(user_in.password)
    new_user = models.User(username=user_in.username, hashed_password=hashed_pw)
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username taken")

@app.post("/auth/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not pwd_context.verify(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    token = create_access_token(data={"sub": user.username})
    return {"access_token": token, "token_type": "bearer"}

@app.get("/auth/me", response_model=schemas.UserOut)
def read_users_me(current_user: models.User = Depends(get_current_user)):
    return current_user

# --- BACKGROUND TASKS (Лаб 3) ---
async def fetch_forecast_background(order_id: int):
    db: Session = SessionLocal()
    try:
        order = db.query(models.Order).filter(models.Order.id == order_id).first()
        if not order:
            return
        payload = {
            "gr_liv_area": order.gr_liv_area, "total_bsmt_sf": order.total_bsmt_sf,
            "garage_area": order.garage_area, "year_built": order.year_built,
            "overall_qual": order.overall_qual, "ms_zoning": order.ms_zoning,
        }
        response = await http_client.post(f"{FORECAST_URL}/predict", json=payload)
        response.raise_for_status()
        order.predicted_price = response.json().get("predicted_price")
        order.status = "priced"
    except Exception as exc:
        if order: order.status = "failed"
    finally:
        db.commit()
        db.close()

# --- ORDER ENDPOINTS (ОБ'ЄДНАНІ Лаб 2 + Лаб 3) ---
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.post("/orders", response_model=schemas.OrderRead, status_code=status.HTTP_202_ACCEPTED)
async def create_order(
    data: schemas.OrderCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user) # ЗАХИСТ З ЛАБ 2
):
    order = crud.create_order(db, data)
    background_tasks.add_task(fetch_forecast_background, order.id)
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=schemas.OrderRead.model_validate(order).model_dump(mode='json'),
        headers={"Location": f"{request.base_url}orders/{order.id}"}
    )

@app.post("/orders/batch", response_model=schemas.BatchResponse)
async def create_orders_batch(
    orders_data: List[schemas.OrderCreate],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user) # ЗАХИСТ З ЛАБ 2
):
    if len(orders_data) > 50:
        raise HTTPException(status_code=422, detail="BATCH_MAX_ITEMS exceeded.")

    saved_orders = [crud.create_order(db, data) for data in orders_data]

    async def fetch_single(index: int, order: models.Order):
        payload = {
            "gr_liv_area": order.gr_liv_area, "total_bsmt_sf": order.total_bsmt_sf,
            "garage_area": order.garage_area, "year_built": order.year_built,
            "overall_qual": order.overall_qual, "ms_zoning": order.ms_zoning,
        }
        try:
            res = await http_client.post(f"{FORECAST_URL}/predict", json=payload)
            res.raise_for_status()
            price = res.json().get("predicted_price")
            order.predicted_price = price
            order.status = "priced"
            return {"index": index, "order_id": order.id, "status": "priced", "predicted_price": price}
        except Exception:
            order.status = "failed"
            return {"index": index, "order_id": order.id, "status": "failed", "error": "Unavailable"}

    results = await asyncio.gather(*[fetch_single(i, order) for i, order in enumerate(saved_orders)])
    db.commit()
    return {"total": len(results), "results": results}

@app.get("/orders", response_model=list[schemas.OrderRead])
def list_orders(limit: int = 20, offset: int = 0, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return crud.list_orders(db, limit, offset)

@app.get("/orders/{oid}", response_model=schemas.OrderRead)
def get_order(oid: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    order = crud.get_order(db, oid)
    if not order: raise HTTPException(status_code=404, detail="Not found")
    return order

@app.patch("/orders/{oid}", response_model=schemas.OrderRead)
async def update_order(
    oid: int,
    data: schemas.OrderUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    order = crud.get_order(db, oid)
    if not order: raise HTTPException(status_code=404, detail="Not found")
    
    update_data = data.model_dump(exclude_unset=True)
    needs_recalc = any(f in update_data for f in {"gr_liv_area", "total_bsmt_sf", "garage_area", "year_built", "overall_qual", "ms_zoning"})
    
    crud.update_order(db, order, data)
    
    if needs_recalc:
        order.status = "pending"
        order.predicted_price = None
        db.commit()
        background_tasks.add_task(fetch_forecast_background, order.id)
        
    return order

@app.delete("/orders/{oid}", status_code=204)
def delete_order(oid: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    order = crud.get_order(db, oid)
    if not order: raise HTTPException(status_code=404, detail="Not found")
    crud.delete_order(db, order)