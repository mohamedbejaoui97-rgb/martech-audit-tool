# MarTech Audit Tool — Status

## Cosa funziona (MVP)

| Componente | Stato | Note |
|---|---|---|
| CLI Audit L0 (auto-discovery) | ✅ Funzionante | `python3 cli/cli-audit.py <dominio>` |
| Report HTML McKinsey-style | ✅ Funzionante | Generato automaticamente in `output/` |
| Scoring system A-F (6 aree) | ✅ Funzionante | GTM, Analytics, Consent, SEO, Ads, Performance |
| AI Analysis (Claude API) | ✅ Funzionante | Richiede `CLAUDE_API_KEY` in `credentials/.env` |
| CrUX / PageSpeed integration | ✅ Funzionante | Richiede `GOOGLE_API_KEY` |
| Knowledge base YAML | ✅ Completa | ~400KB, 8450+ righe, 5 checklist verticali |

## In Progress (WIP)

| Componente | Stato | Note |
|---|---|---|
| Web interface | 🔧 Prototipo | Server locale funzionante, UI da rifinire |
| L1 Audit (deep checklist) | 📋 Pianificato | Usa le checklist YAML per audit approfondito |
| L2 Audit (expert review) | 📋 Pianificato | Review manuale guidata dall'AI |

## Pianificato

| Componente | Note |
|---|---|
| Core module (logica condivisa CLI/Web) | Estrazione da cli-audit.py |
| API REST (Flask/FastAPI) | Per versione web production |
| Dashboard investitori | Demo interattiva |
| Multi-client management | Gestione portfolio clienti |
