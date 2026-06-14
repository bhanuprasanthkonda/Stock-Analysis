import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app import models, schemas

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


def _sf(val) -> float | None:
    try:
        v = float(val)
        return round(v, 4) if v == v else None
    except (TypeError, ValueError):
        return None


def _si(val) -> int | None:
    try:
        v = int(val)
        return None if v == 0 else v
    except (TypeError, ValueError):
        return None


_EMPTY_PRICE: dict = {
    "current_price": None, "previous_close": None,
    "day_change": None, "day_change_pct": None,
    "day_high": None, "day_low": None,
    "week_52_high": None, "week_52_low": None,
    "market_cap": None, "avg_volume": None,
    "post_market_price": None, "post_market_change": None, "post_market_change_pct": None,
    "pre_market_price": None, "pre_market_change": None, "pre_market_change_pct": None,
}


def _fetch_ticker_data(tkr: str) -> tuple[str, dict]:
    """Fetch live price, ranges, and extended-hours data for one ticker.
    Uses fast_info for speed + info for pre/post market prices.
    Returns (ticker, data_dict) so results can be mapped back by the caller.
    """
    try:
        t    = yf.Ticker(tkr)
        fi   = t.fast_info
        info = t.info

        last = float(fi.last_price)
        prev = float(fi.previous_close)
        last = last if last == last else None   # NaN guard
        prev = prev if prev == prev else None
        chg  = round(last - prev, 4) if last is not None and prev else None
        chg_p = round(chg / prev * 100, 2) if chg is not None and prev else None
        reg   = round(last, 4) if last else None

        post_p   = _sf(info.get("postMarketPrice"))
        post_c   = _sf(info.get("postMarketChange"))
        post_pct = round(post_c / reg * 100, 2) if post_c and reg else None
        pre_p    = _sf(info.get("preMarketPrice"))
        pre_c    = _sf(info.get("preMarketChange"))
        pre_pct  = round(pre_c / reg * 100, 2) if pre_c and reg else None

        return tkr, {
            "current_price":          reg,
            "previous_close":         round(prev, 4) if prev else None,
            "day_change":             chg,
            "day_change_pct":         chg_p,
            "day_high":               _sf(fi.day_high),
            "day_low":                _sf(fi.day_low),
            "week_52_high":           _sf(fi.year_high),
            "week_52_low":            _sf(fi.year_low),
            "market_cap":             _si(fi.market_cap),
            "avg_volume":             _si(fi.three_month_average_volume),
            "post_market_price":      post_p,
            "post_market_change":     post_c,
            "post_market_change_pct": post_pct,
            "pre_market_price":       pre_p,
            "pre_market_change":      pre_c,
            "pre_market_change_pct":  pre_pct,
        }
    except Exception:
        return tkr, dict(_EMPTY_PRICE)


# ── Watchlist CRUD ────────────────────────────────────────────────────────────

@router.get("/", response_model=List[schemas.WatchlistOut])
def list_watchlists(db: Session = Depends(get_db)):
    """Return all watchlists with the count of tickers in each."""
    rows = db.query(models.Watchlist).order_by(models.Watchlist.created_at.asc()).all()
    result = []
    for wl in rows:
        count = db.query(models.WatchlistItem).filter(
            models.WatchlistItem.watchlist_id == wl.id
        ).count()
        result.append(schemas.WatchlistOut(
            id=wl.id, name=wl.name, item_count=count, created_at=wl.created_at
        ))
    return result


@router.post("/", response_model=schemas.WatchlistOut, status_code=201)
def create_watchlist(payload: schemas.WatchlistCreate, db: Session = Depends(get_db)):
    """Create a new named watchlist."""
    wl = models.Watchlist(name=payload.name.strip())
    db.add(wl)
    db.commit()
    db.refresh(wl)
    return schemas.WatchlistOut(id=wl.id, name=wl.name, item_count=0, created_at=wl.created_at)


@router.patch("/{wl_id}", response_model=schemas.WatchlistOut)
def rename_watchlist(wl_id: int, payload: schemas.WatchlistUpdate, db: Session = Depends(get_db)):
    """Rename an existing watchlist."""
    wl = db.query(models.Watchlist).filter(models.Watchlist.id == wl_id).first()
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    wl.name = payload.name.strip()
    db.commit()
    db.refresh(wl)
    count = db.query(models.WatchlistItem).filter(models.WatchlistItem.watchlist_id == wl_id).count()
    return schemas.WatchlistOut(id=wl.id, name=wl.name, item_count=count, created_at=wl.created_at)


