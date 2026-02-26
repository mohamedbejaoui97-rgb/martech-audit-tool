// Checklist Engine - Renders steps, handles scoring
const Checklist = {
  template: null,
  currentPhase: 0,
  currentAudit: null,

  async init(audit) {
    this.currentAudit = audit;
    const res = await fetch('data/audit-template.json');
    this.template = await res.json();
    this.currentPhase = 0;
    this.render();
  },

  render() {
    const main = document.getElementById('main-content');
    const phase = this.template.phases[this.currentPhase];

    main.innerHTML = `
      <div class="audit-layout">
        <nav class="audit-sidebar">
          <div class="sidebar-header">
            <h3>${this.currentAudit.clientName}</h3>
            <span class="domain-badge">${this.currentAudit.domain}</span>
          </div>
          <div class="sidebar-phases">
            ${this.template.phases.map((p, i) => `
              <button class="phase-btn ${i === this.currentPhase ? 'active' : ''} ${this._phaseComplete(p) ? 'completed' : ''}"
                      onclick="Checklist.goToPhase(${i})">
                <span class="phase-icon">${p.icon}</span>
                <span class="phase-name">${p.id} ${p.name}</span>
                <span class="phase-progress">${this._phaseProgress(p)}</span>
              </button>
            `).join('')}
          </div>
          <div class="sidebar-scores">
            <h4>Scoring Live</h4>
            ${this.template.scoring.areas.map(a => `
              <div class="score-row">
                <span>${a.name}</span>
                <input type="number" min="0" max="${a.max}" value="${this.currentAudit.scores[a.id] || 0}"
                       onchange="Checklist.updateScore('${a.id}', this.value)" class="score-input">
                <span>/${a.max}</span>
              </div>
            `).join('')}
            <div class="score-total">
              <strong>Totale: ${this._totalScore()}/60</strong>
              <span class="maturity-badge" style="background:${this._maturityColor()}">${this._maturityLabel()}</span>
            </div>
          </div>
          <div class="sidebar-actions">
            <button class="btn btn-ai full-audit-btn" onclick="Checklist.runFullAudit()" id="full-audit-btn">AI Full Audit</button>
            <button class="btn btn-finding" onclick="Checklist.addFindingModal()">+ Aggiungi Finding</button>
            <button class="btn btn-report" onclick="App.showReport()">Genera Report</button>
            <button class="btn btn-back" onclick="App.showDashboard()">&#x2190; Dashboard</button>
          </div>
        </nav>
        <div class="audit-main">
          <div class="phase-header">
            <h2>${phase.icon} ${phase.id} - ${phase.name}</h2>
            <p>${phase.description}</p>
          </div>
          ${phase.sections.map(s => this._renderSection(s)).join('')}
          <div class="phase-nav">
            ${this.currentPhase > 0 ? '<button class="btn" onclick="Checklist.prevPhase()">← Fase Precedente</button>' : ''}
            ${this.currentPhase < this.template.phases.length - 1 ? '<button class="btn btn-primary" onclick="Checklist.nextPhase()">Fase Successiva →</button>' : ''}
          </div>
          ${this._renderFindings()}
        </div>
      </div>
    `;
  },

  _renderSection(section) {
    const apiKey = Storage.getApiKey();
    const aiButton = section.ai_enabled ? `
      <button class="btn btn-ai ${!apiKey ? 'disabled' : ''}"
              onclick="Checklist.runAI('${section.ai_action}', '${section.id}')"
              ${!apiKey ? 'disabled title="Configura API key Claude"' : ''}>
        Analizza con AI
      </button>` : '';

    return `
      <div class="section-card" id="section-${section.id}">
        <div class="section-header">
          <h3>${section.name}</h3>
          <span class="tool-badge">${section.tool}</span>
          ${aiButton}
        </div>
        <div class="ai-result" id="ai-result-${section.id}" style="display:none"></div>
        <div class="checklist-items">
          ${section.items.map(item => this._renderItem(item)).join('')}
        </div>
      </div>
    `;
  },

  _renderItem(item) {
    const checked = this.currentAudit.checks[item.id] || false;
    const note = this.currentAudit.notes[item.id] || '';
    const isAutoDetected = this.currentAudit.discovered && this.currentAudit.discovered[item.id];

    return `
      <div class="check-item ${checked ? 'checked' : ''}">
        <label class="check-label">
          <input type="checkbox" ${checked ? 'checked' : ''}
                 onchange="Checklist.toggleCheck('${item.id}', this.checked)">
          <span>${item.label}</span>
          ${isAutoDetected ? '<span class="auto-badge">Auto</span>' : ''}
        </label>
        <input type="text" class="check-note" placeholder="${item.note_placeholder}"
               value="${this._escapeHtml(note)}"
               onchange="Checklist.updateNote('${item.id}', this.value)">
      </div>
    `;
  },

  _renderFindings() {
    const findings = this.currentAudit.findings || [];
    if (findings.length === 0) return '<div class="findings-section"><h3>Findings</h3><p class="text-muted">Nessun finding aggiunto. Usa il bottone "+ Aggiungi Finding" nella sidebar.</p></div>';

    return `
      <div class="findings-section">
        <h3>Findings (${findings.length})</h3>
        <div class="findings-list">
          ${findings.map(f => `
            <div class="finding-card severity-${f.severity.toLowerCase()}">
              <div class="finding-header">
                <span class="severity-badge severity-${f.severity.toLowerCase()}">${f.severity}</span>
                <span class="source-badge ${f.source === 'ai' ? 'source-ai' : 'source-manual'}">${f.source === 'ai' ? 'AI' : 'Manuale'}</span>
                <strong>${this._escapeHtml(f.title)}</strong>
                <button class="btn-icon" onclick="Checklist.deleteFinding('${f.id}')" title="Elimina">✕</button>
              </div>
              <p>${this._escapeHtml(f.description)}</p>
              ${f.impact ? `<p class="finding-impact"><strong>Impatto:</strong> ${this._escapeHtml(f.impact)}</p>` : ''}
              ${f.recommendation ? `<p class="finding-rec"><strong>Raccomandazione:</strong> ${this._escapeHtml(f.recommendation)}</p>` : ''}
            </div>
          `).join('')}
        </div>
      </div>
    `;
  },

  toggleCheck(checkId, value) {
    this.currentAudit = Storage.updateAuditCheck(this.currentAudit.id, checkId, value);
    // Update just the item visually without re-rendering everything
    const item = document.querySelector(`input[onchange*="${checkId}"]`);
    if (item) item.closest('.check-item').classList.toggle('checked', value);
  },

  updateNote(checkId, note) {
    this.currentAudit = Storage.updateAuditNote(this.currentAudit.id, checkId, note);
  },

  updateScore(areaId, value) {
    this.currentAudit.scores[areaId] = parseInt(value) || 0;
    Storage.updateScores(this.currentAudit.id, this.currentAudit.scores);
    // Update total display
    const totalEl = document.querySelector('.score-total');
    if (totalEl) {
      totalEl.innerHTML = `<strong>Totale: ${this._totalScore()}/60</strong>
        <span class="maturity-badge" style="background:${this._maturityColor()}">${this._maturityLabel()}</span>`;
    }
  },

  goToPhase(idx) {
    this.currentPhase = idx;
    this.render();
  },

  nextPhase() {
    if (this.currentPhase < this.template.phases.length - 1) {
      this.currentPhase++;
      this.render();
      window.scrollTo(0, 0);
    }
  },

  prevPhase() {
    if (this.currentPhase > 0) {
      this.currentPhase--;
      this.render();
      window.scrollTo(0, 0);
    }
  },

  async runAI(action, sectionId) {
    const apiKey = Storage.getApiKey();
    if (!apiKey) return alert('Configura la API key Claude nelle impostazioni');

    const resultDiv = document.getElementById(`ai-result-${sectionId}`);
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = '<div class="ai-loading">Analisi AI in corso...</div>';

    const btn = resultDiv.previousElementSibling?.querySelector('.btn-ai');
    if (btn) btn.disabled = true;

    try {
      const url = this.currentAudit.domain.startsWith('http') ? this.currentAudit.domain : 'https://' + this.currentAudit.domain;
      const result = await AIAnalysis.analyze(action, url, apiKey);
      // Auto-create findings from AI response
      const newFindings = this._autoCreateFindings(result.analysis);
      resultDiv.innerHTML = `
        <div class="ai-response">
          <div class="ai-header">Analisi AI ${newFindings > 0 ? `<span class="ai-findings-badge">${newFindings} findings creati</span>` : ''}</div>
          <div class="ai-content">${this._markdownToHtml(result.analysis)}</div>
        </div>`;
      if (newFindings > 0) this.render();
    } catch (e) {
      resultDiv.innerHTML = `<div class="ai-error">Errore: ${e.message}</div>`;
    }

    if (btn) btn.disabled = false;
  },

  addFindingModal() {
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal">
        <h3>Aggiungi Finding</h3>
        <div class="form-group">
          <label>Titolo</label>
          <input type="text" id="finding-title" placeholder="Es: Nessun tag Google Ads installato">
        </div>
        <div class="form-group">
          <label>Severità</label>
          <select id="finding-severity">
            <option value="CRITICO">CRITICO</option>
            <option value="ALTO">ALTO</option>
            <option value="MEDIO">MEDIO</option>
            <option value="BASSO">BASSO</option>
          </select>
        </div>
        <div class="form-group">
          <label>Descrizione</label>
          <textarea id="finding-desc" rows="3" placeholder="Descrizione del problema trovato"></textarea>
        </div>
        <div class="form-group">
          <label>Impatto Business</label>
          <textarea id="finding-impact" rows="2" placeholder="Impatto sul business del cliente"></textarea>
        </div>
        <div class="form-group">
          <label>Raccomandazione</label>
          <textarea id="finding-rec" rows="2" placeholder="Cosa fare per risolvere"></textarea>
        </div>
        <div class="modal-actions">
          <button class="btn" onclick="this.closest('.modal-overlay').remove()">Annulla</button>
          <button class="btn btn-primary" onclick="Checklist.saveFinding()">Salva Finding</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  },

  saveFinding() {
    const title = document.getElementById('finding-title').value.trim();
    if (!title) return alert('Inserisci un titolo');

    const finding = {
      title,
      severity: document.getElementById('finding-severity').value,
      description: document.getElementById('finding-desc').value.trim(),
      impact: document.getElementById('finding-impact').value.trim(),
      recommendation: document.getElementById('finding-rec').value.trim()
    };

    this.currentAudit = Storage.addFinding(this.currentAudit.id, finding);
    document.querySelector('.modal-overlay').remove();
    this.render();
  },

  async runFullAudit() {
    const apiKey = Storage.getApiKey();
    if (!apiKey) return alert('Configura la API key Claude nelle impostazioni della dashboard');

    const btn = document.getElementById('full-audit-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Audit in corso...'; }

    try {
      const url = this.currentAudit.domain.startsWith('http') ? this.currentAudit.domain : 'https://' + this.currentAudit.domain;
      const results = await AIAnalysis.runFullAudit(url, apiKey);

      // Auto-create findings from all successful results
      let totalNewFindings = 0;
      for (const r of results) {
        if (r.success && r.result?.analysis) {
          totalNewFindings += this._autoCreateFindings(r.result.analysis);
        }
      }

      // Show results in a modal
      const modal = document.createElement('div');
      modal.className = 'modal-overlay';
      modal.innerHTML = `
        <div class="modal" style="max-width:800px;max-height:90vh;overflow-y:auto">
          <h3>AI Full Audit Completato ${totalNewFindings > 0 ? `<span class="ai-findings-badge">${totalNewFindings} findings creati</span>` : ''}</h3>
          ${results.map(r => `
            <div class="ai-response" style="margin:12px 0">
              <div class="ai-header">${r.type.toUpperCase()} ${r.success ? '✅' : '❌'}</div>
              <div class="ai-content" style="max-height:300px;overflow-y:auto">
                ${r.success ? this._markdownToHtml(r.result.analysis) : `<span style="color:red">Errore: ${r.error}</span>`}
              </div>
            </div>
          `).join('')}
          <div class="modal-actions">
            <button class="btn btn-primary" onclick="this.closest('.modal-overlay').remove(); Checklist.render();">Chiudi</button>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
    } catch (e) {
      alert('Errore: ' + e.message);
    }

    if (btn) { btn.disabled = false; btn.textContent = 'AI Full Audit'; }
  },

  deleteFinding(findingId) {
    if (!confirm('Eliminare questo finding?')) return;
    this.currentAudit = Storage.deleteFinding(this.currentAudit.id, findingId);
    this.render();
  },

  _phaseProgress(phase) {
    let total = 0, checked = 0;
    phase.sections.forEach(s => {
      s.items.forEach(item => {
        total++;
        if (this.currentAudit.checks[item.id]) checked++;
      });
    });
    return total > 0 ? `${checked}/${total}` : '';
  },

  _phaseComplete(phase) {
    let total = 0, checked = 0;
    phase.sections.forEach(s => {
      s.items.forEach(item => {
        total++;
        if (this.currentAudit.checks[item.id]) checked++;
      });
    });
    return total > 0 && checked === total;
  },

  _totalScore() {
    return Object.values(this.currentAudit.scores).reduce((a, b) => a + (parseInt(b) || 0), 0);
  },

  _maturityLabel() {
    const total = this._totalScore();
    const level = this.template.scoring.levels.find(l => total >= l.min && total <= l.max);
    return level ? level.label : 'N/A';
  },

  _maturityColor() {
    const total = this._totalScore();
    const level = this.template.scoring.levels.find(l => total >= l.min && total <= l.max);
    return level ? level.color : '#999';
  },

  _escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  },

  /**
   * Parse AI findings from text using the **FINDING [SEVERITY]:** pattern
   */
  _parseAIFindings(text) {
    if (!text) return [];
    const findings = [];
    // Match: **FINDING [SEVERITY]:** Title\n- Problema: ...\n- Impatto: ...\n- Fix: ...
    const regex = /\*\*FINDING\s*\[?(CRITICO|ALTO|MEDIO|BASSO)\]?\s*:?\*\*:?\s*(.+?)(?:\n|$)([\s\S]*?)(?=\*\*FINDING|\*\*---|\n\n\n|$)/gi;
    let match;

    while ((match = regex.exec(text)) !== null) {
      const severity = match[1].toUpperCase();
      const title = match[2].trim();
      const body = match[3] || '';

      const problemaMatch = body.match(/[-•]\s*(?:\*\*)?Problema(?:\*\*)?:\s*([\s\S]*?)(?=[-•]\s*(?:\*\*)?(?:Impatto|Fix)|$)/i);
      const impattoMatch = body.match(/[-•]\s*(?:\*\*)?Impatto(?:\*\*)?:\s*([\s\S]*?)(?=[-•]\s*(?:\*\*)?Fix|$)/i);
      const fixMatch = body.match(/[-•]\s*(?:\*\*)?Fix(?:\*\*)?:\s*([\s\S]*?)$/i);

      findings.push({
        title,
        severity,
        description: (problemaMatch?.[1] || '').trim(),
        impact: (impattoMatch?.[1] || '').trim(),
        recommendation: (fixMatch?.[1] || '').trim(),
        source: 'ai'
      });
    }

    return findings;
  },

  /**
   * Auto-create findings from AI analysis text
   */
  _autoCreateFindings(text) {
    const parsed = this._parseAIFindings(text);
    let count = 0;
    for (const finding of parsed) {
      // Avoid duplicates by title
      const existing = (this.currentAudit.findings || []).find(f => f.title === finding.title);
      if (!existing) {
        this.currentAudit = Storage.addFinding(this.currentAudit.id, finding);
        count++;
      }
    }
    return count;
  },

  _markdownToHtml(md) {
    return (md || '')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n- /g, '\n<li>')
      .replace(/\n/g, '<br>')
      .replace(/<li>/g, '</li><li>')
      .replace(/<br><\/li>/g, '</li>');
  }
};
