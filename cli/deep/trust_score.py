"""Measurement Trust Score — Cross-platform intelligence.

Calculates a unified Trust Score (0-100) across all audited platforms,
plus Gap-to-Revenue qualitative impact analysis.
FRs: FR45, FR46, FR47, FR48, FR49, FR50.
NFR: NFR3.
"""


# ─── CONSTANTS (ADR-5) ────────────────────────────────────────────────────

PILLAR_WEIGHTS = {
    "consent_health":         0.25,  # Iubenda
    "implementation_quality": 0.20,  # GTM
    "conversion_reliability": 0.20,  # Google Ads
    "event_match_quality":    0.15,  # Meta
    "data_foundation":        0.20,  # GSC
}

PILLAR_LABELS = {
    "consent_health":         "Consent Health (Iubenda)",
    "implementation_quality": "Implementation Quality (GTM)",
    "conversion_reliability": "Conversion Reliability (Google Ads)",
    "event_match_quality":    "Event Match Quality (Meta)",
    "data_foundation":        "Data Foundation (GSC)",
}

PILLAR_PLATFORM_KEY = {
    "consent_health":         "iubenda_data",
    "implementation_quality": "gtm_data",
    "conversion_reliability": "gads_data",
    "event_match_quality":    "meta_data",
    "data_foundation":        "gsc_data",
}

GRADE_THRESHOLDS = [
    (90, "A"), (75, "B"), (60, "C"), (40, "D"),
]

# Gap-to-Revenue qualitative impact labels by severity
IMPACT_LABELS = {
    "critical": "Impatto critico su conversioni e revenue",
    "high":     "Impatto alto su tracking e ottimizzazione",
    "medium":   "Impatto moderato su qualità dati",
    "low":      "Impatto limitato, ottimizzazione consigliata",
}


# ─── GRADE HELPER ──────────────────────────────────────────────────────────

def score_to_grade(score):
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


# ─── PILLAR SCORING ───────────────────────────────────────────────────────

def _score_consent_health(data):
    """Score Consent Health pillar (0-100) from Iubenda data."""
    grade = data.get("triage_score", "F")
    grade_map = {"A": 95, "B": 78, "C": 62, "D": 40, "F": 15}
    base = grade_map.get(grade, 30)

    # Penalty for mismatches
    mismatches = data.get("l0_mismatches", [])
    penalty = min(len(mismatches) * 5, 20)

    return max(0, min(100, base - penalty))


def _score_implementation_quality(data):
    """Score Implementation Quality pillar (0-100) from GTM data."""
    gap = data.get("gap_analysis", {})
    score = 100

    # Critical missing: -20 each
    missing_crit = gap.get("missing_critical", [])
    score -= len(missing_crit) * 20

    # Tags without consent: -3 each (cap -25)
    no_consent = gap.get("no_consent_check", [])
    score -= min(len(no_consent) * 3, 25)

    # Missing recommended events: -5 each (cap -25)
    missing_rec = gap.get("missing_recommended", [])
    score -= min(len(missing_rec) * 5, 25)

    # Duplicates: -5 each (cap -15)
    dupes = gap.get("duplicates", [])
    score -= min(len(dupes) * 5, 15)

    return max(0, min(100, score))


