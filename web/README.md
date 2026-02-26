# Web Interface (WIP)

Server locale per la versione web del MarTech Audit Tool.

## Stato attuale

- `server.py` — Server HTTP con CORS proxy, CrUX API, Playwright rendering
- `index.html` — Frontend prototipo
- `js/` — Moduli JS (app, checklist, ai-analysis, auto-discovery, report-generator, storage)
- `css/` — Stili

## Come avviare

```bash
cd web
python3 server.py
# Apri http://localhost:8080
```

## Stack futuro

Da valutare: Flask/FastAPI backend + HTMX o React lite per frontend production.
