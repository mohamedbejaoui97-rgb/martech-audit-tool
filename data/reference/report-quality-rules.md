# Report Quality Rules — MarTech Audit Tool

## 1. TONO
- MAI usare: "catastrofico", "devastante", "disastroso", "terribile", "pazzesco"
- Tono professionale e oggettivo, come un consulente senior
- Severity tramite etichette (CRITICO/ALTO/MEDIO/BASSO), non aggettivi emotivi

## 2. DATI
- MAI inventare stime in euro o cifre di revenue
- MAI inventare percentuali di impatto senza fonte
- Usare solo dati misurati (PSI, CrUX, HTML parsing)
- Se un dato non è disponibile, dire "dato non disponibile" — MAI inventare

## 3. SOLUZIONI
- Ogni fix DEVE essere actionable: nome app/plugin, path file, percorso admin, snippet codice
- MAI scrivere "contatta il supporto", "verifica manualmente", "audita"
- Se Shopify: usare path come sections/header.liquid, snippets/, config/settings_schema.json
- Se WordPress: indicare plugin specifico e hook
- Se non conosci la piattaforma: dare soluzione generica con codice HTML/JS

## 4. STRUTTURA REPORT
- Ogni finding in UNA SOLA sezione (no duplicazioni)
- Ownership: performance possiede CWV, seo possiede meta/heading, security possiede headers
- Per ogni finding: cosa → stato attuale → target → perché → come si risolve
- Impact levels: CRITICO/ALTO/MEDIO/BASSO con spiegazione qualitativa

## 5. COMPLETEZZA
- NON delegare mai lavoro al lettore
- Analizzare TUTTE le pagine fornite, non solo homepage
- Per immagini senza alt: elencare URL+src (prime 10 + "e altre X")
- Per heading: mostrare struttura ad albero reale, poi proporre struttura ideale
- Per schema: proporre JSON-LD completi con esempio specifico per il sito

## 6. ROBOTS.TXT
- Disallow su sort_by, filter, cart, checkout, admin = BEST PRACTICE, non problemi
- Bot tiers: CRITICI (Googlebot*), IMPORTANTI (Bingbot, Slurp), SOCIAL (facebookexternalhit, Twitterbot)
- Altri bot: ignorare o notare come "correttamente bloccato"

## 7. DATI CRAWLER
- Se SquirrelScan non raggiunge un URL ma il sito risponde 200 = limite crawler
- MAI spacciare limiti del crawler come problemi del sito
