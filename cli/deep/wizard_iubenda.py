"""Wizard Iubenda — Consent & privacy assessment.

Collects rejection rate, Consent Mode v2 status, and banner services.
Calculates Triage Score and cross-checks with L0 auto_discover() data.
FRs: FR6, FR7, FR8, FR9, FR10, FR11.
"""

from deep.input_helpers import _ask_input, _ask_select, _ask_operator_notes, _ask_evidence_screenshots


# ─── CONSTANTS ──────────────────────────────────────────────────────────────

PLATFORM_NAME = "Iubenda — Consent & Privacy"

CONSENT_MODE_OPTIONS = ["Assente", "Basic", "Advanced"]
CONSENT_MODE_MAP = {
    "Assente": "none",
    "Basic": "basic",
    "Advanced": "advanced",
}

BANNER_SERVICES = [
    "Google Analytics",
    "Google Ads",
    "Meta Pixel (Facebook)",
    "LinkedIn Insight Tag",
    "TikTok Pixel",
    "Hotjar",
    "Microsoft Clarity",
    "HubSpot",
    "Mailchimp",
    "Google Tag Manager",
]

# Mapping banner service labels → L0 detection keys (auto_discover patterns)
BANNER_TO_L0_KEYS = {
    "Google Analytics": ["google_analytics", "ga4", "gtag"],
    "Google Ads": ["google_ads", "adwords", "googleads"],
    "Meta Pixel (Facebook)": ["facebook_pixel", "meta_pixel", "fbevents"],
    "LinkedIn Insight Tag": ["linkedin"],
    "TikTok Pixel": ["tiktok"],
    "Hotjar": ["hotjar"],
    "Microsoft Clarity": ["clarity"],
    "HubSpot": ["hubspot"],
    "Mailchimp": ["mailchimp"],
    "Google Tag Manager": ["google_tag_manager", "gtm"],
}

# Triage Score matrix: (rejection_rate_bucket, consent_mode) → (grade, detail)
# Rejection rate buckets: low (<25%), medium (25-50%), high (>50%)
TRIAGE_MATRIX = {
    ("low", "advanced"):  ("A", "CM v2 Advanced con basso rifiuto = setup ottimale"),
    ("low", "basic"):     ("B", "CM v2 Basic con basso rifiuto = buono ma migliorabile"),
    ("low", "none"):      ("C", "Basso rifiuto ma CM v2 assente = conversioni non modellate"),
    ("medium", "advanced"): ("B", "CM v2 Advanced compensa il rifiuto medio"),
    ("medium", "basic"):   ("C", "CM v2 Basic con rifiuto medio = conversioni parzialmente sottostimate"),
    ("medium", "none"):    ("D", "Rifiuto medio senza CM v2 = conversioni significativamente perse"),
    ("high", "advanced"):  ("C", "CM v2 Advanced mitiga il rifiuto alto ma impatto significativo"),
    ("high", "basic"):     ("D", "CM v2 Basic con alto rifiuto = conversioni significativamente sottostimate"),
    ("high", "none"):      ("F", "Alto rifiuto senza CM v2 = la maggior parte delle conversioni invisibili"),
}


# ─── VALIDATION & WARNING FUNCTIONS ────────────────────────────────────────

def _validate_rejection_rate(raw):
    """Validate rejection rate is a number between 0 and 100."""
    try:
        val = float(raw.replace(",", "."))
    except ValueError:
        return False, "Inserisci un numero tra 0 e 100 (es. 42 o 42.5)"
    if val < 0 or val > 100:
        return False, f"Il tasso di rifiuto deve essere tra 0% e 100% (inserito: {val}%)"
    return True, ""


def _warn_rejection_rate(raw):
    """Warn for suspicious rejection rate values."""
    val = float(raw.replace(",", "."))
    if val < 10:
        return (f"Un tasso di rifiuto del {val:.0f}% è insolito — "
                "potrebbe indicare che il banner non blocca effettivamente i cookie. "
                "Verifica il dato.")
    if val > 85:
        return (f"Un tasso di rifiuto del {val:.0f}% è molto alto — "
                "verifica che il dato sia corretto e non includa bounce senza interazione.")
    return None


# ─── TRIAGE SCORE CALCULATION (FR9) ────────────────────────────────────────

def _get_rejection_bucket(rate):
    """Categorize rejection rate into low/medium/high."""
    if rate < 25:
        return "low"
    elif rate <= 50:
        return "medium"
    else:
        return "high"


def _calculate_triage_score(rejection_rate, consent_mode_v2):
    """Calculate Triage Score (A-F) from rejection rate × CM v2 status.

    Args:
        rejection_rate: float 0-100
        consent_mode_v2: str "none" | "basic" | "advanced"

    Returns:
        tuple (grade, detail)
    """
    bucket = _get_rejection_bucket(rejection_rate)
    key = (bucket, consent_mode_v2)
    return TRIAGE_MATRIX.get(key, ("D", "Valutazione non disponibile"))


# ─── L0 CROSS-CHECK (FR10) ────────────────────────────────────────────────

