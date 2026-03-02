"""McKinsey HTML report generator for Deep mode.

Loads template from data/templates/report_deep.html (ADR-4),
populates {{placeholder}} markers via str.replace().
FRs: FR52-FR59.  NFRs: NFR10.
"""

import base64
import os
import re
import html
import json
import math
from datetime import datetime

# ─── PATHS ──────────────────────────────────────────────────────────────────

CLI_DIR = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(os.path.dirname(CLI_DIR))
TEMPLATE_PATH = os.path.join(TOOL_DIR, "data", "templates", "report_deep.html")
OUTPUT_DIR = os.path.join(TOOL_DIR, "output")

# ─── GRADE COLORS ───────────────────────────────────────────────────────────

GRADE_COLORS = {
    "A": "#22c55e",
    "B": "#3b82f6",
    "C": "#eab308",
    "D": "#f59e0b",
    "F": "#ef4444",
}

SEVERITY_CSS = {
    "critical": "sev-critical",
    "high": "sev-high",
    "medium": "sev-medium",
    "low": "sev-low",
}

# ─── HELPERS ────────────────────────────────────────────────────────────────

def _esc(s):
    """HTML-escape a string."""
    return html.escape(str(s)) if s else ""


def _italian_date():
    """Current date in Italian format."""
    date_str = datetime.now().strftime("%d %B %Y")
    months = {
        "January": "Gennaio", "February": "Febbraio", "March": "Marzo",
        "April": "Aprile", "May": "Maggio", "June": "Giugno",
        "July": "Luglio", "August": "Agosto", "September": "Settembre",
        "October": "Ottobre", "November": "Novembre", "December": "Dicembre",
    }
    for en, it in months.items():
        date_str = date_str.replace(en, it)
    return date_str


def _md_to_html(text):
    """Minimal markdown → HTML conversion for synthesis output."""
    if not text:
        return ""
    t = _esc(text)
    # Headers
    t = re.sub(r'^#{4}\s+(.+)$', r'<h4>\1</h4>', t, flags=re.MULTILINE)
    t = re.sub(r'^#{3}\s+(.+)$', r'<h3>\1</h3>', t, flags=re.MULTILINE)
    t = re.sub(r'^#{2}\s+(.+)$', r'<h3>\1</h3>', t, flags=re.MULTILINE)
    # Bold
    t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
    # Inline code
    t = re.sub(r'`([^`]+)`', r'<code>\1</code>', t)
    # List items
    t = re.sub(r'^[-*]\s+(.+)$', r'<li>\1</li>', t, flags=re.MULTILINE)
    # Wrap consecutive <li> in <ul>
    t = re.sub(r'((?:<li>.*?</li>\n?)+)', r'<ul>\1</ul>', t)
    # Numbered list items
    t = re.sub(r'^\d+\.\s+(.+)$', r'<li>\1</li>', t, flags=re.MULTILINE)
    # Paragraphs (double newline)
    t = re.sub(r'\n\n+', '</p>\n<p>', t)
    # Single newlines → <br> (except inside tags)
    t = re.sub(r'(?<!</p>)\n(?!<)', '<br>\n', t)
    if not t.startswith('<'):
        t = '<p>' + t + '</p>'
    return t


# ─── RADAR SVG (FR53) ──────────────────────────────────────────────────────

