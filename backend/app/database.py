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
    """Create all tables (if they don't exist) and run lightweight column migrations.
    Uses SQLite PRAGMA table_info instead of Alembic to keep the tool simple and
    dependency-free. New columns are added with ALTER TABLE ADD COLUMN on startup.
    Called once from the FastAPI lifespan handler before the server starts accepting requests.
    """
    from app import models  # noqa: F401 — ensures models register with Base
    Base.metadata.create_all(bind=engine)
    # Add columns that may be missing in existing databases (migration without Alembic)
    with engine.connect() as conn:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(search_history)")).fetchall()]
        if 'company_name' not in cols:
            conn.execute(text("ALTER TABLE search_history ADD COLUMN company_name VARCHAR"))
            conn.commit()


def get_db():
    """FastAPI dependency that yields a SQLAlchemy session and guarantees it is
    closed after the request completes, even if an exception is raised.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
