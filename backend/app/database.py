from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "stocks.db")
DATABASE_URL = f"sqlite:///{os.path.abspath(DB_PATH)}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def init_db():
    from app import models  # noqa: F401 — ensures models register with Base
    Base.metadata.create_all(bind=engine)
    # Add columns that may be missing in existing databases
    with engine.connect() as conn:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(search_history)")).fetchall()]
        if 'company_name' not in cols:
            conn.execute(text("ALTER TABLE search_history ADD COLUMN company_name VARCHAR"))
            conn.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
