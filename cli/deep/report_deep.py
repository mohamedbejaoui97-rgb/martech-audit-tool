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

    # Parse synthesis sections
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
        "{{executive_summary}}": _md_to_html(exec_summary) if exec_summary else '<p style="color:#999">Non disponibile</p>',
        "{{consent_impact_chain}}": chain_html,
        "{{filo_conduttore_narrative}}": _md_to_html(filo) if filo else "",
        "{{gap_to_revenue_table}}": gap_table + (_md_to_html(gap_narrative) if gap_narrative else ""),
        "{{priority_roadmap}}": _md_to_html(roadmap_text) if roadmap_text else '<p style="color:#999">Non disponibile</p>',
        "{{platform_analysis}}": _md_to_html(platform_analysis_text) if platform_analysis_text else '<p style="color:#999">Non disponibile</p>',
        "{{technical_appendix}}": _md_to_html(appendix_text) if appendix_text else '<p style="color:#999">Non disponibile</p>',
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
