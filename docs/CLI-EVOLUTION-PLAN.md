# Piano Evoluzione CLI — MarTech Audit Tool

## 1. Stato Attuale vs Requisiti

### ✅ Cosa funziona GIÀ

| Funzionalità | Stato | Dettagli |
|---|---|---|
| Audit one-command | ✅ Parziale | `python3 cli/cli-audit.py example.com` — funziona ma NO subcommand `audit` |
| Auto-discovery (60+ tech) | ✅ Completo | CMS, payment, tracking, consent, schema, security headers |
| 11 analisi AI parallele | ✅ Completo | Claude Sonnet, 3 worker paralleli, retry su errori |
| Report HTML McKinsey-style | ✅ Completo | Cover, scoring, radar chart, findings, roadmap |
| Scoring A-F (6 aree) | ✅ Completo | Consent, tracking, ecommerce, SEO, accessibility, advertising |
| PageSpeed / CrUX integration | ✅ Completo | Con GOOGLE_API_KEY opzionale |
| Playwright JS rendering | ✅ Completo | Opzionale con `--render` |
| Caricamento .env | ✅ Completo | CLAUDE_API_KEY + GOOGLE_API_KEY da credentials/.env |

### 🔧 Cosa va ADATTATO

| Requisito | Cosa esiste | Cosa manca |
|---|---|---|
| Subcommand `audit` | Comando diretto (positional arg) | Ristrutturare con subcommand: `audit`, `wizard`, `report`, `auth` |
| Flag `--full` | Tutte le analisi girano sempre | Distinguere `--quick` (solo discovery) vs `--full` (discovery + AI) |
| Output colori/progress | Emoji + ANSI codes custom (classe `C`) | Migrare a `rich` per progress bar, tabelle, spinner |
| Report HTML | Generazione inline (500+ righe di HTML in Python) | Funziona, ma aggiungere `--format` per PDF/Markdown |

### 🆕 Cosa va sviluppato DA ZERO

| Requisito | Complessità | Note |
|---|---|---|
| **Subcommand routing** (audit/wizard/report/auth) | 🟢 Bassa | argparse subparsers, solo struttura |
| **Wizard interattivo** | 🟡 Media | questionary per Q&A, logica di configurazione audit |
| **OAuth Google (browser redirect)** | 🔴 Alta | google-auth-oauthlib, flusso OAuth2, token storage/refresh |
| **Google Ads API read-only** | 🔴 Alta | google-ads-api, CustomerService, CampaignService |
| **Google Analytics Data API** | 🟡 Media | google-analytics-data, report properties/metrics |
| **Google Search Console API** | 🟡 Media | google-auth, searchconsole API, query/sitemap data |
| **Export PDF** | 🟡 Media | weasyprint o playwright print-to-pdf |
| **Export Markdown** | 🟢 Bassa | Conversione findings → markdown strutturato |
| **Rich CLI experience** | 🟢 Bassa | Sostituire classe `C` con `rich` (progress, tables, panels) |
| **requirements.txt / pyproject.toml** | 🟢 Bassa | Gestione dipendenze |

---

## 2. Architettura CLI Proposta

```
python3 cli/cli-audit.py <command> [options]

COMANDI:
  audit <dominio>        Audit diretto (one-command)
    --full               Tutte le analisi (discovery + AI + API Google)
    --quick              Solo auto-discovery (no AI, no API)
    --client "Nome"      Nome cliente per il report
    --output file.html   Path output personalizzato
    --render             JS rendering con Playwright
    --pages URL1,URL2    Pagine aggiuntive

  wizard                 Audit guidato interattivo
                         Q&A → configurazione → lancio audit

  report                 Genera report da ultimo audit
    --format html|pdf|md Formato output (default: html)
    --input file.json    Da audit specifico (JSON intermedio)

  auth                   Gestione autenticazione Google
    auth login           OAuth browser flow → salva token
    auth status          Mostra token attivi e scope
    auth revoke          Revoca token salvati
```

---

## 3. Dipendenze Nuove

```txt
# requirements.txt
rich>=13.0              # CLI: progress bar, tabelle, colori, panels
questionary>=2.0        # CLI: wizard interattivo (select, checkbox, text)

# Google APIs (opzionali — il tool funziona anche senza)
google-auth>=2.0        # OAuth2 core
google-auth-oauthlib>=1.0  # OAuth2 browser flow
google-api-python-client>=2.0  # Google APIs generiche
google-ads>=24.0        # Google Ads API
google-analytics-data>=0.18  # GA4 Data API

# Report export (opzionali)
weasyprint>=60.0        # HTML → PDF (alternativa: playwright pdf)
```

