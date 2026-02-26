// AI Analysis - Claude API + Osmani Web Quality Skills Integration
const AIAnalysis = {

  // Config loaded from osmani-config.json
  _config: null,

  // Inline fallback for OSMANI_BASE
  _FALLBACK_OSMANI_BASE: `You are a senior web quality auditor trained on Google Lighthouse internals and Addy Osmani's web quality methodology (150+ production audits). You provide specific, actionable findings categorized by severity. Always respond in ITALIAN.

For EVERY finding, use this exact format:
**FINDING [SEVERITY]:** Title
- Problema: detailed description of the current state
- Impatto: quantified business impact (e.g., -20% CTR, +0.5s LCP, €X lost revenue, legal risk)
- Fix: specific actionable recommendation with code snippets where applicable, and expected result after fix

Severity levels: CRITICO (immediate fix, revenue/legal impact), ALTO (fix within 1 month, significant impact), MEDIO (fix within 3 months), BASSO (nice to have).

When analyzing multi-page content, clearly indicate which page each finding applies to.`,

  get OSMANI_BASE() {
    return this._config?.prompts?.osmani_base || this._FALLBACK_OSMANI_BASE;
  },

  get PROMPTS() {
    if (this._config?.prompts) {
      const p = { ...this._config.prompts };
      delete p.osmani_base;
      if (Object.keys(p).length) return p;
    }
    return this._FALLBACK_PROMPTS;
  },

  async _loadConfig() {
    if (this._config) return;
    try {
      const res = await fetch('/data/osmani-config.json');
      if (res.ok) this._config = await res.json();
    } catch (e) {
      console.warn('AIAnalysis: config load failed, using fallbacks', e);
    }
  },

  _FALLBACK_PROMPTS: {
    performance: `${''} Esegui un audit performance completo basato su Lighthouse e Core Web Vitals.

BUDGET DI PERFORMANCE (soglie Osmani):
- Peso totale pagina: < 1.5MB
- JavaScript: < 300KB (compresso)
- CSS: < 100KB
- Immagini above-fold: < 500KB
- Font: < 100KB
- Script terze parti: < 200KB
- TTFB: < 800ms
- LCP: <= 2.5s (buono), 2.5-4s (migliorabile), >4s (scarso)
- INP: <= 200ms (buono), 200-500ms (migliorabile), >500ms (scarso)
- CLS: <= 0.1 (buono), 0.1-0.25 (migliorabile), >0.25 (scarso)

CHECKLIST:
1. SERVER: TTFB, compressione Brotli/Gzip, HTTP/2+, CDN, edge caching
2. RENDER-BLOCKING: Critical CSS inline < 14KB? Script defer/async? Font preload con font-display:swap?
3. IMMAGINI: Formati moderni (AVIF > WebP > PNG)? srcset responsive? Lazy loading below-fold? LCP image con fetchpriority="high"?
4. JAVASCRIPT: Code splitting? Tree shaking? Codice inutilizzato?
5. FONT: font-display impostato? Font preloaded? Subsetting unicode?
6. CACHING: Cache-Control headers? Immutable per asset hashati?
7. TERZE PARTI: Script async/defer? Facade pattern per embed pesanti?
8. IMPATTO GOOGLE ADS: Come le performance impattano Quality Score e CPC

Per ogni problema trovato indica: severità (CRITICO/ALTO/MEDIO/BASSO), impatto business, e fix specifico.`,

    cwv: `Esegui un audit specializzato Core Web Vitals. Google misura al 75° percentile.

**LCP (Largest Contentful Paint) - Target: <= 2.5s:**
- TTFB lento (> 800ms)?
- Risorse render-blocking?
- LCP element: è preloaded? fetchpriority="high"? Nel HTML iniziale (non JS-rendered)?
- Critical CSS inline?
- Font con font-display:swap?

**INP (Interaction to Next Paint) - Target: <= 200ms:**
- Long tasks > 50ms sul main thread?
- Event handlers pesanti (visual feedback immediato? Lavoro non-critico deferito?)
- Script terze parti bloccanti?
- Per React: componenti memoizzati? useTransition per update non urgenti?

**CLS (Cumulative Layout Shift) - Target: <= 0.1:**
- Immagini senza width/height o aspect-ratio?
- Embed/iframe senza spazio riservato?
- Contenuto iniettato dinamicamente sopra il viewport?
- Font che causano FOUT (font-display:optional o size-adjust)?
- Animazioni che usano layout (usare transform/opacity)?

Per ogni metrica: stato attuale, causa root, fix specifico con codice.`,

    seo: `Esegui un audit SEO completo basato su Google Search guidelines e Lighthouse SEO.

**SEO TECNICO:**
- robots.txt: permette crawling? Non blocca risorse? Include sitemap?
- Meta robots: index/follow corretto? noindex dove appropriato?
- Canonical URL: self-referencing? Previene duplicati?
- XML Sitemap: max 50K URL, solo URL canoniche indicizzabili, lastmod aggiornato
- Struttura URL: hyphens, lowercase, < 75 chars, keyword, no parametri
- HTTPS ovunque

**ON-PAGE SEO:**
- Title tag: 50-60 chars, keyword primaria all'inizio, unico per pagina, brand alla fine
- Meta description: 150-160 chars, keyword inclusa, CTA compelling, unica
- Heading hierarchy: singolo H1, gerarchia logica, nessun livello saltato
- Image SEO: filename descrittivi, alt text, compressi, WebP/AVIF, lazy below-fold
- Internal linking: anchor text descrittivo (no "click here"), breadcrumbs

**STRUCTURED DATA (JSON-LD):**
- Schema Organization, Product, Offer, FAQ, BreadcrumbList
- Validazione contro schema.org
- Rich results eligibility

**MOBILE SEO:**
- Viewport meta responsive
- Tap targets >= 48px
- Font-size >= 16px
- No horizontal scroll

**INTERNATIONAL SEO (se multi-lingua):**
- hreflang tags corretti
- html lang attribute

Per ogni issue: severità, impatto su ranking/CTR, fix specifico.`,

    accessibility: `Esegui un audit accessibilità WCAG 2.1 AA completo seguendo i principi POUR.

**PERCEIVABLE:**
- Ogni <img> ha alt text significativo? Decorative con alt=""?
- Icon buttons hanno accessible name (aria-label o visually-hidden text)?
- Contrasto colori >= 4.5:1 testo normale, >= 3:1 testo grande?
- Colore non è unico indicatore (icone + testo)?
- Video con captions?

**OPERABLE:**
- Tutti gli elementi interattivi accessibili da tastiera?
- Nessuna keyboard trap? Modal con Escape per chiudere e focus management?
- Focus indicator visibile (:focus-visible)?
- Skip link "Skip to main content" presente?
- prefers-reduced-motion rispettato?
- Tap targets >= 48px?

**UNDERSTANDABLE:**
- <html lang> impostato?
- Form input con <label> associato?
- Errori form con aria-invalid + aria-describedby?
- role="alert" per errori annunciati?
- Navigazione consistente con aria-current?

**ROBUST:**
- HTML valido (no ID duplicati, nesting corretto)?
- Elementi nativi preferiti su ARIA (button vs div role=button)?
- ARIA roles/properties usati correttamente?
- Live regions per contenuto dinamico (aria-live)?

Categorizza: CRITICO (fix immediato), ALTO (fix prima del lancio), MEDIO (fix presto).
Per ogni issue il fix specifico con codice.
Impatto issues comuni: inaccessibilità per screen reader, violazione legale (EAA 2025), perdita clienti.`,

    security: `Esegui un audit security e best practices web.

**SECURITY:**
- HTTPS ovunque? No mixed content?
- HSTS header (Strict-Transport-Security)?
- Content Security Policy (CSP) configurata? Nonce-based per inline scripts?
- Security headers: X-Frame-Options, X-Content-Type-Options (nosniff), Referrer-Policy, Permissions-Policy
- Nessuna libreria JS vulnerabile (jQuery obsoleto, librerie con CVE note)?
- Input sanitization (textContent vs innerHTML, DOMPurify)?
- Cookie sicuri (Secure, HttpOnly, SameSite=Strict)?

**BROWSER COMPATIBILITY:**
- HTML5 doctype?
- <meta charset="UTF-8"> primo elemento in <head>?
- Viewport meta tag?
- Feature detection (non browser detection)?
- Passive event listeners per touch/wheel?

**API DEPRECATE:**
- No document.write?
- No synchronous XHR?
- No Application Cache?

**ERRORI & CODE QUALITY:**
- Console errors in produzione?
- Error handling corretto (try/catch, error boundaries)?
- Global error handlers (window error + unhandledrejection)?
- HTML semantico (header/nav/main/article)?
- No ID duplicati?
- Immagini con aspect ratio corretto (no layout shift)?

Per ogni issue: severità, rischio (OWASP category se applicabile), fix specifico.`,

    robots: `Analizza questo robots.txt come esperto SEO tecnico.

Verifica:
1. User-agent configurati (Googlebot, Bingbot, * minimo)
2. Sitemap reference presente
3. Disallow sensati (no blocco pagine importanti per errore)
4. Crawl-delay (sconsigliato per Googlebot)
5. Risorse CSS/JS non bloccate (Googlebot ne ha bisogno per rendering)
6. Conformità best practices Google

Rispondi in ITALIANO con:
**STATO:** OK / Problemi trovati
**SITEMAP:** Presente/Assente + URL
**USER-AGENTS:** Lista configurati
**PROBLEMI:** (con severità CRITICO/ALTO/MEDIO/BASSO)
**RACCOMANDAZIONI:** miglioramenti specifici
**SCORE SUGGERITO:** /10`,

    sitemap: `Analizza questa sitemap XML come esperto SEO tecnico.

Verifica:
1. Formato XML valido
2. Tipo: sitemap index o sitemap singola
3. Conteggio URL / sub-sitemap
4. lastmod: aggiornato (dinamica) o statico/assente
5. URL coerenti col dominio (no redirect verso domini esterni)
6. Nessun URL non canonico o noindex
7. Max 50K URL per file
8. Struttura logica (per country, per tipo contenuto, per categoria)

Rispondi in ITALIANO con:
**STATO:** OK / Problemi trovati
**TIPO:** Sitemap Index / Singola
**CONTEGGIO:** N URL o sub-sitemap
**LASTMOD:** Aggiornato/Statico/Assente
**PROBLEMI:** (con severità)
**RACCOMANDAZIONI:** miglioramenti specifici
**SCORE SUGGERITO:** /10`,

    datalayer: `Analizza questo dataLayer ecommerce come esperto Google Tag Manager.

Verifica conformità con la documentazione ufficiale Google GA4 Ecommerce:
https://developers.google.com/analytics/devguides/collection/ga4/ecommerce

Per ogni evento controlla:
1. Nome evento corretto (add_to_cart, purchase, etc.)
2. Struttura oggetto ecommerce conforme
3. Campi obbligatori presenti: currency, value, items[]
4. Per items[]: item_id (string), item_name (string), price (number), quantity (number), item_brand, item_category
5. TIPI DATI: price e value devono essere NUMBER (non string), item_id deve essere STRING (non number)
6. ecommerce:null push PRIMA dell'evento (pulizia dataLayer)
7. transaction_id univoco per purchase
8. Nessun campo vuoto o undefined dove critico

Rispondi in ITALIANO con:
**EVENTI TROVATI:** lista
**CONFORMITA:** % conforme a Google docs
**PROBLEMI:** (con severità e impatto su GA4/Google Ads)
**FIX SUGGERITI:** codice corretto per ogni problema`,

    seo_deep: `Esegui un SEO AUDIT APPROFONDITO basato su Google Search Quality Rater Guidelines e E-E-A-T.

**E-E-A-T (Experience, Expertise, Authoritativeness, Trustworthiness):**
- Autore identificabile con bio/credenziali? Pagina "Chi siamo" completa?
- Contenuti mostrano esperienza diretta (foto originali, case study, dati proprietari)?
- Segnali di autorità: backlink profile quality, menzioni brand, citazioni
- Trust: HTTPS, privacy policy, contatti chiari, recensioni verificate

**SITE-TYPE SPECIFIC (Ecommerce):**
- Keyword cannibalization: pagine multiple che competono per stesse keyword?
- Thin content: pagine prodotto con < 300 parole di contenuto unico?
- Faceted navigation: filtri creano URL duplicati? Gestione canonical/noindex?
- Pagination: rel="next"/"prev" o scroll infinito? Crawl budget impact
- Out-of-stock products: 404, 301, o mantieni pagina con alternativa?
- Internal search: genera URL crawlabili? noindex se necessario?

**CRAWL BUDGET & INDEXATION:**
- Rapporto pagine indicizzate vs totali (site:domain.com)
- Pagine orfane (non linkate internamente)?
- Redirect chains (max 2 hop)?
- Soft 404 (pagine che sembrano errori ma danno 200)?
- Parametri URL in Search Console (se deducibili)

**CONTENT GAPS:**
- Categorie senza contenuto editoriale/guida?
- Blog collegato a pagine commerciali?
- Landing page per intent navigazionale vs transazionale vs informazionale
- FAQ schema per long-tail keywords

**UTM & NAMING CONVENTIONS:**
- URL campaign tracking: utm_source/medium/campaign structure
- Naming convention consistente: object_action format (es: newsletter_click, banner_view)
- Tracking plan documentato?

Per ogni issue: severità, impatto su ranking/traffico organico, fix specifico con priorità.`,

    cro: `Esegui un audit CRO (Conversion Rate Optimization) completo della pagina.

**1. VALUE PROPOSITION (Above the Fold):**
- Il visitatore capisce COSA offri, PER CHI, e PERCHÉ scegliere te in 5 secondi?
- Headline: specifica e outcome-driven? O generica/buzzword?
- Subheadline: complementa la headline con il "come"?
- Visual hero: supporta il messaggio o è stock photography generica?

**2. COPYWRITING & MESSAGING:**
- Benefici > Features? Focus su outcome del cliente?
- Linguaggio del target (non aziendalese)?
- Testo scansionabile: bullet points, paragrafi corti, bold su parole chiave?
- Storytelling: problema → soluzione → risultato?

**3. CTA (Call-to-Action):**
- CTA primaria above-the-fold? Alto contrasto?
- Testo action-oriented e specifico? ("Inizia prova gratuita" > "Scopri di più" > "Submit")
- Un solo CTA primario per sezione (no paradosso della scelta)?
- Micro-copy di supporto sotto CTA ("Nessuna carta richiesta", "30gg gratis")
- Gerarchia visiva: primario (pieno) > secondario (outline) > terziario (link)

**4. TRUST SIGNALS & SOCIAL PROOF:**
- Recensioni con nome, foto, dettagli specifici (no generiche)?
- Rating aggregato visibile (stelle)?
- Loghi clienti/media/certificazioni?
- Numeri concreti ("10.000+ clienti", "+35% conversioni")?
- Garanzie esplicite (reso, rimborso)?
- Badge sicurezza pagamento?

**5. OBJECTION HANDLING:**
- FAQ presenti che rispondono alle obiezioni principali?
- Prezzo trasparente (no sorprese al checkout)?
- Policy reso facilmente trovabile?
- Contatto facile (chat, telefono visibile)?

**6. FRICTION POINTS:**
- Checkout: guest checkout? Campi minimi? Progress bar?
- Form: validazione inline? Autofill supportato?
- Loading: skeleton screens? Feedback immediato su azioni?
- Error recovery: messaggi specifici con soluzione?

**7. PAGE-TYPE SPECIFIC:**
- Homepage: hero + percorso chiaro per segmenti diversi
- Categoria: filtri, ordinamento, info essenziali su card prodotto
- Prodotto: gallery zoomabile, stock/urgency, cross-sell non invasivo
- Carrello: summary, upsell, rassicurazione
- Checkout: passi chiari, dati salvati, opzioni pagamento visibili

Per ogni area: score /10, problemi specifici con severità, fix concreto con impatto atteso su conversion rate.`,

    advertising: `Esegui un audit della readiness pubblicitaria del sito ecommerce.

**GOOGLE ADS READINESS:**
- Tag di Google (gtag.js o Google Tag via GTM) presente e configurato?
- Conversion Linker attivo per cross-device tracking?
- Remarketing tag / Google Ads remarketing configurato?
- Enhanced Conversions (conversioni avanzate) attive? User data (email, phone) passati?
- Conversion tracking: purchase, add_to_cart, begin_checkout tracciati come conversioni?
- Google Merchant Center: feed prodotti probabile? Structured data Product/Offer per Shopping?
- Dynamic remarketing: parametri ecomm_prodid, ecomm_pagetype nel dataLayer?

**META ADS READINESS:**
- Meta Pixel installato e funzionante?
- Eventi standard configurati (ViewContent, AddToCart, Purchase)?
- Conversions API (CAPI) server-side presente?
- Catalogo prodotti collegabile?

**TRACKING QUALITY per ADVERTISING:**
- Deduplication: eventi purchase non duplicati?
- Attribution: UTM parameters strutturati? GCLID/FBCLID preservati?
- Cross-domain: linker attivo se checkout su dominio diverso?
- Consent Mode: ad_storage e ad_user_data gestiti correttamente per DMA?

**IMPATTO BUSINESS:**
- Quality Score Google Ads: come le performance del sito (LCP, speed) impattano il CPC
- ROAS tracking accuracy: se i dati di conversione sono affidabili per l'ottimizzazione bidding
- Audience building: se il remarketing puo costruire liste audience efficaci

Per ogni issue: severita, impatto su ROAS/CPC, fix specifico.`
  },

  // Fetch via local proxy to avoid CORS
  async _fetch(url) {
    const proxyUrl = '/proxy?url=' + encodeURIComponent(url);
    const res = await fetch(proxyUrl);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
      throw new Error(err.error || `Errore fetch ${url}`);
    }
    return res;
  },

  async analyze(type, url, apiKey) {
    if (!apiKey) throw new Error('API key Claude non configurata');
    await this._loadConfig();

    // Fetch resource content based on type
    let content = '';
    try {
      if (type === 'robots') {
        const cleanUrl = url.replace(/\/$/, '');
        const res = await this._fetch(cleanUrl + '/robots.txt');
        content = await res.text();
      } else if (type === 'sitemap') {
        const res = await this._fetch(url);
        content = await res.text();
      } else if (type === 'performance' || type === 'cwv') {
        const googleKey = Storage.getGoogleKey();
        const apiUrl = `https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=${encodeURIComponent(url)}&strategy=mobile&category=performance&category=accessibility&category=seo&category=best-practices${googleKey ? '&key=' + googleKey : ''}`;
        const res = await fetch(apiUrl);
        const data = await res.json();
        content = JSON.stringify({
          scores: {
            performance: Math.round((data.lighthouseResult?.categories?.performance?.score || 0) * 100),
            accessibility: Math.round((data.lighthouseResult?.categories?.accessibility?.score || 0) * 100),
            seo: Math.round((data.lighthouseResult?.categories?.seo?.score || 0) * 100),
            best_practices: Math.round((data.lighthouseResult?.categories?.['best-practices']?.score || 0) * 100)
          },
          metrics: {
            lcp: data.lighthouseResult?.audits?.['largest-contentful-paint']?.displayValue,
            inp: data.lighthouseResult?.audits?.['interaction-to-next-paint']?.displayValue || 'N/A',
            cls: data.lighthouseResult?.audits?.['cumulative-layout-shift']?.displayValue,
            fcp: data.lighthouseResult?.audits?.['first-contentful-paint']?.displayValue,
            si: data.lighthouseResult?.audits?.['speed-index']?.displayValue,
            tbt: data.lighthouseResult?.audits?.['total-blocking-time']?.displayValue,
            ttfb: data.lighthouseResult?.audits?.['server-response-time']?.displayValue
          },
          opportunities: Object.entries(data.lighthouseResult?.audits || {})
            .filter(([k, v]) => v.score !== null && v.score < 1 && v.details?.type === 'opportunity')
            .map(([k, v]) => ({ audit: k, title: v.title, savings: v.displayValue, score: v.score }))
            .slice(0, 10),
          diagnostics: Object.entries(data.lighthouseResult?.audits || {})
            .filter(([k, v]) => v.score !== null && v.score < 1 && v.details?.type === 'table')
            .map(([k, v]) => ({ audit: k, title: v.title, score: v.score }))
            .slice(0, 10)
        }, null, 2);
      } else if (type === 'cro') {
        // CRO: fetch homepage + discover and fetch category + product pages
        try {
          const res = await this._fetch(url);
          const html = await res.text();
          const headMatch = html.match(/<head[^>]*>([\s\S]*?)<\/head>/i);
          const bodyMatch = html.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
          const homepageContent = `HEAD:\n${(headMatch?.[1] || '').substring(0, 5000)}\nBODY (first 10000 chars):\n${(bodyMatch?.[1] || '').substring(0, 10000)}`;

          // Discover internal links for category and product pages
          const baseUrl = new URL(url);
          const linkRegex = /href=["'](\/[^"'#?]+)["']/gi;
          const links = [];
          let match;
          while ((match = linkRegex.exec(html)) !== null) links.push(match[1]);
          const uniqueLinks = [...new Set(links)];

          // Heuristic: category pages have fewer path segments, product pages have more
          const categoryPatterns = /\/(categori|collections|shop|c\/|categoria|prodotti|products|catalog)/i;
          const productPatterns = /\/(product|prodotto|p\/|item|detail|dp\/)/i;
          const categoryLink = uniqueLinks.find(l => categoryPatterns.test(l))
            || uniqueLinks.find(l => l.split('/').filter(Boolean).length === 1 && !l.match(/\.(js|css|png|jpg|svg|ico|xml|json)/));
          const productLink = uniqueLinks.find(l => productPatterns.test(l))
            || uniqueLinks.find(l => l.split('/').filter(Boolean).length >= 2 && !l.match(/\.(js|css|png|jpg|svg|ico|xml|json)/) && !l.match(/\/(cart|checkout|account|login|register|privacy|cookie|terms|contatti|about|blog|faq|sitemap)/i));

          let categoryContent = 'Non trovata automaticamente.';
          let productContent = 'Non trovata automaticamente.';

          // Fetch category page
          if (categoryLink) {
            try {
              const catRes = await this._fetch(baseUrl.origin + categoryLink);
              const catHtml = await catRes.text();
              const catBody = catHtml.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
              categoryContent = `URL: ${categoryLink}\nBODY (first 10000 chars):\n${(catBody?.[1] || '').substring(0, 10000)}`;
            } catch (e) { categoryContent = `Errore fetch ${categoryLink}: ${e.message}`; }
          }

          // Fetch product page
          if (productLink) {
            try {
              const prodRes = await this._fetch(baseUrl.origin + productLink);
              const prodHtml = await prodRes.text();
              const prodHead = prodHtml.match(/<head[^>]*>([\s\S]*?)<\/head>/i);
              const prodBody = prodHtml.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
              productContent = `URL: ${productLink}\nHEAD (first 5000 chars):\n${(prodHead?.[1] || '').substring(0, 5000)}\nBODY (first 10000 chars):\n${(prodBody?.[1] || '').substring(0, 10000)}`;
            } catch (e) { productContent = `Errore fetch ${productLink}: ${e.message}`; }
          }

          content = `=== HOMEPAGE ===\n${homepageContent}\n\n=== PAGINA CATEGORIA ===\n${categoryContent}\n\n=== PAGINA PRODOTTO ===\n${productContent}`;
        } catch (e) {
          content = `Non è stato possibile fetchare il sito: ${e.message}. Analizza in base all'URL e alle best practices generali per ecommerce.`;
        }
      } else if (type === 'seo' || type === 'seo_deep' || type === 'accessibility' || type === 'security' || type === 'advertising') {
        // Multi-page fetch: homepage + discovered category/product pages
        try {
          const res = await this._fetch(url);
          const html = await res.text();
          const headMatch = html.match(/<head[^>]*>([\s\S]*?)<\/head>/i);
          const bodyMatch = html.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
          const homepageContent = `HEAD:\n${(headMatch?.[1] || '').substring(0, 5000)}\nBODY (first 10000 chars):\n${(bodyMatch?.[1] || '').substring(0, 10000)}`;

          // Discover and fetch extra pages
          const baseUrl = new URL(url);
          const linkRegex = /href=["'](\/[^"'#?]+)["']/gi;
          const links = [];
          let linkMatch;
          while ((linkMatch = linkRegex.exec(html)) !== null) links.push(linkMatch[1]);
          const uniqueLinks = [...new Set(links)];

          const categoryPatterns = /\/(categori|collections|shop|c\/|categoria|prodotti|products|catalog)/i;
          const productPatterns = /\/(product|prodotto|p\/|item|detail|dp\/)/i;
          const categoryLink = uniqueLinks.find(l => categoryPatterns.test(l))
            || uniqueLinks.find(l => l.split('/').filter(Boolean).length === 1 && !l.match(/\.(js|css|png|jpg|svg|ico|xml|json)/));
          const productLink = uniqueLinks.find(l => productPatterns.test(l))
            || uniqueLinks.find(l => l.split('/').filter(Boolean).length >= 2 && !l.match(/\.(js|css|png|jpg|svg|ico|xml|json)/) && !l.match(/\/(cart|checkout|account|login|register|privacy|cookie|terms|contatti|about|blog|faq|sitemap)/i));

          let categoryContent = 'Non trovata automaticamente.';
          let productContent = 'Non trovata automaticamente.';

          if (categoryLink) {
            try {
              const catRes = await this._fetch(baseUrl.origin + categoryLink);
              const catHtml = await catRes.text();
              const catHead = catHtml.match(/<head[^>]*>([\s\S]*?)<\/head>/i);
              const catBody = catHtml.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
              categoryContent = `URL: ${categoryLink}\nHEAD (first 3000 chars):\n${(catHead?.[1] || '').substring(0, 3000)}\nBODY (first 8000 chars):\n${(catBody?.[1] || '').substring(0, 8000)}`;
            } catch (e) { categoryContent = `Errore fetch ${categoryLink}: ${e.message}`; }
          }

          if (productLink) {
            try {
              const prodRes = await this._fetch(baseUrl.origin + productLink);
              const prodHtml = await prodRes.text();
              const prodHead = prodHtml.match(/<head[^>]*>([\s\S]*?)<\/head>/i);
              const prodBody = prodHtml.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
              productContent = `URL: ${productLink}\nHEAD (first 3000 chars):\n${(prodHead?.[1] || '').substring(0, 3000)}\nBODY (first 8000 chars):\n${(prodBody?.[1] || '').substring(0, 8000)}`;
            } catch (e) { productContent = `Errore fetch ${productLink}: ${e.message}`; }
          }

          content = `=== HOMEPAGE ===\n${homepageContent}\n\n=== PAGINA CATEGORIA ===\n${categoryContent}\n\n=== PAGINA PRODOTTO ===\n${productContent}`;
        } catch (e) {
          content = `Non è stato possibile fetchare il sito: ${e.message}. Analizza in base all'URL e alle best practices generali per ecommerce.`;
        }
      }
    } catch (e) {
      content = `Errore nel fetch: ${e.message}`;
    }

    // Select prompt
    const prompt = this.PROMPTS[type] || this.PROMPTS.seo;

    // Call Claude API
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true'
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 12000,
        system: this.OSMANI_BASE,
        messages: [{
          role: 'user',
          content: `Audit del sito: ${url}\n\nTipo analisi: ${type}\n\n${prompt}\n\nContenuto recuperato:\n\`\`\`\n${content.substring(0, 50000)}\n\`\`\``
        }]
      })
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.error?.message || `Errore API Claude (${response.status})`);
    }

    const data = await response.json();
    return {
      analysis: data.content[0].text,
      rawContent: content,
      type
    };
  },

  // Run all audits in parallel
  async runFullAudit(url, apiKey) {
    await this._loadConfig();
    const types = ['seo', 'seo_deep', 'performance', 'accessibility', 'security', 'cro', 'advertising'];
    const results = await Promise.allSettled(
      types.map(type => this.analyze(type, url, apiKey))
    );

    return types.map((type, i) => ({
      type,
      success: results[i].status === 'fulfilled',
      result: results[i].status === 'fulfilled' ? results[i].value : null,
      error: results[i].status === 'rejected' ? results[i].reason.message : null
    }));
  }
};
