"""Wizard Meta — Event match quality audit.

Collects Pixel ID, CAPI status, events, EMQ score, attribution window,
and runs cross-checks against L0 discovery and GTM data.
FRs: FR26, FR27, FR28, FR29, FR30, FR31, FR32.
"""

from deep.input_helpers import _ask_input, _ask_select, _ask_operator_notes, _ask_evidence_screenshots, _ask_multiline


# ─── CONSTANTS ──────────────────────────────────────────────────────────────

PLATFORM_NAME = "Meta — Event Match Quality"

CAPI_OPTIONS = ["Solo Pixel", "Pixel + CAPI", "Solo CAPI"]
CAPI_MAP = {
    "Solo Pixel": "pixel_only",
    "Pixel + CAPI": "pixel_capi",
    "Solo CAPI": "capi_only",
}

ATTRIBUTION_WINDOW_OPTIONS = ["7d click + 1d view", "1d click + 1d view", "7d click", "Altro"]
ATTRIBUTION_WINDOW_MAP = {
    "7d click + 1d view": "7d_1d",
    "1d click + 1d view": "1d_1d",
    "7d click": "7d",
    "Altro": "other",
}

EVENT_STATUS_OPTIONS = ["Funziona", "Errori", "Manca"]
EVENT_STATUS_MAP = {
    "Funziona": "ok",
    "Errori": "error",
    "Manca": "missing",
}

# Dynamic event checklists by business type (FR28)
ECOMMERCE_EVENTS = [
    "PageView", "ViewContent", "AddToCart",
    "InitiateCheckout", "AddPaymentInfo", "Purchase",
]
LEAD_GEN_EVENTS = [
    "PageView", "Lead", "Contact",
    "CompleteRegistration", "SubmitApplication",
]

# L0 detection keys for Meta Pixel
PIXEL_L0_KEYS = ["facebook_pixel", "meta_pixel", "fbevents", "fbq("]


# ─── VALIDATION ────────────────────────────────────────────────────────────

def _validate_emq(raw):
    try:
        val = float(raw.replace(",", "."))
    except ValueError:
        return False, "EMQ è un valore da 0 a 10. Inserisci un numero valido."
    if val < 0 or val > 10:
        return False, f"EMQ deve essere tra 0 e 10 (inserito: {val})"
    return True, ""


def _warn_emq(raw):
    val = float(raw.replace(",", "."))
    if val < 3:
        return (f"EMQ {val}/10 è molto basso — il matching utenti è insufficiente. "
                "Verifica la configurazione CAPI e i parametri inviati.")
    return None


def _validate_pixel_id(raw):
    if not raw:
        return False, "Inserisci il Pixel ID"
    if not raw.isdigit():
        return False, "Il Pixel ID deve contenere solo numeri (es. 123456789012345)"
    if len(raw) < 10 or len(raw) > 20:
        return False, f"Il Pixel ID ha tipicamente 15-16 cifre (inserito: {len(raw)} cifre)"
    return True, ""


# ─── L0 CROSS-CHECK (FR26) ────────────────────────────────────────────────

def _cross_check_pixel_l0(pixel_id, discovery_block):
    """Cross-check Pixel ID against L0 auto_discover() data."""
    if not discovery_block:
        return {"checked": False, "match": None, "detail": "L0 discovery non disponibile"}

    discovery_str = str(discovery_block).lower()

    # Check if pixel ID appears in discovery
    if pixel_id in discovery_str:
        return {"checked": True, "match": True, "detail": f"Pixel ID {pixel_id} rilevato sul sito ✓"}

    # Check if any Meta pixel detected at all
    pixel_detected = any(key in discovery_str for key in PIXEL_L0_KEYS)
    if pixel_detected:
        return {
            "checked": True, "match": False,
            "detail": f"Meta Pixel rilevato sul sito ma ID diverso da {pixel_id} — verifica configurazione",
        }

    return {
        "checked": True, "match": False,
        "detail": f"Nessun Meta Pixel rilevato sul sito — verifica installazione",
    }


# ─── EVENT COLLECTION (FR28) ──────────────────────────────────────────────

