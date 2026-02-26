# Architettura MarTech Audit Tool

## Principio fondamentale: Doppia natura CLI/Web

Ogni funzionalità deve essere utilizzabile in due modalità:
1. **CLI** (Claude Max) — per audit operativi, automazione, uso quotidiano
2. **Web** (API + UI) — per demo investitori, dashboard clienti, self-service

## Struttura del progetto

```
martech-audit-tool/
├── cli/          # Interfaccia CLI (entry point: cli-audit.py)
├── web/          # Interfaccia Web (server.py + frontend)
├── core/         # Logica condivisa (futuro — da estrarre da cli-audit.py)
├── data/
│   ├── checklists/   # Template audit + 5 checklist YAML verticali
│   └── reference/    # Configurazioni e reference (Osmani, consent EU)
├── output/       # Report generati (gitignored)
├── credentials/  # API keys (gitignored)
└── docs/         # Documentazione
```

## 3 livelli di audit

| Livello | Descrizione | Stato |
|---|---|---|
| **L0** | Auto-discovery automatico (tag, tecnologie, metriche) | ✅ Implementato |
| **L1** | Deep checklist audit con knowledge base YAML | 📋 Pianificato |
| **L2** | Expert review guidata dall'AI | 📋 Pianificato |

## Knowledge Base YAML

~400KB, 8450+ righe distribuite su 5 checklist verticali:

- `gtm-ecommerce-checklist.yaml` — 46KB, Google Tag Manager + ecommerce tracking
- `iubenda-consent-checklist.yaml` — 54KB, Consent/CMP compliance EU/DMA
- `gsc-audit-checklist.yaml` — 82KB, Google Search Console
- `google-ads-audit-checklist.yaml` — 114KB, Google Ads audit
- `meta-ads-audit-checklist.yaml` — 103KB, Meta Business Suite

## Scoring System

6 aree, score 0-10 ciascuna, grade A-F:
1. Tag Management (GTM)
2. Analytics (GA4)
3. Consent & Privacy
4. SEO tecnico
5. Advertising pixels
6. Performance (CWV)

## Stack futuro (Web)

Opzioni considerate:
- **Backend**: Flask o FastAPI (Python, riuso logica CLI)
- **Frontend**: HTMX (semplicità) o React lite (interattività)
- **Deploy**: Railway / Render per MVP, poi scaling
