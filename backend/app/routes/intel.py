"""Market intelligence routes: market-wide news, DoD defense contracts, and economic calendar."""

import re
import logging
from datetime import datetime, timedelta, date
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf
import requests
from bs4 import BeautifulSoup
from fastapi import APIRouter

from app.routes.stocks import _parse_news, _safe_float

router = APIRouter(prefix="/intel", tags=["intel"])
logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# ── Market News ───────────────────────────────────────────────────────────────

_MARKET_TICKERS = [
    ("S&P 500",       "SPY"),
    ("Nasdaq 100",    "QQQ"),
    ("Dow Jones",     "DIA"),
    ("Russell 2000",  "IWM"),
    ("VIX",           "^VIX"),
    ("Gold",          "GLD"),
    ("Crude Oil",     "USO"),
    ("10Y Treasury",  "^TNX"),
    ("US Dollar",     "UUP"),
]


@router.get("/market-news")
def get_market_news():
    """Fetch and merge latest news from major market indices and ETFs."""
    def _fetch(label: str, sym: str):
        try:
            news = _parse_news(yf.Ticker(sym).news or [])
            return label, sym, news[:6]
        except Exception:
            return label, sym, []

    seen_titles: set[str] = set()
    all_news = []

    with ThreadPoolExecutor(max_workers=len(_MARKET_TICKERS)) as pool:
        futures = {pool.submit(_fetch, label, sym): (label, sym) for label, sym in _MARKET_TICKERS}
        for future in as_completed(futures):
            label, sym, items = future.result()
            for n in items:
                if n.title not in seen_titles:
                    seen_titles.add(n.title)
                    d = n.model_dump()
                    d["source_label"]  = label
                    d["source_symbol"] = sym
                    all_news.append(d)

    all_news.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return all_news[:40]


# ── Defense Contracts ─────────────────────────────────────────────────────────

# Ticker lookup table for common defense contractors.
_DEFENSE_TICKERS: dict[str, str | None] = {
    "boeing":              "BA",
    "lockheed martin":     "LMT",
    "lockheed":            "LMT",
    "raytheon":            "RTX",
    "rtx":                 "RTX",
    "general dynamics":    "GD",
    "northrop grumman":    "NOC",
    "northrop":            "NOC",
    "l3harris":            "LHX",
    "l3 harris":           "LHX",
    "l3 technologies":     "LHX",
    "bae systems":         "BAESY",
    "leidos":              "LDOS",
    "saic":                "SAIC",
    "textron":             "TXT",
    "bell textron":        "TXT",
    "huntington ingalls":  "HII",
    "hii":                 "HII",
    "transdigm":           "TDG",
    "heico":               "HEI",
    "curtiss-wright":      "CW",
    "mercury systems":     "MRCY",
    "kratos":              "KTOS",
    "palantir":            "PLTR",
    "booz allen":          "BAH",
    "caci":                "CACI",
    "parsons":             "PSN",
    "viasat":              "VSAT",
    "honeywell":           "HON",
    "rolls-royce":         "RYCEY",
    "general electric":    "GE",
    "ge aerospace":        "GE",
    "sikorsky":            "LMT",   # Lockheed Martin subsidiary
    "pratt & whitney":     "RTX",   # RTX subsidiary
    "collins aerospace":   "RTX",   # RTX subsidiary
}


def _guess_ticker(company_text: str) -> str | None:
    low = company_text.lower()
    for name, ticker in _DEFENSE_TICKERS.items():
        if name in low:
            return ticker
    # Fall back to yfinance search
    try:
        results = yf.Search(company_text, max_results=1).quotes
        if results:
            sym = results[0].get("symbol", "")
            # Skip obvious indices / ETFs
            if sym and "^" not in sym and len(sym) <= 5:
                return sym
    except Exception:
        pass
    return None


def _fetch_stock_snapshot(ticker: str) -> dict:
    try:
        fi   = yf.Ticker(ticker).fast_info
        last = _safe_float(fi.last_price)
        prev = _safe_float(fi.previous_close)
        chg_pct = round((last - prev) / prev * 100, 2) if last and prev else None
        return {"current_price": last, "day_change_pct": chg_pct}
    except Exception:
        return {}


_DEFENSE_NEWS_TICKERS = ["ITA", "LMT", "RTX", "NOC", "GD", "BA", "LHX", "LDOS", "SAIC", "HII", "KTOS", "PLTR"]


