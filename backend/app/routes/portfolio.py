import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import date

from app.database import get_db
from app import models, schemas

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


# ── Portfolio CRUD ────────────────────────────────────────────────────────────

@router.get("/", response_model=List[schemas.PortfolioOut])
def list_portfolio(db: Session = Depends(get_db)):
    """Return all portfolio positions ordered by creation date (newest first)."""
    return db.query(models.Portfolio).order_by(models.Portfolio.created_at.desc()).all()


@router.post("/", response_model=schemas.PortfolioOut, status_code=201)
def add_position(payload: schemas.PortfolioCreate, db: Session = Depends(get_db)):
    """Add a new portfolio position. `buy_date` defaults to today if omitted by the caller."""
    data = payload.model_dump()
    data['buy_date'] = data.get('buy_date') or date.today().isoformat()
    entry = models.Portfolio(**data)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.put("/{entry_id}", response_model=schemas.PortfolioOut)
def update_position(entry_id: int, payload: schemas.PortfolioUpdate, db: Session = Depends(get_db)):
    """Partially update a position. Only fields present in the payload are changed."""
    entry = db.query(models.Portfolio).filter(models.Portfolio.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Portfolio entry not found")
    if payload.shares is not None:
        entry.shares = payload.shares
    if payload.buy_price is not None:
        entry.buy_price = payload.buy_price
    if payload.notes is not None:
        entry.notes = payload.notes
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
def delete_position(entry_id: int, db: Session = Depends(get_db)):
    """Delete a portfolio position by ID. Returns 404 if not found."""
    entry = db.query(models.Portfolio).filter(models.Portfolio.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Portfolio entry not found")
    db.delete(entry)
    db.commit()


# ── Search history ────────────────────────────────────────────────────────────

@router.get("/history", response_model=List[schemas.SearchHistoryOut])
def list_history(db: Session = Depends(get_db)):
    """Return the 20 most recently searched tickers, newest first.
    Uniqueness is enforced on insert (old row deleted before new one is added),
    so each ticker appears at most once in the list.
    """
    return db.query(models.SearchHistory).order_by(models.SearchHistory.searched_at.desc()).limit(20).all()


@router.post("/history", response_model=schemas.SearchHistoryOut, status_code=201)
def log_search(ticker: str, db: Session = Depends(get_db)):
    """Manually log a ticker search. In practice, search logging happens inside
    the GET /stocks/{ticker} route which also deletes the old row first.
    """
    entry = models.SearchHistory(ticker=ticker.upper())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


# ── Mark stock as read (cleanup) ──────────────────────────────────────────────

@router.post("/read/{ticker}", response_model=schemas.ReadStockOut, status_code=201)
def mark_read(ticker: str, db: Session = Depends(get_db)):
    """Remove ticker from search history and record it in the read_stocks table.
    Used for cleanup — lets users dismiss tickers they've finished reviewing.
    """
    ticker = ticker.upper()
    db.query(models.SearchHistory).filter(models.SearchHistory.ticker == ticker).delete()
    read_entry = models.ReadStock(ticker=ticker)
    db.add(read_entry)
    db.commit()
    db.refresh(read_entry)
    return read_entry


@router.get("/read", response_model=List[schemas.ReadStockOut])
def list_read(db: Session = Depends(get_db)):
    """Return all tickers that have been marked as read, newest first."""
    return db.query(models.ReadStock).order_by(models.ReadStock.marked_read_at.desc()).all()


# ── Positions with live P&L ───────────────────────────────────────────────────

@router.get("/positions", response_model=List[schemas.PositionOut])
def list_positions(db: Session = Depends(get_db)):
    """Return all positions enriched with live prices and P&L.
    Prices are fetched once per unique ticker (not once per row) to avoid
    duplicate yfinance calls when the same ticker has multiple positions.
    NaN prices are treated as None so the frontend can show '—' gracefully.
    """
    rows = db.query(models.Portfolio).order_by(models.Portfolio.created_at.desc()).all()

    # Fetch live prices once per unique ticker
    prices: dict[str, float | None] = {}
    for tkr in {r.ticker for r in rows}:
        try:
            v = float(yf.Ticker(tkr).fast_info.last_price)
            prices[tkr] = round(v, 4) if v == v else None  # v != v is True for NaN
        except Exception:
            prices[tkr] = None

    results = []
    for r in rows:
        cp = prices.get(r.ticker)
        if cp is not None:
            mv    = round(cp * r.shares, 2)
            cost  = r.buy_price * r.shares
            pnl_d = round(mv - cost, 2)
            pnl_p = round(pnl_d / cost * 100, 2) if cost else None
        else:
            mv = pnl_d = pnl_p = None

        results.append(schemas.PositionOut(
            id=r.id,
            ticker=r.ticker,
            company_name=r.company_name,
            shares=r.shares,
            buy_price=r.buy_price,
            buy_date=r.buy_date,
            notes=r.notes,
            current_price=cp,
            market_value=mv,
            pnl_dollar=pnl_d,
            pnl_pct=pnl_p,
        ))

    return results
