"""Wizard GSC — Data foundation audit.

Collects sitemap status, indexing data, and parses CSV exports for
trend analysis and opportunity detection.
FRs: FR33, FR34, FR35, FR36, FR37, FR38, FR39.
NFRs: NFR2, NFR14, NFR15, NFR18.
"""

import csv
import io
import time

from deep.input_helpers import _ask_input, _ask_select, _ask_file_path


# ─── CONSTANTS ──────────────────────────────────────────────────────────────

PLATFORM_NAME = "GSC — Data Foundation"

SITEMAP_OPTIONS = ["OK", "Errori", "Non inviata"]
SITEMAP_MAP = {"OK": "ok", "Errori": "errors", "Non inviata": "not_submitted"}

NON_INDEXING_REASONS = [
    "Crawled - currently not indexed",
    "Discovered - currently not crawled",
    "Noindex tag",
    "Redirect",
    "Soft 404",
    "URL bloccato da robots.txt",
    "Server error (5xx)",
    "Altro",
]

# Known GSC CSV header variants by interface language (NFR15)
PERFORMANCE_HEADERS_MAP = {
    "en": {"query": "Top queries", "page": "Top pages", "clicks": "Clicks",
           "impressions": "Impressions", "ctr": "CTR", "position": "Position"},
    "it": {"query": "Query principali", "page": "Pagine principali", "clicks": "Clic",
           "impressions": "Impressioni", "ctr": "CTR", "position": "Posizione"},
    "es": {"query": "Consultas principales", "page": "Páginas principales", "clicks": "Clics",
           "impressions": "Impresiones", "ctr": "CTR", "position": "Posición"},
    "de": {"query": "Top-Suchanfragen", "page": "Top-Seiten", "clicks": "Klicks",
           "impressions": "Impressionen", "ctr": "CTR", "position": "Position"},
    "fr": {"query": "Requêtes les plus fréquentes", "page": "Pages les plus populaires",
           "clicks": "Clics", "impressions": "Impressions", "ctr": "CTR", "position": "Position"},
}

# Normalized column names we map everything to
NORM_CLICKS = "clicks"
NORM_IMPRESSIONS = "impressions"
NORM_CTR = "ctr"
NORM_POSITION = "position"
NORM_PAGE = "page"
NORM_QUERY = "query"


# ─── VALIDATION ────────────────────────────────────────────────────────────

def _validate_pages_count(raw):
    try:
        val = int(raw)
        if val < 0:
            return False, "Il numero di pagine non può essere negativo"
        return True, ""
    except ValueError:
        return False, "Inserisci un numero intero valido"


def _validate_csv_content(content):
    """Validate that content looks like a CSV with at least a header row."""
    lines = content.strip().split("\n")
    if len(lines) < 2:
        return False, "Il file CSV deve contenere almeno un header e una riga di dati"
    # Check it has comma or tab separators
    header = lines[0]
    if "," not in header and "\t" not in header:
        return False, "Formato CSV non riconosciuto — atteso separatore virgola o tab"
    return True, ""


# ─── CSV PARSING (FR35, FR36, FR37, FR39, NFR2, NFR14, NFR15) ─────────────

def _detect_delimiter(header_line):
    """Detect CSV delimiter (tab or comma)."""
    if "\t" in header_line:
        return "\t"
    return ","


def _normalize_headers(headers):
    """Map localized GSC headers to normalized English keys (NFR15).

    Returns dict mapping column index -> normalized name.
    """
    mapping = {}
    headers_lower = [h.strip().lower() for h in headers]

    for lang, lang_map in PERFORMANCE_HEADERS_MAP.items():
        for norm_key, localized in lang_map.items():
            localized_lower = localized.lower()
            for i, h in enumerate(headers_lower):
                if localized_lower in h or h in localized_lower:
                    mapping[i] = norm_key

    # Fallback: try common patterns
    for i, h in enumerate(headers_lower):
        if i in mapping:
            continue
        if "click" in h or "clic" in h:
            mapping[i] = NORM_CLICKS
        elif "impression" in h:
            mapping[i] = NORM_IMPRESSIONS
        elif "ctr" in h:
            mapping[i] = NORM_CTR
        elif "position" in h or "posizione" in h or "posición" in h:
            mapping[i] = NORM_POSITION
        elif "page" in h or "pagin" in h or "url" in h or "seite" in h:
            mapping[i] = NORM_PAGE
        elif "query" in h or "such" in h or "requête" in h or "consulta" in h:
            mapping[i] = NORM_QUERY

    return mapping


