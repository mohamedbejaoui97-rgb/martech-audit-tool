"""Deep mode — MarTech Audit Tool.

Orchestrates the deep audit workflow: Step Zero → Wizards → Trust Score → Synthesis → Report.
"""

import os
import sys
import json
import signal
import time
import importlib

# ─── PATHS ──────────────────────────────────────────────────────────────────

CLI_DIR = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(os.path.dirname(CLI_DIR))
STATE_FILE = os.path.join(TOOL_DIR, "output", ".deep_state_tmp.json")

# ─── WIZARD SEQUENCE ────────────────────────────────────────────────────────

WIZARD_SEQUENCE = [
    ("iubenda", "wizard_iubenda", "run_wizard_iubenda"),
    ("gtm", "wizard_gtm", "run_wizard_gtm"),
    ("gads", "wizard_gads", "run_wizard_gads"),
    ("meta", "wizard_meta", "run_wizard_meta"),
    ("gsc", "wizard_gsc", "run_wizard_gsc"),
]

# ─── STATE MANAGEMENT (ADR-2) ──────────────────────────────────────────────

def save_state(data):
    """Persist collected data to temp state file."""
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # best-effort, never crash on state save


def delete_state():
    """Remove temp state file after successful completion."""
    try:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
    except Exception:
        pass


# ─── ORCHESTRATOR ───────────────────────────────────────────────────────────

def run_deep_mode(url, args):
    """Main entry point for deep audit mode.

    Args:
        url: Target URL (https://domain)
        args: Parsed argparse namespace
    """
    collected_data = {"business_profile": {}, "wizards_completed": []}

    # ── SIGINT Handler (ADR-2) ──
    def sigint_handler(sig, frame):
        print("\n\n  ⚠ Audit interrotto. Dati raccolti finora salvati.")
        save_state(collected_data)
        try:
            choice = input("  → Continuare con dati parziali? (s/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            choice = 'n'
        if choice == 's':
            print("  ℹ Proseguo con i dati raccolti finora...\n")
            return
        else:
            print(f"  ℹ Stato salvato in {STATE_FILE}")
            sys.exit(0)

    original_handler = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, sigint_handler)

    # ── Initialize state file ──
    save_state(collected_data)

    print(f"\n{'='*60}")
    print(f"  🔬 DEEP MODE — Audit Approfondito")
    print(f"{'='*60}\n")

    try:
        # ── Step Zero: Business Profiling ──
        from deep.step_zero import run_step_zero
        business_profile = run_step_zero(url)
        collected_data["business_profile"] = business_profile
        save_state(collected_data)

        # ── Import auto_discover from cli-audit.py ──
        if CLI_DIR not in sys.path:
            sys.path.insert(0, os.path.dirname(CLI_DIR))
        cli_audit = importlib.import_module("cli-audit")
        auto_discover = cli_audit.auto_discover

        # ── L0 Discovery ──
        domain = url.replace('https://', '').replace('http://', '').rstrip('/')
        discovery_block, homepage_html, resp_headers, extra_htmls = auto_discover(domain, [], use_render=False)

        # ── Run Wizards (Progressive Disclosure — FR4) ──
        wizard_count = sum(1 for p, _, _ in WIZARD_SEQUENCE if p in business_profile.get("platforms", []))
        completed = 0

        deep_wizard_block = {"business_profile": business_profile}

        for platform, module_name, func_name in WIZARD_SEQUENCE:
            if platform in business_profile.get("platforms", []):
                try:
                    module = importlib.import_module(f"deep.{module_name}")
                    wizard_fn = getattr(module, func_name)
                    result = wizard_fn(business_profile, discovery_block)
                    if result:
                        deep_wizard_block[f"{platform}_data"] = result
                        collected_data[f"{platform}_data"] = result
                except Exception as e:
                    print(f"  ⚠ Errore nel wizard {platform}: {e}")
                    deep_wizard_block[f"{platform}_data"] = {}

                completed += 1
                collected_data["wizards_completed"].append(platform)
                save_state(collected_data)
                print(f"\n  [{completed}/{wizard_count}] Wizard completati\n")

        # ── Trust Score ──
        # TODO: trust_score.calculate_trust_score(deep_wizard_block)

        # ── Act 2 (existing, from cli-audit.py) ──
        # TODO: run existing L2 analyses

        # ── Act 3: Synthesis ──
        # TODO: synthesis.run_synthesis(...)

        # ── Report Generation ──
        # TODO: report_deep.generate_deep_report(...)

        # ── Cleanup ──
        delete_state()
        print(f"\n{'='*60}")
        print(f"  ✅ Deep Audit Completato")
        print(f"{'='*60}\n")

    except Exception as e:
        print(f"\n  ⚠ Errore durante l'audit deep: {e}")
        save_state(collected_data)
    finally:
        # Restore original signal handler
        signal.signal(signal.SIGINT, original_handler)
