"""Wizard Google Ads — Conversion reliability audit.

Collects conversion actions, diagnostics (CM, EC, attribution),
and runs cross-checks against GTM data.
FRs: FR18, FR19, FR20, FR21, FR22, FR23, FR24, FR25.
"""

from deep.input_helpers import _ask_input, _ask_select


# ─── CONSTANTS ──────────────────────────────────────────────────────────────

PLATFORM_NAME = "Google Ads — Conversion Reliability"

CONVERSION_SOURCES = ["Website", "GA4 Import"]
CONVERSION_COUNTING = ["Ogni conversione", "Una conversione"]
CONVERSION_STATUS_OPTIONS = ["Attiva", "Inattiva", "Recente (nessun dato)"]

CONSENT_MODE_DIAG_OPTIONS = ["Excellent", "Needs attention", "Not set up"]
ENHANCED_CONV_DIAG_OPTIONS = ["Excellent", "Needs attention", "Not set up"]
ATTRIBUTION_MODEL_OPTIONS = ["Data-driven", "Last-click", "Altro"]

# Expected funnel events by business type (FR24)
ECOMMERCE_FUNNEL = {
    "upper": ["view_item", "view_item_list"],
    "mid": ["add_to_cart", "begin_checkout", "add_payment_info"],
    "bottom": ["purchase"],
}
LEAD_GEN_FUNNEL = {
    "upper": ["page_view", "view_content"],
    "mid": ["form_start", "phone_call"],
    "bottom": ["generate_lead", "contact", "sign_up"],
}


# ─── VALIDATION HELPERS ────────────────────────────────────────────────────

def _validate_positive_int(raw):
    try:
        val = int(raw)
        if val < 0:
            return False, "Il numero non può essere negativo"
        if val > 100:
            return False, "Numero massimo di conversion actions: 100"
        return True, ""
    except ValueError:
        return False, "Inserisci un numero intero valido"


# ─── CONVERSION COLLECTION (FR18) ─────────────────────────────────────────

def _collect_conversion_actions(count):
    """Collect details for each conversion action.

    Returns list of dicts with name, primary, source, status, counting.
    """
    actions = []
    for i in range(count):
        print(f"\n  ── Conversione {i+1}/{count} ──")

        name = _ask_input(f"Nome conversione #{i+1}")

        primary_label = _ask_select(
            "Tipo conversione:",
            ["Primary", "Secondary"]
        )
        is_primary = primary_label == "Primary"

        source = _ask_select(
            "Fonte conversione:",
            CONVERSION_SOURCES,
            help_text="Website = tag sul sito, GA4 Import = importata da Google Analytics 4"
        )

        status = _ask_select("Stato:", CONVERSION_STATUS_OPTIONS)

        counting = _ask_select(
            "Metodo di conteggio:",
            CONVERSION_COUNTING,
            help_text="'Ogni conversione' per ecommerce (purchase), 'Una conversione' per lead gen"
        )

        actions.append({
            "name": name,
            "is_primary": is_primary,
            "source": source,
            "status": status,
            "counting": counting,
        })

    return actions


# ─── CROSS-CHECKS (FR22, FR23, FR24, FR25) ────────────────────────────────

def _check_primary_conflicts(actions):
    """Detect multiple primary conversion actions (FR22)."""
    primaries = [a for a in actions if a["is_primary"]]
    if len(primaries) > 1:
        names = [a["name"] for a in primaries]
        return {
            "has_conflict": True,
            "count": len(primaries),
            "names": names,
            "detail": (f"{len(primaries)} conversioni primary in conflitto: "
                       f"{', '.join(names)}. Google Ads ottimizza su tutte — "
                       "può confondere il bidding automatico."),
        }
    return {"has_conflict": False, "count": len(primaries), "names": [], "detail": ""}


