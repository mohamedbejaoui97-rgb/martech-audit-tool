"""Step Zero — Business profiling and platform selection.

Collects business type, available platforms, and establishes audit context.
This is the foundation for Progressive Disclosure (FR4) and dynamic checks (FR5).
"""

from deep.input_helpers import _ask_select

# ─── CONSTANTS ──────────────────────────────────────────────────────────────

BUSINESS_TYPES = ["Ecommerce", "Lead Generation", "Entrambi"]
BUSINESS_TYPE_MAP = {
    "Ecommerce": "ecommerce",
    "Lead Generation": "lead_gen",
    "Entrambi": "both",
}

PLATFORMS = ["Iubenda", "GTM", "Google Ads", "Meta", "GSC"]
PLATFORM_KEYS = ["iubenda", "gtm", "gads", "meta", "gsc"]
PLATFORM_DESCRIPTIONS = {
    "iubenda": "Consent & Privacy Assessment",
    "gtm": "Implementation Quality Audit (container JSON)",
    "gads": "Conversion Reliability Audit",
    "meta": "Event Match Quality Audit (Pixel/CAPI)",
    "gsc": "Data Foundation Audit (sitemap + CSV)",
}


def run_step_zero(url):
    """Run Step Zero: business profiling and platform selection.

    Collects business type and platform access, then asks the operator
    to confirm before proceeding. Returns a business_profile dict
    that drives Progressive Disclosure (FR4) and dynamic checks (FR5).

    Args:
        url: Target URL (https://domain)

    Returns:
        dict with business_type, platforms, url
    """
    print(f"\n{'='*50}")
    print(f"  📋 Step Zero — Profilo Business")
    print(f"{'='*50}\n")

    while True:
        # ── Business type selection (FR2) ──
        business_type_label = _ask_select(
            "Qual è il business type del cliente?",
            BUSINESS_TYPES
        )
        business_type = BUSINESS_TYPE_MAP.get(business_type_label, "ecommerce")

        # ── Platform selection (FR3) ──
        selected_labels = _ask_select(
            "A quali piattaforme hai accesso? (seleziona tutte quelle disponibili)",
            PLATFORMS,
            allow_multiple=True
        )

        # Map labels to keys
        selected_keys = []
        for label in selected_labels:
            if label in PLATFORMS:
                idx = PLATFORMS.index(label)
                selected_keys.append(PLATFORM_KEYS[idx])

        if not selected_keys:
            print("  ⚠ Devi selezionare almeno una piattaforma. Riprova.\n")
            continue

        # ── Preview: Progressive Disclosure (FR4) ──
        print(f"\n  {'─'*46}")
        print(f"  📊 Riepilogo configurazione:")
        print(f"  {'─'*46}")
        print(f"     Business type:  {business_type_label}")
        print(f"     URL target:     {url}")
        print(f"     Piattaforme:    {len(selected_keys)}/5 selezionate")
        print()
        print(f"  Wizard che verranno eseguiti:")
        for key in selected_keys:
            desc = PLATFORM_DESCRIPTIONS.get(key, "")
            label = PLATFORMS[PLATFORM_KEYS.index(key)]
            print(f"     ✓ {label} — {desc}")

        skipped = [PLATFORMS[i] for i, k in enumerate(PLATFORM_KEYS) if k not in selected_keys]
        if skipped:
            print()
            for label in skipped:
                print(f"     ○ {label} — saltato")
        print(f"  {'─'*46}")

        # ── Confirmation (AC: "When the operator confirms selections") ──
        try:
            confirm = input("\n  → Confermi e procedi? (s/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            confirm = 's'

        if confirm == 's':
            break
        else:
            print("  ℹ Ricominciamo la configurazione.\n")
            continue

    business_profile = {
        "business_type": business_type,
        "platforms": selected_keys,
        "url": url,
    }

    print(f"\n  ✅ Profilo confermato — avvio wizard...\n")

    return business_profile