def _score_conversion_reliability(data):
    """Score Conversion Reliability pillar (0-100) from Google Ads data."""
    score = 100
    cross = data.get("cross_checks", {})

    # Consent Mode diagnostics
    cm = data.get("consent_mode_status", "")
    if cm == "Not set up":
        score -= 30
    elif cm == "Needs attention":
        score -= 15

    # Enhanced Conversions
    ec = data.get("enhanced_conversions_status", "")
    if ec == "Not set up":
        score -= 20
    elif ec == "Needs attention":
        score -= 10

    # Attribution model
    attr = data.get("attribution_model", "")
    if attr == "Last-click":
        score -= 10
    elif attr == "Altro":
        score -= 5

    # Primary conflicts
    primary = cross.get("primary_conflicts", {})
    if primary.get("has_conflict"):
        score -= 15

    # GTM discrepancies
    gtm_check = cross.get("gtm_cross_check", {})
    discrep = gtm_check.get("discrepancies", [])
    score -= min(len(discrep) * 8, 20)

    # Missing funnel events
    missing_funnel = cross.get("missing_funnel_events", {})
    total_missing = sum(len(v) for v in missing_funnel.values() if isinstance(v, list))
    score -= min(total_missing * 5, 20)

    # Source discrepancies
    source_disc = cross.get("source_discrepancies", [])
    score -= min(len(source_disc) * 10, 20)

    return max(0, min(100, score))


def _score_event_match_quality(data):
    """Score Event Match Quality pillar (0-100) from Meta data."""
    score = 100

    # EMQ Score: scale 0-10 → 0-40 contribution
    emq = data.get("emq_score", 0)
    if emq < 4:
        score -= 35
    elif emq < 7:
        score -= 15

    # CAPI status
    capi = data.get("capi_status", "pixel_only")
    if capi == "pixel_only":
        score -= 25
    elif capi == "capi_only":
        score -= 5  # slight concern: no client-side fallback

    # Pixel L0 match
    if data.get("pixel_id_match_l0") is False:
        score -= 15

    # Event status
    events = data.get("events", {})
    missing = sum(1 for s in events.values() if s == "missing")
    errors = sum(1 for s in events.values() if s == "error")
    score -= missing * 8
    score -= errors * 5

    # Cross-checks
    cross = data.get("cross_checks", {})
    capi_crit = cross.get("capi_critical", {})
    if capi_crit.get("is_critical"):
        score -= 15

    return max(0, min(100, score))


def _score_data_foundation(data):
    """Score Data Foundation pillar (0-100) from GSC data."""
    score = 100

    # Sitemap
    sitemap = data.get("sitemap_status", "ok")
    if sitemap == "not_submitted":
        score -= 25
    elif sitemap == "errors":
        score -= 15

    # Indexing ratio
    indexed = data.get("pages_indexed", 0)
    submitted = data.get("pages_submitted", 0)
    if submitted > 0:
        ratio = indexed / submitted
        if ratio < 0.5:
            score -= 30
        elif ratio < 0.7:
            score -= 15
        elif ratio < 0.9:
            score -= 5

    # Opportunities found = data is rich (bonus back if penalties applied)
    opportunities = data.get("opportunities", [])
    if not opportunities and submitted > 0:
        score -= 10  # No CSV data = less foundation

    return max(0, min(100, score))


PILLAR_SCORERS = {
    "consent_health":         _score_consent_health,
    "implementation_quality": _score_implementation_quality,
    "conversion_reliability": _score_conversion_reliability,
    "event_match_quality":    _score_event_match_quality,
    "data_foundation":        _score_data_foundation,
}


# ─── TRUST SCORE CALCULATION (FR45, FR46) ──────────────────────────────────