def _cross_check_l0(banner_services, discovery_block, platforms=None):
    """Cross-check banner services against L0 auto_discover() data.

    Args:
        banner_services: List of services declared in Iubenda banner
        discovery_block: L0 auto_discover() output
        platforms: List of selected platforms from Step Zero (for GTM-aware messaging)

    Returns list of mismatch dicts with type, service, detail.
    """
    mismatches = []
    if not discovery_block:
        return mismatches

    has_gtm = platforms and "gtm" in platforms

    # Flatten discovery_block to a searchable string for simple matching
    discovery_str = str(discovery_block).lower()

    for service in banner_services:
        l0_keys = BANNER_TO_L0_KEYS.get(service, [])
        found_in_l0 = any(key in discovery_str for key in l0_keys)

        if not found_in_l0:
            if has_gtm:
                detail = f"{service} dichiarato nel banner ma non rilevato sul sito — Probabilmente caricato via GTM — verificare nel container"
            else:
                detail = f"{service} dichiarato nel banner ma non rilevato sul sito"
            mismatches.append({
                "type": "in_banner_not_detected",
                "service": service,
                "detail": detail
            })

    # Check for technologies detected on site but NOT in banner
    l0_to_banner = {}
    for service, keys in BANNER_TO_L0_KEYS.items():
        for key in keys:
            l0_to_banner[key] = service

    for key, service in l0_to_banner.items():
        if key in discovery_str and service not in banner_services:
            # Avoid duplicate alerts for same service
            already_flagged = any(m["service"] == service and m["type"] == "detected_not_in_banner"
                                  for m in mismatches)
            if not already_flagged:
                mismatches.append({
                    "type": "detected_not_in_banner",
                    "service": service,
                    "detail": f"{service} rilevato sul sito ma non dichiarato nel banner Iubenda"
                })

    return mismatches


# ─── RESULTS DISPLAY ───────────────────────────────────────────────────────

def _show_results(data):
    """Display immediate wizard results to console (FR11)."""
    grade = data.get("triage_score", "?")
    detail = data.get("triage_detail", "")
    rejection = data.get("rejection_rate", 0)
    cm_v2 = data.get("consent_mode_v2", "")
    services = data.get("banner_services", [])
    mismatches = data.get("l0_mismatches", [])

    grade_emoji = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴", "F": "⛔"}.get(grade, "❓")

    print(f"\n  {'─'*46}")
    print(f"  📊 Risultati Wizard Iubenda")
    print(f"  {'─'*46}")
    print(f"     Tasso rifiuto:    {rejection:.0f}%")
    print(f"     Consent Mode v2:  {cm_v2.title()}")
    print(f"     Servizi banner:   {len(services)}")
    print()
    print(f"  {grade_emoji} Triage Score: {grade} — {detail}")

    if mismatches:
        print(f"\n  ⚠ Mismatch rilevati ({len(mismatches)}):")
        for m in mismatches:
            icon = "🔸" if m["type"] == "in_banner_not_detected" else "🔹"
            print(f"     {icon} {m['detail']}")

    print(f"  {'─'*46}")


# ─── MAIN WIZARD ───────────────────────────────────────────────────────────

def run_wizard_iubenda(business_profile, discovery_block):
    """Run the Iubenda wizard. Returns iubenda_data dict.

    Args:
        business_profile: Step Zero output (business_type, platforms, url)
        discovery_block: L0 auto_discover() output (for cross-checking)

    Returns:
        dict with rejection_rate, consent_mode_v2, banner_services,
        triage_score, triage_detail, l0_mismatches
    """
    print(f"\n{'='*50}")
    print(f"  🔍 Wizard {PLATFORM_NAME}")
    print(f"{'='*50}\n")

    data = {}

    try:
        # ── 1. Rejection rate (FR6) ──
        rejection_rate = _ask_input(
            "Tasso di rifiuto cookie (%)",
            validation_fn=_validate_rejection_rate,
            warning_fn=_warn_rejection_rate,
            help_text="Vai su Dashboard Iubenda > Cookie Solution > Statistiche",
            coerce_fn=lambda x: float(x.replace(",", "."))
        )
        data["rejection_rate"] = rejection_rate

        # ── 2. Consent Mode v2 status (FR7) ──
        cm_v2_label = _ask_select(
            "Stato del Consent Mode v2:",
            CONSENT_MODE_OPTIONS,
            help_text="Verifica in Google Tag Manager > Admin > Container Settings, o in Google Ads > Strumenti > Consent"
        )
        cm_v2 = CONSENT_MODE_MAP.get(cm_v2_label, "none")
        data["consent_mode_v2"] = cm_v2

        # ── 3. Banner services checklist (FR8) ──
        banner_services = _ask_select(
            "Quali servizi marketing sono presenti nel banner Iubenda?",
            BANNER_SERVICES,
            allow_multiple=True,
            help_text="Vai su Dashboard Iubenda > Cookie Solution > Servizi attivi nel banner"
        )
        data["banner_services"] = banner_services

        # ── 4. Triage Score (FR9, FR11) ──
        grade, detail = _calculate_triage_score(rejection_rate, cm_v2)
        data["triage_score"] = grade
        data["triage_detail"] = detail

        # ── 5. L0 cross-check (FR10) ──
        platforms = business_profile.get("platforms", [])
        mismatches = _cross_check_l0(banner_services, discovery_block, platforms=platforms)
        data["l0_mismatches"] = mismatches

        # ── Show immediate results (FR11) ──
        _show_results(data)

        # ── 6. Anomalies + Operator notes ──
        print("\n  ── Anomalie rilevate (opzionale, max 2000 caratteri) ──")
        try:
            anomalies = input("  → Anomalie (Invio per saltare): ").strip()
        except (EOFError, KeyboardInterrupt):
            anomalies = ""
        if anomalies and len(anomalies) > 2000:
            anomalies = anomalies[:2000]
        if anomalies:
            data["anomalies_detected"] = anomalies

        notes = _ask_operator_notes()
        if notes:
            data["operator_notes"] = notes

        screenshots = _ask_evidence_screenshots("iubenda")
        if screenshots:
            data["evidence_screenshots"] = screenshots

    except Exception as e:
        print(f"  ⚠ Errore nel wizard Iubenda: {e}")
        if not data:
            return {}

    return data
