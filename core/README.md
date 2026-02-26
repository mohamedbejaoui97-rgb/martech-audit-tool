# Core Module (Pianificato)

Questo modulo conterrà la logica condivisa tra CLI e Web, estratta da `cli-audit.py`.

## Piano di estrazione

Funzionalità da estrarre in moduli separati:
- `scanner.py` — Auto-discovery tag e tecnologie
- `scoring.py` — Sistema di scoring A-F
- `report.py` — Generazione report HTML
- `ai_analysis.py` — Integrazione Claude API
- `crux.py` — Integrazione CrUX/PageSpeed

## Stato

Non ancora implementato. Il codice attuale vive interamente in `cli/cli-audit.py` (1920 righe).
