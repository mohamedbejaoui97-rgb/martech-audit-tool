"""Act 3 — Opus synthesis mega-prompt orchestration.

Reads synthesis prompt template from osmani-config.json (ADR-3),
populates with all collected data, sends to Claude Opus 4.6.
FRs: FR51, FR60.  NFRs: NFR4, NFR7, NFR11, NFR17, NFR21, NFR22.
"""

import json
import os
import time
import urllib.request
import urllib.error
import ssl

# ─── PATHS ──────────────────────────────────────────────────────────────────

CLI_DIR = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(os.path.dirname(CLI_DIR))
CONFIG_PATH = os.path.join(TOOL_DIR, "data", "reference", "osmani-config.json")

# Secure SSL context for API calls
_CTX_SECURE = ssl.create_default_context()

# ─── PRICING (per-token, USD, Opus 4.6) ─────────────────────────────────────

_PRICE_INPUT = 15.0 / 1_000_000   # $15/M input tokens
_PRICE_OUTPUT = 75.0 / 1_000_000  # $75/M output tokens


# ─── CONFIG LOADER ──────────────────────────────────────────────────────────

def _load_synthesis_config():
    """Load synthesis_prompt config from osmani-config.json (ADR-3)."""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        return cfg.get("synthesis_prompt", {})
    except Exception:
        return {}


# ─── API CALL ───────────────────────────────────────────────────────────────

def _call_opus(api_key, system_prompt, user_message, config):
    """Call Claude Opus API with configurable timeout and retry (NFR4, NFR11).

    Returns:
        tuple: (response_text, usage_dict)
    """
    model = config.get("model", "claude-opus-4-6")
    max_tokens = config.get("max_tokens", 16000)
    temperature = config.get("temperature", 0)
    timeout_s = config.get("timeout_seconds", 300)
    max_retries = config.get("max_retries", 2)

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
                print(f"  ⏳ Opus API {e.code}, retry {attempt+1}/{max_retries} tra {wait:.1f}s...")
                time.sleep(wait)
                continue
            raise RuntimeError(f"Claude Opus API error {e.code}: {body[:500]}") from e
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            raise RuntimeError(f"Claude Opus API parse error: {e}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < max_retries:
                wait = (2 ** attempt) + 1
                print(f"  ⏳ Opus timeout/network error, retry {attempt+1}/{max_retries} tra {wait:.1f}s...")
                time.sleep(wait)
                continue
            raise RuntimeError(f"Claude Opus API network error: {e}") from e

    raise RuntimeError("Claude Opus API: max retries exceeded")


# ─── PROMPT BUILDER ─────────────────────────────────────────────────────────

def _build_user_message(deep_wizard_block, discovery_block, l2_results, trust_result):
    """Build the mega-prompt user message with all collected data (FR51)."""
    sections = []

    sections.append("=== BUSINESS PROFILE ===")
    sections.append(json.dumps(deep_wizard_block.get("business_profile", {}), ensure_ascii=False, indent=2))

    sections.append("\n=== DISCOVERY BLOCK (L0 Auto-Discovery) ===")
    if isinstance(discovery_block, str):
        sections.append(discovery_block[:15000])  # cap to avoid token explosion
    else:
        sections.append(json.dumps(discovery_block, ensure_ascii=False, indent=2)[:15000])

    sections.append("\n=== WIZARD DATA (Deep Mode Interviews) ===")
    wizard_keys = ["iubenda_data", "gtm_data", "gads_data", "meta_data", "gsc_data"]
    for key in wizard_keys:
        data = deep_wizard_block.get(key, {})
        if data:
            sections.append(f"\n--- {key.upper()} ---")
            sections.append(json.dumps(data, ensure_ascii=False, indent=2))

    sections.append("\n=== TRUST SCORE ===")
    sections.append(json.dumps(trust_result, ensure_ascii=False, indent=2))

    sections.append("\n=== L2 AI ANALYSES (11 Claude Analyses) ===")
    if isinstance(l2_results, dict):
        for atype, result in l2_results.items():
            sections.append(f"\n--- {atype.upper()} ---")
            if isinstance(result, str):
                sections.append(result[:5000])  # cap per analysis
            else:
                sections.append(json.dumps(result, ensure_ascii=False, indent=2)[:5000])
    elif isinstance(l2_results, str):
        sections.append(l2_results[:50000])

    return "\n".join(sections)


# ─── PUBLIC API ─────────────────────────────────────────────────────────────

def run_synthesis(deep_wizard_block, discovery_block, l2_results, trust_result):
    """Run Act 3 Opus synthesis — mega-prompt orchestration.

    Args:
        deep_wizard_block: Accumulated wizard data (ADR-1 dict)
        discovery_block: L0 auto_discover() output
        l2_results: Dict of 11 L2 AI analysis results
        trust_result: Trust Score output from trust_score.calculate_trust_score()

    Returns:
        dict with synthesis_text, cost info, or partial fallback (NFR17)
    """
    print("\n  🧠 Avvio sintesi Opus (Act 3)...")

    # Read API key from env (NFR7)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("  ⚠ ANTHROPIC_API_KEY non configurata — sintesi saltata")
        return _fallback_result("API key mancante")

    # Load config (ADR-3)
    config = _load_synthesis_config()
    if not config:
        print("  ⚠ synthesis_prompt non trovato in osmani-config.json — uso config default")
        config = {
            "model": "claude-opus-4-6",
            "temperature": 0,
            "max_tokens": 16000,
            "timeout_seconds": 300,
            "max_retries": 2,
        }

    system_prompt = config.get("system_prompt", _FALLBACK_SYSTEM_PROMPT)
    user_template = config.get("user_prompt_template", "Ecco tutti i dati raccolti. Produci la sintesi completa.\n\n{{data}}")

    # Build user message
    data_payload = _build_user_message(deep_wizard_block, discovery_block, l2_results, trust_result)
    user_message = user_template.replace("{{data}}", data_payload)

    # Call Opus (NFR4, NFR22)
    start = time.time()
    try:
        response_text, usage = _call_opus(api_key, system_prompt, user_message, config)
        elapsed = time.time() - start

        # Cost calculation (FR60, NFR21)
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cost = (input_tokens * _PRICE_INPUT) + (output_tokens * _PRICE_OUTPUT)

        print(f"  ✓ Sintesi completata in {elapsed:.1f}s")
        print(f"  ℹ Token: {input_tokens:,} input + {output_tokens:,} output")
        print(f"  ℹ Costo Act 3: ${cost:.4f}")

        return {
            "synthesis_text": response_text,
            "success": True,
            "elapsed_seconds": round(elapsed, 1),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 4),
            "model": config.get("model", "claude-opus-4-6"),
        }

    except Exception as e:
        elapsed = time.time() - start
        print(f"  ⚠ Errore sintesi Opus dopo {elapsed:.1f}s: {e}")
        print("  ℹ Proseguo con report parziale senza sintesi narrativa (NFR17)")
        return _fallback_result(str(e))


def _fallback_result(reason):
    """Return partial result when synthesis fails (NFR17)."""
    return {
        "synthesis_text": "",
        "success": False,
        "error": reason,
        "elapsed_seconds": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0,
        "model": "",
    }


# ─── FALLBACK SYSTEM PROMPT ────────────────────────────────────────────────

_FALLBACK_SYSTEM_PROMPT = (
    "Sei un senior MarTech consultant con 15+ anni di esperienza in digital analytics, "
    "conversion tracking e advertising technology. Produci un'analisi di sintesi cross-platform "
    "in italiano, con tono professionale e actionable."
)
