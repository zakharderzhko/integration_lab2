import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

def read_db_password() -> str:
    """Зчитує пароль з Docker Secret або повертає дефолтний для локального запуску."""
    path = Path("/run/secrets/db_password")
    if path.exists():
        return path.read_text().strip()
    return "orders"

POSTGRES_USER = os.getenv("POSTGRES_USER", "orders")
POSTGRES_DB = os.getenv("POSTGRES_DB", "orders")
DB_PASSWORD = read_db_password()

DATABASE_URL = f"postgresql+psycopg://{POSTGRES_USER}:{DB_PASSWORD}@postgres:5432/{POSTGRES_DB}"

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()