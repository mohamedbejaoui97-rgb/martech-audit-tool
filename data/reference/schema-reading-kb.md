# Schema Reading KB (Structured Data Audit Playbook)

## Scopo
Questo documento serve come knowledge base per leggere correttamente i risultati dei test schema (Schema Markup Validator + Google Rich Results Test) e produrre audit SEO tecnici, coerenti e non fuorvianti.

---

## Principio chiave
**Markup valido su Schema.org ≠ garanzia di Rich Results su Google.**

Un audit corretto deve separare:
1. Presenza markup
2. Validità sintattica
3. Idoneità rich results Google
4. Qualità/coerenza/completezza
5. Copertura per template del sito

---

## Differenza tra i tool (OBBLIGATORIA)

### 1) Schema Markup Validator (validator.schema.org)
**Serve per:**
- Validare markup Schema.org in generale
- Estrarre JSON-LD / Microdata / RDFa
- Trovare errori sintattici
- Vedere i tipi rilevati nel grafo

**NON serve per:**
- Dire se Google mostrerà rich results
- Verificare linee guida qualità Google
- Garantire eligibility di feature Google

**Interpretazione output:**
- `0 errori, 0 avvisi` = sintassi OK
- Non implica "schema completi"
- Non implica "SEO perfetto"
- Non implica "Google mostrerà snippet avanzati"

---

### 2) Google Rich Results Test
**Serve per:**
- Verificare quali rich results Google può generare
- Vedere errori/warning relativi alle feature Google
- Valutare eligibility tecnica alle feature supportate

**NON serve per:**
- Validare tutti i tipi Schema.org possibili
- Fare da solo un audit di qualità semantica completo

**Interpretazione output:**
- Se una feature è idonea, può essere *eligible*
- Anche con test OK, Google non garantisce la visualizzazione del rich result

---

## Gerarchia di lettura (ordine corretto)
Quando analizzi una pagina, leggi in questo ordine:

1. **Contesto pagina**
   - homepage / category / service / product / article / local / contact

2. **Tool usato**
   - Schema Markup Validator / Rich Results Test / entrambi

3. **Tipi rilevati**
   - Es: Organization, WebSite, BreadcrumbList, Product, Article, FAQPage

4. **Esito tecnico**
   - errori
   - avvisi
   - note

5. **Completezza**
   - required (se Google feature-specific)
   - recommended
   - campi utili mancanti

6. **Coerenza con contenuto visibile**
   - il markup descrive davvero ciò che l'utente vede?
   - il focus della pagina è rappresentato dal tipo principale?

7. **Conclusione**
   - cosa è OK
   - cosa manca
   - priorità di fix
   - prossimi test

---

## Regole anti-fraintendimento (hard rules)
- Mai scrivere "schema perfetti" se hai solo testato una homepage.
- Mai confondere "validator ok" con "rich result guaranteed".
- Mai proporre schema non supportati da Google come se generassero rich results.
- Mai usare schema per contenuti non visibili in pagina.
- Mai usare tipi generici se esiste un tipo specifico adatto alla pagina.
- Mai fare audit completo senza controllare i template interni.

---

## Homepage: lettura standard

### Caso comune
Tipi rilevati:
- `Organization`
- `WebSite`

### Interpretazione corretta
- La homepage ha **schema base** implementati
- Se `0 errori / 0 avvisi`, il markup è **tecnicamente valido**
- Questo NON certifica:
  - copertura completa del sito
  - corretta implementazione dei template interni
  - idoneità a rich results Google oltre al contesto supportato

### Prossimo step obbligatorio
Testare almeno 1 URL per ciascun template principale.

---

## Cosa aspettarsi per tipo pagina (guida rapida)

### Homepage
**Attesi frequentemente:**
- `WebSite`
- `Organization` (o `LocalBusiness` se azienda locale)
- `WebPage` (esplicito o implicito)
- `BreadcrumbList` (opzionale, dipende dal template)

**Controlli chiave:**
- brand coerente (`name`, `url`, `logo`)
- dati visibili / coerenti
- assenza di duplicati inutili di `WebSite`

---

### Pagina articolo/blog
**Attesi frequentemente:**
- `Article` / `BlogPosting` / `NewsArticle`
- `BreadcrumbList`
- `WebPage`
- eventualmente `FAQPage` (solo se FAQ presenti e visibili)

**Controlli chiave:**
- headline, author, datePublished/dateModified, image
- corrispondenza con contenuto reale
- immagine crawlable e pertinente

---

### Pagina prodotto (e-commerce)
**Attesi frequentemente:**
- `Product`
- `Offer` / `AggregateOffer`
- eventuale `Review` / `AggregateRating` (solo se reali)
- `BreadcrumbList`

**Controlli chiave:**
- prezzo, disponibilità, valuta
- SKU/GTIN/brand se disponibili
- dati aggiornati e coerenti con UI

---

