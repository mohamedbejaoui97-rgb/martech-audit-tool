"""Act 3 — Sectional synthesis orchestration (ADR-6).

Splits synthesis into N parallel focused API calls, one per report section.
Each call receives ONLY the data it needs → no timeout, consistent quality.

Reads section configs from osmani-config.json → synthesis_sections (ADR-3).
Falls back to legacy monolithic synthesis if synthesis_sections not found.

FRs: FR51, FR60.  NFRs: NFR4, NFR7, NFR11, NFR17, NFR21, NFR22.
"""

import json
import os
import time
import urllib.request
import urllib.error
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── PATHS ──────────────────────────────────────────────────────────────────

CLI_DIR = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(os.path.dirname(CLI_DIR))
CONFIG_PATH = os.path.join(TOOL_DIR, "data", "reference", "osmani-config.json")

# Secure SSL context for API calls
_CTX_SECURE = ssl.create_default_context()

# ─── PRICING (per-token, USD) ───────────────────────────────────────────────

_PRICES = {
    "claude-opus-4-6":   {"input": 15.0 / 1_000_000, "output": 75.0 / 1_000_000},
    "claude-sonnet-4-6": {"input":  3.0 / 1_000_000, "output": 15.0 / 1_000_000},
}

WIZARD_KEYS = ["iubenda_data", "gtm_data", "gads_data", "meta_data", "gsc_data"]

PLATFORM_MAP = {
    "iubenda_data": "iubenda",
    "gtm_data": "gtm",
    "gads_data": "gads",
    "meta_data": "meta",
    "gsc_data": "gsc",
}


# ─── CONFIG LOADER ──────────────────────────────────────────────────────────

def _load_full_config():
    """Load full osmani-config.json."""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _load_sections_config():
    """Load synthesis_sections config (ADR-6). Returns None if not found."""
    cfg = _load_full_config()
    return cfg.get("synthesis_sections")


def _load_legacy_config():
    """Load legacy synthesis_prompt config (pre-ADR-6 fallback)."""
    cfg = _load_full_config()
    return cfg.get("synthesis_prompt", {})


# ─── API CALL ───────────────────────────────────────────────────────────────

def _call_claude(api_key, system_prompt, user_message, model, max_tokens,
                 temperature=0, timeout_s=120, max_retries=1):
    """Call Claude API. Works for both Opus and Sonnet.

    Returns:
        tuple: (response_text, usage_dict)
    """
    payload = json.dumps({
        'model': model,
        'max_tokens': max_tokens,
        'temperature': temperature,
        'system': system_prompt,
        'messages': [{'role': 'user', 'content': user_message}]
    }).encode('utf-8')

    headers = {
        'Content-Type': 'application/json',
        'x-api-key': api_key,
        'anthropic-version': '2023-06-01',
    }

    for attempt in range(max_retries + 1):
        try:
            req = urllib.request.Request(
                'https://api.anthropic.com/v1/messages',
                data=payload, headers=headers,
            )
            resp = urllib.request.urlopen(req, timeout=timeout_s, context=_CTX_SECURE)
            data = json.loads(resp.read().decode('utf-8'))
            if 'content' not in data or not data['content']:
                raise ValueError(f"Unexpected API response: {list(data.keys())}")
            usage = data.get('usage', {})
            return data['content'][0]['text'], usage
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace') if e.fp else ''
            if e.code in (429, 500, 502, 503, 529) and attempt < max_retries:
                wait = (2 ** attempt) + (time.time() % 1)
                time.sleep(wait)
                continue
            raise RuntimeError(f"Claude API error {e.code}: {body[:500]}") from e
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            raise RuntimeError(f"Claude API parse error: {e}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < max_retries:
                wait = (2 ** attempt) + 1
                time.sleep(wait)
                continue
            raise RuntimeError(f"Claude API network error: {e}") from e

    raise RuntimeError("Claude API: max retries exceeded")


# ─── WIZARD FORMATTERS (Story 10.2) ────────────────────────────────────────

def _format_wizard_summary(key, data):
    """One-liner summary of wizard data (for sections that need overview, not full data)."""
    if not data:
        return ""

    name = key.replace("_data", "").upper()
    parts = [f"[{name}]"]

    # Generic fields present in most wizards
    if data.get("triage_score"):
        parts.append(f"Triage: {data['triage_score']}")
    if data.get("health_score"):
        parts.append(f"Health: {data['health_score']}")
    if data.get("emq_score"):
        parts.append(f"EMQ: {data['emq_score']}")
    if data.get("consent_mode_status"):
        parts.append(f"CM: {data['consent_mode_status']}")
    if data.get("rejection_rate") is not None:
        parts.append(f"Rejection: {data['rejection_rate']}%")
    if data.get("conversions_total") is not None:
        parts.append(f"Conv: {data['conversions_total']}")
    if data.get("conversions_active") is not None:
        parts.append(f"Active: {data['conversions_active']}")
    if data.get("tag_count") is not None:
        parts.append(f"Tags: {data['tag_count']}")
    if data.get("anomalies_detected"):
        parts.append(f"ANOMALIA: {data['anomalies_detected'][:100]}")
    if data.get("operator_notes"):
        parts.append(f"Note: {data['operator_notes'][:100]}")

    return " | ".join(parts)


MAX_WIZARD_FULL_CHARS = 8000


def _format_wizard_full(data, max_chars=MAX_WIZARD_FULL_CHARS):
    """Structured text for wizard data (for dedicated platform section).

    Converts JSON to readable key: value lines. ~40% fewer tokens than json.dumps(indent=2).
    Capped at max_chars to prevent token overflow.
    """
    if not data:
        return "(nessun dato)"

    lines = []
    for k, v in data.items():
        if k in ("evidence_screenshots",):
            continue  # skip binary/path data
        if isinstance(v, dict):
            lines.append(f"\n  [{k}]")
            for k2, v2 in v.items():
                if isinstance(v2, (dict, list)):
                    raw = json.dumps(v2, ensure_ascii=False)
                    lines.append(f"    {k2}: {raw[:500]}")
                else:
                    lines.append(f"    {k2}: {str(v2)[:300]}")
        elif isinstance(v, list):
            raw = json.dumps(v, ensure_ascii=False)
            lines.append(f"  {k}: {raw[:1000]}")
        else:
            lines.append(f"  {k}: {str(v)[:300]}")
    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars] + f"\n  ... [troncato a {max_chars} caratteri]"
    return result


