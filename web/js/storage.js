// Storage Manager - localStorage wrapper
const Storage = {
  KEYS: {
    AUDITS: 'martech_audits',
    API_KEY: 'martech_claude_key',
    GOOGLE_KEY: 'martech_google_key',
    SETTINGS: 'martech_settings'
  },

  getAudits() {
    return JSON.parse(localStorage.getItem(this.KEYS.AUDITS) || '[]');
  },

  saveAudit(audit) {
    const audits = this.getAudits();
    const idx = audits.findIndex(a => a.id === audit.id);
    if (idx >= 0) audits[idx] = audit;
    else audits.unshift(audit);
    try {
      localStorage.setItem(this.KEYS.AUDITS, JSON.stringify(audits));
    } catch (e) {
      alert('Spazio di archiviazione esaurito. Elimina audit vecchie per continuare.');
    }
  },

  deleteAudit(id) {
    const audits = this.getAudits().filter(a => a.id !== id);
    localStorage.setItem(this.KEYS.AUDITS, JSON.stringify(audits));
  },

  getAudit(id) {
    return this.getAudits().find(a => a.id === id) || null;
  },

  getApiKey() {
    return localStorage.getItem(this.KEYS.API_KEY) || '';
  },

  setApiKey(key) {
    localStorage.setItem(this.KEYS.API_KEY, key);
  },

  getGoogleKey() {
    return localStorage.getItem(this.KEYS.GOOGLE_KEY) || '';
  },

  setGoogleKey(key) {
    localStorage.setItem(this.KEYS.GOOGLE_KEY, key);
  },

  async loadEnvKeys() {
    try {
      const res = await fetch('/api/keys');
      const keys = await res.json();
      if (keys.claude_key && !this.getApiKey()) this.setApiKey(keys.claude_key);
      if (keys.google_key && !this.getGoogleKey()) this.setGoogleKey(keys.google_key);
    } catch (e) { /* not running via server.py, skip */ }
  },

  getSettings() {
    return JSON.parse(localStorage.getItem(this.KEYS.SETTINGS) || '{}');
  },

  saveSettings(settings) {
    localStorage.setItem(this.KEYS.SETTINGS, JSON.stringify(settings));
  },

  createAudit(domain, clientName) {
    const audit = {
      id: 'audit_' + Date.now(),
      domain,
      clientName,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      status: 'in_progress',
      checks: {},
      notes: {},
      discovered: {},
      findings: [],
      scores: { consent: 0, tracking: 0, ecommerce: 0, seo: 0, accessibility: 0, advertising: 0 }
    };
    this.saveAudit(audit);
    return audit;
  },

  updateAuditCheck(auditId, checkId, value) {
    const audit = this.getAudit(auditId);
    if (!audit) return;
    audit.checks[checkId] = value;
    audit.updatedAt = new Date().toISOString();
    this.saveAudit(audit);
    return audit;
  },

  updateAuditNote(auditId, checkId, note) {
    const audit = this.getAudit(auditId);
    if (!audit) return;
    audit.notes[checkId] = note;
    audit.updatedAt = new Date().toISOString();
    this.saveAudit(audit);
    return audit;
  },

  addFinding(auditId, finding) {
    const audit = this.getAudit(auditId);
    if (!audit) return;
    finding.id = 'f_' + Date.now();
    audit.findings.push(finding);
    audit.updatedAt = new Date().toISOString();
    this.saveAudit(audit);
    return audit;
  },

  updateFinding(auditId, findingId, updates) {
    const audit = this.getAudit(auditId);
    if (!audit) return;
    const f = audit.findings.find(f => f.id === findingId);
    if (f) Object.assign(f, updates);
    audit.updatedAt = new Date().toISOString();
    this.saveAudit(audit);
    return audit;
  },

  deleteFinding(auditId, findingId) {
    const audit = this.getAudit(auditId);
    if (!audit) return;
    audit.findings = audit.findings.filter(f => f.id !== findingId);
    audit.updatedAt = new Date().toISOString();
    this.saveAudit(audit);
    return audit;
  },

  updateDiscovered(auditId, discovered) {
    const audit = this.getAudit(auditId);
    if (!audit) return;
    audit.discovered = discovered;
    audit.updatedAt = new Date().toISOString();
    this.saveAudit(audit);
    return audit;
  },

  updateScores(auditId, scores) {
    const audit = this.getAudit(auditId);
    if (!audit) return;
    audit.scores = scores;
    audit.updatedAt = new Date().toISOString();
    this.saveAudit(audit);
    return audit;
  }
};