def calculate_trust_score(deep_wizard_block):
    """Calculate Measurement Trust Score (0-100) with weight redistribution.

    Args:
        deep_wizard_block: Accumulated wizard data dict (ADR-1)

    Returns:
        dict with score, grade, coverage, coverage_label, pillars
    """
    # Determine available pillars (FR46)
    available = {}
    pillar_scores = {}

    for pillar, platform_key in PILLAR_PLATFORM_KEY.items():
        data = deep_wizard_block.get(platform_key, {})
        if data:  # Non-empty dict = platform was audited
            available[pillar] = PILLAR_WEIGHTS[pillar]
            scorer = PILLAR_SCORERS[pillar]
            pillar_scores[pillar] = scorer(data)

    if not available:
        return {
            "score": 0,
            "grade": "F",
            "coverage": 0.0,
            "coverage_label": "0/5 platforms",
            "pillars": {},
        }

    # Weight redistribution (FR46, ADR-5)
    total_weight = sum(available.values())
    normalized_weights = {k: v / total_weight for k, v in available.items()}

    # Weighted score
    score = sum(normalized_weights[k] * pillar_scores[k] for k in available)
    score = round(score)

    coverage = len(available) / len(PILLAR_WEIGHTS)
    coverage_label = f"{len(available)}/{len(PILLAR_WEIGHTS)} platforms"

    pillars = {}
    for pillar in available:
        pillars[pillar] = {
            "score": round(pillar_scores[pillar]),
            "weight_original": PILLAR_WEIGHTS[pillar],
            "weight_normalized": round(normalized_weights[pillar], 3),
            "label": PILLAR_LABELS[pillar],
        }

    return {
        "score": score,
        "grade": score_to_grade(score),
        "coverage": round(coverage, 2),
        "coverage_label": coverage_label,
        "pillars": pillars,
    }


# ─── GAP-TO-REVENUE (FR47) ────────────────────────────────────────────────