def _parse_numeric(val):
    """Parse a numeric value from CSV, handling locale formats."""
    val = val.strip().replace("\xa0", "").replace(" ", "")
    if not val or val == "--":
        return 0.0
    # Handle percentage
    if val.endswith("%"):
        val = val[:-1]
    # Handle comma as decimal separator
    if "," in val and "." in val:
        val = val.replace(".", "").replace(",", ".")
    elif "," in val:
        val = val.replace(",", ".")
    try:
        return float(val)
    except ValueError:
        return 0.0


def parse_gsc_csv(content):
    """Parse a GSC CSV export into normalized rows.

    Handles encoding variations (already handled by _ask_file_path),
    delimiter detection, and header normalization.

    Returns:
        list of dicts with normalized keys, or [] on failure.
    """
    lines = content.strip().split("\n")
    if len(lines) < 2:
        return []

    delimiter = _detect_delimiter(lines[0])
    reader = csv.reader(io.StringIO(content), delimiter=delimiter)

    try:
        headers = next(reader)
    except StopIteration:
        return []

    col_map = _normalize_headers(headers)
    if not col_map:
        return []

    rows = []
    for row in reader:
        normalized = {}
        for i, val in enumerate(row):
            key = col_map.get(i)
            if key:
                if key in (NORM_CLICKS, NORM_IMPRESSIONS, NORM_CTR, NORM_POSITION):
                    normalized[key] = _parse_numeric(val)
                else:
                    normalized[key] = val.strip()
        if normalized:
            rows.append(normalized)

    return rows


# ─── TREND ANALYSIS (FR37) ────────────────────────────────────────────────

def analyze_trends(rows):
    """Identify pages/queries in growth and decline (FR37).

    Works with a single export period — ranks by clicks and flags
    top/bottom performers. For full trend analysis, two periods
    would be compared; this implementation works with available data.

    Returns:
        dict with top_pages, low_ctr_pages, high_impression_low_click
    """
    if not rows:
        return {"top_pages": [], "declining_pages": [], "opportunities": []}

    # Sort by clicks descending
    sorted_by_clicks = sorted(rows, key=lambda r: r.get(NORM_CLICKS, 0), reverse=True)
    top_pages = sorted_by_clicks[:10]

    # Pages with high impressions but low CTR (FR38)
    opportunities = []
    for row in rows:
        impressions = row.get(NORM_IMPRESSIONS, 0)
        ctr = row.get(NORM_CTR, 0)
        position = row.get(NORM_POSITION, 0)

        # High impressions + low CTR (FR38)
        if impressions > 100 and ctr < 3.0:
            opportunities.append({
                "page": row.get(NORM_PAGE, row.get(NORM_QUERY, "N/D")),
                "impressions": impressions,
                "ctr": ctr,
                "position": position,
                "type": "high_impressions_low_ctr",
                "detail": f"Impressioni: {impressions:.0f}, CTR: {ctr:.1f}%, Pos: {position:.1f}",
            })

        # Position 5-15 = striking distance (FR38)
        if 5 <= position <= 15 and impressions > 50:
            already = any(o["page"] == row.get(NORM_PAGE, row.get(NORM_QUERY, ""))
                         and o["type"] == "striking_distance" for o in opportunities)
            if not already:
                opportunities.append({
                    "page": row.get(NORM_PAGE, row.get(NORM_QUERY, "N/D")),
                    "impressions": impressions,
                    "ctr": ctr,
                    "position": position,
                    "type": "striking_distance",
                    "detail": f"Posizione {position:.1f} — vicino alla prima pagina. "
                              f"Impressioni: {impressions:.0f}",
                })

    # Sort opportunities by impressions descending
    opportunities.sort(key=lambda x: x["impressions"], reverse=True)

    return {
        "top_pages": [{"page": r.get(NORM_PAGE, r.get(NORM_QUERY, "N/D")),
                        "clicks": r.get(NORM_CLICKS, 0),
                        "impressions": r.get(NORM_IMPRESSIONS, 0)}
                       for r in top_pages],
        "declining_pages": [],  # Requires two-period comparison
        "opportunities": opportunities[:20],  # Cap at 20
    }


# ─── RESULTS DISPLAY ───────────────────────────────────────────────────────