### Pagina servizio
**Attesi possibili (dipende dal caso):**
- `Service` (Schema.org, non sempre con rich result Google diretto)
- `Organization` / `LocalBusiness`
- `BreadcrumbList`
- `FAQPage` se presente e visibile

**Controlli chiave:**
- descrizione servizio chiara
- area geografica (se local/service area)
- coerenza con offerta reale

---

### Pagina local / contatti
**Attesi frequentemente:**
- `LocalBusiness` (tipo specifico se possibile)
- `PostalAddress`
- `OpeningHoursSpecification`
- `GeoCoordinates` (se pertinente)
- `ContactPoint`

**Controlli chiave:**
- NAP coerente (name-address-phone)
- orari e contatti aggiornati
- dati visibili in pagina

---

## Matrix di valutazione (scoring interno consigliato)

### 1. Presenza (0-2)
- 0 = assente
- 1 = presente ma minimo
- 2 = presente e adeguato

### 2. Validità tecnica (0-2)
- 0 = errori bloccanti
- 1 = warning / problemi minori
- 2 = nessun errore rilevante

### 3. Completezza (0-2)
- 0 = povero / campi chiave mancanti
- 1 = discreto
- 2 = ricco e ben compilato

### 4. Coerenza con contenuto (0-2)
- 0 = incoerente / fuorviante
- 1 = parziale
- 2 = coerente e rappresentativo

### 5. Idoneità Google (0-2)
- 0 = non idoneo / non supportato / test non fatto
- 1 = potenzialmente idoneo ma incompleto
- 2 = testato e idoneo tecnicamente

**Totale per pagina: /10**

---

## Output standard (template risposta audit)

### Sintesi esecutiva
- [1-3 frasi]
- Tipi trovati
- Stato tecnico
- Livello di maturità (base / discreto / avanzato)

### Dettaglio test
- Tool usato:
- URL:
- Tipi rilevati:
- Errori:
- Avvisi:
- Note:

### Interpretazione corretta
- Cosa significa:
- Cosa non significa:

### Gap / miglioramenti
- [elenco puntato]

### Prossimi test consigliati
- [template interni da controllare]

### Conclusione
- Priorità 1:
- Priorità 2:
- Priorità 3:

---

## Frasi standard da usare (per evitare errori comunicativi)

### Quando vedi 0 errori / 0 avvisi in homepage
"Il markup strutturato presente in homepage risulta tecnicamente valido nel validator, ma questo dato da solo non consente di concludere che l'implementazione schema dell'intero sito sia completa né che Google mostrerà risultati avanzati."

### Quando Claude tende a sovrainterpretare
"Valido a livello sintattico non equivale a idoneo a livello Google né a semanticamente completo."

### Quando manca il test Google
"Per confermare l'idoneità ai rich results, è necessario un test aggiuntivo con Google Rich Results Test."

---

## Tipi homepage base: cosa controllare (quick checklist)

### WebSite (homepage root)
- `@type = WebSite`
- `name`
- `url`
- eventuale `alternateName`
- eventuale `potentialAction` con `SearchAction` (se ricerca interna presente)

### Organization
- `@type = Organization` (o tipo più specifico)
- `name`
- `url`
- `logo`
- `sameAs`
- `contactPoint` (se utile)
- `address` (se pertinente)
- identificativi aziendali (se disponibili e utili)

---

## Escalation: quando segnalare "attenzione"
Segnala come **Critico** se:
- markup descrive contenuti non visibili
- review/rating fake o non supportati
- dati prodotto incoerenti con prezzo reale
- markup bloccato a Googlebot / noindex / access issues
- duplicate homepages con schema incoerente

Segnala come **Medio** se:
- markup valido ma estremamente minimale
- tipi troppo generici
- campi raccomandati mancanti
- assenza markup nei template chiave

Segnala come **Basso** se:
- piccoli miglioramenti di completezza
- refactoring / pulizia nodi duplicati non bloccanti

---

## Workflow audit consigliato (5 minuti / 15 minuti / approfondito)

### Audit rapido (5 min)
- Homepage (validator + rich results)
- Un template principale
- Verdetto base + rischio

### Audit standard (15 min)
- Homepage
- 1 categoria/servizio
- 1 prodotto/articolo
- 1 contatti/local
- Lista gap prioritari

### Audit approfondito
- Campionamento template completo
- Verifica output CMS/plugin
- Confronto con Search Console (Enhancements / manual actions / indexing)
- Piano di implementazione per template

---

## Note finali
- L'obiettivo dello schema non è "aggiungere più markup possibile".
- L'obiettivo è dare segnali strutturati corretti, coerenti, specifici e utili.
- La qualità semantica + coerenza con la pagina batte la quantità.

IMPORTANT:
Do not conclude "schema implementation is good" from homepage-only validation.
Always separate:
- Schema.org syntax validity
- Google rich result eligibility
- semantic completeness
- site-wide template coverage
