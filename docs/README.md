# MarTech Audit Tool — Guida Uso

## Requisiti

- Python 3.10+
- Connessione internet
- (Opzionale) `CLAUDE_API_KEY` per AI analysis
- (Opzionale) `GOOGLE_API_KEY` per CrUX/PageSpeed

## Installazione

```bash
# Clona il repository
cd martech-audit-tool

# Configura le credenziali
cp credentials/.env.example credentials/.env
# Modifica credentials/.env con le tue API keys
```

Il core dell'audit usa solo la libreria standard Python. Feature opzionali richiedono:
- **Playwright** per JS rendering (`pip install playwright && playwright install chromium`)
- **Claude API key** per analisi AI
- **Google API key** per CrUX/PageSpeed

## Uso CLI

```bash
# Audit base
python3 cli/cli-audit.py example.com

# Con nome cliente
python3 cli/cli-audit.py example.com --client "Acme Corp"

# Output personalizzato
python3 cli/cli-audit.py example.com --output mio-report.html

# Pagine specifiche
python3 cli/cli-audit.py example.com --pages https://example.com/about,https://example.com/contact
```

## Cosa produce

Un report HTML completo con:
- Score A-F per 6 aree (GTM, Analytics, Consent, SEO, Ads, Performance)
- Auto-discovery di tag e tecnologie
- Analisi AI delle criticità (se API key configurata)
- Metriche CrUX/Core Web Vitals (se Google API key configurata)
- Raccomandazioni prioritizzate

I report vengono salvati in `output/`.

## Configurazione credenziali

Crea `credentials/.env`:

```
CLAUDE_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
```
