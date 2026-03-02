"""MarTech Audit Tool — Web App Backend.

FastAPI server that reuses CLI deep mode logic with a web UI.
Run: uvicorn app:app --reload
"""

import os
import sys
import json
import time
import uuid
import shutil
import asyncio
import importlib
import traceback
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

# ─── PATHS ──────────────────────────────────────────────────────────────────

WEBAPP_DIR = Path(__file__).parent.resolve()
TOOL_DIR = WEBAPP_DIR.parent
CLI_DIR = TOOL_DIR / "cli"
DEEP_DIR = CLI_DIR / "deep"
OUTPUT_DIR = TOOL_DIR / "output"
EVIDENCE_DIR = OUTPUT_DIR / "evidence"
CREDENTIALS_ENV = TOOL_DIR / "credentials" / ".env"


def _load_api_keys():
    """Load API keys from environment or credentials/.env fallback."""
    keys = {}
    for name in ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "GOOGLE_API_KEY"):
        val = os.environ.get(name, "")
        if val:
            keys[name] = val
    if not keys.get("ANTHROPIC_API_KEY") and not keys.get("CLAUDE_API_KEY"):
        if CREDENTIALS_ENV.exists():
            with open(CREDENTIALS_ENV) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if k in ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "GOOGLE_API_KEY"):
                            keys.setdefault(k, v)
    # Normalize: prefer ANTHROPIC over CLAUDE
    if not keys.get("ANTHROPIC_API_KEY") and keys.get("CLAUDE_API_KEY"):
        keys["ANTHROPIC_API_KEY"] = keys["CLAUDE_API_KEY"]
    return keys


_API_KEYS = _load_api_keys()

# Add CLI dir to path so we can import cli-audit and deep modules
if str(CLI_DIR) not in sys.path:
    sys.path.insert(0, str(CLI_DIR))
if str(CLI_DIR.parent) not in sys.path:
    sys.path.insert(0, str(CLI_DIR.parent))

# ─── LAZY IMPORTS (from CLI codebase) ───────────────────────────────────────

_cli_audit = None
_trust_score = None
_synthesis = None
_report_deep = None


def _get_cli_audit():
    global _cli_audit
    if _cli_audit is None:
        _cli_audit = importlib.import_module("cli-audit")
    return _cli_audit


def _get_trust_score():
    global _trust_score
    if _trust_score is None:
        _trust_score = importlib.import_module("deep.trust_score")
    return _trust_score


def _get_synthesis():
    global _synthesis
    if _synthesis is None:
        _synthesis = importlib.import_module("deep.synthesis")
    return _synthesis


def _get_report_deep():
    global _report_deep
    if _report_deep is None:
        _report_deep = importlib.import_module("deep.report_deep")
    return _report_deep


# ─── APP ────────────────────────────────────────────────────────────────────

app = FastAPI(title="MarTech Audit Tool")

# Serve static files
app.mount("/static", StaticFiles(directory=str(WEBAPP_DIR / "static")), name="static")

# In-memory audit sessions
_sessions: dict = {}


# ─── MODELS / HELPERS ───────────────────────────────────────────────────────

def _emit(session_id: str, step: str, status: str, detail: str = "",
          progress: int = -1, data: dict = None):
    """Push a progress event to the session queue."""
    event = {"step": step, "status": status, "detail": detail,
             "progress": progress, "ts": time.time()}
    if data:
        event["data"] = data
    session = _sessions.get(session_id)
    if session and "queue" in session:
        session["queue"].append(event)


