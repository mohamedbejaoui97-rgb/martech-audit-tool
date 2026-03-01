"""Wizard GTM — Implementation quality audit.

Uploads and parses a GTM container JSON export, then runs gap analysis
against the client's business type checklist.
FRs: FR12, FR13, FR14, FR15, FR16, FR17.
NFRs: NFR1, NFR13, NFR18.
"""

import json
import time

from deep.input_helpers import _ask_file_path, _ask_select


# ─── CONSTANTS ──────────────────────────────────────────────────────────────

PLATFORM_NAME = "GTM — Implementation Quality"

# Expected ecommerce dataLayer events (FR5, FR14)
ECOMMERCE_EVENTS = [
    "purchase", "add_to_cart", "begin_checkout", "view_item",
    "view_item_list", "add_payment_info", "add_shipping_info", "remove_from_cart",
]

# Expected lead gen events (FR5, FR14)
LEAD_GEN_EVENTS = [
    "generate_lead", "form_submit", "contact", "sign_up",
    "phone_call", "schedule_appointment",
]

# Critical tags/configurations to check (FR15)
CRITICAL_CHECKS = {
    "conversion_linker": {
        "tag_types": ["cvt_c", "gclidw", "awct"],  # Conversion Linker type IDs
        "name_patterns": ["conversion linker", "conversion_linker", "linker"],
        "severity": "critical",
        "detail_missing": "Conversion Linker mancante — le conversioni cross-domain non funzionano",
    },
    "enhanced_conversions": {
        "tag_types": ["aec"],
        "name_patterns": ["enhanced conversion", "conversioni migliorate", "user provided data"],
        "severity": "critical",
        "detail_missing": "Enhanced Conversions non configurate — match rate ridotto",
    },
}

# Known consent-related trigger/variable patterns
CONSENT_PATTERNS = [
    "consent", "cookie", "gdpr", "privacy", "iubenda",
    "cookiebot", "onetrust", "consent_mode", "ad_storage",
    "analytics_storage",
]


# ─── CONTAINER PARSING (FR13, NFR13) ───────────────────────────────────────

def _validate_gtm_json(content):
    """Validate that the file is a GTM container JSON export (FR44).

    Handles both published (containerVersion) and workspace
    (containerVersion inside exportContainers) variants (NFR13).

    Returns:
        (bool, error_msg)
    """
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return False, f"File JSON non valido: {e}"

    if not isinstance(data, dict):
        return False, "Struttura JSON non valida — atteso un oggetto, non un array"

    # Variant 1: Direct containerVersion (most common export)
    if "containerVersion" in data:
        return True, ""

    # Variant 2: exportContainers array (workspace export)
    if "exportContainers" in data:
        containers = data["exportContainers"]
        if isinstance(containers, list) and len(containers) > 0:
            if "containerVersion" in containers[0]:
                return True, ""
        return False, "exportContainers presente ma senza containerVersion valida"

    # Variant 3: Nested inside container key
    if "container" in data and isinstance(data["container"], dict):
        if "containerVersion" in data["container"]:
            return True, ""

    return False, ("Struttura GTM non riconosciuta — atteso 'containerVersion' "
                   "(esporta da GTM > Admin > Export Container)")


def _extract_container_version(data):
    """Extract the containerVersion dict from various GTM export formats (NFR13).

    Returns:
        dict (containerVersion) or None
    """
    if "containerVersion" in data:
        return data["containerVersion"]

    if "exportContainers" in data:
        containers = data["exportContainers"]
        if isinstance(containers, list) and len(containers) > 0:
            return containers[0].get("containerVersion", {})

    if "container" in data and isinstance(data["container"], dict):
        return data["container"].get("containerVersion", {})

    return None


def parse_gtm_container(content):
    """Parse a GTM container JSON and extract tags, triggers, variables (FR13).

    Args:
        content: Raw JSON string of the GTM container export

    Returns:
        dict with container_version, tags, triggers, variables, tag_count,
        trigger_count, variable_count, container_name, container_id.
        Returns {} on parse failure.
    """
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return {}

    cv = _extract_container_version(data)
    if not cv:
        return {}

    tags = cv.get("tag", [])
    triggers = cv.get("trigger", [])
    variables = cv.get("variable", [])
    builtins = cv.get("builtInVariable", [])

    # Container metadata
    container_name = cv.get("container", {}).get("name", "") if isinstance(cv.get("container"), dict) else ""
    container_id = cv.get("containerId", "")

    return {
        "container_version": cv,
        "tags": tags,
        "triggers": triggers,
        "variables": variables,
        "built_in_variables": builtins,
        "tag_count": len(tags),
        "trigger_count": len(triggers),
        "variable_count": len(variables) + len(builtins),
        "container_name": container_name,
        "container_id": container_id,
    }


