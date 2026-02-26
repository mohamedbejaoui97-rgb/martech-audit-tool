// Main App - Routing & State (OpenAI Academy Layout)
const App = {
  currentView: 'dashboard',

  init() {
    this.showDashboard();
  },

  // SVG Icons (outline style like OpenAI)
  icons: {
    home: `<svg viewBox="0 0 24 24"><path d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0a1 1 0 01-1-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 01-1 1h-2z" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    info: `<svg viewBox="0 0 24 24"><path d="M13 16h-1v-4h-1m1-4h.01M12 2a10 10 0 100 20 10 10 0 000-20z" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    book: `<svg viewBox="0 0 24 24"><path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    tool: `<svg viewBox="0 0 24 24"><path d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.573-1.066z" stroke-linecap="round" stroke-linejoin="round"/><circle cx="12" cy="12" r="3" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    chart: `<svg viewBox="0 0 24 24"><path d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    help: `<svg viewBox="0 0 24 24"><path d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M12 2a10 10 0 100 20 10 10 0 000-20z" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  },

  _renderShell(active, content) {
    return `
      <div class="app-shell">
        <aside class="app-sidebar">
          <a class="sidebar-brand" onclick="App.showDashboard()">
            <svg viewBox="0 0 28 28" width="28" height="28">
              <rect width="28" height="28" rx="7" fill="#10a37f"/>
              <text x="14" y="20" text-anchor="middle" fill="white" font-size="16" font-weight="800" font-family="Inter,sans-serif">M</text>
            </svg>
            <span>MarTech Audit</span>
          </a>
          <nav class="sidebar-nav">
            <button class="sidebar-link ${active === 'dashboard' ? 'active' : ''}" onclick="App.showDashboard()">
              ${this.icons.home}
              Home
            </button>
            <button class="sidebar-link ${active === 'about' ? 'active' : ''}" onclick="App.showAbout()">
              ${this.icons.book}
              Metodologia
            </button>

            <div class="sidebar-divider"></div>
            <div class="sidebar-section-title">Risorse</div>

            <button class="sidebar-link" onclick="window.open('https://support.google.com/analytics/answer/9267735','_blank')">
              ${this.icons.help}
              Help GA4
            </button>
          </nav>
          <div class="sidebar-footer">
            Powered by Mr Tech
          </div>
        </aside>
        <main class="app-main">
          <div class="app-content">${content}</div>
        </main>
      </div>
    `;
  },

  showDashboard() {
    this.currentView = 'dashboard';
    const audits = Storage.getAudits();
    const apiKey = Storage.getApiKey();
    const main = document.getElementById('main-content');

    const dashContent = `
      <div class="dashboard">
        <div class="dash-hero">
          <h1>MarTech Audit<br>Intelligence</h1>
          <p>Audit ecommerce strutturato con AI. Analisi tecnica, scoring automatico e report consultivo professionale.</p>
          <button class="btn btn-lg btn-primary" onclick="App.newAuditModal()">Nuova Audit</button>
        </div>

        <div class="settings-bar">
          <div class="api-key-section">
            <label>Claude API Key</label>
            <input type="password" id="api-key-input" value="${apiKey}" placeholder="sk-ant-api03-..."
                   onchange="Storage.setApiKey(this.value)" class="api-key-input">
            <button class="btn btn-sm btn-ghost" onclick="const i=document.getElementById('api-key-input');i.type=i.type==='password'?'text':'password'">
              Mostra
            </button>
            <span class="api-status ${apiKey ? 'active' : ''}">${apiKey ? '&#9679; Attiva' : '&#9675; Non configurata'}</span>
          </div>
          <div class="api-key-section" style="margin-top:8px">
            <label>Google API Key <span style="font-weight:400;color:#9ca3af">(PageSpeed)</span></label>
            <input type="password" id="google-key-input" value="${Storage.getGoogleKey()}" placeholder="AIzaSy..."
                   onchange="Storage.setGoogleKey(this.value)" class="api-key-input">
            <button class="btn btn-sm btn-ghost" onclick="const i=document.getElementById('google-key-input');i.type=i.type==='password'?'text':'password'">
              Mostra
            </button>
            <span class="api-status ${Storage.getGoogleKey() ? 'active' : ''}">${Storage.getGoogleKey() ? '&#9679; Attiva' : '&#9675; Non configurata'}</span>
          </div>
        </div>

        ${audits.length === 0 ? `
          <div class="empty-state">
            <div class="empty-icon">&#9744;</div>
            <h3>Nessuna audit presente</h3>
            <p>Crea la tua prima audit MarTech per iniziare l'analisi.</p>
            <button class="btn btn-primary" onclick="App.newAuditModal()">Crea Prima Audit</button>
          </div>
        ` : `
          <div class="dash-header">
            <h2>Audit Salvate</h2>
            <button class="btn btn-sm" onclick="App.newAuditModal()">+ Nuova</button>
          </div>
          <div class="audit-grid">
            ${audits.map(a => {
              const total = Object.values(a.scores).reduce((x, y) => x + (parseInt(y) || 0), 0);
              const date = new Date(a.updatedAt).toLocaleDateString('it-IT');
              const findings = (a.findings || []).length;
              const checks = Object.values(a.checks || {}).filter(v => v).length;
              return `
              <div class="audit-card" onclick="App.openAudit('${a.id}')">
                <div class="audit-card-header">
                  <h3>${a.clientName}</h3>
                  <button class="btn-icon" onclick="event.stopPropagation(); App.deleteAudit('${a.id}')" title="Elimina">&#x2715;</button>
                </div>
                <span class="domain-badge">${a.domain}</span>
                <div class="audit-card-stats">
                  <div class="stat">
                    <span class="stat-value">${total}<span style="font-size:11px;color:#9ca3af;font-weight:400">/60</span></span>
                    <span class="stat-label">Score</span>
                  </div>
                  <div class="stat">
                    <span class="stat-value">${findings}</span>
                    <span class="stat-label">Findings</span>
                  </div>
                  <div class="stat">
                    <span class="stat-value">${checks}</span>
                    <span class="stat-label">Checks</span>
                  </div>
                </div>
                <div class="audit-card-footer">
                  <span class="status-badge ${a.status}">${a.status === 'in_progress' ? 'In corso' : 'Completata'}</span>
                  <span class="date">${date}</span>
                </div>
              </div>`;
            }).join('')}
          </div>
        `}
      </div>
    `;

    main.innerHTML = this._renderShell('dashboard', dashContent);
  },

  showAbout() {
    this.currentView = 'about';
    const main = document.getElementById('main-content');

    const aboutContent = `
      <div class="about-page">
        <div class="about-hero-banner">
          <h1>Il Framework di Analisi<br>piu Avanzato sul Mercato</h1>
          <p>Una metodologia proprietaria che integra le competenze dell'Engineering Lead di Google Chrome, standard internazionali di web quality e intelligenza artificiale di ultima generazione. Ogni audit segue un protocollo strutturato in 7 fasi con oltre 100 checkpoint validati.</p>
        </div>

        <!-- KPI Banner -->
        <div class="about-stats">
          <div class="about-stat-item"><div class="num">7</div><div class="desc">Fasi di Analisi</div></div>
          <div class="about-stat-item"><div class="num">100+</div><div class="desc">Checkpoint Validati</div></div>
          <div class="about-stat-item"><div class="num">11</div><div class="desc">Modelli AI Specializzati</div></div>
          <div class="about-stat-item"><div class="num">6</div><div class="desc">Aree di Scoring</div></div>
        </div>

        <!-- PROCESS DIAGRAM -->
        <div class="about-section">
          <h2>Processo di Audit End-to-End</h2>
          <div class="about-diagram">
            <div class="diagram-row">
              <div class="diagram-phase phase-recon">
                <div class="diagram-phase-id">FASE 1</div>
                <div class="diagram-phase-title">Ricognizione</div>
                <div class="diagram-phase-items">Stack tecnologico<br>Performance & CWV<br>Advertising Intelligence<br>Security Headers</div>
              </div>
              <div class="diagram-arrow">&#x2192;</div>
              <div class="diagram-phase phase-compliance">
                <div class="diagram-phase-id">FASE 2</div>
                <div class="diagram-phase-title">Compliance</div>
                <div class="diagram-phase-items">Cookie Banner UX<br>Consent Mode v2<br>GDPR / DMA<br>Default States</div>
              </div>
              <div class="diagram-arrow">&#x2192;</div>
              <div class="diagram-phase phase-tracking">
                <div class="diagram-phase-id">FASE 3</div>
                <div class="diagram-phase-title">Tracking</div>
                <div class="diagram-phase-items">GTM / GA4 / Ads<br>Server-Side Check<br>Pixel Inventory<br>Cross-Domain</div>
              </div>
            </div>
            <div class="diagram-connector">&#x2193;</div>
            <div class="diagram-row">
              <div class="diagram-phase phase-ecommerce">
                <div class="diagram-phase-id">FASE 4</div>
                <div class="diagram-phase-title">Ecommerce</div>
                <div class="diagram-phase-items">Event Matrix GA4<br>DataLayer Quality<br>Purchase Test<br>Enhanced Conversions</div>
              </div>
              <div class="diagram-arrow">&#x2192;</div>
              <div class="diagram-phase phase-seo">
                <div class="diagram-phase-id">FASE 5</div>
                <div class="diagram-phase-title">SEO & Accessibility</div>
                <div class="diagram-phase-items">On-Page / Schema<br>E-E-A-T Analysis<br>WCAG 2.1 AA<br>Mobile Optimization</div>
              </div>
              <div class="diagram-arrow">&#x2192;</div>
              <div class="diagram-phase phase-cro">
                <div class="diagram-phase-id">FASE 6</div>
                <div class="diagram-phase-title">CRO & Conversion</div>
                <div class="diagram-phase-items">Value Proposition<br>Trust Signals<br>Friction Analysis<br>Page-Type Specific</div>
              </div>
            </div>
            <div class="diagram-connector">&#x2193;</div>
            <div class="diagram-output">
              <div class="diagram-phase phase-output" style="max-width:100%">
                <div class="diagram-phase-id">OUTPUT</div>
                <div class="diagram-phase-title">Report Consultivo & Roadmap Strategica</div>
                <div class="diagram-phase-items">Executive Summary &bull; Scoring Dashboard con Radar Chart &bull; Findings per Severita &bull; Roadmap Prioritizzata per Impatto Business</div>
              </div>
            </div>
          </div>
        </div>

        <!-- OSMANI SPOTLIGHT -->
        <div class="about-section">
          <h2>Il Vantaggio Competitivo</h2>
          <div class="about-spotlight">
            <div class="spotlight-badge">CORE METHODOLOGY</div>
            <h3>Addy Osmani &mdash; Engineering Leadership, Google Chrome</h3>
            <p class="spotlight-subtitle">Il nostro framework di analisi performance e web quality e costruito sulle metodologie sviluppate da Addy Osmani, Engineering Leader del team Google Chrome.</p>
            <div class="spotlight-grid">
              <div class="spotlight-item">
                <div class="spotlight-item-title">Google Lighthouse</div>
                <div class="spotlight-item-desc">Creatore e lead del progetto Lighthouse, lo standard globale per la misurazione della qualita web. Il nostro audit utilizza gli stessi criteri interni di valutazione.</div>
              </div>
              <div class="spotlight-item">
                <div class="spotlight-item-title">Core Web Vitals</div>
                <div class="spotlight-item-desc">Contributor diretto alle metriche LCP, INP, CLS che determinano il ranking su Google. I nostri budget di performance derivano dai suoi benchmark interni.</div>
              </div>
              <div class="spotlight-item">
                <div class="spotlight-item-title">150+ Production Audits</div>
                <div class="spotlight-item-desc">Metodologia validata su oltre 150 audit di produzione per aziende Fortune 500. Le soglie che applichiamo sono calibrate su dati reali, non teorici.</div>
              </div>
              <div class="spotlight-item">
                <div class="spotlight-item-title">Performance Budget Framework</div>
                <div class="spotlight-item-desc">JS &lt; 300KB, page weight &lt; 1.5MB, TTFB &lt; 800ms. Budget scientifici che correlano direttamente con conversion rate e bounce rate.</div>
              </div>
            </div>
            <p class="spotlight-closing">Quando analizziamo le performance del vostro ecommerce, applichiamo lo stesso livello di rigore che Google utilizza internamente per valutare i siti web piu importanti al mondo.</p>
          </div>
        </div>

        <!-- EXPERTISE PANEL -->
        <div class="about-section">
          <h2>Panel di Expertise</h2>
          <div class="about-grid">
            <div class="about-card">
              <h3>Claude AI &mdash; Anthropic</h3>
              <p>Intelligenza artificiale di ultima generazione per l'analisi automatica. 11 modelli specializzati analizzano HTML, robots.txt, sitemap, dataLayer, security headers e generano findings dettagliati con raccomandazioni operative.</p>
              <span class="about-tag tag-ai">AI Engine</span>
            </div>
            <div class="about-card">
              <h3>Corey Haines &mdash; Marketing Strategy</h3>
              <p>Framework SEO avanzato con analisi E-E-A-T, keyword cannibalization, crawl budget optimization. Metodologia CRO strutturata: value proposition, trust signals, friction analysis e ottimizzazione page-type specific.</p>
              <span class="about-tag tag-method">Marketing Expert</span>
            </div>
            <div class="about-card">
              <h3>Matteo Zambon &mdash; GTM & Tracking</h3>
              <p>Massimo esperto italiano di Google Tag Manager. Configurazione Consent Mode v2 compliant, GA4 ecommerce tracking avanzato, Enhanced Conversions setup per massimizzare il ritorno sugli investimenti pubblicitari.</p>
              <span class="about-tag tag-method">GTM Expert</span>
            </div>
            <div class="about-card">
              <h3>Google Developer Documentation</h3>
              <p>Ogni validazione dataLayer segue la documentazione ufficiale Google per developer. Conformita strutturale eventi GA4, tipi dati, parametri obbligatori. Zero interpretazioni, solo standard ufficiali.</p>
              <span class="about-tag tag-google">Google Dev</span>
            </div>
          </div>
        </div>

        <!-- STANDARDS -->
        <div class="about-section">
          <h2>Standard Internazionali Applicati</h2>
          <div class="about-standards-list">
            <div class="standard-row">
              <div class="standard-name">WCAG 2.1 Level AA</div>
              <div class="standard-org">W3C</div>
              <div class="standard-scope">Accessibilita web &mdash; Principi POUR, conformita legale EAA 2025</div>
            </div>
            <div class="standard-row">
              <div class="standard-name">OWASP Top 10</div>
              <div class="standard-org">OWASP Foundation</div>
              <div class="standard-scope">Security headers, CSP, HSTS, XSS prevention, mixed content</div>
            </div>
            <div class="standard-row">
              <div class="standard-name">GDPR & Digital Markets Act</div>
              <div class="standard-org">Unione Europea</div>
              <div class="standard-scope">Consent Mode v2 obbligatoria, ad_user_data/ad_personalization dal marzo 2024</div>
            </div>
            <div class="standard-row">
              <div class="standard-name">Google E-E-A-T</div>
              <div class="standard-org">Google Search Quality</div>
              <div class="standard-scope">Experience, Expertise, Authoritativeness, Trustworthiness &mdash; Quality Rater Guidelines</div>
            </div>
            <div class="standard-row">
              <div class="standard-name">Core Web Vitals</div>
              <div class="standard-org">Google Chrome</div>
              <div class="standard-scope">LCP &le; 2.5s, INP &le; 200ms, CLS &le; 0.1 &mdash; Fattori di ranking diretti</div>
            </div>
            <div class="standard-row">
              <div class="standard-name">GA4 Ecommerce Specification</div>
              <div class="standard-org">Google Analytics</div>
              <div class="standard-scope">Struttura eventi, items[], tipi dati, transaction deduplication</div>
            </div>
          </div>
        </div>

        <!-- MATURITY MODEL -->
        <div class="about-section">
          <h2>Maturity Model</h2>
          <div class="about-score-grid">
            <div class="about-score-card" style="border-top:3px solid #ef4444">
              <h4>0 &mdash; 15</h4>
              <p>Critico. Gap strutturali che impattano direttamente revenue, compliance e posizionamento competitivo.</p>
            </div>
            <div class="about-score-card" style="border-top:3px solid #f59e0b">
              <h4>16 &mdash; 30</h4>
              <p>Base. Infrastruttura minima presente. Interventi prioritari identificati con ROI stimato elevato.</p>
            </div>
            <div class="about-score-card" style="border-top:3px solid #3b82f6">
              <h4>31 &mdash; 45</h4>
              <p>Intermedio. Buona maturita digitale. Ottimizzazioni mirate per massimizzare l'efficienza dell'investimento.</p>
            </div>
            <div class="about-score-card" style="border-top:3px solid #10a37f">
              <h4>46 &mdash; 60</h4>
              <p>Avanzato. Ecosistema MarTech maturo e ottimizzato. Focus su fine-tuning e innovazione incrementale.</p>
            </div>
          </div>
        </div>

        <!-- TOOLING -->
        <div class="about-section">
          <h2>Strumentazione Tecnica</h2>
          <div class="about-tools-grid">
            <div class="about-tool-item"><h4>Google Tag Assistant</h4><p>GTM, GA4, Google Ads</p></div>
            <div class="about-tool-item"><h4>Meta Pixel Helper</h4><p>Facebook / Meta Ads</p></div>
            <div class="about-tool-item"><h4>InfoTrust Inspector</h4><p>Consent Mode v2</p></div>
            <div class="about-tool-item"><h4>EC Assist</h4><p>Enhanced Conversions</p></div>
            <div class="about-tool-item"><h4>Builtwith / Wappalyzer</h4><p>Technology Profiling</p></div>
            <div class="about-tool-item"><h4>PageSpeed Insights</h4><p>Core Web Vitals</p></div>
            <div class="about-tool-item"><h4>Rich Results Test</h4><p>Schema / Structured Data</p></div>
            <div class="about-tool-item"><h4>axe DevTools</h4><p>WCAG Accessibility</p></div>
          </div>
        </div>

        <div class="about-footer">
          <p><strong>Mr Tech</strong> &mdash; MarTech Audit Intelligence</p>
          <p style="margin-top:6px">Powered by Claude AI (Anthropic) &bull; Osmani Web Quality Methodology &bull; Google Developer Standards</p>
        </div>
      </div>
    `;

    main.innerHTML = this._renderShell('about', aboutContent);
  },

  newAuditModal() {
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal">
        <h3>Nuova Audit</h3>
        <div class="form-group">
          <label>Nome Cliente</label>
          <input type="text" id="new-client" placeholder="Es: Lorenzetti Sport s.r.l.">
        </div>
        <div class="form-group">
          <label>Dominio</label>
          <input type="text" id="new-domain" placeholder="Es: lorenzetti.com">
        </div>
        <div class="form-group">
          <label>URL Aggiuntive <span style="font-weight:400;color:#9ca3af">(opzionale, una per riga)</span></label>
          <textarea id="new-extra-urls" rows="3" placeholder="Es: /collections/scarpe&#10;/products/scarpa-running&#10;https://example.com/blog/articolo" style="width:100%;font-size:14px;padding:8px;border:1px solid #d1d5db;border-radius:6px;resize:vertical"></textarea>
        </div>
        <div class="modal-actions">
          <button class="btn" onclick="this.closest('.modal-overlay').remove()">Annulla</button>
          <button class="btn btn-primary" onclick="App.createAudit()">Crea Audit</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    document.getElementById('new-client').focus();
  },

  createAudit() {
    const clientName = document.getElementById('new-client').value.trim();
    const domain = document.getElementById('new-domain').value.trim();
    if (!clientName || !domain) return alert('Compila tutti i campi');

    // Parse extra URLs
    const extraUrlsRaw = (document.getElementById('new-extra-urls')?.value || '').trim();
    const extraUrls = extraUrlsRaw ? extraUrlsRaw.split('\n').map(u => u.trim()).filter(Boolean) : [];

    const audit = Storage.createAudit(domain, clientName);
    audit._extraUrls = extraUrls;
    Storage.saveAudit(audit);
    document.querySelector('.modal-overlay').remove();
    this.openAudit(audit.id);
  },

  async openAudit(id) {
    const audit = Storage.getAudit(id);
    if (!audit) return;

    // Show scanning modal
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.id = 'scanning-modal';
    modal.innerHTML = `
      <div class="modal scanning-modal">
        <div class="scanning-icon">&#128269;</div>
        <h3>Scanning ${audit.domain}...</h3>
        <p class="scanning-subtitle">Rilevamento automatico tech stack, tracking, consent e security</p>
        <div class="scanning-progress"><div class="scanning-bar"></div></div>
        <p class="scanning-status" id="scanning-status">Connessione in corso...</p>
      </div>
    `;
    document.body.appendChild(modal);

    try {
      const statusEl = document.getElementById('scanning-status');
      const extraUrls = audit._extraUrls || [];

      const onProgress = (msg) => {
        if (statusEl) statusEl.textContent = msg;
      };

      const discovered = await AutoDiscovery.run(audit.domain, extraUrls, onProgress);
      const count = Object.keys(discovered).filter(k => !k.startsWith('_')).length;

      if (statusEl) statusEl.textContent = `${count} elementi rilevati. Compilazione checklist...`;
      await new Promise(r => setTimeout(r, 400));

      // Pre-fill checks and notes
      for (const [checkId, data] of Object.entries(discovered)) {
        if (!audit.checks[checkId]) {
          audit.checks[checkId] = data.value;
        }
        if (!audit.notes[checkId] && data.note) {
          audit.notes[checkId] = data.note;
        }
      }

      audit.discovered = discovered;
      audit.discoveredPages = discovered._discoveredPages || [];
      delete audit._extraUrls;
      audit.updatedAt = new Date().toISOString();
      Storage.saveAudit(audit);
    } catch (e) {
      console.warn('Auto-discovery failed:', e);
    }

    // Remove scanning modal
    const m = document.getElementById('scanning-modal');
    if (m) m.remove();

    Checklist.init(audit);
  },

  deleteAudit(id) {
    if (!confirm('Eliminare questa audit?')) return;
    Storage.deleteAudit(id);
    this.showDashboard();
  },

  async showReport() {
    if (!Checklist.currentAudit || !Checklist.template) return;
    await ReportGenerator.showPreview(Checklist.currentAudit, Checklist.template);
  }
};

// Boot
document.addEventListener('DOMContentLoaded', async () => {
  await Storage.loadEnvKeys();
  App.init();
});