def _parse_gtm_json(raw: str) -> dict:
    """Parse GTM container JSON (3 variants: raw export, containerVersion, array)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try stripping BOM / banner
        cleaned = raw.strip()
        if cleaned.startswith('\ufeff'):
            cleaned = cleaned[1:]
        data = json.loads(cleaned)

    # Variant 1: direct export {"exportFormatVersion": 2, "containerVersion": {...}}
    if isinstance(data, dict) and "containerVersion" in data:
        return data["containerVersion"]
    # Variant 2: {"containerVersion": {"tag": [...]}}
    if isinstance(data, dict) and "tag" in data:
        return data
    # Variant 3: array wrapper
    if isinstance(data, list) and len(data) > 0:
        return data[0].get("containerVersion", data[0]) if isinstance(data[0], dict) else data[0]
    return data


# ─── WIZARD CONSTANTS ENDPOINT ──────────────────────────────────────────────

@app.get("/api/constants")
def get_constants():
    """Return wizard constants for frontend form population."""
    from deep.step_zero import BUSINESS_TYPES, PLATFORMS, PLATFORM_KEYS, PLATFORM_DESCRIPTIONS
    from deep.wizard_iubenda import (
        CONSENT_MODE_OPTIONS, BANNER_SERVICES,
    )
    from deep.wizard_gtm import ECOMMERCE_EVENTS, LEAD_GEN_EVENTS, CRITICAL_CHECKS
    from deep.wizard_gads import (
        CONVERSION_SOURCES, CONVERSION_COUNTING, CONVERSION_STATUS_OPTIONS,
        CONSENT_MODE_DIAG_OPTIONS, ENHANCED_CONV_DIAG_OPTIONS,
        ATTRIBUTION_MODEL_OPTIONS, ECOMMERCE_FUNNEL, LEAD_GEN_FUNNEL,
    )
    from deep.wizard_meta import (
        CAPI_OPTIONS, ATTRIBUTION_WINDOW_OPTIONS,
        EVENT_STATUS_OPTIONS,
        ECOMMERCE_EVENTS as META_ECOM_EVENTS,
        LEAD_GEN_EVENTS as META_LEAD_EVENTS,
    )
    from deep.wizard_gsc import (
        SITEMAP_OPTIONS, NON_INDEXING_REASONS,
    )

    return {
        "business_types": BUSINESS_TYPES,
        "platforms": PLATFORMS,
        "platform_keys": PLATFORM_KEYS,
        "platform_descriptions": PLATFORM_DESCRIPTIONS,
        "iubenda": {
            "consent_mode_options": CONSENT_MODE_OPTIONS,
            "banner_services": BANNER_SERVICES,
        },
        "gtm": {
            "ecommerce_events": ECOMMERCE_EVENTS,
            "lead_gen_events": LEAD_GEN_EVENTS,
            "critical_checks": list(CRITICAL_CHECKS.keys()),
        },
        "gads": {
            "conversion_sources": CONVERSION_SOURCES,
            "conversion_counting": CONVERSION_COUNTING,
            "conversion_status_options": CONVERSION_STATUS_OPTIONS,
            "consent_mode_diag_options": CONSENT_MODE_DIAG_OPTIONS,
            "enhanced_conv_diag_options": ENHANCED_CONV_DIAG_OPTIONS,
            "attribution_model_options": ATTRIBUTION_MODEL_OPTIONS,
            "ecommerce_funnel": ECOMMERCE_FUNNEL,
            "lead_gen_funnel": LEAD_GEN_FUNNEL,
        },
        "meta": {
            "capi_options": CAPI_OPTIONS,
            "attribution_window_options": ATTRIBUTION_WINDOW_OPTIONS,
            "event_status_options": EVENT_STATUS_OPTIONS,
            "ecommerce_events": META_ECOM_EVENTS,
            "lead_gen_events": META_LEAD_EVENTS,
        },
        "gsc": {
            "sitemap_options": SITEMAP_OPTIONS,
            "non_indexing_reasons": NON_INDEXING_REASONS,
        },
    }


# ─── FILE UPLOADS ───────────────────────────────────────────────────────────

@app.post("/api/upload/gtm")
async def upload_gtm(file: UploadFile = File(...)):
    """Upload and parse GTM container JSON."""
    try:
        raw = (await file.read()).decode("utf-8")
        parsed = _parse_gtm_json(raw)
        tags = parsed.get("tag", [])
        triggers = parsed.get("trigger", [])
        variables = parsed.get("variable", [])
        return {
            "success": True,
            "summary": {
                "tags_count": len(tags),
                "triggers_count": len(triggers),
                "variables_count": len(variables),
                "tag_names": [t.get("name", "?") for t in tags[:50]],
            },
            "parsed": parsed,
        }
    except Exception as e:
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})


@app.post("/api/upload/gsc")
async def upload_gsc(files: list[UploadFile] = File(...)):
    """Upload GSC CSV files, return parsed summary."""
    results = []
    for f in files:
        try:
            raw = (await f.read()).decode("utf-8")
            lines = raw.strip().split("\n")
            results.append({
                "filename": f.filename,
                "rows": max(0, len(lines) - 1),
                "headers": lines[0] if lines else "",
                "success": True,
            })
        except Exception as e:
            results.append({"filename": f.filename, "success": False, "error": str(e)})
    return {"files": results}


@app.post("/api/upload/evidence")
async def upload_evidence(wizard_name: str = Form(...), files: list[UploadFile] = File(...)):
    """Upload evidence screenshots for a wizard."""
    dest_dir = EVIDENCE_DIR / wizard_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in files:
        dest = dest_dir / f.filename
        with open(dest, "wb") as out:
            out.write(await f.read())
        saved.append(str(dest))
    return {"saved": saved, "count": len(saved)}


# ─── AUDIT EXECUTION ───────────────────────────────────────────────────────

def _run_audit_sync(session_id: str, config: dict, wizard_data: dict):
    """Run the full audit pipeline synchronously (called in thread)."""
    emit = lambda step, status, detail="", progress=-1, data=None: \
        _emit(session_id, step, status, detail, progress, data)

    session = _sessions[session_id]
    results = session["results"]
    business_profile = config["business_profile"]
    url = business_profile["url"]
    domain = url.replace("https://", "").replace("http://", "").rstrip("/")

    try:
        cli_audit = _get_cli_audit()

        # ── L0: auto_discover ──
        emit("l0", "running", "Avvio discovery L0...")
        try:
            discovery_block, homepage_html, resp_headers, extra_htmls = \
                cli_audit.auto_discover(domain, [], use_render=False)
            emit("l0", "done", f"Discovery completata: {len(discovery_block)} segnali")
            results["discovery_block"] = discovery_block
        except Exception as e:
            emit("l0", "error", str(e))
            discovery_block = {}
            homepage_html = ""
            extra_htmls = {}

        # ── SquirrelScan ──
        emit("squirrelscan", "running", "SquirrelScan in corso...")
        try:
            scan_data = cli_audit.run_squirrelscan(domain)
            if scan_data:
                cli_audit.squirrelscan_to_discovery(scan_data, discovery_block)
                emit("squirrelscan", "done", f"SquirrelScan completato")
            else:
                emit("squirrelscan", "done", "SquirrelScan: nessun dato")
        except Exception as e:
            emit("squirrelscan", "error", str(e))

        # ── Build deep_wizard_block from wizard_data ──
        deep_wizard_block = {"business_profile": business_profile}
        for platform in business_profile.get("platforms", []):
            key = f"{platform}_data"
            if key in wizard_data and wizard_data[key]:
                deep_wizard_block[key] = wizard_data[key]

        # ── Trust Score ──
        emit("trust_score", "running", "Calcolo Trust Score...")
        try:
            ts = _get_trust_score()
            trust_result = ts.calculate_trust_score(deep_wizard_block)
            gap_revenue = ts.calculate_gap_to_revenue(deep_wizard_block)
            consent_chain = ts.build_consent_impact_chain(deep_wizard_block)
            attr_comparison = ts.compare_attribution_windows(deep_wizard_block)
            leverage_nodes = ts.identify_leverage_nodes(gap_revenue)

            deep_wizard_block["trust_score"] = trust_result
            deep_wizard_block["gap_to_revenue"] = gap_revenue
            deep_wizard_block["consent_impact_chain"] = consent_chain
            deep_wizard_block["attribution_comparison"] = attr_comparison
            deep_wizard_block["leverage_nodes"] = leverage_nodes

            emit("trust_score", "done",
                 f"Trust Score: {trust_result.get('score', 0)}/100 ({trust_result.get('grade', 'N/A')})",
                 data={"score": trust_result.get("score", 0), "grade": trust_result.get("grade", "N/A")})
            results["trust_result"] = trust_result
            results["gap_revenue"] = gap_revenue
        except Exception as e:
            emit("trust_score", "error", str(e))
            trust_result = {}

        # ── L2 AI Analyses ──
        api_key = _API_KEYS.get("ANTHROPIC_API_KEY", "")
        l2_results = {}
        if api_key:
            analysis_types = ['performance', 'cwv', 'seo', 'seo_deep',
                              'robots', 'sitemap', 'datalayer', 'cro', 'advertising']
            google_key = _API_KEYS.get("GOOGLE_API_KEY", "")
            hp_html = extra_htmls.get("homepage", "") if isinstance(extra_htmls, dict) else homepage_html

            emit("l2", "running", f"Avvio {len(analysis_types)} analisi L2...", progress=0)
            completed = 0

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {
                    executor.submit(
                        cli_audit.run_analysis, atype, url, api_key, google_key,
                        hp_html, extra_htmls, discovery_block
                    ): atype for atype in analysis_types
                }
                from concurrent.futures import as_completed
                for future in as_completed(futures):
                    atype = futures[future]
                    try:
                        res_type, res_text = future.result(timeout=180)
                        l2_results[res_type] = res_text
                    except Exception as e:
                        l2_results[atype] = f"Errore: {e}"
                    completed += 1
                    pct = int(completed / len(analysis_types) * 100)
                    emit("l2", "running", f"{completed}/{len(analysis_types)} completate ({atype})", progress=pct)

            emit("l2", "done", f"{len(l2_results)} analisi completate")
        else:
            emit("l2", "skipped", "ANTHROPIC_API_KEY non configurata")

        results["l2_results"] = l2_results

        # ── Synthesis ──
        emit("synthesis", "running", "Synthesis Opus in corso...")
        try:
            syn = _get_synthesis()
            synthesis_result = syn.run_synthesis(deep_wizard_block, discovery_block, l2_results, trust_result)
            emit("synthesis", "done", "Synthesis completata")
            results["synthesis_result"] = synthesis_result
        except Exception as e:
            emit("synthesis", "error", str(e))
            synthesis_result = {"synthesis_text": "", "section_results": {}}

        # ── Report Generation ──
        emit("report", "running", "Generazione report McKinsey...")
        try:
            rpt = _get_report_deep()
            report_path = rpt.generate_deep_report(
                synthesis_result, deep_wizard_block, trust_result,
                l2_results=l2_results,
            )
            results["report_path"] = report_path
            emit("report", "done", "Report generato", data={"report_path": report_path})
        except Exception as e:
            emit("report", "error", str(e))

        # ── Done ──
        emit("complete", "done", "Audit completato!")
        session["status"] = "done"

    except Exception as e:
        emit("error", "error", f"Errore fatale: {e}\n{traceback.format_exc()}")
        session["status"] = "error"


@app.post("/api/audit/start")
async def start_audit(request: Request):
    """Start the audit pipeline in a background thread."""
    body = await request.json()
    config = body.get("config", {})
    wizard_data = body.get("wizard_data", {})

    session_id = str(uuid.uuid4())[:8]
    _sessions[session_id] = {
        "status": "running",
        "queue": [],
        "results": {},
        "started_at": time.time(),
    }

    # Run in background thread
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _run_audit_sync, session_id, config, wizard_data)

    return {"session_id": session_id}


@app.get("/api/audit/progress/{session_id}")
async def audit_progress(session_id: str):
    """SSE stream of audit progress events."""
    async def event_generator():
        if session_id not in _sessions:
            yield {"event": "error", "data": json.dumps({"error": "Session not found"})}
            return

        sent = 0
        while True:
            session = _sessions.get(session_id)
            if not session:
                break

            queue = session["queue"]
            while sent < len(queue):
                yield {"event": "progress", "data": json.dumps(queue[sent])}
                sent += 1

            if session["status"] in ("done", "error"):
                yield {"event": "done", "data": json.dumps({"status": session["status"]})}
                break

            await asyncio.sleep(0.3)

    return EventSourceResponse(event_generator())


@app.get("/api/audit/result/{session_id}")
def get_result(session_id: str):
    """Return final audit results."""
    session = _sessions.get(session_id)
    if not session:
        return JSONResponse(status_code=404, content={"error": "Session not found"})

    results = session.get("results", {})
    trust = results.get("trust_result", {})
    gap = results.get("gap_revenue", {})
    report_path = results.get("report_path", "")

    return {
        "status": session["status"],
        "trust_score": trust.get("score"),
        "trust_grade": trust.get("grade"),
        "trust_coverage": trust.get("coverage_label"),
        "trust_pillars": trust.get("pillars"),
        "gap_to_revenue": gap,
        "report_path": report_path,
        "report_filename": os.path.basename(report_path) if report_path else None,
    }


@app.get("/api/report/{filename}")
def download_report(filename: str):
    """Download generated report HTML."""
    path = OUTPUT_DIR / filename
    if not path.exists() or not path.is_file():
        return JSONResponse(status_code=404, content={"error": "Report not found"})
    return FileResponse(str(path), media_type="text/html", filename=filename)


# ─── FRONTEND ───────────────────────────────────────────────────────────────

@app.get("/")
def index():
    """Serve the SPA."""
    return FileResponse(str(WEBAPP_DIR / "static" / "index.html"))


# ─── MAIN ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