# ─── GAP ANALYSIS (FR14, FR15) ────────────────────────────────────────────

def _get_tag_name(tag):
    """Extract tag name, handling various structures."""
    return (tag.get("name", "") or "").lower()


def _get_tag_type(tag):
    """Extract tag type ID."""
    return (tag.get("type", "") or "").lower()


def _tag_has_consent_check(tag):
    """Check if a tag has any consent-related firing condition (FR15).

    Looks at consentSettings, firingTriggerId references, and
    blockingTriggerId for consent patterns.
    """
    # GTM v2 consent settings
    consent_settings = tag.get("consentSettings", {})
    if consent_settings and consent_settings.get("consentStatus", "") == "needed":
        return True

    # Check tag parameters for consent references
    tag_str = json.dumps(tag).lower()
    return any(pattern in tag_str for pattern in CONSENT_PATTERNS)


def _find_duplicate_tags(tags):
    """Detect duplicate tags by type+name similarity (FR15)."""
    seen = {}
    duplicates = []
    for tag in tags:
        key = (_get_tag_type(tag), _get_tag_name(tag))
        if key in seen and key[0] and key[1]:
            duplicates.append({
                "tag_name": tag.get("name", "Unknown"),
                "tag_type": tag.get("type", "Unknown"),
                "detail": f"Tag duplicato: '{tag.get('name', '')}' (tipo: {tag.get('type', '')})",
            })
        else:
            seen[key] = tag
    return duplicates


def _check_critical_tags(tags):
    """Check for critical tags/configurations presence (FR15).

    Returns:
        dict of check_name -> {found: bool, severity, detail}
    """
    results = {}

    for check_name, check_config in CRITICAL_CHECKS.items():
        found = False
        for tag in tags:
            tag_type = _get_tag_type(tag)
            tag_name = _get_tag_name(tag)

            # Check by type ID
            if any(t == tag_type for t in check_config["tag_types"]):
                found = True
                break

            # Check by name pattern
            if any(p in tag_name for p in check_config["name_patterns"]):
                found = True
                break

        results[check_name] = {
            "found": found,
            "severity": check_config["severity"],
            "detail": "" if found else check_config["detail_missing"],
        }

    return results


def _check_no_consent_tags(tags):
    """Find tags that fire without any consent check (FR15).

    Returns list of tag names without consent conditions.
    """
    no_consent = []
    for tag in tags:
        if not _tag_has_consent_check(tag):
            name = tag.get("name", "Senza nome")
            tag_type = tag.get("type", "unknown")
            # Skip GTM internal tags that don't need consent
            if tag_type in ("jsm", "html") and "consent" in name.lower():
                continue
            no_consent.append({
                "tag_name": name,
                "tag_type": tag_type,
                "detail": f"'{name}' (tipo: {tag_type}) — nessun consent check rilevato",
            })
    return no_consent


def _check_datalayer_events(tags, triggers, variables, business_type):
    """Check for expected dataLayer events based on business type (FR5, FR14).

    Returns:
        dict with missing_events, found_events
    """
    if business_type == "ecommerce":
        expected = ECOMMERCE_EVENTS
    elif business_type == "lead_gen":
        expected = LEAD_GEN_EVENTS
    else:  # "both"
        expected = ECOMMERCE_EVENTS + LEAD_GEN_EVENTS

    # Search for events in tags, triggers, and variables
    container_str = json.dumps(tags + triggers + variables).lower()

    found = []
    missing = []
    for event in expected:
        if event.lower() in container_str:
            found.append(event)
        else:
            missing.append(event)

    return {
        "expected_events": expected,
        "found_events": found,
        "missing_events": missing,
    }


def run_gap_analysis(parsed_container, business_type):
    """Run full gap analysis on parsed GTM container (FR14, FR15, FR16).

    Args:
        parsed_container: Output from parse_gtm_container()
        business_type: "ecommerce" | "lead_gen" | "both"

    Returns:
        dict with missing_critical, missing_recommended, no_consent_check,
        duplicates, datalayer_events
    """
    tags = parsed_container.get("tags", [])
    triggers = parsed_container.get("triggers", [])
    variables = parsed_container.get("variables", [])

    # Critical checks (FR15)
    critical_results = _check_critical_tags(tags)
    missing_critical = [name for name, r in critical_results.items() if not r["found"]]

    # Tags without consent (FR15)
    no_consent = _check_no_consent_tags(tags)

    # Duplicate tags (FR15)
    duplicates = _find_duplicate_tags(tags)

    # DataLayer events by business type (FR14, FR5)
    datalayer = _check_datalayer_events(tags, triggers, variables, business_type)

    return {
        "critical_checks": critical_results,
        "missing_critical": missing_critical,
        "missing_recommended": datalayer["missing_events"],
        "no_consent_check": no_consent,
        "duplicates": duplicates,
        "datalayer_events": datalayer,
    }


