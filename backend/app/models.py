from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from app.database import Base


class Portfolio(Base):
    __tablename__ = "portfolio"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, nullable=False, index=True)
    company_name = Column(String, nullable=True)
    shares = Column(Float, nullable=False)
    buy_price = Column(Float, nullable=False)
    buy_date = Column(String, nullable=False)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class SearchHistory(Base):
    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, nullable=False, index=True)
    company_name = Column(String, nullable=True)
    searched_at = Column(DateTime, server_default=func.now())


class ReadStock(Base):
    __tablename__ = "read_stocks"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, nullable=False, index=True)
    marked_read_at = Column(DateTime, server_default=func.now())