def _format_l2_result(result):
    """Format a single L2 analysis result as readable text."""
    if isinstance(result, str):
        return result[:4000]
    if isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False, indent=1)[:4000]
    return str(result)[:4000]


# ─── DATA SLICER (Story 10.2) ──────────────────────────────────────────────

def _collect_all_notes_and_anomalies(deep_wizard_block):
    """Extract operator notes and anomalies from ALL wizards."""
    notes = []
    anomalies = []
    for key in WIZARD_KEYS:
        wdata = deep_wizard_block.get(key, {})
        if wdata.get("operator_notes"):
            notes.append(f"{key.replace('_data','').upper()}: {wdata['operator_notes']}")
        if wdata.get("anomalies_detected"):
            anomalies.append(f"{key.replace('_data','').upper()}: {wdata['anomalies_detected']}")
    return notes, anomalies


def _build_section_data(section_id, data_keys, deep_wizard_block,
                         discovery_block, l2_results, trust_result,
                         phase1_results=None):
    """Build minimal data payload for a specific section (ADR-6).

    Returns: str ready for user message.
    """
    parts = []

    all_notes, all_anomalies = _collect_all_notes_and_anomalies(deep_wizard_block)
    bp = deep_wizard_block.get("business_profile", {})

    for key in data_keys:
        if key == "business_profile":
            parts.append("=== BUSINESS PROFILE ===")
            parts.append(_format_wizard_full(bp))

        elif key == "business_profile_summary":
            parts.append("=== BUSINESS PROFILE (Summary) ===")
            parts.append(f"  domain: {bp.get('domain', '?')}")
            parts.append(f"  business_type: {bp.get('business_type', '?')}")
            parts.append(f"  platforms: {', '.join(bp.get('platforms', []))}")

        elif key == "trust_score_summary":
            ts = trust_result or {}
            parts.append("=== TRUST SCORE (Summary) ===")
            parts.append(f"Score: {ts.get('score', 'N/A')}/100 ({ts.get('grade', '?')})")
            parts.append(f"Coverage: {ts.get('coverage_label', '?')}")
            for p in ts.get("pillars", []):
                parts.append(f"  {p.get('name', '?')}: {p.get('score', 0)}/100 (peso {p.get('weight', 0)}%)")

        elif key == "trust_score_full":
            parts.append("=== TRUST SCORE (Full) ===")
            parts.append(json.dumps(trust_result or {}, ensure_ascii=False, indent=1))

        elif key == "gap_to_revenue_summary":
            gr = deep_wizard_block.get("gap_to_revenue", {})
            parts.append("=== GAP-TO-REVENUE (Summary) ===")
            issues = gr.get("issues", [])
            parts.append(f"Problemi identificati: {len(issues)}, Nodi di leva: {len(gr.get('leverage_nodes', []))}")
            for gap in issues[:5]:
                parts.append(f"  - {gap.get('platform','?')}: {gap.get('issue','?')} [{gap.get('severity','?')}] {gap.get('impact_label','')}")

        elif key == "gap_to_revenue":
            parts.append("=== GAP-TO-REVENUE (Full) ===")
            parts.append(json.dumps(deep_wizard_block.get("gap_to_revenue", {}), ensure_ascii=False, indent=1))

        elif key == "consent_impact_chain":
            parts.append("=== CONSENT IMPACT CHAIN ===")
            chain = deep_wizard_block.get("consent_impact_chain", {})
            parts.append(json.dumps(chain, ensure_ascii=False, indent=1) if chain else "(nessuna chain)")

        elif key == "leverage_nodes":
            parts.append("=== LEVERAGE NODES ===")
            nodes = deep_wizard_block.get("leverage_nodes", [])
            parts.append(json.dumps(nodes, ensure_ascii=False, indent=1) if nodes else "(nessun nodo)")

        elif key == "attribution_comparison":
            parts.append("=== ATTRIBUTION COMPARISON ===")
            attr = deep_wizard_block.get("attribution_comparison", {})
            parts.append(json.dumps(attr, ensure_ascii=False, indent=1) if attr else "(nessun confronto)")

        elif key == "all_operator_notes":
            if all_notes:
                parts.append("=== NOTE OPERATORE ===")
                parts.extend(all_notes)

        elif key == "all_anomalies":
            if all_anomalies:
                parts.append("=== ANOMALIE RILEVATE (PRIORITÀ ALTA) ===")
                parts.extend(all_anomalies)

        elif key == "wizard_summaries":
            parts.append("=== WIZARD SUMMARIES ===")
            for wk in WIZARD_KEYS:
                wdata = deep_wizard_block.get(wk, {})
                if wdata:
                    parts.append(_format_wizard_summary(wk, wdata))

        # Wizard full data keys
        elif key == "iubenda_data":
            parts.append("=== IUBENDA DATA ===")
            parts.append(_format_wizard_full(deep_wizard_block.get("iubenda_data", {})))

        elif key == "gtm_data":
            parts.append("=== GTM DATA ===")
            parts.append(_format_wizard_full(deep_wizard_block.get("gtm_data", {})))

        elif key == "gads_data":
            parts.append("=== GOOGLE ADS DATA ===")
            parts.append(_format_wizard_full(deep_wizard_block.get("gads_data", {})))

        elif key == "meta_data":
            parts.append("=== META DATA ===")
            parts.append(_format_wizard_full(deep_wizard_block.get("meta_data", {})))

        elif key == "gsc_data":
            parts.append("=== GSC DATA ===")
            parts.append(_format_wizard_full(deep_wizard_block.get("gsc_data", {})))

        # Discovery signals
        elif key == "discovery_consent_signals":
            parts.append("=== DISCOVERY: Consent Signals ===")
            if isinstance(discovery_block, dict):
                signals = discovery_block.get("consent_signals", discovery_block.get("consent", ""))
                parts.append(str(signals)[:3000])
            elif isinstance(discovery_block, str):
                parts.append(discovery_block[:3000])

        elif key == "discovery_tag_managers":
            parts.append("=== DISCOVERY: Tag Managers ===")
            if isinstance(discovery_block, dict):
                tms = discovery_block.get("tag_managers", "")
                parts.append(str(tms)[:3000])

        # L2 results
        elif key.startswith("l2_"):
            l2_type = key[3:]  # strip "l2_" prefix
            result = l2_results.get(l2_type, "") if isinstance(l2_results, dict) else ""
            if result:
                parts.append(f"=== L2 ANALYSIS: {l2_type.upper()} ===")
                parts.append(_format_l2_result(result))

        elif key == "sitemap_cross_check":
            sc = deep_wizard_block.get("gsc_data", {}).get("sitemap_cross_check", {})
            if sc:
                parts.append("=== SITEMAP CROSS-CHECK ===")
                parts.append(json.dumps(sc, ensure_ascii=False, indent=1))

        elif key == "robots_txt":
            rt = deep_wizard_block.get("gsc_data", {}).get("robots_txt", {})
            if rt and rt.get("raw_content"):
                parts.append("=== ROBOTS.TXT ===")
                parts.append(rt["raw_content"][:4000])

        elif key == "phase1_findings":
            if phase1_results:
                parts.append("=== FINDINGS DALLE SEZIONI PRECEDENTI ===")
                for sid, sres in phase1_results.items():
                    if sres.get("success") and sres.get("text"):
                        parts.append(f"\n--- {sid.upper()} ---")
                        parts.append(sres["text"][:3000])

    return "\n\n".join(parts)