def _article_links_from_listing(n: int = 10) -> list[str]:
    """Scrape defense.gov/News/Contracts/ listing to find links to recent contract articles."""
    base = "https://www.defense.gov"
    try:
        resp = requests.get(f"{base}/News/Contracts/", headers=_HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        seen, links = set(), []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/News/Contracts/Article/" in href:
                full = base + href if href.startswith("/") else href
                if full not in seen:
                    seen.add(full)
                    links.append(full)
            if len(links) >= n:
                break
        # Always include the main page as fallback for today
        if not links:
            links = [f"{base}/News/Contracts/"]
        return links
    except Exception:
        return ["https://www.defense.gov/News/Contracts/"]


def _parse_article(url: str) -> list[dict]:
    """Fetch one defense.gov contract article and return a list of contract dicts."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return []

    body = (
        soup.find("div", class_="body")
        or soup.find("article")
        or soup.find("div", class_="article-body")
        or soup.find("main")
    )
    if not body:
        return []

    date_tag = soup.find("h1") or soup.find("h2") or soup.find("time")
    contract_date = date_tag.get_text(strip=True) if date_tag else ""

    contracts = []
    for para in body.find_all("p"):
        text = para.get_text(" ", strip=True)
        if not text or "$" not in text or len(text) < 40:
            continue
        if any(kw in text.lower() for kw in ["dod contracts", "click here", "subscribe", "share this"]):
            continue

        value_m: float | None = None
        m = re.search(r"\$([0-9,]+(?:\.[0-9]+)?)\s*(million|billion)", text, re.IGNORECASE)
        if m:
            mult = 1_000_000 if m.group(2).lower() == "million" else 1_000_000_000
            value_m = float(m.group(1).replace(",", "")) * mult / 1_000_000
        else:
            raw = re.search(r"\$([0-9,]{4,})", text)
            if raw:
                value_m = float(raw.group(1).replace(",", "")) / 1_000_000

        if not value_m:
            continue

        company_raw = text.split(",")[0].strip()
        company_raw = re.sub(r"\b(LLC|Inc\.?|Corp\.?|Co\.?|Ltd\.?)$", "", company_raw, flags=re.IGNORECASE).strip()

        contracts.append({
            "date":                    contract_date,
            "company_name":            company_raw,
            "ticker":                  None,
            "contract_value_millions": round(value_m, 2),
            "description":             text[:500] + ("…" if len(text) > 500 else ""),
            "current_price":           None,
            "day_change_pct":          None,
            "investment_note":         None,
            "recent_news":             [],
        })
    return contracts


@router.get("/defense-contracts")
def get_defense_contracts(page: int = 1, page_size: int = 10):
    """Scrape recent DoD contracts from defense.gov (last ~10 contract days),
    enrich with live stock data and recent yfinance news, return paginated results."""

    # ── 1. Scrape multiple days of contract articles in parallel ─────────────
    article_urls = _article_links_from_listing(n=10)
    all_contracts: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(len(article_urls), 5)) as pool:
        for batch in pool.map(_parse_article, article_urls):
            all_contracts.extend(batch)

    if not all_contracts:
        return {"total": 0, "page": page, "page_size": page_size, "items": []}

    # ── 2. Match company names to tickers ────────────────────────────────────
    for c in all_contracts:
        c["ticker"] = _guess_ticker(c["company_name"])

    # ── 3. Fetch live prices for every unique ticker in parallel ─────────────
    unique_tickers = list({c["ticker"] for c in all_contracts if c.get("ticker")})
    snapshots: dict[str, dict] = {}
    if unique_tickers:
        with ThreadPoolExecutor(max_workers=min(len(unique_tickers), 8)) as pool:
            for tkr, data in pool.map(lambda t: (t, _fetch_stock_snapshot(t)), unique_tickers):
                snapshots[tkr] = data

    # ── 4. Fetch recent news for known defense tickers ───────────────────────
    defense_news: dict[str, list] = {}
    news_tickers = list({c["ticker"] for c in all_contracts if c.get("ticker")} | set(_DEFENSE_NEWS_TICKERS))

    def _fetch_ticker_news(tkr: str):
        try:
            items = _parse_news(yf.Ticker(tkr).news or [])
            return tkr, [n.model_dump() for n in items[:3]]
        except Exception:
            return tkr, []

    with ThreadPoolExecutor(max_workers=min(len(news_tickers), 8)) as pool:
        for tkr, news in pool.map(_fetch_ticker_news, news_tickers):
            defense_news[tkr] = news

    # ── 5. Enrich each contract with stock data + news + investment note ─────
    for c in all_contracts:
        tkr = c.get("ticker")
        if tkr and tkr in snapshots:
            snap = snapshots[tkr]
            c["current_price"]  = snap.get("current_price")
            c["day_change_pct"] = snap.get("day_change_pct")
            chg = c["day_change_pct"]
            if chg is None:
                c["investment_note"] = "Price data unavailable"
            elif chg >= 3:
                c["investment_note"] = "Strong momentum — contract already priced in, wait for pullback"
            elif chg >= 0:
                c["investment_note"] = "Mild positive reaction — worth monitoring for entry"
            elif chg >= -3:
                c["investment_note"] = "Flat / minor dip — potential accumulation opportunity"
            else:
                c["investment_note"] = "Significant sell-off — investigate cause before investing"
        if tkr and tkr in defense_news:
            c["recent_news"] = defense_news[tkr]

    # ── 6. Paginate ──────────────────────────────────────────────────────────
    total  = len(all_contracts)
    start  = (page - 1) * page_size
    end    = start + page_size
    return {
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "pages":     max(1, (total + page_size - 1) // page_size),
        "items":     all_contracts[start:end],
    }


# ── Economic Calendar ─────────────────────────────────────────────────────────

_IMPORTANCE_KEYWORDS = {
    "High": [
        "employment", "nonfarm", "payroll", "cpi", "consumer price", "ppi", "producer price",
        "gdp", "gross domestic", "fomc", "federal open", "interest rate", "unemployment",
        "retail sales", "industrial production", "housing starts", "ism",
    ],
    "Medium": [
        "trade balance", "current account", "durable goods", "factory orders",
        "consumer confidence", "consumer sentiment", "business inventories",
        "building permits", "existing home", "new home sales", "job openings",
    ],
}


def _classify_importance(name: str) -> str:
    low = name.lower()
    for level, keywords in _IMPORTANCE_KEYWORDS.items():
        if any(k in low for k in keywords):
            return level
    return "Low"


def _classify_category(name: str) -> str:
    low = name.lower()
    if any(k in low for k in ["employment", "nonfarm", "payroll", "unemployment", "job", "labor"]):
        return "Employment"
    if any(k in low for k in ["cpi", "ppi", "consumer price", "producer price", "inflation", "pce"]):
        return "Inflation"
    if any(k in low for k in ["gdp", "gross domestic"]):
        return "GDP"
    if any(k in low for k in ["fomc", "federal open", "interest rate", "fed ", "federal reserve"]):
        return "Federal Reserve"
    if any(k in low for k in ["retail", "sales"]):
        return "Retail"
    if any(k in low for k in ["housing", "home", "building", "construction"]):
        return "Housing"
    if any(k in low for k in ["trade", "import", "export", "current account"]):
        return "Trade"
    if any(k in low for k in ["manufacturing", "industrial", "factory", "ism", "pmi"]):
        return "Manufacturing"
    return "Other"


_MONTH_NAMES = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December",
]

def _parse_event_date(date_text: str, target_year: int) -> datetime | None:
    """Try multiple date formats used by BLS and Fed calendars.

    BLS uses "Wednesday, January 15, 2025" — we strip the weekday prefix first.
    """
    # Strip leading weekday name ("Wednesday, " etc.)
    clean = re.sub(r'^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*\.?,?\s*', '', date_text.strip(), flags=re.IGNORECASE).strip()
    # Strip trailing ordinal suffixes (1st → 1, 2nd → 2)
    clean = re.sub(r'(\d)(st|nd|rd|th)\b', r'\1', clean)

    for fmt in ("%B %d, %Y", "%b. %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d", "%B %d %Y"):
        try:
            return datetime.strptime(clean, fmt)
        except ValueError:
            pass
    # Without year — assume target_year
    for fmt in ("%B %d", "%b %d", "%b. %d"):
        try:
            d = datetime.strptime(clean, fmt)
            return d.replace(year=target_year)
        except ValueError:
            pass
    return None


@router.get("/economic-calendar")
def get_economic_calendar(days_back: int = 15, days_forward: int = 15):
    """Return economic events in a rolling window around today (default −15 / +15 days).
    Sources: BLS release calendar + Federal Reserve FOMC schedule.
    Uses curl_cffi with Chrome impersonation for BLS to bypass bot detection.
    """
    from curl_cffi import requests as cffi_req

    today        = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    window_start = today - timedelta(days=days_back)
    window_end   = today + timedelta(days=days_forward)

    all_events: list[dict] = []
    seen_sort_keys: set[str] = set()   # date_sort + event name, for dedup

    # ── BLS release calendar ──────────────────────────────────────────────────
    try:
        resp = cffi_req.get(
            "https://www.bls.gov/schedule/news_release/releaseCalendar.htm",
            impersonate="chrome120",
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # BLS page has a single data table; fall back to first table if no id
        table = (
            soup.find("table", id="releaseCalendar")
            or soup.find("table", class_=re.compile(r"release", re.I))
            or soup.find("table")
        )
        if table:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                release_name = cells[0].get_text(" ", strip=True)
                date_text    = cells[1].get_text(" ", strip=True)
                time_text    = cells[2].get_text(strip=True) if len(cells) > 2 else "8:30 AM ET"

                # Skip obvious header rows or empty cells
                if not release_name or not date_text:
                    continue
                if release_name.lower() in ("release", "name", "title", "report"):
                    continue

                parsed = _parse_event_date(date_text, today.year)
                if not parsed:
                    continue

                key = parsed.strftime("%Y-%m-%d") + "|" + release_name
                if key in seen_sort_keys:
                    continue
                seen_sort_keys.add(key)

                all_events.append({
                    "date":       parsed.strftime("%B %d, %Y"),
                    "date_sort":  parsed.strftime("%Y-%m-%d"),
                    "time":       time_text or "8:30 AM ET",
                    "event":      release_name,
                    "category":   _classify_category(release_name),
                    "importance": _classify_importance(release_name),
                    "source":     "BLS",
                })
        else:
            logger.warning("BLS calendar: no table found in page")
    except Exception as e:
        logger.warning("BLS calendar scrape failed: %s", e)

    # ── Federal Reserve FOMC calendar ────────────────────────────────────────
    try:
        resp = cffi_req.get(
            "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            impersonate="chrome120",
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Fed page lists meetings like "January 28-29, 2025" in various tags
        _MONTH_RE = (
            r"(January|February|March|April|May|June|July|August|"
            r"September|October|November|December)"
        )
        pattern = re.compile(
            _MONTH_RE + r"\s+(\d{1,2})(?:\s*[-–—]\s*(\d{1,2}))?,?\s*(\d{4})"
        )

        for tag in soup.find_all(["p", "div", "li", "td", "h3", "h4", "span"]):
            text = tag.get_text(" ", strip=True)
            for m in pattern.finditer(text):
                mon_name, day1, day2, yr = m.groups()
                yr   = int(yr)
                day1 = int(day1)
                mon_num = _MONTH_NAMES.index(mon_name) + 1
                # Use the last day (statement release day)
                end_day = int(day2) if day2 else day1
                try:
                    dt = datetime(yr, mon_num, end_day)
                except ValueError:
                    continue
                sort_key = dt.strftime("%Y-%m-%d") + "|FOMC Meeting"
                if sort_key in seen_sort_keys:
                    continue
                seen_sort_keys.add(sort_key)
                all_events.append({
                    "date":       dt.strftime("%B %d, %Y"),
                    "date_sort":  dt.strftime("%Y-%m-%d"),
                    "time":       "2:00 PM ET",
                    "event":      "FOMC Meeting",
                    "category":   "Federal Reserve",
                    "importance": "High",
                    "source":     "Federal Reserve",
                })
    except Exception as e:
        logger.warning("Fed calendar scrape failed: %s", e)

    # ── Filter to rolling window, sort, tag past/today ────────────────────────
    ws = window_start.strftime("%Y-%m-%d")
    we = window_end.strftime("%Y-%m-%d")
    filtered = [e for e in all_events if ws <= e.get("date_sort", "") <= we]
    filtered.sort(key=lambda x: x["date_sort"])

    today_str = today.strftime("%Y-%m-%d")
    for e in filtered:
        ds = e["date_sort"]
        e["is_today"] = ds == today_str
        e["is_past"]  = ds < today_str

    return filtered