@router.delete("/{wl_id}", status_code=204)
def delete_watchlist(wl_id: int, db: Session = Depends(get_db)):
    """Delete a watchlist and all its items (cascade handled by FK ondelete)."""
    wl = db.query(models.Watchlist).filter(models.Watchlist.id == wl_id).first()
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    # Manually delete items first since SQLite may not enforce FK cascades by default
    db.query(models.WatchlistItem).filter(models.WatchlistItem.watchlist_id == wl_id).delete()
    db.delete(wl)
    db.commit()


# ── Watchlist items ───────────────────────────────────────────────────────────

@router.get("/{wl_id}/items", response_model=List[schemas.WatchlistItemOut])
def list_items(wl_id: int, db: Session = Depends(get_db)):
    """Return all items in a watchlist enriched with live price and day change.
    Prices are fetched once per unique ticker using fast_info to minimise latency.
    """
    wl = db.query(models.Watchlist).filter(models.Watchlist.id == wl_id).first()
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    rows = db.query(models.WatchlistItem).filter(
        models.WatchlistItem.watchlist_id == wl_id
    ).order_by(models.WatchlistItem.position.asc(), models.WatchlistItem.added_at.asc()).all()

    # Parallel yfinance calls — one thread per unique ticker so a 10-item watchlist
    # takes ~max(per-ticker latency) instead of ~sum(per-ticker latency).
    unique_tickers = {r.ticker for r in rows}
    prices: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(len(unique_tickers), 12)) as pool:
        futures = {pool.submit(_fetch_ticker_data, tkr): tkr for tkr in unique_tickers}
        for future in as_completed(futures):
            tkr, data = future.result()
            prices[tkr] = data

    return [
        schemas.WatchlistItemOut(
            id=r.id,
            watchlist_id=r.watchlist_id,
            ticker=r.ticker,
            company_name=r.company_name,
            notes=r.notes,
            added_at=r.added_at,
            **prices.get(r.ticker, {}),
        )
        for r in rows
    ]


@router.put("/{wl_id}/items/reorder", status_code=204)
def reorder_items(wl_id: int, payload: schemas.WatchlistReorder, db: Session = Depends(get_db)):
    """Persist a new display order for watchlist items after drag-and-drop."""
    for pos, item_id in enumerate(payload.ids):
        db.query(models.WatchlistItem).filter(
            models.WatchlistItem.id == item_id,
            models.WatchlistItem.watchlist_id == wl_id,
        ).update({"position": pos})
    db.commit()


@router.post("/{wl_id}/items", response_model=List[schemas.WatchlistItemOut], status_code=201)
def add_items(wl_id: int, payload: schemas.WatchlistItemAdd, db: Session = Depends(get_db)):
    """Add one or more tickers (comma-separated) to a watchlist.
    Duplicates within the same watchlist are silently skipped.
    Company name is auto-fetched from yfinance for each ticker.
    """
    wl = db.query(models.Watchlist).filter(models.Watchlist.id == wl_id).first()
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    # Parse comma-separated input, uppercase, deduplicate
    raw = [t.strip().upper() for t in payload.tickers.split(",") if t.strip()]
    tickers = list(dict.fromkeys(raw))  # preserve order, deduplicate

    # Fetch existing tickers in this watchlist to avoid duplicates
    existing = {
        r.ticker for r in db.query(models.WatchlistItem.ticker)
        .filter(models.WatchlistItem.watchlist_id == wl_id).all()
    }

    # Next position = current max + 1 so new items go to the end
    max_pos = db.query(models.WatchlistItem).filter(
        models.WatchlistItem.watchlist_id == wl_id
    ).count()

    added = []
    for idx, tkr in enumerate(tickers):
        if tkr in existing:
            continue
        # Auto-lookup company name
        try:
            info = yf.Ticker(tkr).info
            name = info.get("longName") or info.get("shortName") or None
        except Exception:
            name = None
        item = models.WatchlistItem(
            watchlist_id=wl_id, ticker=tkr, company_name=name,
            notes=payload.notes, position=max_pos + idx,
        )
        db.add(item)
        added.append(item)

    db.commit()
    for item in added:
        db.refresh(item)

    # Return all items in the watchlist (with prices) via the list endpoint logic
    return list_items(wl_id, db)


@router.delete("/{wl_id}/items/{item_id}", status_code=204)
def remove_item(wl_id: int, item_id: int, db: Session = Depends(get_db)):
    """Remove a single ticker from a watchlist."""
    item = db.query(models.WatchlistItem).filter(
        models.WatchlistItem.id == item_id,
        models.WatchlistItem.watchlist_id == wl_id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()
