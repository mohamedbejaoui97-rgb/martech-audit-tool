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

        # ── L0 Discovery + SquirrelScan ──
        domain = url.replace('https://', '').replace('http://', '').rstrip('/')
        discovery_block, homepage_html, resp_headers, extra_htmls = auto_discover(domain, [], use_render=False)

        # SquirrelScan — merge crawl data into discovery
        if getattr(cli_audit, 'SQUIRREL_BIN', None):
            print("  🐿️ SquirrelScan in avvio...")
            try:
                from concurrent.futures import ThreadPoolExecutor as _SqTPE
                with _SqTPE(max_workers=1) as _sq_exec:
                    _sq_future = _sq_exec.submit(cli_audit.run_squirrelscan, domain, 100)
                    _scan_data = _sq_future.result(timeout=310)
                if _scan_data and hasattr(cli_audit, 'squirrelscan_to_discovery'):
                    cli_audit.squirrelscan_to_discovery(_scan_data, discovery_block)
                    print("  ✓ SquirrelScan completato e integrato")
            except Exception as _e:
                print(f"  ⚠ SquirrelScan: {_e}")

        # ── Run Wizards (Progressive Disclosure — FR4) ──
        wizard_count = sum(1 for p, _, _ in WIZARD_SEQUENCE if p in business_profile.get("platforms", []))
        completed = 0

        deep_wizard_block = {"business_profile": business_profile}

        for platform, module_name, func_name in WIZARD_SEQUENCE:
            if platform in business_profile.get("platforms", []):
                try:
                    module = importlib.import_module(f"deep.{module_name}")
                    wizard_fn = getattr(module, func_name)
                    # Pass accumulated data for cross-platform checks (gads, meta)
                    import inspect
                    sig = inspect.signature(wizard_fn)
                    if len(sig.parameters) >= 3:
                        result = wizard_fn(business_profile, discovery_block, deep_wizard_block)
                    else:
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

        # ── Trust Score (Epic 8) ──
        from deep.trust_score import (
            calculate_trust_score,
            calculate_gap_to_revenue,
            build_consent_impact_chain,
            compare_attribution_windows,
            identify_leverage_nodes,
        )
        trust_result = calculate_trust_score(deep_wizard_block)
        gap_revenue = calculate_gap_to_revenue(deep_wizard_block)
        consent_chain = build_consent_impact_chain(deep_wizard_block)
        attr_comparison = compare_attribution_windows(deep_wizard_block)
        leverage_nodes = identify_leverage_nodes(gap_revenue)

        deep_wizard_block["trust_score"] = trust_result
        deep_wizard_block["gap_to_revenue"] = gap_revenue
        deep_wizard_block["consent_impact_chain"] = consent_chain
        deep_wizard_block["attribution_comparison"] = attr_comparison
        deep_wizard_block["leverage_nodes"] = leverage_nodes
        save_state(collected_data)

        print(f"\n  ✅ Trust Score: {trust_result.get('score', 0)}/100 "
              f"({trust_result.get('grade', 'N/A')}) — {trust_result.get('coverage_label', '')}")
        n_issues = len(gap_revenue.get("issues", []))
        n_leverage = len(gap_revenue.get("leverage_nodes", []))
        if n_issues:
            print(f"  ℹ Gap-to-Revenue: {n_issues} problemi identificati, {n_leverage} nodi di leva")

        # ── Act 2: L2 AI Analyses (existing, from cli-audit.py) ──
        l2_results = {}
        try:
            api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY", "")
            if not api_key:
                env_path = os.path.join(TOOL_DIR, "credentials", ".env")
                if os.path.exists(env_path):
                    with open(env_path) as _ef:
                        for _line in _ef:
                            _line = _line.strip()
                            if _line.startswith("CLAUDE_API_KEY=") or _line.startswith("ANTHROPIC_API_KEY="):
                                api_key = _line.split("=", 1)[1].strip()
                                break
            google_key = os.environ.get("GOOGLE_API_KEY", "")
            if not google_key:
                env_path = os.path.join(TOOL_DIR, "credentials", ".env")
                if os.path.exists(env_path):
                    with open(env_path) as _ef:
                        for _line in _ef:
                            _line = _line.strip()
                            if _line.startswith("GOOGLE_API_KEY="):
                                google_key = _line.split("=", 1)[1].strip()
                                break

            if api_key:
                # ADR-6: Deep mode drops security + accessibility (no wizard data to enrich)
                analysis_types = ['performance', 'cwv', 'seo', 'seo_deep',
                                  'robots', 'sitemap', 'datalayer', 'cro', 'advertising']
                homepage_html = extra_htmls.get("homepage", "") if isinstance(extra_htmls, dict) else ""

                print(f"\n  🚀 Avvio {len(analysis_types)} analisi L2 in parallelo...")
                l2_start = time.time()

                from concurrent.futures import ThreadPoolExecutor, as_completed
                run_analysis = cli_audit.run_analysis

                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = {
                        executor.submit(run_analysis, atype, url, api_key, google_key,
                                        homepage_html, extra_htmls, discovery_block): atype
                        for atype in analysis_types
                    }
                    for future in as_completed(futures, timeout=200):
                        atype_key = futures[future]
                        try:
                            _atype, result = future.result(timeout=10)
                            l2_results[_atype] = result
                            print(f"    ✓ {_atype}")
                        except Exception as e:
                            l2_results[atype_key] = f"Errore: {e}"
                            print(f"    ⚠ {atype_key}: {e}")

                l2_elapsed = time.time() - l2_start
                print(f"  ✓ {len(l2_results)} analisi L2 completate in {l2_elapsed:.1f}s")
            else:
                print("  ⚠ API key non trovata (ANTHROPIC_API_KEY / CLAUDE_API_KEY) — analisi L2 saltate")
        except Exception as e:
            print(f"  ⚠ Errore analisi L2: {e}")

        # ── Act 3: Synthesis (Epic 9 — Story 9.1) ──
        from deep.synthesis import run_synthesis
        synthesis_result = run_synthesis(deep_wizard_block, discovery_block, l2_results, trust_result)

        # ── Report Generation (Epic 9 — Story 9.2) ──
        from deep.report_deep import generate_deep_report
        report_path = generate_deep_report(
            synthesis_result, deep_wizard_block, trust_result,
            l2_results=l2_results,
        )

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