def _build_radar_svg(pillars):
    """Generate SVG radar chart for Trust Score pillars (FR53).

    Args:
        pillars: dict of pillar_name → {score, label, ...}

    Returns:
        SVG string
    """
    if not pillars:
        return '<p style="color:#999;text-align:center">Dati insufficienti per radar chart</p>'

    items = list(pillars.items())
    n = len(items)
    if n < 3:
        return '<p style="color:#999;text-align:center">Servono almeno 3 pilastri per il radar</p>'

    cx, cy, r = 200, 200, 160
    size = 400

    # Build SVG
    svg = [f'<svg viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">']

    # Grid circles
    for level in [25, 50, 75, 100]:
        lr = r * level / 100
        svg.append(f'  <circle cx="{cx}" cy="{cy}" r="{lr:.1f}" fill="none" stroke="#e5e7eb" stroke-width="1"/>')

    # Axes and labels
    for i, (key, data) in enumerate(items):
        angle = (2 * math.pi * i / n) - math.pi / 2
        x_end = cx + r * math.cos(angle)
        y_end = cy + r * math.sin(angle)
        svg.append(f'  <line x1="{cx}" y1="{cy}" x2="{x_end:.1f}" y2="{y_end:.1f}" stroke="#e5e7eb" stroke-width="1"/>')

        # Label
        label = data.get("label", key).split("(")[0].strip()
        lx = cx + (r + 24) * math.cos(angle)
        ly = cy + (r + 24) * math.sin(angle)
        anchor = "middle"
        if math.cos(angle) > 0.3:
            anchor = "start"
        elif math.cos(angle) < -0.3:
            anchor = "end"
        svg.append(f'  <text x="{lx:.1f}" y="{ly:.1f}" font-size="11" fill="#666" '
                   f'text-anchor="{anchor}" font-family="Inter,sans-serif">{_esc(label)}</text>')

    # Data polygon
    points = []
    for i, (key, data) in enumerate(items):
        score = data.get("score", 0)
        angle = (2 * math.pi * i / n) - math.pi / 2
        pr = r * score / 100
        px = cx + pr * math.cos(angle)
        py = cy + pr * math.sin(angle)
        points.append(f"{px:.1f},{py:.1f}")

    pts_str = " ".join(points)
    svg.append(f'  <polygon points="{pts_str}" fill="rgba(15,52,96,0.15)" stroke="#0f3460" stroke-width="2.5"/>')

    # Data points
    for i, (key, data) in enumerate(items):
        score = data.get("score", 0)
        angle = (2 * math.pi * i / n) - math.pi / 2
        pr = r * score / 100
        px = cx + pr * math.cos(angle)
        py = cy + pr * math.sin(angle)
        svg.append(f'  <circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="#0f3460" stroke="#fff" stroke-width="2"/>')
        svg.append(f'  <text x="{px:.1f}" y="{py - 10:.1f}" font-size="12" fill="#0f3460" '
                   f'text-anchor="middle" font-weight="700" font-family="Inter,sans-serif">{score}</text>')

    svg.append('</svg>')
    return "\n".join(svg)


# ─── PILLAR CARDS ───────────────────────────────────────────────────────────

def _build_pillar_cards(pillars):
    """Build HTML cards for each Trust Score pillar."""
    if not pillars:
        return ""
    cards = []
    for key, data in pillars.items():
        label = data.get("label", key)
        score = data.get("score", 0)
        weight = data.get("weight_normalized", 0)
        cards.append(
            f'<div class="pillar-card">'
            f'<div class="pillar-score">{score}</div>'
            f'<div class="pillar-label">{_esc(label)}</div>'
            f'<div class="pillar-weight">Peso: {weight:.0%}</div>'
            f'</div>'
        )
    return "\n".join(cards)


# ─── CONSENT IMPACT CHAIN (FR54) ───────────────────────────────────────────

def _build_chain_html(consent_chain):
    """Build visual consent impact chain (FR54)."""
    if not consent_chain:
        return '<p style="color:#999">Nessun impatto significativo sulla catena del consent.</p>'

    chain = consent_chain.get("chain", [])
    if not chain:
        return '<p style="color:#999">Nessun impatto significativo sulla catena del consent.</p>'

    parts = []
    parts.append('<div class="chain">')
    for i, step in enumerate(chain):
        if i > 0:
            parts.append('<span class="chain-arrow">&rarr;</span>')
        parts.append(
            f'<div class="chain-step">'
            f'<div class="step-num">STEP {step.get("step", i+1)}</div>'
            f'<div class="step-title">{_esc(step.get("title", ""))}</div>'
            f'<div class="step-detail">{_esc(step.get("detail", ""))}</div>'
            f'</div>'
        )
    parts.append('</div>')
    return "\n".join(parts)