# ─── RESULTS DISPLAY (FR16) ───────────────────────────────────────────────

def _show_results(parsed, gap_analysis):
    """Display immediate gap analysis results to console (FR16)."""
    print(f"\n  {'─'*46}")
    print(f"  📊 Risultati Wizard GTM")
    print(f"  {'─'*46}")

    # Container overview
    name = parsed.get("container_name", "") or parsed.get("container_id", "N/D")
    print(f"     Container:    {name}")
    print(f"     Tag:          {parsed.get('tag_count', 0)}")
    print(f"     Trigger:      {parsed.get('trigger_count', 0)}")
    print(f"     Variabili:    {parsed.get('variable_count', 0)}")

    # Critical missing
    missing_crit = gap_analysis.get("missing_critical", [])
    if missing_crit:
        print(f"\n  ⛔ Critici mancanti ({len(missing_crit)}):")
        for name in missing_crit:
            check = gap_analysis["critical_checks"][name]
            print(f"     ⛔ {check['detail']}")
    else:
        print(f"\n  ✅ Tutti i tag critici presenti")

    # Missing recommended events
    missing_rec = gap_analysis.get("missing_recommended", [])
    if missing_rec:
        print(f"\n  ⚠ Eventi mancanti ({len(missing_rec)}):")
        for event in missing_rec:
            print(f"     🔸 {event}")

    # No consent tags
    no_consent = gap_analysis.get("no_consent_check", [])
    if no_consent:
        print(f"\n  ⚠ Tag senza consent check ({len(no_consent)}):")
        for item in no_consent[:5]:  # Show max 5
            print(f"     🔸 {item['detail']}")
        if len(no_consent) > 5:
            print(f"     ... e altri {len(no_consent) - 5}")

    # Duplicates
    dupes = gap_analysis.get("duplicates", [])
    if dupes:
        print(f"\n  ⚠ Tag duplicati ({len(dupes)}):")
        for d in dupes:
            print(f"     🔸 {d['detail']}")

    print(f"  {'─'*46}")


# ─── MAIN WIZARD ───────────────────────────────────────────────────────────

def run_wizard_gtm(business_profile, discovery_block):
    """Run the GTM wizard. Returns gtm_data dict.

    Args:
        business_profile: Step Zero output (business_type, platforms, url)
        discovery_block: L0 auto_discover() output (for cross-checking)

    Returns:
        dict with container_raw, tag_count, trigger_count, variable_count,
        gap_analysis. Returns {} if skipped or on error.
    """
    print(f"\n{'='*50}")
    print(f"  🔍 Wizard {PLATFORM_NAME}")
    print(f"{'='*50}\n")

    try:
        # ── 1. File upload (FR12, FR44) ──
        filepath, content = _ask_file_path(
            "Percorso del file JSON export container GTM",
            validation_fn=_validate_gtm_json,
            help_text="Esporta da GTM: Admin > Export Container > Scarica JSON"
        )

        if filepath is None or content is None:
            return {}

        # ── 2. Parse container (FR13, NFR1) ──
        start_time = time.time()
        parsed = parse_gtm_container(content)
        parse_time = time.time() - start_time

        if not parsed:
            print("  ⚠ Impossibile analizzare il container GTM.")
            return {}

        print(f"  ✓ Container parsato in {parse_time:.2f}s — "
              f"{parsed['tag_count']} tag, {parsed['trigger_count']} trigger, "
              f"{parsed['variable_count']} variabili")

        # ── 3. Gap analysis (FR14, FR15, FR16) ──
        business_type = business_profile.get("business_type", "ecommerce")
        gap = run_gap_analysis(parsed, business_type)

        # ── Show immediate results (FR16) ──
        _show_results(parsed, gap)

        # ── Build return dict ──
        return {
            "container_raw": parsed.get("container_version", {}),
            "tag_count": parsed["tag_count"],
            "trigger_count": parsed["trigger_count"],
            "variable_count": parsed["variable_count"],
            "container_name": parsed.get("container_name", ""),
            "container_id": parsed.get("container_id", ""),
            "parse_time_seconds": round(parse_time, 3),
            "gap_analysis": gap,
        }

    except Exception as e:
        print(f"  ⚠ Errore nel wizard GTM: {e}")
        return {}