def _collect_events(business_type):
    """Collect event status for each event in the dynamic checklist."""
    if business_type == "ecommerce":
        events_list = ECOMMERCE_EVENTS
    elif business_type == "lead_gen":
        events_list = LEAD_GEN_EVENTS
    else:  # both
        events_list = list(dict.fromkeys(ECOMMERCE_EVENTS + LEAD_GEN_EVENTS))

    print(f"\n  Per ogni evento, indica lo stato attuale:")

    events = {}
    for event_name in events_list:
        status_label = _ask_select(
            f"Evento '{event_name}':",
            EVENT_STATUS_OPTIONS
        )
        events[event_name] = EVENT_STATUS_MAP.get(status_label, "missing")

    return events


# ─── CROSS-CHECKS (FR31, FR32) ────────────────────────────────────────────

def _check_capi_critical(capi_status, business_type):
    """Flag CAPI missing as critical for lead gen (FR31)."""
    if capi_status == "pixel_only" and business_type in ("lead_gen", "both"):
        return {
            "is_critical": True,
            "detail": ("CAPI mancante per lead gen — critico. "
                       "Senza CAPI il matching utenti è significativamente ridotto, "
                       "soprattutto con restrizioni iOS e browser."),
        }
    return {"is_critical": False, "detail": ""}


def _cross_check_gtm(events, deep_wizard_block):
    """Cross-check Meta events against GTM tags (FR32)."""
    gtm_data = deep_wizard_block.get("gtm_data", {})
    if not gtm_data:
        return {"available": False, "discrepancies": []}

    tags = gtm_data.get("container_raw", {}).get("tag", [])
    gtm_str = str(tags).lower()

    discrepancies = []
    # Map Meta event names to GTM search patterns
    meta_to_gtm = {
        "PageView": ["pageview", "page_view"],
        "ViewContent": ["view_content", "viewcontent", "view_item"],
        "AddToCart": ["add_to_cart", "addtocart"],
        "InitiateCheckout": ["initiate_checkout", "begin_checkout"],
        "Purchase": ["purchase"],
        "Lead": ["lead", "generate_lead"],
        "Contact": ["contact", "form_submit"],
        "CompleteRegistration": ["complete_registration", "sign_up"],
        "AddPaymentInfo": ["add_payment_info"],
        "SubmitApplication": ["submit_application"],
    }

    for event_name, status in events.items():
        if status == "missing":
            continue  # already known missing, no GTM check needed
        patterns = meta_to_gtm.get(event_name, [event_name.lower()])
        found_in_gtm = any(p in gtm_str for p in patterns)
        if not found_in_gtm and status == "ok":
            discrepancies.append({
                "event": event_name,
                "detail": (f"Evento Meta '{event_name}' attivo ma nessun tag/trigger "
                           "corrispondente trovato in GTM"),
            })

    return {"available": True, "discrepancies": discrepancies}


# ─── RESULTS DISPLAY ───────────────────────────────────────────────────────

def _show_results(data):
    """Display immediate wizard results to console."""
    pixel_id = data.get("pixel_id", "")
    pixel_check = data.get("pixel_id_check_l0", {})
    capi = data.get("capi_status", "")
    emq = data.get("emq_score", 0)
    events = data.get("events", {})
    attr = data.get("attribution_window", "")
    cross = data.get("cross_checks", {})

    ok_count = sum(1 for s in events.values() if s == "ok")
    error_count = sum(1 for s in events.values() if s == "error")
    missing_count = sum(1 for s in events.values() if s == "missing")

    emq_emoji = "🟢" if emq >= 7 else "🟡" if emq >= 4 else "🔴"

    print(f"\n  {'─'*46}")
    print(f"  📊 Risultati Wizard Meta")
    print(f"  {'─'*46}")
    print(f"     Pixel ID:          {pixel_id}")

    # L0 check
    if pixel_check.get("checked"):
        icon = "✅" if pixel_check.get("match") else "⚠"
        print(f"     L0 cross-check:    {icon} {pixel_check.get('detail', '')}")

    print(f"     CAPI:              {capi}")
    print(f"     {emq_emoji} EMQ Score:       {emq}/10")
    print(f"     Attribution:       {attr}")
    print(f"     Eventi:            {ok_count} ok, {error_count} errori, {missing_count} mancanti")

    # CAPI critical alert (FR31)
    capi_alert = cross.get("capi_critical", {})
    if capi_alert.get("is_critical"):
        print(f"\n  ⛔ {capi_alert['detail']}")

    # GTM cross-check (FR32)
    gtm = cross.get("gtm_cross_check", {})
    if gtm.get("available"):
        discrep = gtm.get("discrepancies", [])
        if discrep:
            print(f"\n  ⚠ Discrepanze GTM ({len(discrep)}):")
            for d in discrep:
                print(f"     🔸 {d['detail']}")
        else:
            print(f"\n  ✅ Eventi Meta coerenti con tag GTM")
    else:
        print(f"\n  ℹ GTM non disponibile — cross-check saltato")

    print(f"  {'─'*46}")