# ─── SECTION SYNTHESIZER (Story 10.3) ──────────────────────────────────────

def _synthesize_section(section_id, section_cfg, global_cfg, shared_rules,
                         api_key, data_payload):
    """Run a single section synthesis call.

    Returns:
        dict: {success, text, section_id, input_tokens, output_tokens, cost_usd, model, elapsed}
    """
    model = section_cfg.get("model", global_cfg.get("model_default", "claude-opus-4-6"))
    max_tokens = section_cfg.get("max_tokens", 5000)
    temperature = global_cfg.get("temperature", 0)
    timeout_s = global_cfg.get("timeout_seconds", 120)
    max_retries = global_cfg.get("max_retries", 1)

    system_prompt = shared_rules + "\n\n" + section_cfg.get("system_prompt", "")
    user_message = (
        f"Analizza i seguenti dati e produci la sezione richiesta.\n"
        f"Basa la tua analisi ESCLUSIVAMENTE sui dati forniti.\n\n"
        f"{data_payload}"
    )

    start = time.time()
    try:
        text, usage = _call_claude(
            api_key, system_prompt, user_message,
            model=model, max_tokens=max_tokens,
            temperature=temperature, timeout_s=timeout_s,
            max_retries=max_retries,
        )
        elapsed = time.time() - start

        in_tok = usage.get("input_tokens", 0)
        out_tok = usage.get("output_tokens", 0)
        prices = _PRICES.get(model, _PRICES["claude-opus-4-6"])
        cost = (in_tok * prices["input"]) + (out_tok * prices["output"])

        return {
            "success": True,
            "text": text,
            "section_id": section_id,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cost_usd": round(cost, 4),
            "model": model,
            "elapsed": round(elapsed, 1),
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "success": False,
            "text": "",
            "error": str(e),
            "section_id": section_id,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0,
            "model": model,
            "elapsed": round(elapsed, 1),
        }