def _cross_check_gtm(actions, deep_wizard_block):
    """Cross-check conversion actions against GTM tags (FR23).

    Looks for each conversion action name in the GTM gap analysis data.
    """
    gtm_data = deep_wizard_block.get("gtm_data", {})
    if not gtm_data:
        return {"available": False, "discrepancies": []}

    # Build searchable string from GTM tags
    tags = gtm_data.get("container_raw", {}).get("tag", [])
    gtm_str = str(tags).lower()

    discrepancies = []
    for action in actions:
        action_name_lower = action["name"].lower()
        # Simplify: check if conversion name appears in any GTM tag
        found = action_name_lower in gtm_str
        if not found:
            # Also try common patterns
            simplified = action_name_lower.replace(" ", "_").replace("-", "_")
            found = simplified in gtm_str

        if not found and action["source"] == "Website":
            discrepancies.append({
                "action_name": action["name"],
                "detail": (f"Conversione '{action['name']}' (Website) "
                           "non ha un tag corrispondente in GTM"),
            })

    return {"available": True, "discrepancies": discrepancies}


def _check_missing_funnel_events(actions, business_type):
    """Flag missing mid-funnel and upper-funnel events (FR24)."""
    if business_type == "ecommerce":
        funnel = ECOMMERCE_FUNNEL
    elif business_type == "lead_gen":
        funnel = LEAD_GEN_FUNNEL
    else:  # both
        funnel = {
            "upper": ECOMMERCE_FUNNEL["upper"] + LEAD_GEN_FUNNEL["upper"],
            "mid": ECOMMERCE_FUNNEL["mid"] + LEAD_GEN_FUNNEL["mid"],
            "bottom": ECOMMERCE_FUNNEL["bottom"] + LEAD_GEN_FUNNEL["bottom"],
        }

    action_names_lower = [a["name"].lower().replace(" ", "_") for a in actions]

    missing = {"upper": [], "mid": [], "bottom": []}
    for level, events in funnel.items():
        for event in events:
            if not any(event in name for name in action_names_lower):
                missing[level].append(event)

    return missing


def _check_source_discrepancies(actions):
    """Flag discrepancies between Website and GA4 Import sources (FR25)."""
    website_actions = {a["name"].lower() for a in actions if a["source"] == "Website"}
    ga4_actions = {a["name"].lower() for a in actions if a["source"] == "GA4 Import"}

    discrepancies = []

    # Same conversion tracked from both sources
    overlap = website_actions & ga4_actions
    for name in overlap:
        discrepancies.append({
            "type": "duplicate_source",
            "action_name": name,
            "detail": f"'{name}' presente sia come Website che GA4 Import — possibile doppio conteggio",
        })

    return discrepancies


# ─── RESULTS DISPLAY ───────────────────────────────────────────────────────

def _show_results(data):
    """Display immediate wizard results to console."""
    actions = data.get("conversion_actions", [])
    cm = data.get("consent_mode_status", "")
    ec = data.get("enhanced_conversions_status", "")
    attr = data.get("attribution_model", "")
    cross = data.get("cross_checks", {})

    print(f"\n  {'─'*46}")
    print(f"  📊 Risultati Wizard Google Ads")
    print(f"  {'─'*46}")
    print(f"     Conversion actions:      {len(actions)}")
    print(f"     Consent Mode diagnostica: {cm}")
    print(f"     Enhanced Conversions:     {ec}")
    print(f"     Modello attribuzione:     {attr}")

    # Primary conflicts (FR22)
    primary = cross.get("primary_conflicts", {})
    if primary.get("has_conflict"):
        print(f"\n  ⛔ {primary['detail']}")

    # GTM cross-check (FR23)
    gtm_check = cross.get("gtm_cross_check", {})
    if gtm_check.get("available"):
        discrep = gtm_check.get("discrepancies", [])
        if discrep:
            print(f"\n  ⚠ Discrepanze GTM ({len(discrep)}):")
            for d in discrep:
                print(f"     🔸 {d['detail']}")
        else:
            print(f"\n  ✅ Tutte le conversioni Website hanno tag GTM corrispondenti")
    else:
        print(f"\n  ℹ GTM non disponibile — cross-check saltato")

    # Missing funnel events (FR24)
    missing_funnel = cross.get("missing_funnel_events", {})
    has_missing = any(missing_funnel.get(level) for level in ("upper", "mid", "bottom"))
    if has_missing:
        print(f"\n  ⚠ Eventi funnel mancanti:")
        for level, label in [("upper", "Upper-funnel"), ("mid", "Mid-funnel"), ("bottom", "Bottom-funnel")]:
            events = missing_funnel.get(level, [])
            if events:
                print(f"     🔸 {label}: {', '.join(events)}")

    # Source discrepancies (FR25)
    source_disc = cross.get("source_discrepancies", [])
    if source_disc:
        print(f"\n  ⚠ Discrepanze fonte ({len(source_disc)}):")
        for d in source_disc:
            print(f"     🔸 {d['detail']}")

    print(f"  {'─'*46}")


