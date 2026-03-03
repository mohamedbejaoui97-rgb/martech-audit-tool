"""Wizard GSC — Data foundation audit.

Collects sitemap status, indexing data, and parses CSV exports for
trend analysis and opportunity detection.
FRs: FR33, FR34, FR35, FR36, FR37, FR38, FR39.
NFRs: NFR2, NFR14, NFR15, NFR18.
"""

import csv
import io
import re
import time
import urllib.request
import urllib.error
import ssl

from deep.input_helpers import _ask_input, _ask_select, _ask_file_path, _ask_folder_path, _ask_operator_notes, _ask_evidence_screenshots, _ask_multiline


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


# ─── COVERAGE CSV PARSING (Fix 15) ─────────────────────────────────────────

COVERAGE_FILE_PATTERNS = {
    "problemi critici": "critical_issues",
    "problemi non critici": "non_critical_issues",
    "metadati": "metadata",
    "grafico": "chart",
    "critical": "critical_issues",
    "non-critical": "non_critical_issues",
    "not indexed": "not_indexed",
}


def parse_coverage_csv(filename, content):
    """Parse a GSC Coverage/Indexing CSV export.

    Returns dict with parsed data (rows or key-value pairs).
    """
    lines = content.strip().split("\n")
    if len(lines) < 2:
        return {"rows": [], "filename": filename}

    delimiter = _detect_delimiter(lines[0])
    reader = csv.reader(io.StringIO(content), delimiter=delimiter)

    try:
        headers = next(reader)
    except StopIteration:
        return {"rows": [], "filename": filename}

    rows = []
    for row in reader:
        if row:
            row_dict = {}
            for i, val in enumerate(row):
                key = headers[i].strip() if i < len(headers) else f"col_{i}"
                row_dict[key] = val.strip()
            rows.append(row_dict)

    return {"rows": rows, "headers": [h.strip() for h in headers], "filename": filename, "row_count": len(rows)}


SITEMAP_GSC_STATUS_OPTIONS = [
    "Operazione riuscita",
    "Impossibile recuperare",
    "Ha problemi",
    "Non letta",
]


# ─── ROBOTS.TXT ANALYSIS (Change 11) ────────────────────────────────────

def fetch_robots_txt(url):
    """Fetch and parse robots.txt from the target URL.

    Returns:
        dict with raw_content, sitemap_urls, disallow_rules, user_agents, fetch_error
    """
    domain = url.replace("https://", "").replace("http://", "").rstrip("/")
    robots_url = f"https://{domain}/robots.txt"

    result = {
        "raw_content": "",
        "sitemap_urls": [],
        "disallow_rules": [],
        "user_agents": [],
        "fetch_error": None,
    }

    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(robots_url, headers={"User-Agent": "MarTech-Audit/1.0"})
        resp = urllib.request.urlopen(req, timeout=15, context=ctx)
        content = resp.read().decode("utf-8", errors="replace")
        result["raw_content"] = content

        current_agent = "*"
        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            lower = line.lower()
            if lower.startswith("sitemap:"):
                sitemap_url = line.split(":", 1)[1].strip()
                # Handle "Sitemap: http..." where split on : takes only the scheme
                if sitemap_url.startswith("//") or not sitemap_url.startswith("http"):
                    sitemap_url = line[len("sitemap:"):].strip()
                    if ":" in line[8:]:
                        sitemap_url = line[8:].strip()
                result["sitemap_urls"].append(sitemap_url)
            elif lower.startswith("user-agent:"):
                current_agent = line.split(":", 1)[1].strip()
                if current_agent not in result["user_agents"]:
                    result["user_agents"].append(current_agent)
            elif lower.startswith("disallow:"):
                path = line.split(":", 1)[1].strip()
                if path:
                    result["disallow_rules"].append({
                        "user_agent": current_agent,
                        "path": path,
                    })

    except Exception as e:
        result["fetch_error"] = str(e)

    return result