def _show_results(data):
    """Display immediate wizard results to console."""
    sitemap = data.get("sitemap_status", "")
    indexed = data.get("pages_indexed", 0)
    submitted = data.get("pages_submitted", 0)
    issues = data.get("indexing_issues", [])
    trends = data.get("trend_analysis", {})
    opportunities = trends.get("opportunities", [])
    perf_rows = data.get("_performance_row_count", 0)
    pages_rows = data.get("_pages_row_count", 0)

    index_pct = (indexed / submitted * 100) if submitted > 0 else 0

    print(f"\n  {'─'*46}")
    print(f"  📊 Risultati Wizard GSC")
    print(f"  {'─'*46}")
    print(f"     Sitemap:          {sitemap}")
    print(f"     Pagine:           {indexed}/{submitted} indicizzate ({index_pct:.0f}%)")

    if issues:
        print(f"     Motivi non-index: {len(issues)}")
        for issue in issues[:5]:
            print(f"       🔸 {issue}")

    if perf_rows or pages_rows:
        print(f"     CSV rendimento:   {perf_rows} righe analizzate")
        print(f"     CSV pagine:       {pages_rows} righe analizzate")

    top = trends.get("top_pages", [])
    if top:
        print(f"\n  🏆 Top {min(5, len(top))} pagine per click:")
        for p in top[:5]:
            print(f"     {p['clicks']:.0f} click — {p['page'][:60]}")

    if opportunities:
        print(f"\n  💡 Opportunità nascoste ({len(opportunities)}):")
        for opp in opportunities[:5]:
            print(f"     🔸 {opp['detail']} — {opp['page'][:50]}")
        if len(opportunities) > 5:
            print(f"     ... e altre {len(opportunities) - 5}")

    print(f"  {'─'*46}")


# ─── MAIN WIZARD ───────────────────────────────────────────────────────────

def run_wizard_gsc(business_profile, discovery_block):
    """Run the GSC wizard. Returns gsc_data dict.

    Args:
        business_profile: Step Zero output (business_type, platforms, url)
        discovery_block: L0 auto_discover() output

    Returns:
        dict with sitemap_status, pages_indexed, pages_submitted,
        indexing_issues, trend_analysis, opportunities.
        Returns {} if skipped or on error.
    """
    print(f"\n{'='*50}")
    print(f"  🔍 Wizard {PLATFORM_NAME}")
    print(f"{'='*50}\n")

    try:
        # ── 1. Sitemap status (FR33) ──
        sitemap_label = _ask_select(
            "Stato della sitemap:",
            SITEMAP_OPTIONS,
            help_text="Vai su GSC > Sitemap. Verifica lo stato dell'ultima sitemap inviata"
        )
        sitemap_status = SITEMAP_MAP.get(sitemap_label, "ok")

        # ── 2. Indexing data (FR34) ──
        pages_indexed = _ask_input(
            "Numero di pagine indicizzate",
            validation_fn=_validate_pages_count,
            help_text="Vai su GSC > Pagine. Numero totale pagine con stato 'Indicizzata'",
            coerce_fn=int
        )

        pages_submitted = _ask_input(
            "Numero totale di pagine (indicizzate + non indicizzate)",
            validation_fn=_validate_pages_count,
            help_text="Somma pagine indicizzate + non indicizzate nella sezione Pagine",
            coerce_fn=int
        )

        # Non-indexing reasons
        indexing_issues = _ask_select(
            "Motivi principali di non indicizzazione (seleziona tutti quelli presenti):",
            NON_INDEXING_REASONS,
            allow_multiple=True,
            help_text="Nella sezione 'Perché le pagine non sono indicizzate'"
        )

        # ── 3. CSV rendimento upload (FR35, FR39) ──
        perf_rows = []
        perf_path, perf_content = _ask_file_path(
            "Percorso CSV export rendimento GSC (ultimi 3 mesi)",
            validation_fn=_validate_csv_content,
            help_text="Vai su GSC > Rendimento > Esporta > CSV. Seleziona ultimi 3 mesi"
        )

        if perf_content:
            start = time.time()
            perf_rows = parse_gsc_csv(perf_content)
            parse_time = time.time() - start
            print(f"  ✓ CSV rendimento parsato in {parse_time:.2f}s — {len(perf_rows)} righe")

        # ── 4. CSV pagine upload (FR36) ──
        pages_csv_rows = []
        pages_path, pages_content = _ask_file_path(
            "Percorso CSV export pagine GSC",
            validation_fn=_validate_csv_content,
            help_text="Vai su GSC > Pagine > Esporta > CSV"
        )

        if pages_content:
            start = time.time()
            pages_csv_rows = parse_gsc_csv(pages_content)
            parse_time = time.time() - start
            print(f"  ✓ CSV pagine parsato in {parse_time:.2f}s — {len(pages_csv_rows)} righe")

        # ── 5. Trend analysis + opportunities (FR37, FR38) ──
        all_rows = perf_rows + pages_csv_rows
        trends = analyze_trends(all_rows)

        data = {
            "sitemap_status": sitemap_status,
            "pages_indexed": pages_indexed,
            "pages_submitted": pages_submitted,
            "indexing_issues": indexing_issues,
            "trend_analysis": trends,
            "opportunities": trends.get("opportunities", []),
            "_performance_row_count": len(perf_rows),
            "_pages_row_count": len(pages_csv_rows),
        }

        _show_results(data)
        return data

    except Exception as e:
        print(f"  ⚠ Errore nel wizard GSC: {e}")
        return {}
