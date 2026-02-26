// Auto-Discovery Engine — Automated MarTech Detection (Multi-Page)
const AutoDiscovery = {

  // Config loaded from osmani-config.json (single source of truth)
  _config: null,

  // Inline fallbacks (used if config fetch fails)
  _FALLBACK_SCHEMA_REQUIRED: {
    Product: ['name', 'image', 'description', 'offers'],
    Offer: ['price', 'priceCurrency', 'availability'],
    Organization: ['name', 'url', 'logo'],
    LocalBusiness: ['name', 'address', 'telephone'],
    BreadcrumbList: ['itemListElement'],
    FAQPage: ['mainEntity'],
    Article: ['headline', 'author', 'datePublished', 'image'],
    WebSite: ['name', 'url'],
    Event: ['name', 'startDate', 'location'],
  },
  _FALLBACK_PAGE_PATTERNS: {
    category: /\/(categori|collections|shop|c\/|categoria|prodotti|products|catalog)/i,
    product: /\/(product|prodotto|p\/|item|detail|dp\/)/i,
    blog: /\/(blog|news|articol|journal|magazine|post)/i,
  },
  _FALLBACK_EXCLUDE_PATTERNS: /\.(js|css|png|jpg|jpeg|gif|svg|ico|xml|json|pdf|zip|woff|woff2|ttf|eot)(\?|$)/i,
  _FALLBACK_EXCLUDE_PATHS: /\/(cart|checkout|account|login|register|privacy|cookie|terms|contatti|about|faq|sitemap|search|wishlist|compare|reset|confirm|unsubscribe)/i,

  // Dynamic getters that use config or fallback
  get SCHEMA_REQUIRED() {
    return this._config?.schema_required || this._FALLBACK_SCHEMA_REQUIRED;
  },
  get PAGE_PATTERNS() {
    if (this._config?.page_patterns) {
      const pp = {};
      for (const [k, v] of Object.entries(this._config.page_patterns)) {
        pp[k] = new RegExp(v, 'i');
      }
      return pp;
    }
    return this._FALLBACK_PAGE_PATTERNS;
  },
  get EXCLUDE_PATTERNS() {
    if (this._config?.exclude_patterns) return new RegExp(this._config.exclude_patterns, 'i');
    return this._FALLBACK_EXCLUDE_PATTERNS;
  },
  get EXCLUDE_PATHS() {
    if (this._config?.exclude_paths) return new RegExp(this._config.exclude_paths, 'i');
    return this._FALLBACK_EXCLUDE_PATHS;
  },

  /**
   * Load config from osmani-config.json
   */
  async _loadConfig() {
    if (this._config) return this._config;
    try {
      const res = await fetch('/data/osmani-config.json');
      if (res.ok) {
        this._config = await res.json();
      }
    } catch (e) {
      console.warn('Auto-discovery: failed to load config, using inline fallbacks', e);
    }
    return this._config;
  },

  /**
   * Data-driven detection: loop over config entries, return list of matched names
   */
  _detectByPatterns(htmlLower, htmlRaw, entries) {
    const found = [];
    for (const entry of entries) {
      let matched = false;
      for (const pat of (entry.patterns || [])) {
        if (htmlLower.includes(pat)) { matched = true; break; }
      }
      if (!matched && entry.regex) {
        if (new RegExp(entry.regex, 'i').test(htmlRaw)) matched = true;
      }
      if (matched && !found.includes(entry.name)) found.push(entry.name);
    }
    return found;
  },

  /**
   * Fetch HTML — tries /proxy-render first (Playwright), falls back to /proxy
   */
  async _fetchHtml(url) {
    // Try rendered version first
    try {
      const res = await fetch(`/proxy-render?url=${encodeURIComponent(url)}`);
      if (res.ok) {
        const rendered = res.headers.get('X-Rendered') === 'playwright';
        return { html: await res.text(), rendered };
      }
    } catch (e) { /* fall through */ }
    // Fallback to static proxy
    try {
      const res = await fetch(`/proxy?url=${encodeURIComponent(url)}`);
      return { html: await res.text(), rendered: false };
    } catch (e) {
      return { html: '', rendered: false };
    }
  },

  /**
   * Measure page resources from HTML
   */
  _measureResources(html) {
    if (!html) return null;
    const scripts = (html.match(/<script[^>]*src=["'][^"']+["']/gi) || []);
    const stylesheets = (html.match(/<link[^>]*rel=["']stylesheet["'][^>]*>/gi) || []);
    const images = (html.match(/<img[^>]*src=["'][^"']+["']/gi) || []);
    const inlineScripts = html.match(/<script(?![^>]*src=)[^>]*>([\s\S]*?)<\/script>/gi) || [];
    const inlineStyles = html.match(/<style[^>]*>([\s\S]*?)<\/style>/gi) || [];

    return {
      html_size: new Blob([html]).size,
      script_count: scripts.length,
      stylesheet_count: stylesheets.length,
      image_count: images.length,
      inline_script_bytes: inlineScripts.reduce((s, v) => s + new Blob([v]).size, 0),
      inline_style_bytes: inlineStyles.reduce((s, v) => s + new Blob([v]).size, 0),
    };
  },

  /**
   * Fetch CrUX field data via server proxy
   */
  async _fetchCrUX(url) {
    try {
      const res = await fetch(`/api/crux?url=${encodeURIComponent(url)}`);
      if (res.ok) return await res.json();
    } catch (e) { /* ignore */ }
    return null;
  },

  /**
   * Validate resources + CrUX against Osmani budgets
   */
  _validateBudgets(resources, config) {
    const findings = {};
    const budgets = config?.performance_budgets || {};

    if (resources) {
      const htmlKB = (resources.html_size || 0) / 1024;
      const budgetKB = (budgets.page_weight || 1500000) / 1024;
      if (htmlKB > budgetKB) {
        findings['a0_2_1'] = { value: false, note: `⚠️ HTML ${Math.round(htmlKB)}KB supera budget ${Math.round(budgetKB)}KB. Impatto: LCP degradato. Fix: ottimizzare risorse.` };
      } else {
        findings['a0_2_1'] = { value: true, note: `HTML ${Math.round(htmlKB)}KB entro budget` };
      }
      if (resources.script_count > 15) {
        findings['a0_2_2'] = { value: false, note: `⚠️ ${resources.script_count} script esterni. Impatto: INP degradato. Fix: consolidare, defer/async.` };
      }
      if (resources.image_count > 20) {
        findings['a0_2_3'] = { value: false, note: `⚠️ ${resources.image_count} immagini. Verificare lazy loading e formati moderni.` };
      }
    }
    return findings;
  },

  /**
   * Validate CrUX data against Osmani CWV thresholds
   */
  _validateCWV(cruxData, config) {
    const findings = {};
    if (!cruxData?.record?.metrics) return findings;
    const metrics = cruxData.record.metrics;
    const budgets = config?.performance_budgets || {};

    const checks = {
      largest_contentful_paint: { id: 'a0_2_4', label: 'LCP', thresholds: budgets.lcp },
      interaction_to_next_paint: { id: 'a0_2_5', label: 'INP', thresholds: budgets.inp },
      cumulative_layout_shift: { id: 'a0_2_6', label: 'CLS', thresholds: budgets.cls },
      experimental_time_to_first_byte: { id: 'a0_2_7', label: 'TTFB', thresholds: null },
    };

    for (const [key, { id, label, thresholds }] of Object.entries(checks)) {
      const p75 = metrics[key]?.percentiles?.p75;
      if (p75 == null) continue;

      if (key === 'experimental_time_to_first_byte') {
        const ttfbBudget = budgets.ttfb || 800;
        findings[id] = p75 > ttfbBudget
          ? { value: false, note: `⚠️ TTFB p75=${p75}ms > ${ttfbBudget}ms. Fix: CDN, edge caching.` }
          : { value: true, note: `TTFB p75=${p75}ms ✓` };
      } else if (thresholds) {
        const valStr = key === 'cumulative_layout_shift' ? p75.toFixed(2) : `${p75}ms`;
        if (p75 <= thresholds.good) {
          findings[id] = { value: true, note: `${label} p75=${valStr} (buono ✓)` };
        } else if (p75 <= thresholds.needs_improvement) {
          findings[id] = { value: false, note: `⚠️ ${label} p75=${valStr} (migliorabile). Target: ${thresholds.good}.` };
        } else {
          findings[id] = { value: false, note: `⚠️ ${label} p75=${valStr} (scarso). Intervento urgente.` };
        }
      }
    }
    return findings;
  },

  /**
   * Main entry — crawls homepage + discovered/manual pages
   * @param {string} domain
   * @param {string[]} additionalUrls - manual URLs from user
   * @param {function} onProgress - callback(message)
   */
  async run(domain, additionalUrls = [], onProgress = () => {}) {
    const baseUrl = domain.startsWith('http') ? domain : 'https://' + domain;
    const discovered = {};
    const discoveredPages = []; // {url, type, discovered: bool}

    // --- 0. Load config ---
    await this._loadConfig();

    // --- 1. Fetch homepage (prefer rendered) ---
    let homepageHtml = '';
    let homepageRendered = false;
    let headers = {};
    onProgress('Analisi homepage...');

    try {
      const result = await this._fetchHtml(baseUrl);
      homepageHtml = result.html;
      homepageRendered = result.rendered;
    } catch (e) {
      console.warn('Auto-discovery: failed to fetch HTML', e);
    }

    try {
      const headRes = await fetch(`/proxy-headers?url=${encodeURIComponent(baseUrl)}`);
      headers = await headRes.json();
    } catch (e) {
      console.warn('Auto-discovery: failed to fetch headers', e);
    }

    discoveredPages.push({ url: baseUrl, type: 'homepage', discovered: false, rendered: homepageRendered });

    // --- 1.5. Resource measurement + CrUX ---
    onProgress('Misurazione risorse e CrUX...');
    const resources = this._measureResources(homepageHtml);
    const budgetFindings = this._validateBudgets(resources, this._config);
    for (const [k, v] of Object.entries(budgetFindings)) {
      discovered[k] = v;
    }

    const cruxData = await this._fetchCrUX(baseUrl);
    if (cruxData) {
      const cwvFindings = this._validateCWV(cruxData, this._config);
      for (const [k, v] of Object.entries(cwvFindings)) {
        discovered[k] = v;
      }
    }

    // --- 2. Discover internal pages ---
    onProgress('Scoperta pagine interne...');
    const autoPages = this._discoverPages(homepageHtml, baseUrl);

    // Add manual URLs
    for (const u of additionalUrls) {
      const fullUrl = u.startsWith('http') ? u : baseUrl.replace(/\/$/, '') + (u.startsWith('/') ? u : '/' + u);
      if (!autoPages.find(p => p.url === fullUrl)) {
        autoPages.push({ url: fullUrl, type: 'manual' });
      }
    }

    // --- 3. Fetch extra pages (max 4, prefer rendered) ---
    const extraPages = autoPages.slice(0, 4);
    const pageHtmls = [{ url: baseUrl, type: 'homepage', html: homepageHtml }];

    for (const page of extraPages) {
      onProgress(`Scanning ${new URL(page.url).pathname}...`);
      discoveredPages.push({ url: page.url, type: page.type, discovered: true });
      try {
        const result = await this._fetchHtml(page.url);
        pageHtmls.push({ url: page.url, type: page.type, html: result.html });
      } catch (e) {
        console.warn(`Auto-discovery: failed to fetch ${page.url}`, e);
      }
    }

    // --- 4. Run detectors on ALL pages ---
    onProgress('Analisi tech stack e tracking...');
    for (const page of pageHtmls) {
      const pageDetectors = [
        this._detectTechStack(page.html),
        this._detectTracking(page.html),
        this._detectPixels(page.html),
        this._detectConsent(page.html),
        this._detectSchema(page.html, page.url),
        this._detectDataLayer(page.html),
        this._detectHeadings(page.html, page.url),
      ];
      // Only run security on homepage
      if (page.type === 'homepage') {
        pageDetectors.push(this._detectSecurity(headers, baseUrl));
      }

      for (const result of pageDetectors) {
        this._mergeDiscovered(discovered, result, page.url);
      }
    }

    // Store discovered pages metadata
    discovered._discoveredPages = discoveredPages;

    return discovered;
  },

  /**
   * Discover internal pages from homepage HTML
   */
  _discoverPages(html, baseUrl) {
    const pages = [];
    if (!html) return pages;

    try {
      const base = new URL(baseUrl);
      const linkRegex = /href=["'](\/(?!\/)[^"'#?][^"']*?)["']/gi;
      const seen = new Set();
      let match;

      while ((match = linkRegex.exec(html)) !== null) {
        const path = match[1];
        if (seen.has(path)) continue;
        seen.add(path);
        if (this.EXCLUDE_PATTERNS.test(path)) continue;

        const fullUrl = base.origin + path;
        let type = 'other';

        if (this.PAGE_PATTERNS.category.test(path)) type = 'category';
        else if (this.PAGE_PATTERNS.product.test(path)) type = 'product';
        else if (this.PAGE_PATTERNS.blog.test(path)) type = 'blog';
        else if (this.EXCLUDE_PATHS.test(path)) continue;

        if (type !== 'other') {
          pages.push({ url: fullUrl, type });
        }
      }

      // If no typed pages found, try heuristics
      if (!pages.find(p => p.type === 'category')) {
        const fallback = [...seen].find(l => l.split('/').filter(Boolean).length === 1 && !this.EXCLUDE_PATTERNS.test(l) && !this.EXCLUDE_PATHS.test(l));
        if (fallback) pages.push({ url: base.origin + fallback, type: 'category' });
      }
      if (!pages.find(p => p.type === 'product')) {
        const fallback = [...seen].find(l => l.split('/').filter(Boolean).length >= 2 && !this.EXCLUDE_PATTERNS.test(l) && !this.EXCLUDE_PATHS.test(l));
        if (fallback) pages.push({ url: base.origin + fallback, type: 'product' });
      }
    } catch (e) {
      console.warn('_discoverPages error', e);
    }

    // Deduplicate by type — keep first of each
    const byType = {};
    return pages.filter(p => {
      if (byType[p.type]) return false;
      byType[p.type] = true;
      return true;
    });
  },

  /**
   * Merge results: keep existing notes, append page source for multi-page
   */
  _mergeDiscovered(target, source, pageUrl) {
    for (const [key, data] of Object.entries(source)) {
      if (key.startsWith('_')) { // metadata keys
        target[key] = data;
        continue;
      }
      if (!target[key]) {
        target[key] = { ...data, pages: [pageUrl] };
      } else {
        // Append page source and merge notes
        if (!target[key].pages) target[key].pages = [];
        if (!target[key].pages.includes(pageUrl)) target[key].pages.push(pageUrl);
        // If new note has more info, append
        if (data.note && !target[key].note.includes(data.note)) {
          target[key].note += ' | ' + data.note;
        }
      }
    }
  },

  _detectTechStack(html) {
    const d = {};
    const lower = html.toLowerCase();
    const detection = this._config?.detection || {};

    // Data-driven detection for categories with check_id
    for (const category of ['cms', 'cdn', 'analytics', 'email', 'ab_testing', 'crm', 'chat']) {
      const catCfg = detection[category];
      if (catCfg?.entries && catCfg.check_id) {
        const found = this._detectByPatterns(lower, html, catCfg.entries);
        // CMS fallback: meta generator
        if (category === 'cms' && !found.length) {
          const genMatch = html.match(/<meta[^>]*name=["']generator["'][^>]*content=["']([^"']+)["']/i);
          if (genMatch) found.push(genMatch[1]);
        }
        if (found.length) d[catCfg.check_id] = { value: true, note: [...new Set(found)].join(', ') };
      }
    }

    // Payment (kept separate — regex-based)
    const payments = [];
    if (lower.includes('stripe.js') || lower.includes('js.stripe.com')) payments.push('Stripe');
    if (lower.includes('adyen')) payments.push('Adyen');
    if (lower.includes('paypal')) payments.push('PayPal');
    if (lower.includes('klarna')) payments.push('Klarna');
    if (lower.includes('scalapay')) payments.push('Scalapay');
    if (payments.length) d['a0_1_3'] = { value: true, note: payments.join(', ') };

    return d;
  },

  _detectTracking(html) {
    const d = {};

    // GTM
    const gtmMatch = html.match(/GTM-[A-Z0-9]{5,8}/g);
    if (gtmMatch) {
      const ids = [...new Set(gtmMatch)];
      d['a2_1_1'] = { value: true, note: ids.join(', ') };
    }

    // GA4
    const ga4Match = html.match(/G-[A-Z0-9]{8,12}/g);
    if (ga4Match) {
      const ids = [...new Set(ga4Match)];
      d['a2_1_2'] = { value: true, note: ids.join(', ') };
    }

    // Google Ads
    const adsMatch = html.match(/AW-[0-9]{8,12}/g);
    if (adsMatch) {
      const ids = [...new Set(adsMatch)];
      d['a2_1_3'] = { value: true, note: ids.join(', ') };
    }

    // gtag.js direct
    if (/googletagmanager\.com\/gtag\/js/i.test(html)) {
      d['a2_1_4'] = { value: true, note: 'gtag.js caricato direttamente' };
    }

    // Server-side GTM
    const trackingDomains = html.match(/https?:\/\/[a-z0-9.-]+\/gtm\.js/gi) || [];
    const ssgtm = trackingDomains.filter(u => !u.includes('googletagmanager.com'));
    if (ssgtm.length) {
      const domains = ssgtm.map(u => { try { return new URL(u).hostname; } catch(e) { return u; } });
      d['a2_2_1'] = { value: true, note: 'Server-side GTM: ' + [...new Set(domains)].join(', ') };
      d['a2_2_2'] = { value: true, note: 'Dominio custom: ' + [...new Set(domains)].join(', ') };
    }

    return d;
  },

  _detectPixels(html) {
    const d = {};
    const lower = html.toLowerCase();
    const pixelEntries = this._config?.detection?.pixels?.entries || [];

    // Data-driven pixel detection
    for (const entry of pixelEntries) {
      for (const pat of (entry.patterns || [])) {
        if (lower.includes(pat)) {
          const checkId = entry.check_id;
          if (!d[checkId]) {
            d[checkId] = { value: true, note: entry.name + ' rilevato' };
          } else {
            d[checkId].note += ', ' + entry.name + ' rilevato';
          }
          break;
        }
      }
    }

    // Enhanced Meta Pixel detection (extract ID)
    if (!d['a2_3_1']) {
      const fbqMatch = html.match(/fbq\s*\(\s*['"]init['"]\s*,\s*['"](\d+)['"]/);
      if (fbqMatch) {
        d['a2_3_1'] = { value: true, note: 'Meta Pixel ID: ' + fbqMatch[1] };
      } else if (lower.includes('fbq(') || lower.includes('facebook.com/tr') || lower.includes('connect.facebook.net')) {
        d['a2_3_1'] = { value: true, note: 'Meta Pixel rilevato' };
      }
    }

    // Enhanced Clarity detection (extract ID)
    if (d['a2_3_2'] && lower.includes('clarity.ms')) {
      const clarityMatch = html.match(/clarity\.ms\/tag\/([a-z0-9]+)/i);
      if (clarityMatch) d['a2_3_2'].note = 'Clarity ID: ' + clarityMatch[1];
    }

    return d;
  },

  _detectConsent(html) {
    const d = {};
    const lower = html.toLowerCase();

    // Data-driven consent banner detection
    const consentEntries = this._config?.detection?.consent?.entries || [];
    const banners = this._detectByPatterns(lower, html, consentEntries);
    if (banners.length) {
      d['a1_1_1'] = { value: true, note: banners.join(', ') };
      d['a1_1_2'] = { value: true, note: 'Banner: ' + banners.join(', ') };
    }

    // Consent Mode v2
    const consentMatch = html.match(/gtag\s*\(\s*['"]consent['"]\s*,\s*['"]default['"]\s*,\s*(\{[^}]+\})/s);
    if (consentMatch) {
      d['a1_2_1'] = { value: true, note: 'Consent Mode v2 configurato' };

      const block = consentMatch[1];
      const consentMap = {
        'ad_storage': 'a1_2_2',
        'analytics_storage': 'a1_2_3',
        'ad_user_data': 'a1_2_4',
        'ad_personalization': 'a1_2_5',
        'functionality_storage': 'a1_2_6',
        'personalization_storage': 'a1_2_7',
        'security_storage': 'a1_2_8',
      };

      for (const [key, checkId] of Object.entries(consentMap)) {
        const stateMatch = block.match(new RegExp(key + `\\s*[:=]\\s*['"]?(denied|granted)['"]?`));
        if (stateMatch) {
          d[checkId] = { value: true, note: `${key}: ${stateMatch[1]}` };
        }
      }
    } else if (lower.includes("gtag('consent'") || lower.includes('gtag("consent"')) {
      d['a1_2_1'] = { value: true, note: 'Consent Mode rilevato (parsing parziale)' };
    }

    return d;
  },

  _detectSecurity(headers, url) {
    const d = {};

    // HTTPS
    if (url.startsWith('https://')) {
      d['a0_4_1'] = { value: true, note: 'HTTPS attivo' };
    } else {
      d['a0_4_1'] = { value: false, note: '⚠️ HTTPS non attivo. Impatto: rischio sicurezza dati utente, penalizzazione ranking Google. Fix: attivare certificato SSL/TLS e redirect 301 da HTTP a HTTPS.' };
    }

    if (!headers || typeof headers !== 'object' || headers.error) return d;

    const h = {};
    for (const [k, v] of Object.entries(headers)) {
      h[k.toLowerCase()] = v;
    }

    if (h['strict-transport-security']) {
      d['a0_4_2'] = { value: true, note: 'HSTS: ' + h['strict-transport-security'] };
    } else {
      d['a0_4_2'] = { value: false, note: '⚠️ HSTS assente. Impatto: vulnerabilità a downgrade attack. Fix: aggiungere header Strict-Transport-Security: max-age=31536000; includeSubDomains' };
    }
    if (h['content-security-policy']) {
      d['a0_4_3'] = { value: true, note: 'CSP presente' };
    } else {
      d['a0_4_3'] = { value: false, note: '⚠️ CSP assente. Impatto: vulnerabilità XSS. Fix: configurare Content-Security-Policy con direttive restrittive.' };
    }
    if (h['x-frame-options']) {
      d['a0_4_4'] = { value: true, note: 'X-Frame-Options: ' + h['x-frame-options'] };
    }
    if (h['x-content-type-options']) {
      d['a0_4_5'] = { value: true, note: 'X-Content-Type-Options: ' + h['x-content-type-options'] };
    }
    if (h['referrer-policy']) {
      d['a0_4_6'] = { value: true, note: 'Referrer-Policy: ' + h['referrer-policy'] };
    }
    if (h['permissions-policy'] || h['feature-policy']) {
      d['a0_4_7'] = { value: true, note: 'Permissions-Policy presente' };
    }

    return d;
  },

  /**
   * Deep schema detection with field validation (Phase 2)
   */
  _detectSchema(html, pageUrl) {
    const d = {};
    const ldJsonRegex = /<script[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi;
    const schemas = [];
    const validationResults = [];
    let match;

    while ((match = ldJsonRegex.exec(html)) !== null) {
      try {
        let json = JSON.parse(match[1]);
        // Handle @graph
        const items = json['@graph'] ? json['@graph'] : (Array.isArray(json) ? json : [json]);

        for (const item of items) {
          const type = item['@type'];
          if (!type) continue;
          const types = Array.isArray(type) ? type : [type];

          for (const t of types) {
            schemas.push(t);
            // Deep validation
            const validation = this._validateSchemaFields(item, t);
            validationResults.push({ type: t, ...validation, page: pageUrl });
          }
        }
      } catch (e) { /* malformed JSON-LD */ }
    }

    if (schemas.length) {
      const unique = [...new Set(schemas)];

      // Build detailed notes with validation
      const schemaDetails = validationResults.map(v => {
        const pagePath = v.page ? new URL(v.page).pathname : '';
        if (v.missing.length === 0) {
          return `${v.type}: ${v.present}/${v.total} campi ✓${pagePath ? ' (' + pagePath + ')' : ''}`;
        }
        return `${v.type}: ${v.present}/${v.total} campi (mancano: ${v.missing.join(', ')})${pagePath ? ' (' + pagePath + ')' : ''}`;
      });

      d['a4_4_1'] = { value: true, note: 'Schema: ' + unique.join(', ') + '. ' + schemaDetails.join('; ') };

      if (unique.some(t => /product/i.test(t))) {
        const productValidation = validationResults.find(v => /product/i.test(v.type));
        const detail = productValidation ? ` (${productValidation.present}/${productValidation.total} campi${productValidation.missing.length ? ', mancano: ' + productValidation.missing.join(', ') : ''})` : '';
        d['a4_4_2'] = { value: true, note: 'Product schema rilevato' + detail };
      }
      if (unique.some(t => /organization/i.test(t))) {
        d['a4_4_3'] = { value: true, note: 'Organization schema rilevato' };
      }
      if (unique.some(t => /breadcrumb/i.test(t))) {
        d['a4_4_4'] = { value: true, note: 'BreadcrumbList schema rilevato' };
      }
      if (unique.some(t => /faq/i.test(t))) {
        d['a4_4_5'] = { value: true, note: 'FAQ schema rilevato' };
      }

      // a4_4_9 — Schema validation errors
      const errors = validationResults.filter(v => v.missing.length > 0);
      if (errors.length) {
        d['a4_4_9'] = { value: false, note: '⚠️ Campi mancanti: ' + errors.map(e => `${e.type}: ${e.missing.join(', ')}`).join('; ') + '. Impatto: ridotta eligibilità rich results. Fix: aggiungere i campi obbligatori nel JSON-LD.' };
      } else {
        d['a4_4_9'] = { value: true, note: 'Tutti i campi obbligatori presenti nei schema rilevati' };
      }

      // a4_4_10 — Rich results eligibility
      const richEligible = validationResults.filter(v => v.missing.length === 0 && ['Product', 'FAQPage', 'Article', 'BreadcrumbList', 'Event'].includes(v.type));
      if (richEligible.length) {
        d['a4_4_10'] = { value: true, note: 'Eligible per rich results: ' + richEligible.map(v => v.type).join(', ') };
      } else if (validationResults.length > 0) {
        d['a4_4_10'] = { value: false, note: '⚠️ Schema presenti ma campi mancanti impediscono rich results. Fix: completare i campi obbligatori.' };
      }
    } else {
      // Proactive note when schema is absent
      d['a4_4_1'] = { value: false, note: '⚠️ Nessuno schema JSON-LD rilevato. Impatto: -20-30% CTR in SERP, nessun rich snippet. Fix: aggiungere JSON-LD per Organization, Product (con name, price, image, availability), BreadcrumbList.' };
    }

    return d;
  },

  /**
   * Validate schema fields against required fields map
   */
  _validateSchemaFields(json, type) {
    const required = this.SCHEMA_REQUIRED[type] || [];
    const present = [];
    const missing = [];

    for (const field of required) {
      if (field.includes('.')) {
        // Nested check e.g. "offers.availability"
        const parts = field.split('.');
        let val = json;
        let found = true;
        for (const p of parts) {
          if (val && typeof val === 'object') {
            val = val[p] || (Array.isArray(val) ? val[0]?.[p] : undefined);
          } else {
            found = false;
            break;
          }
          if (val === undefined || val === null) { found = false; break; }
        }
        found ? present.push(field) : missing.push(field);
      } else {
        const val = json[field];
        if (val !== undefined && val !== null && val !== '') {
          present.push(field);
        } else {
          missing.push(field);
        }
      }
    }

    return {
      total: required.length,
      present: present.length,
      missing,
      complete: missing.length === 0,
    };
  },

  /**
   * Heading structure detection (Phase 3)
   */
  _detectHeadings(html, pageUrl) {
    const d = {};
    if (!html) return d;

    const headingRegex = /<(h[1-6])[^>]*>([\s\S]*?)<\/\1>/gi;
    const headings = [];
    let match;

    while ((match = headingRegex.exec(html)) !== null) {
      const level = parseInt(match[1].charAt(1));
      const text = match[2].replace(/<[^>]+>/g, '').trim().substring(0, 100);
      if (text) headings.push({ level, text });
    }

    if (headings.length === 0) return d;

    const pagePath = pageUrl ? (() => { try { return new URL(pageUrl).pathname; } catch(e) { return ''; } })() : '';

    // Analyze H1
    const h1s = headings.filter(h => h.level === 1);
    const issues = [];

    if (h1s.length === 0) {
      issues.push('H1 assente');
    } else if (h1s.length > 1) {
      issues.push(`${h1s.length} H1 trovati (dovrebbe essere 1)`);
    }

    // Check for skipped levels
    const levels = headings.map(h => h.level);
    for (let i = 1; i < levels.length; i++) {
      if (levels[i] > levels[i - 1] + 1) {
        issues.push(`Livello saltato: H${levels[i - 1]} → H${levels[i]}`);
        break; // Only report first skip
      }
    }

    // Build heading tree summary
    const treeSummary = headings.slice(0, 10).map(h => `${'  '.repeat(h.level - 1)}H${h.level}: ${h.text}`).join('\n');

    const isOk = h1s.length === 1 && issues.length === 0;

    // a4_3_3 — H1 unique check
    if (h1s.length === 1) {
      d['a4_3_3'] = { value: true, note: `H1: "${h1s[0].text}"${pagePath ? ' (' + pagePath + ')' : ''}` };
    } else {
      const issueNote = h1s.length === 0
        ? `⚠️ H1 assente${pagePath ? ' su ' + pagePath : ''}. Impatto: penalizzazione SEO on-page. Fix: aggiungere un singolo H1 descrittivo con keyword primaria.`
        : `⚠️ ${h1s.length} tag H1 trovati${pagePath ? ' su ' + pagePath : ''}: ${h1s.map(h => '"' + h.text + '"').join(', ')}. Impatto: confusione motori di ricerca. Fix: mantenere un solo H1 per pagina.`;
      d['a4_3_3'] = { value: false, note: issueNote };
    }

    // a4_3_4 — Heading hierarchy check
    if (issues.length === 0) {
      d['a4_3_4'] = { value: true, note: `Gerarchia heading corretta (${headings.length} heading)${pagePath ? ' su ' + pagePath : ''}` };
    } else {
      d['a4_3_4'] = { value: false, note: `⚠️ ${issues.join('; ')}${pagePath ? ' su ' + pagePath : ''}. Impatto: struttura semantica compromessa per SEO e accessibilità. Fix: rispettare gerarchia H1→H2→H3 senza saltare livelli.` };
    }

    // Store heading structure for the page
    d['_headings_' + (pagePath || '/')] = { headings: headings.slice(0, 20), issues, ok: isOk };

    return d;
  },

  _detectDataLayer(html) {
    const d = {};

    if (/dataLayer\s*[=\[]/.test(html) || /dataLayer\.push/.test(html)) {
      d['a3_1_1'] = { value: true, note: 'dataLayer presente nel codice' };

      const pushes = html.match(/dataLayer\.push\s*\(\s*\{[^}]*['"]event['"]\s*:\s*['"]([^'"]+)['"]/g);
      if (pushes) {
        const events = pushes.map(p => {
          const m = p.match(/['"]event['"]\s*:\s*['"]([^'"]+)['"]/);
          return m ? m[1] : null;
        }).filter(Boolean);
        if (events.length) {
          d['a3_1_2'] = { value: true, note: 'Eventi: ' + [...new Set(events)].join(', ') };
        }
      }
    }

    return d;
  }
};