# ─── ASSEMBLER (Story 10.4) ────────────────────────────────────────────────

def _assemble_synthesis(section_results, section_order):
    """Concatenate section outputs into final synthesis result.

    Returns: dict compatible with run_synthesis() return format.
    """
    parts = []
    total_in = 0
    total_out = 0
    total_cost = 0.0
    models_used = set()
    success_count = 0

    for sid in section_order:
        res = section_results.get(sid)
        if not res:
            continue
        if res.get("success") and res.get("text"):
            parts.append(res["text"])
            success_count += 1
        total_in += res.get("input_tokens", 0)
        total_out += res.get("output_tokens", 0)
        total_cost += res.get("cost_usd", 0)
        if res.get("model"):
            models_used.add(res["model"])

    return {
        "synthesis_text": "\n\n---\n\n".join(parts),
        "success": success_count > 0,
        "section_results": section_results,
        "sections_ok": success_count,
        "sections_total": len(section_order),
        "input_tokens": total_in,
        "output_tokens": total_out,
        "cost_usd": round(total_cost, 4),
        "model": ", ".join(sorted(models_used)),
    }


# ─── PUBLIC API ─────────────────────────────────────────────────────────────

def run_synthesis(deep_wizard_block, discovery_block, l2_results, trust_result):
    """Run Act 3 — Sectional synthesis (ADR-6).

    Phase 1: parallel section calls (exec_summary, trust, gap, platforms)
    Phase 2: sequential technical_appendix (needs Phase 1 output)

    Falls back to legacy monolithic synthesis if synthesis_sections config not found.

    Args:
        deep_wizard_block: Accumulated wizard data (ADR-1 dict)
        discovery_block: L0 auto_discover() output
        l2_results: Dict of L2 AI analysis results
        trust_result: Trust Score from trust_score.calculate_trust_score()

    Returns:
        dict with synthesis_text, section_results, cost info (NFR17 fallback on error)
    """
    print("\n  🧠 Avvio sintesi sezionale (Act 3 — ADR-6)...")

    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY", "")
    if not api_key:
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "credentials", ".env")
        if os.path.exists(env_path):
            with open(env_path) as _ef:
                for _line in _ef:
                    _line = _line.strip()
                    if _line.startswith("CLAUDE_API_KEY=") or _line.startswith("ANTHROPIC_API_KEY="):
                        api_key = _line.split("=", 1)[1].strip()
                        break
    if not api_key:
        print("  ⚠ API key non trovata (ANTHROPIC_API_KEY / CLAUDE_API_KEY) — sintesi saltata")
        return _fallback_result("API key mancante")

    sections_cfg = _load_sections_config()
    if not sections_cfg:
        print("  ⚠ synthesis_sections non trovato — fallback a sintesi legacy")
        return _run_legacy_synthesis(api_key, deep_wizard_block, discovery_block, l2_results, trust_result)

    shared_rules = sections_cfg.get("shared_rules", "")
    sections = sections_cfg.get("sections", {})
    section_order = sections_cfg.get("section_order", list(sections.keys()))
    max_workers = sections_cfg.get("parallel_workers", 4)
    platforms = deep_wizard_block.get("business_profile", {}).get("platforms", [])

    # Separate Phase 1 and Phase 2 sections
    phase1_ids = [sid for sid in section_order
                  if sections.get(sid, {}).get("phase", 1) == 1]
    phase2_ids = [sid for sid in section_order
                  if sections.get(sid, {}).get("phase", 1) == 2]

    # Filter by requires_platform
    def _should_run(sid):
        req = sections.get(sid, {}).get("requires_platform")
        if req and req not in platforms:
            return False
        return True

    phase1_ids = [sid for sid in phase1_ids if _should_run(sid)]
    phase2_ids = [sid for sid in phase2_ids if _should_run(sid)]

    total_sections = len(phase1_ids) + len(phase2_ids)
    print(f"  ℹ {total_sections} sezioni da sintetizzare ({len(phase1_ids)} Phase 1 + {len(phase2_ids)} Phase 2)")

    section_results = {}
    start_total = time.time()

    # ── Phase 1: Parallel ──
    print(f"  🚀 Phase 1: {len(phase1_ids)} sezioni in parallelo (max_workers={max_workers})...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for sid in phase1_ids:
            scfg = sections.get(sid, {})
            data_keys = scfg.get("data_keys", [])
            data_payload = _build_section_data(
                sid, data_keys, deep_wizard_block,
                discovery_block, l2_results, trust_result,
            )
            future = executor.submit(
                _synthesize_section, sid, scfg, sections_cfg, shared_rules,
                api_key, data_payload,
            )
            futures[future] = sid

        for future in as_completed(futures):
            sid = futures[future]
            try:
                result = future.result(timeout=180)
                section_results[sid] = result
                status = "✓" if result.get("success") else "✗"
                model_short = result.get("model", "?").split("-")[-1]
                print(f"    {status} {sid} ({result.get('elapsed', 0)}s, {model_short}, ${result.get('cost_usd', 0):.3f})")
            except Exception as e:
                section_results[sid] = {"success": False, "error": str(e), "section_id": sid,
                                         "input_tokens": 0, "output_tokens": 0, "cost_usd": 0}
                print(f"    ✗ {sid} (errore: {e})")

    # ── Phase 2: Sequential (needs Phase 1 output) ──
    if phase2_ids:
        print(f"  🔧 Phase 2: {len(phase2_ids)} sezioni sequenziali...")
        for sid in phase2_ids:
            scfg = sections.get(sid, {})
            data_keys = scfg.get("data_keys", [])
            data_payload = _build_section_data(
                sid, data_keys, deep_wizard_block,
                discovery_block, l2_results, trust_result,
                phase1_results=section_results,
            )
            result = _synthesize_section(sid, scfg, sections_cfg, shared_rules,
                                          api_key, data_payload)
            section_results[sid] = result
            status = "✓" if result.get("success") else "✗"
            model_short = result.get("model", "?").split("-")[-1]
            print(f"    {status} {sid} ({result.get('elapsed', 0)}s, {model_short}, ${result.get('cost_usd', 0):.3f})")

    # ── Assemble ──
    assembled = _assemble_synthesis(section_results, section_order)
    elapsed_total = time.time() - start_total

    print(f"\n  ✓ Sintesi completata in {elapsed_total:.1f}s ({assembled['sections_ok']}/{assembled['sections_total']} sezioni)")
    print(f"  ℹ Token totali: {assembled['input_tokens']:,} input + {assembled['output_tokens']:,} output")
    print(f"  ℹ Costo Act 3: ${assembled['cost_usd']:.4f} ({assembled['model']})")

    assembled["elapsed_seconds"] = round(elapsed_total, 1)
    return assembled


# ─── LEGACY FALLBACK (pre-ADR-6) ───────────────────────────────────────────

def _run_legacy_synthesis(api_key, deep_wizard_block, discovery_block, l2_results, trust_result):
    """Legacy monolithic synthesis — used only if synthesis_sections config missing."""
    config = _load_legacy_config()
    if not config:
        config = {"model": "claude-opus-4-6", "temperature": 0,
                  "max_tokens": 32000, "timeout_seconds": 300, "max_retries": 2}

    system_prompt = config.get("system_prompt", _FALLBACK_SYSTEM_PROMPT)
    user_template = config.get("user_prompt_template", "Ecco i dati. Produci la sintesi.\n\n{{data}}")

    # Build legacy mega-prompt
    sections = []
    sections.append("=== BUSINESS PROFILE ===")
    sections.append(json.dumps(deep_wizard_block.get("business_profile", {}), ensure_ascii=False, indent=2))
    sections.append("\n=== TRUST SCORE ===")
    sections.append(json.dumps(trust_result or {}, ensure_ascii=False, indent=2))
    for key in WIZARD_KEYS:
        data = deep_wizard_block.get(key, {})
        if data:
            sections.append(f"\n--- {key.upper()} ---")
            sections.append(json.dumps(data, ensure_ascii=False, indent=2))
    if isinstance(l2_results, dict):
        for atype, result in l2_results.items():
            sections.append(f"\n--- L2: {atype.upper()} ---")
            sections.append(_format_l2_result(result))

    data_payload = "\n".join(sections)
    user_message = user_template.replace("{{data}}", data_payload)

    start = time.time()
    try:
        text, usage = _call_claude(
            api_key, system_prompt, user_message,
            model=config.get("model", "claude-opus-4-6"),
            max_tokens=config.get("max_tokens", 32000),
            temperature=config.get("temperature", 0),
            timeout_s=config.get("timeout_seconds", 300),
            max_retries=config.get("max_retries", 2),
        )
        elapsed = time.time() - start
        in_tok = usage.get("input_tokens", 0)
        out_tok = usage.get("output_tokens", 0)
        prices = _PRICES.get(config.get("model", "claude-opus-4-6"), _PRICES["claude-opus-4-6"])
        cost = (in_tok * prices["input"]) + (out_tok * prices["output"])

        print(f"  ✓ Sintesi legacy completata in {elapsed:.1f}s")
        print(f"  ℹ Token: {in_tok:,} input + {out_tok:,} output — ${cost:.4f}")

        return {
            "synthesis_text": text, "success": True,
            "elapsed_seconds": round(elapsed, 1),
            "input_tokens": in_tok, "output_tokens": out_tok,
            "cost_usd": round(cost, 4), "model": config.get("model", "claude-opus-4-6"),
        }
    except Exception as e:
        elapsed = time.time() - start
        print(f"  ⚠ Errore sintesi legacy dopo {elapsed:.1f}s: {e}")
        return _fallback_result(str(e))


def _fallback_result(reason):
    """Return partial result when synthesis fails (NFR17)."""
    return {
        "synthesis_text": "", "success": False, "error": reason,
        "elapsed_seconds": 0, "input_tokens": 0, "output_tokens": 0,
        "cost_usd": 0, "model": "",
    }


_FALLBACK_SYSTEM_PROMPT = (
    "Sei un senior MarTech consultant con 15+ anni di esperienza in digital analytics, "
    "conversion tracking e advertising technology. Produci un'analisi di sintesi cross-platform "
    "in italiano, con tono professionale e actionable."
)