def _collect_issues(deep_wizard_block):
    """Collect all identified issues across platforms with severity."""
    issues = []

    # Iubenda issues
    iub = deep_wizard_block.get("iubenda_data", {})
    if iub:
        grade = iub.get("triage_score", "F")
        if grade in ("D", "F"):
            issues.append({
                "platform": "Iubenda",
                "issue": f"Triage Score {grade} — consent foundation compromessa",
                "severity": "critical",
                "is_leverage_node": True,
                "affects": ["Google Ads", "Meta", "GTM"],
            })
        elif grade == "C":
            issues.append({
                "platform": "Iubenda",
                "issue": f"Triage Score C — consent parzialmente efficace",
                "severity": "high",
                "is_leverage_node": True,
                "affects": ["Google Ads", "Meta"],
            })
        # Anomalies from operator are critical findings
        if iub.get("anomalies_detected"):
            issues.append({
                "platform": "Iubenda",
                "issue": iub["anomalies_detected"][:200],
                "severity": "critical",
                "is_leverage_node": True,
                "affects": ["Google Ads", "Meta", "Analytics"],
            })
        for m in iub.get("l0_mismatches", []):
            issues.append({
                "platform": "Iubenda",
                "issue": m.get("detail", str(m)),
                "severity": "medium",
                "is_leverage_node": False,
                "affects": [],
            })

    # GTM issues
    gtm = deep_wizard_block.get("gtm_data", {})
    if gtm:
        gap = gtm.get("gap_analysis", {})
        for name in gap.get("missing_critical", []):
            detail = gap.get("critical_checks", {}).get(name, {}).get("detail", name)
            issues.append({
                "platform": "GTM",
                "issue": detail,
                "severity": "critical",
                "is_leverage_node": name == "conversion_linker",
                "affects": ["Google Ads", "Meta"] if name == "conversion_linker" else [],
            })
        for item in gap.get("no_consent_check", []):
            issues.append({
                "platform": "GTM",
                "issue": f"Tag senza consent: {item.get('tag_name', '')}",
                "severity": "medium",
                "is_leverage_node": False,
                "affects": [],
            })

    # Google Ads issues
    gads = deep_wizard_block.get("gads_data", {})
    if gads:
        cross = gads.get("cross_checks", {})
        if cross.get("primary_conflicts", {}).get("has_conflict"):
            issues.append({
                "platform": "Google Ads",
                "issue": cross["primary_conflicts"].get("detail", "Conflitto conversioni primarie"),
                "severity": "high",
                "is_leverage_node": False,
                "affects": [],
            })
        if gads.get("enhanced_conversions_status") == "Not set up":
            issues.append({
                "platform": "Google Ads",
                "issue": "Enhanced Conversions non configurate",
                "severity": "high",
                "is_leverage_node": False,
                "affects": [],
            })
        if gads.get("consent_mode_status") == "Not set up":
            issues.append({
                "platform": "Google Ads",
                "issue": "Consent Mode non configurato",
                "severity": "critical",
                "is_leverage_node": True,
                "affects": ["GTM"],
            })
        # Inactive conversions
        if gads.get("conversions_active") in ("No", "Alcune"):
            days = gads.get("inactive_days", "")
            issues.append({
                "platform": "Google Ads",
                "issue": f"Conversioni inattive{f' da {days} giorni' if days else ''} — Smart Bidding senza dati freschi",
                "severity": "critical",
                "is_leverage_node": False,
                "affects": [],
            })
        if gads.get("ga4_gap_critical"):
            issues.append({
                "platform": "Google Ads",
                "issue": "Gap critico Google Ads ↔ GA4 — tracking rotto o disallineato",
                "severity": "critical",
                "is_leverage_node": False,
                "affects": ["GA4"],
            })
        if gads.get("anomalies_detected"):
            issues.append({
                "platform": "Google Ads",
                "issue": gads["anomalies_detected"][:200],
                "severity": "high",
                "is_leverage_node": False,
                "affects": [],
            })

    # Meta issues
    meta = deep_wizard_block.get("meta_data", {})
    if meta:
        cross = meta.get("cross_checks", {})
        if cross.get("capi_critical", {}).get("is_critical"):
            issues.append({
                "platform": "Meta",
                "issue": "CAPI mancante per lead gen — matching utenti ridotto",
                "severity": "critical",
                "is_leverage_node": False,
                "affects": [],
            })
        if meta.get("emq_score", 10) < 4:
            issues.append({
                "platform": "Meta",
                "issue": f"EMQ Score {meta.get('emq_score', 0)}/10 — insufficiente",
                "severity": "high",
                "is_leverage_node": False,
                "affects": [],
            })
        if meta.get("capi_status") == "pixel_only":
            issues.append({
                "platform": "Meta",
                "issue": "Solo Pixel, nessuna CAPI server-side — match rate ridotto",
                "severity": "high",
                "is_leverage_node": False,
                "affects": [],
            })
        if meta.get("anomalies_detected"):
            issues.append({
                "platform": "Meta",
                "issue": meta["anomalies_detected"][:200],
                "severity": "high",
                "is_leverage_node": False,
                "affects": [],
            })

    # GTM anomalies
    if gtm and gtm.get("anomalies_detected"):
        issues.append({
            "platform": "GTM",
            "issue": gtm["anomalies_detected"][:200],
            "severity": "high",
            "is_leverage_node": False,
            "affects": [],
        })

    # GSC issues
    gsc = deep_wizard_block.get("gsc_data", {})
    if gsc:
        sitemap_check = gsc.get("sitemap_cross_check", {})
        if sitemap_check.get("is_critical"):
            issues.append({
                "platform": "GSC",
                "issue": "Mismatch critico sitemap/robots.txt",
                "severity": "high",
                "is_leverage_node": False,
                "affects": [],
            })
        if gsc.get("anomalies_detected"):
            issues.append({
                "platform": "GSC",
                "issue": gsc["anomalies_detected"][:200],
                "severity": "medium",
                "is_leverage_node": False,
                "affects": [],
            })

    return issues


def calculate_gap_to_revenue(deep_wizard_block):
    """Identify problems and their qualitative impact on conversions (FR47).

    Returns:
        dict with issues (list), leverage_nodes — no monetary values.
    """
    issues = _collect_issues(deep_wizard_block)

    for issue in issues:
        sev = issue["severity"]
        issue["impact_label"] = IMPACT_LABELS.get(sev, "Impatto da valutare")

    leverage_nodes = [i for i in issues if i.get("is_leverage_node")]

    return {
        "issues": issues,
        "leverage_nodes": leverage_nodes,
    }