# ─── MAIN WIZARD ───────────────────────────────────────────────────────────

def run_wizard_meta(business_profile, discovery_block, deep_wizard_block=None):
    """Run the Meta wizard. Returns meta_data dict.

    Args:
        business_profile: Step Zero output (business_type, platforms, url)
        discovery_block: L0 auto_discover() output
        deep_wizard_block: Accumulated wizard data (for GTM cross-check)

    Returns:
        dict with pixel_id, pixel_id_check_l0, capi_status, emq_score,
        events, attribution_window, cross_checks.
        Returns {} if skipped or on error.
    """
    if deep_wizard_block is None:
        deep_wizard_block = {}

    print(f"\n{'='*50}")
    print(f"  🔍 Wizard {PLATFORM_NAME}")
    print(f"{'='*50}\n")

    try:
        business_type = business_profile.get("business_type", "ecommerce")

        # ── 1. Pixel ID + L0 cross-check (FR26) ──
        pixel_id = _ask_input(
            "Meta Pixel ID",
            validation_fn=_validate_pixel_id,
            help_text="Vai su Events Manager > Data Sources > Pixel ID (numero 15-16 cifre)"
        )
        pixel_check = _cross_check_pixel_l0(pixel_id, discovery_block)

        if pixel_check.get("checked"):
            icon = "✅" if pixel_check.get("match") else "⚠"
            print(f"  {icon} {pixel_check['detail']}")

        # ── 2. CAPI configuration (FR27) ──
        capi_label = _ask_select(
            "Configurazione CAPI:",
            CAPI_OPTIONS,
            help_text="Vai su Events Manager > Settings > Conversions API"
        )
        capi_status = CAPI_MAP.get(capi_label, "pixel_only")

        # ── 3. Event checklist by business type (FR28) ──
        events = _collect_events(business_type)

        # ── 4. EMQ Score (FR29) ──
        emq_score = _ask_input(
            "EMQ Score (Event Match Quality, 0-10)",
            validation_fn=_validate_emq,
            warning_fn=_warn_emq,
            help_text="Vai su Events Manager > Dataset > Panoramica > Event Match Quality",
            coerce_fn=lambda x: float(x.replace(",", "."))
        )

        # ── 5. Attribution window (FR30) ──
        attr_label = _ask_select(
            "Attribution window attuale:",
            ATTRIBUTION_WINDOW_OPTIONS,
            help_text="Vai su Events Manager > Settings > Attribution setting"
        )
        attribution_window = ATTRIBUTION_WINDOW_MAP.get(attr_label, "other")

        # ── 6. Cross-checks ──
        cross_checks = {
            "capi_critical": _check_capi_critical(capi_status, business_type),
            "gtm_cross_check": _cross_check_gtm(events, deep_wizard_block),
        }

        # ── Anomalies + Operator notes ──
        anomalies = _ask_multiline("Anomalie rilevate")

        notes = _ask_operator_notes()

        data = {
            "pixel_id": pixel_id,
            "pixel_id_check_l0": pixel_check,
            "pixel_id_match_l0": pixel_check.get("match", None),
            "capi_status": capi_status,
            "emq_score": emq_score,
            "events": events,
            "attribution_window": attribution_window,
            "cross_checks": cross_checks,
        }
        if anomalies:
            data["anomalies_detected"] = anomalies
        if notes:
            data["operator_notes"] = notes

        screenshots = _ask_evidence_screenshots("meta")
        if screenshots:
            data["evidence_screenshots"] = screenshots

        _show_results(data)
        return data

    except Exception as e:
        print(f"  ⚠ Errore nel wizard Meta: {e}")
        return {}