# ─── MAIN WIZARD ───────────────────────────────────────────────────────────

def run_wizard_gads(business_profile, discovery_block, deep_wizard_block=None):
    """Run the Google Ads wizard. Returns gads_data dict.

    Args:
        business_profile: Step Zero output (business_type, platforms, url)
        discovery_block: L0 auto_discover() output
        deep_wizard_block: Accumulated wizard data (for GTM cross-check).
            Optional — if not provided, GTM cross-check is skipped.

    Returns:
        dict with conversion_actions, consent_mode_status,
        enhanced_conversions_status, attribution_model, cross_checks.
        Returns {} if skipped or on error.
    """
    if deep_wizard_block is None:
        deep_wizard_block = {}

    print(f"\n{'='*50}")
    print(f"  🔍 Wizard {PLATFORM_NAME}")
    print(f"{'='*50}\n")

    try:
        # ── 1. Number of conversion actions (FR18) ──
        num_actions = _ask_input(
            "Quante conversion actions sono configurate?",
            validation_fn=_validate_positive_int,
            help_text="Vai su Google Ads > Obiettivi > Conversioni > Riepilogo",
            coerce_fn=int
        )

        if num_actions == 0:
            print("  ℹ Nessuna conversion action configurata.")
            return {
                "conversion_actions": [],
                "consent_mode_status": "",
                "enhanced_conversions_status": "",
                "attribution_model": "",
                "cross_checks": {},
            }

        # ── 2. Collect each conversion action (FR18) ──
        actions = _collect_conversion_actions(num_actions)

        # ── 3. Consent Mode diagnostics (FR19) ──
        cm_status = _ask_select(
            "Diagnostica Consent Mode:",
            CONSENT_MODE_DIAG_OPTIONS,
            help_text="Vai su Strumenti > Attribution, consent e dati proprietari. Cosa vedi accanto a 'Consent mode'?"
        )

        # ── 4. Enhanced Conversions diagnostics (FR20) ──
        ec_status = _ask_select(
            "Diagnostica Enhanced Conversions:",
            ENHANCED_CONV_DIAG_OPTIONS,
            help_text="Nella stessa pagina, sezione 'Conversioni migliorate'"
        )

        # ── 5. Attribution model (FR21) ──
        attr_model = _ask_select(
            "Modello di attribuzione principale:",
            ATTRIBUTION_MODEL_OPTIONS,
            help_text="Vai su Strumenti > Attribution > Modello"
        )

        # ── 6. Cross-checks ──
        business_type = business_profile.get("business_type", "ecommerce")

        cross_checks = {
            "primary_conflicts": _check_primary_conflicts(actions),
            "gtm_cross_check": _cross_check_gtm(actions, deep_wizard_block),
            "missing_funnel_events": _check_missing_funnel_events(actions, business_type),
            "source_discrepancies": _check_source_discrepancies(actions),
        }

        data = {
            "conversion_actions": actions,
            "consent_mode_status": cm_status,
            "enhanced_conversions_status": ec_status,
            "attribution_model": attr_model,
            "cross_checks": cross_checks,
        }

        # ── Show results ──
        _show_results(data)

        return data

    except Exception as e:
        print(f"  ⚠ Errore nel wizard Google Ads: {e}")
        return {}
