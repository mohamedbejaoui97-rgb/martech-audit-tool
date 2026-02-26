// Report Generator - HTML preview + PDF export
const ReportGenerator = {
  async generate(audit, template) {
    const total = Object.values(audit.scores).reduce((a, b) => a + (parseInt(b) || 0), 0);
    const level = template.scoring.levels.find(l => total >= l.min && total <= l.max) || { label: 'N/A', color: '#999' };
    const date = new Date(audit.createdAt).toLocaleDateString('it-IT', { year: 'numeric', month: 'long', day: 'numeric' });

    const findingsBySeverity = { CRITICO: [], ALTO: [], MEDIO: [], BASSO: [] };
    const aiFindings = [];
    const manualFindings = [];
    (audit.findings || []).forEach(f => {
      if (findingsBySeverity[f.severity]) findingsBySeverity[f.severity].push(f);
      if (f.source === 'ai') aiFindings.push(f);
      else manualFindings.push(f);
    });
    const discoveredPages = audit.discoveredPages || [];

    return `
<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<title>MarTech Audit Report - ${audit.clientName}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Inter', sans-serif; color: #1a1a2e; line-height: 1.6; background: #fff; }
  .page { max-width: 800px; margin: 0 auto; padding: 40px; }
  .cover { text-align: center; padding: 80px 40px; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); color: white; border-radius: 12px; margin-bottom: 40px; }
  .cover h1 { font-size: 32px; margin-bottom: 8px; }
  .cover .subtitle { font-size: 18px; opacity: 0.8; margin-bottom: 32px; }
  .cover .meta { font-size: 14px; opacity: 0.6; }
  .cover .domain { font-size: 20px; background: rgba(255,255,255,0.15); padding: 8px 24px; border-radius: 8px; display: inline-block; margin: 16px 0; }

  h2 { font-size: 22px; margin: 32px 0 16px; padding-bottom: 8px; border-bottom: 2px solid #e5e7eb; }
  h3 { font-size: 16px; margin: 20px 0 8px; }

  .exec-summary { background: #f8fafc; padding: 24px; border-radius: 8px; margin-bottom: 32px; border-left: 4px solid #0f3460; }
  .exec-summary p { margin-bottom: 8px; }

  .scores-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 24px 0; }
  .score-card { background: #f8fafc; padding: 20px; border-radius: 8px; text-align: center; }
  .score-card .score-value { font-size: 36px; font-weight: 700; }
  .score-card .score-label { font-size: 13px; color: #666; margin-top: 4px; }
  .total-card { grid-column: span 3; background: linear-gradient(135deg, #1a1a2e, #0f3460); color: white; padding: 24px; border-radius: 8px; text-align: center; }
  .total-card .score-value { font-size: 48px; }
  .maturity-badge { display: inline-block; padding: 4px 16px; border-radius: 20px; font-weight: 600; font-size: 14px; margin-top: 8px; }

  .finding { padding: 16px; margin: 12px 0; border-radius: 8px; border-left: 4px solid; }
  .finding.critico { background: #fef2f2; border-color: #ef4444; }
  .finding.alto { background: #fff7ed; border-color: #f59e0b; }
  .finding.medio { background: #fefce8; border-color: #eab308; }
  .finding.basso { background: #f0fdf4; border-color: #22c55e; }
  .finding .severity { font-size: 12px; font-weight: 700; text-transform: uppercase; margin-bottom: 4px; }
  .finding .severity.critico { color: #ef4444; }
  .finding .severity.alto { color: #f59e0b; }
  .finding .severity.medio { color: #eab308; }
  .finding .severity.basso { color: #22c55e; }
  .finding h4 { margin-bottom: 6px; }
  .finding p { font-size: 14px; color: #444; margin: 4px 0; }

  .checklist-summary { margin: 16px 0; }
  .checklist-summary table { width: 100%; border-collapse: collapse; font-size: 14px; }
  .checklist-summary th, .checklist-summary td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #e5e7eb; }
  .checklist-summary th { background: #f8fafc; font-weight: 600; }
  .status-ok { color: #22c55e; }
  .status-miss { color: #ef4444; }

  .roadmap { margin: 16px 0; }
  .roadmap-item { display: flex; gap: 12px; padding: 12px 0; border-bottom: 1px solid #f0f0f0; }
  .roadmap-priority { min-width: 80px; font-weight: 600; font-size: 13px; }
  .roadmap-priority.p1 { color: #ef4444; }
  .roadmap-priority.p2 { color: #f59e0b; }
  .roadmap-priority.p3 { color: #3b82f6; }

  .footer { text-align: center; margin-top: 48px; padding-top: 24px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #999; }

  details { margin: 16px 0; }
  details summary { cursor: pointer; font-weight: 600; font-size: 16px; padding: 8px 0; user-select: none; }
  details summary:hover { color: #0f3460; }

  .source-badge { display: inline-block; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 10px; margin-left: 8px; }
  .source-ai { background: #dbeafe; color: #1d4ed8; }
  .source-manual { background: #f3f4f6; color: #374151; }

  .pages-list { margin: 12px 0; }
  .pages-list .page-item { padding: 6px 12px; border-left: 3px solid #e5e7eb; margin: 4px 0; font-size: 14px; }
  .pages-list .page-item .page-type { font-weight: 600; text-transform: capitalize; margin-right: 8px; color: #0f3460; }

  .radar-container { text-align: center; margin: 24px 0; }
  canvas#radar { max-width: 400px; margin: 0 auto; }

  @media print {
    .page { padding: 20px; }
    .cover { page-break-after: always; }
    h2 { page-break-before: always; }
    .finding { break-inside: avoid; }
  }
</style>
</head>
<body>
<div class="page">

  <!-- COVER -->
  <div class="cover">
    <h1>MarTech Audit Report</h1>
    <div class="subtitle">Analisi Tecnica & Raccomandazioni Strategiche</div>
    <div class="domain">${audit.domain}</div>
    <div class="meta">
      <p><strong>Cliente:</strong> ${audit.clientName}</p>
      <p><strong>Data:</strong> ${date}</p>
      <p><strong>Tipo:</strong> Audit Senza Accessi (External Recon)</p>
    </div>
  </div>

  <!-- EXECUTIVE SUMMARY -->
  <h2>Executive Summary</h2>
  <div class="exec-summary">
    <p>L'audit MarTech del dominio <strong>${audit.domain}</strong> ha evidenziato un livello di maturità
    <strong style="color:${level.color}">${level.label}</strong> con un punteggio complessivo di
    <strong>${total}/60</strong>.</p>
    ${findingsBySeverity.CRITICO.length > 0 ? `<p>🔴 Sono stati identificati <strong>${findingsBySeverity.CRITICO.length} problemi critici</strong> che richiedono intervento immediato.</p>` : ''}
    ${findingsBySeverity.ALTO.length > 0 ? `<p>🟠 <strong>${findingsBySeverity.ALTO.length} problemi ad alta priorità</strong> con impatto significativo sulle performance.</p>` : ''}
    <p>Totale findings: <strong>${(audit.findings || []).length}</strong> (${findingsBySeverity.CRITICO.length} critici, ${findingsBySeverity.ALTO.length} alti, ${findingsBySeverity.MEDIO.length} medi, ${findingsBySeverity.BASSO.length} bassi)
    ${aiFindings.length > 0 ? ` — di cui <strong>${aiFindings.length} AI</strong> e <strong>${manualFindings.length} manuali</strong>` : ''}</p>
    ${discoveredPages.length > 1 ? `<p>Pagine analizzate: <strong>${discoveredPages.length}</strong> (${discoveredPages.map(p => p.type).join(', ')})</p>` : ''}
  </div>

  <!-- SCORING DASHBOARD -->
  <h2>Scoring Dashboard</h2>
  <div class="scores-grid">
    ${template.scoring.areas.map(a => `
      <div class="score-card">
        <div class="score-value">${audit.scores[a.id] || 0}</div>
        <div class="score-label">${a.name} (/${a.max})</div>
      </div>
    `).join('')}
    <div class="total-card">
      <div class="score-value">${total}<span style="font-size:24px;opacity:0.6">/60</span></div>
      <div class="score-label">Punteggio Complessivo</div>
      <div class="maturity-badge" style="background:${level.color};color:white">${level.label}</div>
    </div>
  </div>

  <div class="radar-container">
    <canvas id="radar" width="400" height="400"></canvas>
  </div>

  <!-- PAGES ANALYZED -->
  ${discoveredPages.length > 0 ? `
  <h2>Pagine Analizzate</h2>
  <div class="pages-list">
    ${discoveredPages.map(p => `
      <div class="page-item">
        <span class="page-type">${p.type}</span>
        <a href="${p.url}" target="_blank">${p.url}</a>
        ${p.discovered ? ' <span style="font-size:11px;color:#9ca3af">(auto-discovered)</span>' : ''}
      </div>
    `).join('')}
  </div>
  ` : ''}

  <!-- AI FINDINGS -->
  ${aiFindings.length > 0 ? `
  <h2>AI Findings (${aiFindings.length})</h2>
  ${['CRITICO', 'ALTO', 'MEDIO', 'BASSO'].map(sev => {
    const items = aiFindings.filter(f => f.severity === sev);
    if (items.length === 0) return '';
    return items.map(f => `
      <div class="finding ${sev.toLowerCase()}">
        <div class="severity ${sev.toLowerCase()}">${sev} <span class="source-badge source-ai">AI</span></div>
        <h4>${f.title}</h4>
        ${f.description ? `<p>${f.description}</p>` : ''}
        ${f.impact ? `<p><strong>Impatto Business:</strong> ${f.impact}</p>` : ''}
        ${f.recommendation ? `<p><strong>Raccomandazione:</strong> ${f.recommendation}</p>` : ''}
      </div>
    `).join('');
  }).join('')}
  ` : ''}

  <!-- MANUAL FINDINGS -->
  ${manualFindings.length > 0 ? `
  <h2>Findings Manuali (${manualFindings.length})</h2>
  ${['CRITICO', 'ALTO', 'MEDIO', 'BASSO'].map(sev => {
    const items = manualFindings.filter(f => f.severity === sev);
    if (items.length === 0) return '';
    return items.map(f => `
      <div class="finding ${sev.toLowerCase()}">
        <div class="severity ${sev.toLowerCase()}">${sev} <span class="source-badge source-manual">Manuale</span></div>
        <h4>${f.title}</h4>
        ${f.description ? `<p>${f.description}</p>` : ''}
        ${f.impact ? `<p><strong>Impatto Business:</strong> ${f.impact}</p>` : ''}
        ${f.recommendation ? `<p><strong>Raccomandazione:</strong> ${f.recommendation}</p>` : ''}
      </div>
    `).join('');
  }).join('')}
  ` : ''}

  ${(aiFindings.length === 0 && manualFindings.length === 0) ? `
  <h2>Findings Dettagliati</h2>
  <p style="color:#999">Nessun finding registrato.</p>
  ` : ''}

  <!-- CHECKLIST SUMMARY (collapsible) -->
  <h2>Checklist Audit</h2>
  ${template.phases.map(phase => `
    <details>
      <summary>${phase.icon} ${phase.id} - ${phase.name}</summary>
      <div class="checklist-summary">
        <table>
          <tr><th>Check</th><th>Stato</th><th>Note</th></tr>
          ${phase.sections.map(s => s.items.map(item => `
            <tr>
              <td>${item.label}</td>
              <td class="${audit.checks[item.id] ? 'status-ok' : 'status-miss'}">${audit.checks[item.id] ? '✓' : '✗'}</td>
              <td>${audit.notes[item.id] || '-'}</td>
            </tr>
          `).join('')).join('')}
        </table>
      </div>
    </details>
  `).join('')}

  <!-- ROADMAP -->
  <h2>Roadmap di Interventi</h2>
  <div class="roadmap">
    ${findingsBySeverity.CRITICO.map(f => `
      <div class="roadmap-item"><span class="roadmap-priority p1">URGENTE</span><span>${f.title} — ${f.recommendation || 'Intervento immediato richiesto'}</span></div>
    `).join('')}
    ${findingsBySeverity.ALTO.map(f => `
      <div class="roadmap-item"><span class="roadmap-priority p2">1 MESE</span><span>${f.title} — ${f.recommendation || 'Intervento a breve termine'}</span></div>
    `).join('')}
    ${findingsBySeverity.MEDIO.map(f => `
      <div class="roadmap-item"><span class="roadmap-priority p3">3 MESI</span><span>${f.title} — ${f.recommendation || 'Ottimizzazione consigliata'}</span></div>
    `).join('')}
  </div>

  <div class="footer">
    <p>Report generato da MarTech Audit Tool — Mr Tech</p>
    <p>${date}</p>
  </div>

</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script>
  const ctx = document.getElementById('radar');
  if (ctx) {
    new Chart(ctx, {
      type: 'radar',
      data: {
        labels: ${JSON.stringify(template.scoring.areas.map(a => a.name))},
        datasets: [{
          label: 'Score',
          data: ${JSON.stringify(template.scoring.areas.map(a => audit.scores[a.id] || 0))},
          backgroundColor: 'rgba(15, 52, 96, 0.2)',
          borderColor: '#0f3460',
          pointBackgroundColor: '#0f3460',
          pointBorderColor: '#fff',
          borderWidth: 2
        }]
      },
      options: {
        scales: {
          r: { min: 0, max: 10, ticks: { stepSize: 2 } }
        },
        plugins: { legend: { display: false } }
      }
    });
  }
</script>
</body>
</html>`;
  },

  async showPreview(audit, template) {
    const html = await this.generate(audit, template);
    const main = document.getElementById('main-content');
    main.innerHTML = `
      <div class="report-preview-controls">
        <button class="btn" onclick="Checklist.render()">&#x2190; Torna all'Audit</button>
        <button class="btn btn-primary" onclick="ReportGenerator.downloadHtml()">Scarica HTML</button>
        <button class="btn" onclick="ReportGenerator.openInNewTab()">Apri in Nuova Tab</button>
      </div>
      <iframe id="report-frame" srcdoc="${html.replace(/"/g, '&quot;')}" style="width:100%;height:calc(100vh - 126px);border:none;"></iframe>
    `;
    this._lastHtml = html;
  },

  downloadHtml() {
    if (!this._lastHtml) return;
    const blob = new Blob([this._lastHtml], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `martech-audit-${Checklist.currentAudit.clientName.replace(/\s/g, '-')}-${new Date().toISOString().slice(0, 10)}.html`;
    a.click();
    URL.revokeObjectURL(url);
  },

  openInNewTab() {
    if (!this._lastHtml) return;
    const w = window.open();
    w.document.write(this._lastHtml);
    w.document.close();
  }
};
