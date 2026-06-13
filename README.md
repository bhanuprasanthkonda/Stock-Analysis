# Local Stock Analyzer & Portfolio Tracker

A completely private, local-first stock intelligence tool. No cloud, no subscriptions, no tracking — everything runs on your machine and is saved in a local SQLite file you own.

Search any ticker to see its candlestick chart, moving averages, Fibonacci levels, news sentiment, and institutional holders. Track your own positions and see live P&L.

---

## How to Run

Double-click `start.command` (macOS/Linux) or `start.bat` (Windows) from the project root.

On first run it will automatically:
- Create a Python virtual environment
- Install all backend dependencies (`requirements.txt`)
- Install all frontend packages (`package.json`)
- Start both servers and open the browser

On subsequent runs it skips the install step and starts immediately.

Press **Ctrl+C** to stop both servers.

---

## Manual Start (optional)

If you prefer to run servers individually, open two terminals from the project root.

**Terminal 1 — Backend** (FastAPI on port 8000)
```bash
cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — Frontend** (Vite on port 5173)
```bash
cd frontend && npm run dev
```

Then open **http://localhost:5173** in your browser.

API docs available at **http://localhost:8000/docs**.

---

## First-time Manual Setup

Only needed if you are not using `start.command`.

**Backend**
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Frontend**
```bash
cd frontend
npm install
```

---

## Project Docs

- [Technical Specification](Project_specs/Spec.md) — architecture, schema, API endpoints
- [Features](Project_specs/features.md) — full feature list and UI behaviour
- [Build Guide](Project_specs/BuildGuide.md) — step-by-step instructions to rebuild from scratch