# ─── CONSENT IMPACT CHAIN (FR48) ──────────────────────────────────────────

def build_consent_impact_chain(deep_wizard_block):
    """Identify the consent → conversions → bidding → CPA cascade (FR48).

    Returns:
        dict with chain steps or None if no consent issues.
    """
    iub = deep_wizard_block.get("iubenda_data", {})
    if not iub:
        return None

    rejection = iub.get("rejection_rate", 0)
    cm_v2 = iub.get("consent_mode_v2") or iub.get("consent_mode", "none")
    grade = iub.get("triage_score", "F")

    if grade in ("A", "B"):
        return None  # No significant chain

    chain = []
    chain.append({
        "step": 1,
        "title": "Banner Cookie",
        "detail": f"{rejection:.0f}% rifiuto cookie, CM v2: {cm_v2}",
    })

    if cm_v2 == "none":
        chain.append({
            "step": 2,
            "title": "Consent Mode Assente",
            "detail": "Nessuna modellazione conversioni — dati completamente persi per utenti che rifiutano",
        })
    elif cm_v2 == "basic":
        chain.append({
            "step": 2,
            "title": "Consent Mode Basic",
            "detail": "Modellazione parziale — ping senza cookie ma senza dati granulari",
        })
    elif cm_v2 == "advanced":
        chain.append({
            "step": 2,
            "title": "Consent Mode Advanced",
            "detail": f"Modellazione attiva ma con {rejection:.0f}% rifiuto — {rejection:.0f}% dei dati è modellato, non osservato",
        })

    chain.append({
        "step": len(chain) + 1,
        "title": "Conversioni Perse",
        "detail": f"~{rejection:.0f}% delle conversioni non tracciate o parzialmente modellate",
    })

    chain.append({
        "step": len(chain) + 1,
        "title": "Bidding Incompleto",
        "detail": "Smart Bidding ottimizza su dati incompleti → CPA gonfiato",
    })

    chain.append({
        "step": len(chain) + 1,
        "title": "Audience Ridotte",
        "detail": "Remarketing e lookalike basati su audience incomplete",
    })

    return {"chain": chain, "triage_grade": grade, "rejection_rate": rejection}


# ─── ATTRIBUTION WINDOW COMPARISON (FR50) ─────────────────────────────────

def compare_attribution_windows(deep_wizard_block):
    """Compare Google Ads and Meta attribution windows (FR50).

    Returns:
        dict with comparison result or None if not both available.
    """
    gads = deep_wizard_block.get("gads_data", {})
    meta = deep_wizard_block.get("meta_data", {})

    if not gads or not meta:
        return None

    gads_attr = gads.get("attribution_model", "")
    meta_attr = meta.get("attribution_window", "")

    inconsistency = None
    if meta_attr == "1d_1d" and gads_attr == "Data-driven":
        inconsistency = ("Meta usa 1d click + 1d view (finestra stretta) mentre "
                         "Google Ads usa Data-driven (finestra ampia). "
                         "Il confronto ROAS tra piattaforme non è comparabile.")
    elif meta_attr == "7d" and gads_attr != "Last-click":
        inconsistency = ("Meta usa solo 7d click (no view-through) — possibile "
                         "sottostima conversioni Meta rispetto a Google Ads.")

    return {
        "gads_model": gads_attr,
        "meta_window": meta_attr,
        "has_inconsistency": inconsistency is not None,
        "detail": inconsistency or "Finestre di attribuzione compatibili",
    }


# ─── LEVERAGE NODES (FR49) ────────────────────────────────────────────────

def identify_leverage_nodes(gap_to_revenue):
    """Identify fix points where one fix resolves multiple platform issues (FR49).

    Args:
        gap_to_revenue: Output from calculate_gap_to_revenue()

    Returns:
        list of leverage node dicts
    """
    return gap_to_revenue.get("leverage_nodes", [])