---

## 4. Google OAuth — Design

```
credentials/
├── .env                    # API keys (Claude, Google API Key)
├── client_secret.json      # OAuth client ID (da Google Cloud Console)
├── token_analytics.json    # Token GA4 (auto-generato dopo login)
├── token_ads.json          # Token Google Ads (auto-generato)
└── token_searchconsole.json # Token GSC (auto-generato)
```

**Scope read-only:**
```python
SCOPES = {
    'analytics': ['https://www.googleapis.com/auth/analytics.readonly'],
    'ads': ['https://www.googleapis.com/auth/adwords.readonly'],
    'searchconsole': ['https://www.googleapis.com/auth/webmasters.readonly'],
}
```

**Flusso:**
1. `python3 cli/cli-audit.py auth login` → apre browser
2. Utente autorizza con account Google → redirect a localhost
3. Token salvato in `credentials/token_*.json`
4. Refresh automatico ad ogni audit (google-auth gestisce il refresh)

**Prerequisito utente:** creare un progetto Google Cloud Console e scaricare `client_secret.json`.

---

## 5. Priorità e Ordine di Sviluppo

### Sprint 1 — Fondamenta CLI (1-2 giorni)
> Obiettivo: CLI professionale con subcommand, senza rompere nulla

1. **requirements.txt + setup** — Creare file dipendenze, testare installazione
2. **Subcommand routing** — Ristrutturare argparse con subparsers (`audit`, `wizard`, `report`, `auth`)
3. **Migrare a Rich** — Sostituire classe `C` con `rich.console`, aggiungere:
   - `Progress` per fasi audit
   - `Table` per risultati discovery
   - `Panel` per executive summary
4. **Backward compatibility** — `python3 cli/cli-audit.py example.com` continua a funzionare (default → `audit`)

### Sprint 2 — Wizard + Export (1-2 giorni)
> Obiettivo: audit guidato e report multi-formato

5. **Wizard interattivo** — questionary-based:
   - Obiettivi audit (tracking, SEO, compliance, tutto)
   - Accesso piattaforme (Google Ads, GA4, GSC)
   - Info sito (CMS, ecommerce, settore)
   - → Genera config → lancia audit con parametri corretti
6. **Export Markdown** — Conversione findings → .md strutturato
7. **Export PDF** — weasyprint o Playwright `page.pdf()` dal report HTML

### Sprint 3 — Google OAuth + API (2-3 giorni)
> Obiettivo: dati reali da Google Ads, Analytics, Search Console

8. **OAuth flow** — `auth login/status/revoke`, browser redirect, token storage
9. **Google Analytics Data API** — Sessioni, bounce rate, conversioni, top pages
10. **Google Search Console API** — Query, impressioni, CTR, copertura, sitemap
11. **Google Ads API** — Campagne, spend, conversioni, quality score
12. **Integrazione nell'audit** — Se token presente, arricchisci il report con dati reali

### Sprint 4 — Rifinitura (1 giorno)
13. **JSON intermedio** — Salvare risultati audit in JSON (per ri-generare report senza ri-eseguire audit)
14. **Configurazione audit-profiles** — Profili preimpostati (ecommerce, lead-gen, publisher)
15. **Test end-to-end** — Verificare tutti i flussi

---

## 6. File da creare/modificare

| File | Azione | Sprint |
|---|---|---|
| `requirements.txt` | NUOVO | 1 |
| `cli/cli-audit.py` | MODIFICARE — subcommand, rich, wizard | 1-2 |
| `cli/auth.py` | NUOVO — Google OAuth flow | 3 |
| `cli/google_apis.py` | NUOVO — GA4, GSC, Ads data fetching | 3 |
| `cli/wizard.py` | NUOVO — Q&A interattivo | 2 |
| `cli/export.py` | NUOVO — PDF/Markdown generation | 2 |
| `credentials/client_secret.json` | MANUALE dall'utente — Google Cloud Console | 3 |

---

## 7. Rischi e Note

- **Google Cloud Console setup**: l'utente deve creare un progetto, abilitare le API, e scaricare `client_secret.json`. Questo è un prerequisito manuale.
- **Google Ads API**: richiede un Developer Token (approvazione Google, può richiedere giorni). Iniziare con test account.
- **WeasyPrint**: richiede dipendenze di sistema (cairo, pango). Alternativa: usare Playwright `page.pdf()` che è già integrato.
- **Backward compatibility**: l'audit attuale DEVE continuare a funzionare durante tutta l'evoluzione. Mai rompere il flusso esistente.