# ─── GAP-TO-REVENUE TABLE (FR55) ───────────────────────────────────────────

def _build_gap_table(gap_revenue):
    """Build Gap-to-Revenue HTML table (FR55)."""
    if not gap_revenue:
        return '<p style="color:#999">Dati Gap-to-Revenue non disponibili.</p>'

    issues = gap_revenue.get("issues", [])
    if not issues:
        return '<p style="color:#999">Nessun problema identificato.</p>'

    rows = []
    rows.append('<table class="gap-table">')
    rows.append('<tr><th>Piattaforma</th><th>Problema</th><th>Severit&agrave;</th><th>Impatto &euro;/mese</th></tr>')

    for issue in sorted(issues, key=lambda x: x.get("impact_max", 0), reverse=True):
        sev = issue.get("severity", "medium")
        css = SEVERITY_CSS.get(sev, "")
        leverage = '<span class="leverage-badge">LEVA</span>' if issue.get("is_leverage_node") else ""
        rows.append(
            f'<tr>'
            f'<td>{_esc(issue.get("platform", ""))}</td>'
            f'<td>{_esc(issue.get("issue", ""))}{leverage}</td>'
            f'<td class="{css}">{_esc(sev.upper())}</td>'
            f'<td>&euro;{issue.get("impact_min", 0):,.0f}&ndash;&euro;{issue.get("impact_max", 0):,.0f}</td>'
            f'</tr>'
        )

    total_label = gap_revenue.get("total_impact_label", "")
    rows.append(f'<tr class="gap-total"><td colspan="3">TOTALE IMPATTO STIMATO</td><td>{_esc(total_label)}</td></tr>')
    rows.append('</table>')

    # Leverage nodes callout
    leverage_nodes = gap_revenue.get("leverage_nodes", [])
    if leverage_nodes:
        rows.append('<div style="background:#dbeafe;padding:16px;border-radius:8px;margin-top:12px;font-size:14px">')
        rows.append('<strong style="color:#1e40af">Nodi di Leva</strong> &mdash; Fix singoli che risolvono problemi multipli:')
        rows.append('<ul style="margin-top:8px">')
        for ln in leverage_nodes:
            affects = ", ".join(ln.get("affects", []))
            rows.append(f'<li>{_esc(ln.get("issue", ""))} &rarr; Impatto su: {_esc(affects)}</li>')
        rows.append('</ul></div>')

    return "\n".join(rows)


# ─── SYNTHESIS SECTION PARSER ───────────────────────────────────────────────

def _extract_synthesis_sections(synthesis_text):
    """Parse synthesis output into named sections.

    Expects ## headers from the Opus prompt structure.
    Returns dict of section_name → content.
    """
    if not synthesis_text:
        return {}

    sections = {}
    current_key = None
    current_lines = []

    for line in synthesis_text.split("\n"):
        header_match = re.match(r'^##\s*\d*\.?\s*(.+)', line)
        if header_match:
            if current_key:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = header_match.group(1).strip().upper()
            current_lines = []
        else:
            current_lines.append(line)

    if current_key:
        sections[current_key] = "\n".join(current_lines).strip()

    return sections


def _find_section(sections, *keywords):
    """Find a section by matching keywords in its title."""
    for key, content in sections.items():
        for kw in keywords:
            if kw.upper() in key:
                return content
    return ""


# ─── EVIDENCE SCREENSHOTS (Change 10) ─────────────────────────────────────

MIME_MAP = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
}