def _check_sitemap_consistency(robots_sitemaps, gsc_sitemaps, gsc_statuses, domain):
    """Cross-check sitemap URLs and www consistency (Change 9).

    Returns:
        dict with mismatches list, www_consistent bool, critical flag
    """
    result = {
        "mismatches": [],
        "www_consistent": True,
        "is_critical": False,
    }

    # Normalize URLs for comparison
    def normalize(url):
        return url.strip().rstrip("/").lower()

    robots_norm = {normalize(u) for u in robots_sitemaps}
    gsc_norm = {normalize(u) for u in gsc_sitemaps if u.strip()}

    # Check robots vs GSC URL mismatch
    if robots_norm and gsc_norm and robots_norm != gsc_norm:
        only_robots = robots_norm - gsc_norm
        only_gsc = gsc_norm - robots_norm
        if only_robots:
            result["mismatches"].append(f"Sitemap in robots.txt ma non in GSC: {', '.join(only_robots)}")
        if only_gsc:
            result["mismatches"].append(f"Sitemap in GSC ma non in robots.txt: {', '.join(only_gsc)}")
        result["is_critical"] = True

    # Check GSC status
    bad_statuses = [s for s in gsc_statuses if s != "Operazione riuscita"]
    if bad_statuses:
        result["mismatches"].append(f"Sitemap con problemi in GSC: {', '.join(bad_statuses)}")
        result["is_critical"] = True

    # www vs non-www consistency
    all_urls = list(robots_norm | gsc_norm)
    has_www = any("://www." in u or u.startswith("www.") for u in all_urls)
    has_non_www = any("://" in u and "://www." not in u for u in all_urls)
    if has_www and has_non_www:
        result["www_consistent"] = False
        result["mismatches"].append("Mix www e non-www nelle URL sitemap — possibili problemi di canonicalizzazione")
        result["is_critical"] = True

    return result


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

    # Sitemap cross-check results
    sitemap_check = data.get("sitemap_cross_check", {})
    if sitemap_check.get("is_critical"):
        print(f"\n  ⛔ CRITICO: sitemap mismatch o irraggiungibile")
        for m in sitemap_check.get("mismatches", []):
            print(f"     🔸 {m}")
    elif sitemap_check:
        print(f"\n  ✅ Sitemap consistente tra robots.txt e GSC")

    # Robots.txt info
    robots = data.get("robots_txt", {})
    if robots and not robots.get("fetch_error"):
        print(f"\n  🤖 Robots.txt:")
        print(f"     Sitemap dichiarate: {len(robots.get('sitemap_urls', []))}")
        print(f"     Regole Disallow: {len(robots.get('disallow_rules', []))}")
        print(f"     User-agent: {', '.join(robots.get('user_agents', [])[:5])}")
    elif robots and robots.get("fetch_error"):
        print(f"\n  ⚠ Robots.txt non raggiungibile: {robots['fetch_error']}")

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

        # ── 2b. Sitemap cross-check (Change 9) ──
        domain = business_profile.get("url", "").replace("https://", "").replace("http://", "").rstrip("/")

        # Fetch robots.txt proactively (Change 11)
        print("\n  🤖 Analisi robots.txt in corso...")
        robots_data = fetch_robots_txt(business_profile.get("url", f"https://{domain}"))
        if robots_data.get("fetch_error"):
            print(f"  ⚠ robots.txt non raggiungibile: {robots_data['fetch_error']}")
        else:
            print(f"  ✓ robots.txt: {len(robots_data['sitemap_urls'])} sitemap, "
                  f"{len(robots_data['disallow_rules'])} regole Disallow")

        # Robots sitemap URL (auto-detected)
        robots_sitemap_display = ", ".join(robots_data.get("sitemap_urls", [])) or "Non trovata"
        print(f"\n  ℹ Sitemap nel robots.txt: {robots_sitemap_display}")

        robots_sitemap_url = _ask_input(
            "URL sitemap dichiarata nel robots.txt (conferma o correggi)",
            allow_empty=True,
            help_text=f"Auto-rilevato: {robots_sitemap_display}. Premi Invio per confermare."
        )
        if not robots_sitemap_url:
            robots_sitemap_urls = robots_data.get("sitemap_urls", [])
        else:
            robots_sitemap_urls = [u.strip() for u in robots_sitemap_url.split("\n") if u.strip()]

        # GSC sitemap URLs
        gsc_sitemap_raw = _ask_input(
            "URL sitemap pushate in GSC (una per riga, separate da virgola)",
            allow_empty=True,
            help_text="Vai su GSC > Sitemap. Elenca le URL inviate."
        )
        gsc_sitemap_urls = [u.strip() for u in gsc_sitemap_raw.replace("\n", ",").split(",") if u.strip()] if gsc_sitemap_raw else []

        # GSC sitemap status
        gsc_sitemap_statuses = _ask_select(
            "Stato sitemap in GSC (seleziona tutti quelli applicabili):",
            SITEMAP_GSC_STATUS_OPTIONS,
            allow_multiple=True,
            help_text="Per ogni sitemap inviata, qual è lo stato?"
        )

        # Last read date
        gsc_last_read = _ask_input(
            "Data ultima lettura GSC (es. 23/10/2025)",
            allow_empty=True,
            help_text="Visibile nella colonna 'Ultima lettura' della sezione Sitemap"
        )

        # Cross-check
        sitemap_check = _check_sitemap_consistency(
            robots_sitemap_urls, gsc_sitemap_urls, gsc_sitemap_statuses, domain
        )

        if sitemap_check.get("is_critical"):
            print("  ⛔ CRITICO: sitemap mismatch o irraggiungibile")
            for m in sitemap_check.get("mismatches", []):
                print(f"     🔸 {m}")

        # ── 3. CSV Rendimento — folder input (Fix 14) ──
        perf_rows = []
        pages_csv_rows = []
        perf_folder, perf_csvs = _ask_folder_path(
            "Cartella export Rendimento GSC (trascina la cartella)",
            help_text="Vai su GSC > Rendimento > Esporta > Scarica CSV. "
                      "Trascina qui la CARTELLA scaricata (contiene Query.csv, Pagine.csv, etc.)"
        )

        if perf_csvs:
            start = time.time()
            for fname, content in perf_csvs.items():
                rows = parse_gsc_csv(content)
                fname_lower = fname.lower()
                if any(k in fname_lower for k in ("pagin", "page", "url")):
                    pages_csv_rows.extend(rows)
                    print(f"  ✓ {fname}: {len(rows)} righe (pagine)")
                else:
                    perf_rows.extend(rows)
                    print(f"  ✓ {fname}: {len(rows)} righe (rendimento)")
            parse_time = time.time() - start
            print(f"  ✓ Totale parsato in {parse_time:.2f}s — "
                  f"{len(perf_rows)} righe rendimento, {len(pages_csv_rows)} righe pagine")

        # ── 4. CSV Indicizzazione/Coverage — folder input (Fix 15) ──
        coverage_data = []
        cov_folder, cov_csvs = _ask_folder_path(
            "Cartella export Indicizzazione/Coverage GSC (opzionale)",
            help_text="Vai su GSC > Pagine > Esporta > Scarica CSV. "
                      "Contiene: Problemi critici.csv, Problemi non critici.csv, etc."
        )

        if cov_csvs:
            for fname, content in cov_csvs.items():
                parsed = parse_coverage_csv(fname, content)
                coverage_data.append(parsed)
                print(f"  ✓ Coverage: {fname} — {parsed.get('row_count', 0)} righe")

        # ── 5. Trend analysis + opportunities (FR37, FR38) ──
        all_rows = perf_rows + pages_csv_rows
        trends = analyze_trends(all_rows)

        # ── Anomalies + Operator notes ──
        anomalies = _ask_multiline("Anomalie rilevate")

        notes = _ask_operator_notes()

        screenshots = _ask_evidence_screenshots("gsc")

        # ADR-7: Build CSV data blocks with rows + metadata
        csv_performance = {}
        if perf_rows:
            # ADR-7d: extract date range from rows (if Date column exists) or ask
            date_vals = sorted(set(r.get("date", "") for r in perf_rows if r.get("date")))
            if date_vals:
                csv_date_range = f"{date_vals[0]} — {date_vals[-1]}"
            else:
                csv_date_range = _ask_input(
                    "Periodo dell'export CSV rendimento (es: 2025-12-01 — 2026-02-28)",
                    allow_empty=True,
                    help_text="Se non sai, premi Invio. Utile per contestualizzare i dati."
                ) or "non specificato"
            total_clicks = sum(r.get("clicks", 0) for r in perf_rows)
            total_impressions = sum(r.get("impressions", 0) for r in perf_rows)
            csv_performance = {
                "date_range": csv_date_range,
                "total_rows": len(perf_rows),
                "rows": perf_rows[:200],
                "summary": {
                    "total_clicks": total_clicks,
                    "total_impressions": total_impressions,
                    "avg_ctr": round(total_clicks / total_impressions * 100, 2) if total_impressions else 0,
                    "avg_position": round(sum(r.get("position", 0) for r in perf_rows) / len(perf_rows), 1) if perf_rows else 0,
                },
            }

        csv_pages = {}
        if pages_csv_rows:
            csv_pages = {
                "total_rows": len(pages_csv_rows),
                "rows": pages_csv_rows[:100],
            }

        data = {
            "sitemap_status": sitemap_status,
            "gsc_pages_indexed": pages_indexed,
            "gsc_pages_total_in_property": pages_submitted,
            "indexing_issues": indexing_issues,
            "trend_analysis": trends,
            "opportunities": trends.get("opportunities", []),
            "csv_performance": csv_performance,
            "csv_pages": csv_pages,
            "csv_coverage": coverage_data,
            "robots_txt": robots_data,
            "sitemap_cross_check": sitemap_check,
            "gsc_sitemap_urls": gsc_sitemap_urls,
            "gsc_sitemap_statuses": gsc_sitemap_statuses,
            "gsc_last_read": gsc_last_read,
        }
        if anomalies:
            data["anomalies_detected"] = anomalies
        if notes:
            data["operator_notes"] = notes
        if screenshots:
            data["evidence_screenshots"] = screenshots

        _show_results(data)
        return data

    except Exception as e:
        print(f"  ⚠ Errore nel wizard GSC: {e}")
        return {}
