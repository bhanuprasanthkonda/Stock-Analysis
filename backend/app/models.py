from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
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


class Watchlist(Base):
    __tablename__ = "watchlists"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id           = Column(Integer, primary_key=True, index=True)
    watchlist_id = Column(Integer, ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False, index=True)
    ticker       = Column(String, nullable=False)
    company_name = Column(String, nullable=True)
    notes        = Column(String, nullable=True)
    position     = Column(Integer, default=0, nullable=False)
    added_at     = Column(DateTime, server_default=func.now())