def _build_evidence_html(deep_wizard_block):
    """Build HTML sections with base64-embedded evidence screenshots."""
    wizard_keys = {
        "iubenda_data": "Iubenda",
        "gtm_data": "GTM",
        "gads_data": "Google Ads",
        "meta_data": "Meta",
        "gsc_data": "GSC",
    }
    parts = []

    for key, label in wizard_keys.items():
        wdata = deep_wizard_block.get(key, {})
        screenshots = wdata.get("evidence_screenshots", [])
        if not screenshots:
            continue

        parts.append(f'<div class="evidence-section">')
        parts.append(f'<h4>Screenshot — {_esc(label)}</h4>')
        parts.append('<div style="display:flex;flex-wrap:wrap;gap:12px">')

        for path in screenshots:
            if not os.path.isfile(path):
                continue
            ext = os.path.splitext(path)[1].lower()
            mime = MIME_MAP.get(ext, "image/png")
            try:
                with open(path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                parts.append(
                    f'<div style="max-width:400px">'
                    f'<img src="data:{mime};base64,{b64}" '
                    f'style="max-width:100%;border:1px solid #e5e7eb;border-radius:8px" '
                    f'alt="Evidence {_esc(os.path.basename(path))}">'
                    f'<p style="font-size:11px;color:#666;margin:4px 0">{_esc(os.path.basename(path))}</p>'
                    f'</div>'
                )
            except Exception:
                continue

        parts.append('</div></div>')

    return "\n".join(parts)


# ─── L2 RESULTS HTML (Fix 17) ──────────────────────────────────────────────

L2_LABELS = {
    "performance": "Performance",
    "cwv": "Core Web Vitals",
    "seo": "SEO",
    "seo_deep": "SEO Deep",
    "accessibility": "Accessibilità",
    "security": "Sicurezza",
    "robots": "Robots.txt",
    "sitemap": "Sitemap",
    "datalayer": "DataLayer",
    "cro": "CRO",
    "advertising": "Advertising",
}

# Map L2 analysis types to wizard platform sections for merging
L2_PLATFORM_MAP = {
    "iubenda": [],
    "gtm": ["datalayer"],
    "gads": ["advertising", "cro"],
    "meta": ["advertising", "cro"],
    "gsc": ["seo", "seo_deep", "robots", "sitemap"],
}


def _build_l2_section_html(l2_results):
    """Build HTML for all L2 analysis results (Fix 17)."""
    if not l2_results:
        return ""

    parts = []
    for atype, result in l2_results.items():
        label = L2_LABELS.get(atype, atype.title())
        parts.append(f'<div class="platform-section">')
        parts.append(f'<h3>L2 — {_esc(label)}</h3>')
        parts.append('<div class="platform-content">')
        if isinstance(result, str):
            if result.startswith("Errore:"):
                parts.append(f'<p style="color:#ef4444">{_esc(result)}</p>')
            else:
                parts.append(_md_to_html(result))
        elif isinstance(result, dict):
            # Try to extract text content from dict
            text = result.get("text", result.get("analysis", ""))
            if text:
                parts.append(_md_to_html(text))
            else:
                parts.append(f'<pre style="font-size:12px;overflow-x:auto">{_esc(json.dumps(result, ensure_ascii=False, indent=2)[:3000])}</pre>')
        parts.append('</div></div>')

    return "\n".join(parts)


def _build_l2_for_platform(platform, l2_results):
    """Build L2 results HTML relevant to a specific platform (Fix 21)."""
    if not l2_results:
        return ""

    relevant_types = L2_PLATFORM_MAP.get(platform, [])
    if not relevant_types:
        return ""

    parts = []
    for atype in relevant_types:
        result = l2_results.get(atype)
        if not result or (isinstance(result, str) and result.startswith("Errore:")):
            continue
        label = L2_LABELS.get(atype, atype.title())
        parts.append(f'<h4>Analisi L2: {_esc(label)}</h4>')
        if isinstance(result, str):
            parts.append(_md_to_html(result[:3000]))
        elif isinstance(result, dict):
            text = result.get("text", result.get("analysis", ""))
            if text:
                parts.append(_md_to_html(text[:3000]))

    return "\n".join(parts)


def _build_platform_fallback(deep_wizard_block, l2_results):
    """Build platform analysis from wizard data + L2 when Opus section is empty (Fix 19)."""
    wizard_configs = {
        "iubenda_data": ("Iubenda — Consent & Privacy", "iubenda"),
        "gtm_data": ("GTM — Implementation Quality", "gtm"),
        "gads_data": ("Google Ads — Conversioni", "gads"),
        "meta_data": ("Meta — Event Match Quality", "meta"),
        "gsc_data": ("GSC — Data Foundation", "gsc"),
    }

    parts = []
    for key, (label, platform) in wizard_configs.items():
        wdata = deep_wizard_block.get(key, {})
        if not wdata:
            continue

        parts.append(f'<div class="platform-section">')
        parts.append(f'<h3>{_esc(label)}</h3>')
        parts.append('<div class="platform-content">')

        # Render key wizard findings
        findings = []
        for field, value in wdata.items():
            if field.startswith("_") or field in ("container_raw", "evidence_screenshots"):
                continue
            if isinstance(value, (dict, list)):
                continue
            findings.append(f"<li><strong>{_esc(field.replace('_', ' ').title())}</strong>: {_esc(str(value))}</li>")

        if findings:
            parts.append("<ul>" + "\n".join(findings[:20]) + "</ul>")

        # Anomalies
        if wdata.get("anomalies_detected"):
            parts.append(f'<div style="background:#fef2f2;padding:12px;border-radius:8px;margin:8px 0;border-left:4px solid #ef4444">')
            parts.append(f'<strong>Anomalie rilevate dall\'operatore:</strong><br>{_esc(wdata["anomalies_detected"])}')
            parts.append('</div>')

        # Operator notes
        if wdata.get("operator_notes"):
            parts.append(f'<div style="background:#fffbeb;padding:12px;border-radius:8px;margin:8px 0;border-left:4px solid #f59e0b">')
            parts.append(f'<strong>Note operatore:</strong><br>{_esc(wdata["operator_notes"])}')
            parts.append('</div>')

        # L2 results for this platform (Fix 21)
        l2_html = _build_l2_for_platform(platform, l2_results)
        if l2_html:
            parts.append(l2_html)

        # Evidence screenshots for this platform (Fix 20)
        screenshots = wdata.get("evidence_screenshots", [])
        if screenshots:
            parts.append('<h4>Screenshot Evidence</h4>')
            parts.append('<div style="display:flex;flex-wrap:wrap;gap:12px">')
            for path in screenshots:
                if not os.path.isfile(path):
                    continue
                ext = os.path.splitext(path)[1].lower()
                mime = MIME_MAP.get(ext, "image/png")
                try:
                    with open(path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("ascii")
                    parts.append(
                        f'<div style="max-width:400px">'
                        f'<img src="data:{mime};base64,{b64}" '
                        f'style="max-width:100%;border:1px solid #e5e7eb;border-radius:8px" '
                        f'alt="Evidence {_esc(os.path.basename(path))}">'
                        f'</div>'
                    )
                except Exception:
                    continue
            parts.append('</div>')

        parts.append('</div></div>')

    return "\n".join(parts)


def _build_roadmap_fallback(deep_wizard_block):
    """Build a basic roadmap from wizard data when Opus doesn't provide one (Fix 19)."""
    items = []

    # Check for critical issues across wizards
    iub = deep_wizard_block.get("iubenda_data", {})
    if iub.get("triage_score") in ("D", "F"):
        items.append(("urgent", "Fix Consent Mode v2 — configurare Advanced per recuperare conversioni modellate"))
    if iub.get("consent_mode_v2") == "none":
        items.append(("urgent", "Implementare Consent Mode v2 in Google Tag Manager"))

    gtm = deep_wizard_block.get("gtm_data", {})
    gap = gtm.get("gap_analysis", {})
    if gap.get("missing_critical"):
        items.append(("urgent", f"Aggiungere tag GTM critici mancanti: {', '.join(gap['missing_critical'])}"))

    gads = deep_wizard_block.get("gads_data", {})
    if gads.get("ga4_gap_critical"):
        items.append(("urgent", "Risolvere GA4-Google Ads conversion gap — tracking rotto"))
    if gads.get("enhanced_conversions_status") in ("Not set up", "Needs attention"):
        items.append(("month1", "Configurare Enhanced Conversions per migliorare match rate"))

    meta = deep_wizard_block.get("meta_data", {})
    if meta.get("capi_status") == "pixel_only":
        items.append(("month1", "Implementare Meta CAPI per migliorare Event Match Quality"))

    gsc = deep_wizard_block.get("gsc_data", {})
    sitemap_check = gsc.get("sitemap_cross_check", {})
    if sitemap_check.get("is_critical"):
        items.append(("urgent", "Risolvere mismatch sitemap tra robots.txt e GSC"))

    if not items:
        return '<p>Nessun problema critico identificato nei dati wizard.</p>'

    phase_labels = {"urgent": "Settimana 1-2 (Quick Wins)", "month1": "Settimana 3-4", "month2": "Mese 2", "month3": "Mese 3+"}
    parts = []
    for phase in ("urgent", "month1", "month2", "month3"):
        phase_items = [item for p, item in items if p == phase]
        if phase_items:
            parts.append(f'<div class="roadmap-phase"><div class="roadmap-phase-title">{phase_labels[phase]}</div>')
            for item in phase_items:
                css = phase
                parts.append(f'<div class="roadmap-item"><span class="roadmap-priority {css}">{phase.upper()}</span><span>{_esc(item)}</span></div>')
            parts.append('</div>')

    return "\n".join(parts)


def _build_appendix_fallback(l2_results):
    """Build technical appendix from L2 results when Opus doesn't provide one (Fix 19)."""
    if not l2_results:
        return '<p>Dati L2 non disponibili per l\'appendice tecnica.</p>'

    parts = []
    # Group L2 results by technical relevance
    tech_types = ["performance", "cwv", "security", "accessibility", "robots", "sitemap", "datalayer"]
    for atype in tech_types:
        result = l2_results.get(atype)
        if not result or (isinstance(result, str) and result.startswith("Errore:")):
            continue
        label = L2_LABELS.get(atype, atype.title())
        parts.append(f'<div class="fix-block">')
        parts.append(f'<h4>{_esc(label)}</h4>')
        if isinstance(result, str):
            parts.append(_md_to_html(result[:5000]))
        elif isinstance(result, dict):
            text = result.get("text", result.get("analysis", ""))
            if text:
                parts.append(_md_to_html(text[:5000]))
            else:
                parts.append(f'<pre style="font-size:12px">{_esc(json.dumps(result, ensure_ascii=False, indent=2)[:3000])}</pre>')
        parts.append('</div>')

    return "\n".join(parts) if parts else '<p>Nessun dato tecnico L2 disponibile.</p>'


# ─── PUBLIC API ─────────────────────────────────────────────────────────────

def generate_deep_report(synthesis_output, deep_wizard_block, trust_result,
                         l2_results=None, cost_l2="N/A"):
    """Generate McKinsey-style HTML report for Deep mode (ADR-4).

    Args:
        synthesis_output: dict from synthesis.run_synthesis()
        deep_wizard_block: accumulated wizard data (ADR-1)
        trust_result: dict from trust_score.calculate_trust_score()
        l2_results: optional dict of L2 analysis results
        cost_l2: optional string with L2 cost info

    Returns:
        str: path to saved report file
    """
    # Load template (ADR-4)
    try:
        with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
            report = f.read()
    except FileNotFoundError:
        print(f"  ⚠ Template non trovato: {TEMPLATE_PATH}")
        return _generate_fallback_report(synthesis_output, deep_wizard_block, trust_result)

    # Extract data
    bp = deep_wizard_block.get("business_profile", {})
    domain = bp.get("url", "").replace("https://", "").replace("http://", "").rstrip("/")
    client_name = bp.get("client_name", domain)
    business_type = bp.get("business_type", "N/A")
    platforms = bp.get("platforms", [])
    date_str = _italian_date()

    # Trust Score
    score = trust_result.get("score", 0)
    grade = trust_result.get("grade", "N/A")
    grade_color = GRADE_COLORS.get(grade, "#999")
    coverage_label = trust_result.get("coverage_label", "0/5")
    coverage_pct = round(trust_result.get("coverage", 0) * 100)
    pillars = trust_result.get("pillars", {})

    # Parse synthesis sections — ADR-6: prefer section_results when available
    section_results = synthesis_output.get("section_results", {})
    if section_results:
        # Sectional synthesis (ADR-6): direct access to per-section output
        def _get_section_text(sid):
            r = section_results.get(sid, {})
            return r.get("text", "") if r.get("success") else ""

        exec_summary = _get_section_text("exec_summary")
        filo = ""  # filo is embedded in exec_summary section
        gap_narrative = _get_section_text("gap_roadmap")
        roadmap_text = gap_narrative  # gap + roadmap are in the same section
        appendix_text = _get_section_text("technical_appendix")

        # Build platform text from individual platform sections
        platform_parts = []
        for sid in ("platform_consent", "platform_gtm", "platform_gads", "platform_meta", "platform_seo"):
            t = _get_section_text(sid)
            if t:
                platform_parts.append(t)
        platform_analysis_text = "\n\n".join(platform_parts)

        # Trust analysis goes into exec summary if present
        trust_text = _get_section_text("trust_analysis")
        if trust_text:
            exec_summary = exec_summary + "\n\n" + trust_text if exec_summary else trust_text
    else:
        # Legacy monolithic synthesis: parse by ## headers
        synthesis_text = synthesis_output.get("synthesis_text", "")
        sections = _extract_synthesis_sections(synthesis_text)

        exec_summary = _find_section(sections, "EXECUTIVE", "SUMMARY")
        filo = _find_section(sections, "FILO", "CONDUTTORE")
        platform_analysis_text = _find_section(sections, "PIATTAFORMA", "PLATFORM")
        roadmap_text = _find_section(sections, "ROADMAP", "PRIORITY")
        appendix_text = _find_section(sections, "APPENDICE", "TECNICA", "APPENDIX")
        gap_narrative = _find_section(sections, "GAP", "REVENUE")

    # Build components
    radar_svg = _build_radar_svg(pillars)
    pillar_cards = _build_pillar_cards(pillars)
    chain_html = _build_chain_html(deep_wizard_block.get("consent_impact_chain"))
    gap_table = _build_gap_table(deep_wizard_block.get("gap_to_revenue"))

    # Cost info
    cost_l3 = f"${synthesis_output.get('cost_usd', 0):.4f}" if synthesis_output.get("success") else "N/A"
    synthesis_model = synthesis_output.get("model", "N/A")

    # If synthesis failed, show data-only sections
    if not synthesis_output.get("success"):
        exec_summary = (
            f"<p><strong>Nota:</strong> La sintesi narrativa Opus non &egrave; disponibile "
            f"({_esc(synthesis_output.get('error', 'errore sconosciuto'))}). "
            f"Il report contiene i dati strutturati raccolti durante l'audit.</p>"
            f"<p>Trust Score: <strong>{score}/100 ({grade})</strong> — {_esc(coverage_label)}</p>"
        )

    # Build platform analysis: Opus synthesis + wizard data fallback + L2 (Fix 17, 19, 21)
    platform_html = ""
    if platform_analysis_text:
        platform_html = _md_to_html(platform_analysis_text)
    # Always add wizard data + L2 per-platform sections (Fix 21: merge Quick+Deep)
    platform_fallback = _build_platform_fallback(deep_wizard_block, l2_results)
    if platform_fallback:
        platform_html += "\n" + platform_fallback

    # Build roadmap: Opus or fallback from wizard data (Fix 19)
    roadmap_html = _md_to_html(roadmap_text) if roadmap_text else _build_roadmap_fallback(deep_wizard_block)

    # Build appendix: Opus synthesis + L2 results (Fix 17, 19)
    appendix_html = ""
    if appendix_text:
        appendix_html = _md_to_html(appendix_text)
    # Always append full L2 results (Fix 17)
    l2_html = _build_l2_section_html(l2_results)
    if l2_html:
        appendix_html += "\n<h3>Analisi L2 Complete</h3>\n" + l2_html
    if not appendix_html:
        appendix_html = _build_appendix_fallback(l2_results)

    # Build executive summary fallback (Fix 19)
    exec_html = _md_to_html(exec_summary) if exec_summary else (
        f"<p>Trust Score: <strong>{score}/100 ({grade})</strong> — {_esc(coverage_label)}</p>"
        f"<p>Piattaforme auditate: {_esc(', '.join(platforms))}</p>"
    )

    # Populate template (ADR-4: str.replace)
    replacements = {
        "{{client_name}}": _esc(client_name),
        "{{domain}}": _esc(domain),
        "{{date}}": _esc(date_str),
        "{{business_type}}": _esc(business_type),
        "{{trust_score_value}}": str(score),
        "{{trust_grade}}": _esc(grade),
        "{{trust_grade_color}}": grade_color,
        "{{trust_coverage_label}}": _esc(coverage_label),
        "{{trust_coverage_pct}}": str(coverage_pct),
        "{{trust_radar_svg}}": radar_svg,
        "{{pillar_cards_html}}": pillar_cards,
        "{{executive_summary}}": exec_html,
        "{{consent_impact_chain}}": chain_html,
        "{{filo_conduttore_narrative}}": _md_to_html(filo) if filo else "",
        "{{gap_to_revenue_table}}": gap_table + (_md_to_html(gap_narrative) if gap_narrative else ""),
        "{{priority_roadmap}}": roadmap_html,
        "{{platform_analysis}}": platform_html if platform_html else '<p>Nessuna piattaforma auditata.</p>',
        "{{technical_appendix}}": appendix_html if appendix_html else '<p>Nessun dato tecnico disponibile.</p>',
        "{{cost_l2}}": _esc(str(cost_l2)),
        "{{cost_l3}}": _esc(cost_l3),
        "{{platforms_list}}": _esc(", ".join(platforms)) if platforms else "N/A",
        "{{synthesis_model}}": _esc(synthesis_model),
        "{{evidence_screenshots}}": _build_evidence_html(deep_wizard_block),
    }

    for placeholder, value in replacements.items():
        report = report.replace(placeholder, value)

    # Save report (NFR10: local output/ only)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_domain = re.sub(r"[^a-zA-Z0-9.-]", "_", domain)
    output_path = os.path.join(OUTPUT_DIR, f"report_deep_{safe_domain}_{timestamp}.html")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"  💾 Report salvato: {output_path}")
    print(f"  📄 Dimensione: {len(report) // 1024} KB")

    return output_path


def _generate_fallback_report(synthesis_output, deep_wizard_block, trust_result):
    """Generate minimal report when template is missing."""
    bp = deep_wizard_block.get("business_profile", {})
    domain = bp.get("url", "unknown")
    score = trust_result.get("score", 0)
    grade = trust_result.get("grade", "N/A")

    report = f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="UTF-8"><title>Deep Audit — {_esc(domain)}</title></head>
<body style="font-family:sans-serif;max-width:800px;margin:40px auto;padding:20px">
<h1>Deep MarTech Audit — {_esc(domain)}</h1>
<p>Trust Score: <strong>{score}/100 ({grade})</strong></p>
<p>Template report_deep.html non trovato. Questo è un report di emergenza.</p>
<pre>{_esc(synthesis_output.get('synthesis_text', 'Sintesi non disponibile'))}</pre>
</body></html>"""

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(OUTPUT_DIR, f"report_deep_fallback_{timestamp}.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  💾 Report fallback salvato: {output_path}")
    return output_path
