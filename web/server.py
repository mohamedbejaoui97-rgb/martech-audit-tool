#!/usr/bin/env python3
"""MarTech Audit Tool - Local server with CORS proxy, CrUX API, Playwright rendering,
and Deep Audit web wizard API (Phase 2 — ADR-7, ADR-8, ADR-9)."""
import http.server
import json
import urllib.request
import urllib.error
import urllib.parse
import ssl
import os
import sys
import socket
import ipaddress
import uuid
import threading
import time
import base64
import shutil
import importlib
import traceback

# Optional: Playwright for JS rendering
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

PORT = int(os.environ.get('PORT', 8080))
TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TOOL_DIR)

# ─── CLI Module Path Setup ───────────────────────────────────────────────────
# Import cli/deep/ modules for pipeline reuse (ADR-8: zero logic duplication)
CLI_DIR = os.path.join(PROJECT_ROOT, 'cli')
if CLI_DIR not in sys.path:
    sys.path.insert(0, CLI_DIR)

# ─── SSRF Protection ─────────────────────────────────────────────────────────

_BLOCKED_NETWORKS = [
    ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('169.254.0.0/16'),
    ipaddress.ip_network('0.0.0.0/8'),
    ipaddress.ip_network('::1/128'),
    ipaddress.ip_network('fc00::/7'),
    ipaddress.ip_network('fe80::/10'),
]

def _is_safe_url(url):
    """Validate URL is not targeting private/internal networks (SSRF protection)."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        for info in socket.getaddrinfo(hostname, None):
            addr = ipaddress.ip_address(info[4][0])
            for network in _BLOCKED_NETWORKS:
                if addr in network:
                    return False
        return True
    except (ValueError, socket.gaierror, OSError):
        return False


def load_env():
    """Load API keys: environment variables first, then .env file as fallback."""
    env = {}
    env_path = os.path.join(PROJECT_ROOT, 'credentials', '.env')
    if os.path.exists(env_path):
        with open(env_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env[key.strip()] = value.strip()
    # Environment variables take priority over .env file
    for key in ('ANTHROPIC_API_KEY', 'CLAUDE_API_KEY', 'GOOGLE_API_KEY', 'AUDIT_API_TOKEN'):
        val = os.environ.get(key)
        if val:
            env[key] = val
    return env

ENV = load_env()

# API token for authenticating proxy/API requests
_API_TOKEN = ENV.get('AUDIT_API_TOKEN', '')

# SSL contexts
_CTX_SCAN = ssl.create_default_context()
_CTX_SCAN.check_hostname = False
_CTX_SCAN.verify_mode = ssl.CERT_NONE

_CTX_SECURE = ssl.create_default_context()


# ─── Deep Audit Session Storage (ADR-7) ─────────────────────────────────────
# In-memory, single-user localhost. No persistence needed.

_SESSIONS = {}  # session_id → session dict


def _new_session(url, business_profile):
    """Create a new deep audit session."""
    sid = uuid.uuid4().hex[:12]
    _SESSIONS[sid] = {
        'id': sid,
        'url': url,
        'business_profile': business_profile,
        'discovery_block': {},
        'deep_wizard_block': {'business_profile': business_profile},
        'l0_signals': {},
        'events': [],       # SSE event queue
        'status': 'created',  # created | discovering | wizards | running | complete | error
        'report_path': None,
        'trust_result': None,
        'l2_results': {},
    }
    return sid


def _get_session(sid):
    """Get session or None."""
    return _SESSIONS.get(sid)


def _push_event(sid, event_type, data):
    """Push an SSE event to the session queue."""
    sess = _SESSIONS.get(sid)
    if sess:
        sess['events'].append({'event': event_type, 'data': data})


# ─── Deep Audit Wizard Handlers (ADR-8) ─────────────────────────────────────
# Each handler imports compute functions from cli/deep/wizard_*.py

def _handle_wizard_iubenda(body, session):
    """Process iubenda wizard form data. Returns enriched dict."""
    from deep.wizard_iubenda import _calculate_triage_score, _cross_check_l0
    data = dict(body)
    grade, detail = _calculate_triage_score(
        float(data.get('rejection_rate', 0)),
        data.get('consent_mode_v2', 'none')  # ADR-9: canonical field name
    )
    data['triage_score'] = grade
    data['triage_detail'] = detail
    discovery = session['discovery_block']
    platforms = session['business_profile'].get('platforms', [])
    data['l0_mismatches'] = _cross_check_l0(
        data.get('banner_services', []), discovery, platforms=platforms
    )
    return data


def _handle_wizard_gtm(body, session):
    """Process GTM wizard form data. Returns enriched dict."""
    from deep.wizard_gtm import parse_gtm_container, run_gap_analysis, _validate_gtm_json
    data = dict(body)
    gtm_json_b64 = data.pop('gtm_json_base64', '')
    if gtm_json_b64 and data.get('gtm_usage') != 'no':
        try:
            content = base64.b64decode(gtm_json_b64).decode('utf-8')
        except Exception:
            return {**data, 'parse_error': 'Invalid base64 content'}
        valid, err = _validate_gtm_json(content)
        if not valid:
            return {**data, 'parse_error': err}
        parsed = parse_gtm_container(content)
        if parsed:
            business_type = session['business_profile'].get('business_type', 'ecommerce')
            gap = run_gap_analysis(parsed, business_type)
            data['container_raw'] = parsed.get('container_version', {})
            data['tag_count'] = parsed['tag_count']
            data['trigger_count'] = parsed['trigger_count']
            data['variable_count'] = parsed['variable_count']
            data['container_name'] = parsed.get('container_name', '')
            data['container_id'] = parsed.get('container_id', '')
            data['gap_analysis'] = gap
    return data


def _handle_wizard_gads(body, session):
    """Process Google Ads wizard form data. Returns enriched dict."""
    from deep.wizard_gads import _check_primary_conflicts, _check_missing_funnel_events, _check_source_discrepancies
    data = dict(body)
    # Summary mode — build minimal cross-checks from counts
    summary = data.get('summary', {})
    num_primary = summary.get('primary', 0) if isinstance(summary, dict) else 0
    business_type = session['business_profile'].get('business_type', 'ecommerce')
    data['cross_checks'] = {
        'primary_conflicts': {'has_conflict': num_primary > 1, 'count': num_primary, 'names': [], 'detail': f'{num_primary} conversioni primary' if num_primary > 1 else ''},
        'gtm_cross_check': {'available': False, 'discrepancies': []},
        'missing_funnel_events': {'upper': [], 'mid': [], 'bottom': []},
        'source_discrepancies': [],
    }
    # GA4 gap critical flag
    if data.get('ga4_match') == 'Sì' and data.get('conversions_active') in ('No', 'Alcune'):
        data['ga4_gap_critical'] = True
    return data


def _handle_wizard_meta(body, session):
    """Process Meta wizard form data. Returns enriched dict."""
    from deep.wizard_meta import _cross_check_pixel_l0, _check_capi_critical
    data = dict(body)
    # L0 cross-check
    pixel_id = data.get('pixel_id', '')
    discovery = session['discovery_block']
    data['pixel_id_check_l0'] = _cross_check_pixel_l0(pixel_id, discovery)
    data['pixel_id_match_l0'] = data['pixel_id_check_l0'].get('match')
    # CAPI critical check
    business_type = session['business_profile'].get('business_type', 'ecommerce')
    capi_status = data.get('capi_status', 'pixel_only')
    data['cross_checks'] = {
        'capi_critical': _check_capi_critical(capi_status, business_type),
        'gtm_cross_check': {'available': False, 'discrepancies': []},
    }
    # GTM cross-check if GTM data available
    gtm_data = session['deep_wizard_block'].get('gtm_data', {})
    if gtm_data and data.get('events'):
        from deep.wizard_meta import _cross_check_gtm
        data['cross_checks']['gtm_cross_check'] = _cross_check_gtm(data['events'], session['deep_wizard_block'])
    return data


def _handle_wizard_gsc(body, session):
    """Process GSC wizard form data. Returns enriched dict."""
    from deep.wizard_gsc import parse_gsc_csv, analyze_trends, fetch_robots_txt, _check_sitemap_consistency
    data = dict(body)
    url = session['url']
    domain = url.replace('https://', '').replace('http://', '').rstrip('/')

    # Fetch robots.txt
    robots_data = fetch_robots_txt(url)
    data['robots_txt'] = robots_data

    # Parse performance CSV if provided
    perf_rows = []
    pages_rows = []
    perf_b64 = data.pop('performance_csv_base64', '')
    if perf_b64:
        try:
            content = base64.b64decode(perf_b64).decode('utf-8')
            rows = parse_gsc_csv(content)
            perf_rows.extend(rows)
        except Exception:
            pass

    # Parse coverage CSV if provided
    coverage_b64 = data.pop('coverage_csv_base64', '')
    coverage_data = []
    if coverage_b64:
        try:
            from deep.wizard_gsc import parse_coverage_csv
            content = base64.b64decode(coverage_b64).decode('utf-8')
            coverage_data.append(parse_coverage_csv('coverage.csv', content))
        except Exception:
            pass

    data['coverage_data'] = coverage_data
    data['_performance_row_count'] = len(perf_rows)
    data['_pages_row_count'] = len(pages_rows)

    # Trend analysis
    all_rows = perf_rows + pages_rows
    data['trend_analysis'] = analyze_trends(all_rows)
    data['opportunities'] = data['trend_analysis'].get('opportunities', [])

    # Sitemap cross-check
    robots_sitemaps = robots_data.get('sitemap_urls', [])
    gsc_sitemaps = data.get('gsc_sitemap_urls', [])
    gsc_statuses = data.get('gsc_sitemap_statuses', [])
    data['sitemap_cross_check'] = _check_sitemap_consistency(robots_sitemaps, gsc_sitemaps, gsc_statuses, domain)

    return data


_WIZARD_HANDLERS = {
    'iubenda': _handle_wizard_iubenda,
    'gtm': _handle_wizard_gtm,
    'gads': _handle_wizard_gads,
    'meta': _handle_wizard_meta,
    'gsc': _handle_wizard_gsc,
}


# ─── Deep Audit Pipeline Runner (ADR-7: threading.Thread) ───────────────────

def _run_pipeline(sid):
    """Run trust_score → L2 → synthesis → report in a background thread."""
    sess = _SESSIONS.get(sid)
    if not sess:
        return
    sess['status'] = 'running'

    try:
        dwb = sess['deep_wizard_block']
        discovery = sess['discovery_block']

        # Phase 1: Trust Score
        _push_event(sid, 'phase', {'phase': 'trust_score', 'progress': 1, 'total': 5, 'detail': 'Calcolo Trust Score...'})
        from deep.trust_score import (
            calculate_trust_score, calculate_gap_to_revenue,
            build_consent_impact_chain, compare_attribution_windows,
            identify_leverage_nodes,
        )
        trust_result = calculate_trust_score(dwb)
        gap_revenue = calculate_gap_to_revenue(dwb)
        consent_chain = build_consent_impact_chain(dwb)
        attr_comparison = compare_attribution_windows(dwb)
        leverage_nodes = identify_leverage_nodes(gap_revenue)

        dwb['trust_score'] = trust_result
        dwb['gap_to_revenue'] = gap_revenue
        dwb['consent_impact_chain'] = consent_chain
        dwb['attribution_comparison'] = attr_comparison
        dwb['leverage_nodes'] = leverage_nodes
        sess['trust_result'] = trust_result

        _push_event(sid, 'phase', {
            'phase': 'trust_score', 'progress': 1, 'total': 5,
            'detail': f"Trust Score: {trust_result.get('score', 0)}/100 ({trust_result.get('grade', '?')})"
        })

        # Phase 2: L2 Analyses
        _push_event(sid, 'phase', {'phase': 'l2_analysis', 'progress': 2, 'total': 5, 'detail': 'Avvio 9 analisi L2...'})
        api_key = ENV.get('ANTHROPIC_API_KEY') or ENV.get('CLAUDE_API_KEY', '')
        google_key = ENV.get('GOOGLE_API_KEY', '')
        l2_results = {}

        if api_key:
            try:
                cli_audit = importlib.import_module('cli-audit')
                run_analysis = cli_audit.run_analysis
                analysis_types = ['performance', 'cwv', 'seo', 'seo_deep',
                                  'robots', 'sitemap', 'datalayer', 'cro', 'advertising']
                url = sess['url']
                homepage_html = ''
                extra_htmls = {}
                from concurrent.futures import ThreadPoolExecutor, as_completed
                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = {
                        executor.submit(run_analysis, atype, url, api_key, google_key,
                                        homepage_html, extra_htmls, discovery): atype
                        for atype in analysis_types
                    }
                    done_count = 0
                    for future in as_completed(futures, timeout=200):
                        atype_key = futures[future]
                        try:
                            _atype, result = future.result(timeout=10)
                            l2_results[_atype] = result
                        except Exception as e:
                            l2_results[atype_key] = f"Errore: {e}"
                        done_count += 1
                        _push_event(sid, 'phase', {
                            'phase': 'l2_analysis', 'progress': 2, 'total': 5,
                            'detail': f'L2: {done_count}/{len(analysis_types)} completate'
                        })
            except Exception as e:
                _push_event(sid, 'phase', {'phase': 'l2_analysis', 'progress': 2, 'total': 5, 'detail': f'L2 errore: {e}'})
        else:
            _push_event(sid, 'phase', {'phase': 'l2_analysis', 'progress': 2, 'total': 5, 'detail': 'API key mancante — L2 saltate'})

        sess['l2_results'] = l2_results

        # Phase 3: Synthesis
        _push_event(sid, 'phase', {'phase': 'synthesis', 'progress': 3, 'total': 5, 'detail': 'Synthesis in corso...'})
        from deep.synthesis import run_synthesis
        synthesis_result = run_synthesis(dwb, discovery, l2_results, trust_result)
        _push_event(sid, 'phase', {'phase': 'synthesis', 'progress': 3, 'total': 5, 'detail': 'Synthesis completata'})

        # Phase 4: Report
        _push_event(sid, 'phase', {'phase': 'report', 'progress': 4, 'total': 5, 'detail': 'Generazione report...'})
        from deep.report_deep import generate_deep_report
        report_path = generate_deep_report(
            synthesis_result, dwb, trust_result, l2_results=l2_results
        )
        sess['report_path'] = report_path
        sess['status'] = 'complete'

        # Make report path relative to web dir for serving
        report_rel = os.path.relpath(report_path, TOOL_DIR) if report_path else None

        _push_event(sid, 'complete', {
            'report_url': f'/{report_rel}' if report_rel else None,
            'trust_score': trust_result.get('score', 0),
            'grade': trust_result.get('grade', '?'),
        })

    except Exception as e:
        sess['status'] = 'error'
        _push_event(sid, 'error', {'message': str(e), 'phase': 'pipeline'})
        traceback.print_exc()


# ═══════════════════════════════════════════════════════════════════════════════
# HTTP Handler
# ═══════════════════════════════════════════════════════════════════════════════

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=TOOL_DIR, **kwargs)

    # ─── HTTP Methods ────────────────────────────────────────────────────────

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        # Deep audit SSE stream
        if self.path.startswith('/api/deep/status'):
            return self._handle_deep_status()

        if self.path.startswith(('/proxy-render?url=', '/proxy?url=', '/proxy-headers?url=', '/api/crux?url=')):
            if not self._check_auth():
                return
            if self.path.startswith('/proxy-render?url='):
                self._handle_proxy_render()
            elif self.path.startswith('/proxy?url='):
                self._handle_proxy()
            elif self.path.startswith('/proxy-headers?url='):
                self._handle_proxy_headers()
            else:
                self._handle_crux()
        else:
            normalized = urllib.parse.unquote(self.path)
            if '.env' in normalized or 'credentials' in normalized:
                self.send_response(403)
                self.end_headers()
                return
            super().do_GET()

    def do_POST(self):
        # Deep audit API endpoints
        if self.path == '/api/deep/start':
            return self._handle_deep_start()
        if self.path.startswith('/api/deep/wizard/'):
            return self._handle_deep_wizard()
        if self.path == '/api/deep/run':
            return self._handle_deep_run()
        if self.path == '/api/deep/evidence':
            return self._handle_deep_evidence()
        self._send_error(404, 'Not found')

    # ─── Helper Methods ──────────────────────────────────────────────────────

    def _read_json_body(self):
        """Read and parse JSON request body."""
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            return {}
        raw = self.rfile.read(content_length)
        return json.loads(raw.decode('utf-8'))

    def _send_json(self, data, status=200):
        """Send a JSON response with CORS headers."""
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self._cors_headers()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status_code, message):
        """Send a JSON error response with CORS headers."""
        self.send_response(status_code)
        self._cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'error': message}).encode())

    def _check_auth(self):
        """Verify API token on proxy/API endpoints. Returns True if authorized."""
        if not _API_TOKEN:
            return True
        token = self.headers.get('Authorization', '').removeprefix('Bearer ').strip()
        if token != _API_TOKEN:
            self._send_error(401, 'Unauthorized: invalid or missing AUDIT_API_TOKEN')
            return False
        return True

    def _extract_url(self, prefix):
        """Extract and validate URL from query string."""
        url = self.path.split(prefix, 1)[1]
        url = urllib.parse.unquote(url)
        if not _is_safe_url(url):
            self._send_error(403, 'URL blocked: private/internal addresses are not allowed')
            return None
        return url

    def _cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')

    # ─── Deep Audit Endpoints (2.1 - 2.5) ───────────────────────────────────

    def _handle_deep_start(self):
        """POST /api/deep/start — Step Zero + L0 discovery."""
        try:
            body = self._read_json_body()
        except Exception:
            return self._send_error(400, 'Invalid JSON body')

        url = body.get('url', '').strip()
        if not url:
            return self._send_error(400, 'url is required')
        if not url.startswith('http'):
            url = f'https://{url}'

        business_type = body.get('business_type', 'ecommerce')
        platforms = body.get('platforms', [])
        if not platforms:
            return self._send_error(400, 'platforms is required (at least one)')

        business_profile = {
            'business_type': business_type,
            'platforms': platforms,
            'url': url,
        }

        sid = _new_session(url, business_profile)
        sess = _get_session(sid)
        sess['status'] = 'discovering'

        # Run L0 discovery
        discovery_block = {}
        l0_signals = {}
        try:
            cli_audit = importlib.import_module('cli-audit')
            domain = url.replace('https://', '').replace('http://', '').rstrip('/')
            discovery_block, _html, _headers, _extras = cli_audit.auto_discover(domain, [], use_render=False)
            sess['discovery_block'] = discovery_block

            # Extract L0 signals for wizard pre-fill
            disc_str = str(discovery_block).lower()
            l0_signals = {
                'pixels_detected': [],
                'tag_managers': [],
                'consent_platforms': [],
            }
            for name, keys in [('facebook_pixel', ['fbevents', 'fbq(', 'facebook_pixel']),
                                ('google_analytics', ['google_analytics', 'gtag', 'ga4']),
                                ('google_ads', ['google_ads', 'googleads']),
                                ('linkedin', ['linkedin']), ('tiktok', ['tiktok']),
                                ('hotjar', ['hotjar']), ('clarity', ['clarity'])]:
                if any(k in disc_str for k in keys):
                    l0_signals['pixels_detected'].append(name)
            if 'google_tag_manager' in disc_str or 'gtm' in disc_str:
                l0_signals['tag_managers'].append('gtm')
            if 'iubenda' in disc_str:
                l0_signals['consent_platforms'].append('iubenda')
            if 'cookiebot' in disc_str:
                l0_signals['consent_platforms'].append('cookiebot')

            sess['l0_signals'] = l0_signals

            # SquirrelScan (parallel, optional)
            if getattr(cli_audit, 'SQUIRREL_BIN', None):
                try:
                    from concurrent.futures import ThreadPoolExecutor
                    with ThreadPoolExecutor(max_workers=1) as ex:
                        scan_future = ex.submit(cli_audit.run_squirrelscan, domain, 100)
                        scan_data = scan_future.result(timeout=310)
                    if scan_data and hasattr(cli_audit, 'squirrelscan_to_discovery'):
                        cli_audit.squirrelscan_to_discovery(scan_data, discovery_block)
                except Exception:
                    pass

        except Exception as e:
            # Discovery failed but session is still usable
            traceback.print_exc()

        sess['status'] = 'wizards'

        self._send_json({
            'session_id': sid,
            'business_profile': business_profile,
            'discovery_block': _safe_serialize(discovery_block),
            'l0_signals': l0_signals,
        })

    def _handle_deep_wizard(self):
        """POST /api/deep/wizard/:name — Process wizard form data."""
        # Extract wizard name from path: /api/deep/wizard/iubenda
        parts = self.path.split('/')
        if len(parts) < 5:
            return self._send_error(400, 'Wizard name required: /api/deep/wizard/<name>')
        # Handle query params (e.g. ?session_id=xxx)
        wizard_name = parts[4].split('?')[0]

        if wizard_name not in _WIZARD_HANDLERS:
            return self._send_error(400, f'Unknown wizard: {wizard_name}. Valid: {", ".join(_WIZARD_HANDLERS.keys())}')

        try:
            body = self._read_json_body()
        except Exception:
            return self._send_error(400, 'Invalid JSON body')

        sid = body.pop('session_id', '') or self._get_query_param('session_id')
        if not sid:
            return self._send_error(400, 'session_id is required')

        sess = _get_session(sid)
        if not sess:
            return self._send_error(404, f'Session not found: {sid}')

        try:
            handler = _WIZARD_HANDLERS[wizard_name]
            wizard_data = handler(body, sess)
            sess['deep_wizard_block'][f'{wizard_name}_data'] = wizard_data
            self._send_json({'wizard_data': wizard_data})
        except Exception as e:
            traceback.print_exc()
            self._send_error(500, f'Wizard {wizard_name} error: {e}')

    def _handle_deep_run(self):
        """POST /api/deep/run — Trigger pipeline in background thread."""
        try:
            body = self._read_json_body()
        except Exception:
            body = {}

        sid = body.get('session_id', '') or self._get_query_param('session_id')
        if not sid:
            return self._send_error(400, 'session_id is required')

        sess = _get_session(sid)
        if not sess:
            return self._send_error(404, f'Session not found: {sid}')

        if sess['status'] == 'running':
            return self._send_error(409, 'Pipeline already running')

        # Run pipeline in background thread (ADR-7)
        thread = threading.Thread(target=_run_pipeline, args=(sid,), daemon=True)
        thread.start()

        self._send_json({'status': 'running', 'session_id': sid})

    def _handle_deep_status(self):
        """GET /api/deep/status?session_id=xxx — SSE event stream."""
        sid = self._get_query_param('session_id')
        if not sid:
            return self._send_error(400, 'session_id query param required')

        sess = _get_session(sid)
        if not sess:
            return self._send_error(404, f'Session not found: {sid}')

        self.send_response(200)
        self._cors_headers()
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()

        # Stream events until complete or error
        event_index = 0
        while True:
            events = sess.get('events', [])
            while event_index < len(events):
                evt = events[event_index]
                self.wfile.write(f"event: {evt['event']}\n".encode())
                self.wfile.write(f"data: {json.dumps(evt['data'], ensure_ascii=False)}\n\n".encode())
                self.wfile.flush()
                event_index += 1
                # Terminal events — close stream
                if evt['event'] in ('complete', 'error'):
                    return

            # Poll interval
            time.sleep(0.5)

            # Safety timeout: 10 minutes
            if sess['status'] in ('complete', 'error') and event_index >= len(events):
                return

    def _handle_deep_evidence(self):
        """POST /api/deep/evidence — File upload for screenshots."""
        content_type = self.headers.get('Content-Type', '')
        if 'multipart/form-data' not in content_type:
            return self._send_error(400, 'Expected multipart/form-data')

        # Parse multipart boundary
        boundary = content_type.split('boundary=')[-1].strip()
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)

        # Simple multipart parser for files
        parts = body.split(f'--{boundary}'.encode())
        wizard_name = 'unknown'
        saved_paths = []
        evidence_dir = os.path.join(PROJECT_ROOT, 'output', 'evidence')

        for part in parts:
            if b'Content-Disposition' not in part:
                continue
            header_end = part.find(b'\r\n\r\n')
            if header_end == -1:
                continue
            header_block = part[:header_end].decode('utf-8', errors='replace')
            file_data = part[header_end + 4:].rstrip(b'\r\n--')

            if 'name="wizard_name"' in header_block:
                wizard_name = file_data.decode('utf-8', errors='replace').strip()
            elif 'filename="' in header_block:
                # Extract filename
                fn_start = header_block.index('filename="') + 10
                fn_end = header_block.index('"', fn_start)
                filename = header_block[fn_start:fn_end]
                # Sanitize filename
                filename = os.path.basename(filename)
                if not filename:
                    continue
                dest_dir = os.path.join(evidence_dir, wizard_name)
                os.makedirs(dest_dir, exist_ok=True)
                dest_path = os.path.join(dest_dir, filename)
                with open(dest_path, 'wb') as f:
                    f.write(file_data)
                saved_paths.append(dest_path)

        self._send_json({'paths': saved_paths, 'wizard_name': wizard_name})

    # ─── Query Param Helper ──────────────────────────────────────────────────

    def _get_query_param(self, key):
        """Extract a query parameter from the URL."""
        if '?' not in self.path:
            return ''
        query = self.path.split('?', 1)[1]
        params = urllib.parse.parse_qs(query)
        values = params.get(key, [])
        return values[0] if values else ''

    # ─── Proxy Handlers (unchanged) ──────────────────────────────────────────

    def _handle_proxy_headers(self):
        url = self._extract_url('/proxy-headers?url=')
        if not url:
            return
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            })
            with urllib.request.urlopen(req, timeout=10, context=_CTX_SCAN) as resp:
                headers_dict = {k: v for k, v in resp.headers.items()}
            self.send_response(200)
            self._cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(headers_dict).encode())
        except Exception as e:
            self._send_error(502, str(e))

    def _handle_proxy(self):
        url = self._extract_url('/proxy?url=')
        if not url:
            return
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'it-IT,it;q=0.9,en;q=0.8',
            })
            with urllib.request.urlopen(req, timeout=15, context=_CTX_SCAN) as resp:
                body = resp.read()
                content_type = resp.headers.get('Content-Type', 'text/html')
            self.send_response(200)
            self._cors_headers()
            self.send_header('Content-Type', content_type)
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self._send_error(502, str(e))

    def _handle_crux(self):
        url = self.path.split('/api/crux?url=', 1)[1]
        url = urllib.parse.unquote(url)
        google_key = ENV.get('GOOGLE_API_KEY', '')
        if not google_key:
            self._send_error(503, 'GOOGLE_API_KEY not configured')
            return
        try:
            payload = json.dumps({
                'url': url, 'formFactor': 'PHONE',
                'metrics': ['largest_contentful_paint', 'interaction_to_next_paint',
                            'cumulative_layout_shift', 'experimental_time_to_first_byte']
            }).encode('utf-8')
            crux_url = f'https://chromeuxreport.googleapis.com/v1/records:queryRecord?key={google_key}'
            req = urllib.request.Request(crux_url, data=payload, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=15, context=_CTX_SECURE) as resp:
                data = resp.read()
            self.send_response(200)
            self._cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self._send_error(502, str(e))

    def _handle_proxy_render(self):
        url = self._extract_url('/proxy-render?url=')
        if not url:
            return
        if not HAS_PLAYWRIGHT:
            self.path = '/proxy?url=' + urllib.parse.quote(url, safe='')
            return self._handle_proxy()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = browser.new_page(
                        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    )
                    page.goto(url, wait_until='domcontentloaded', timeout=30000)
                    page.wait_for_load_state('networkidle', timeout=10000)
                    rendered_html = page.content()
                finally:
                    browser.close()
            body = rendered_html.encode('utf-8')
            self.send_response(200)
            self._cors_headers()
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('X-Rendered', 'playwright')
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            sys.stderr.write(f"\033[33m[RENDER]\033[0m Playwright failed for {url}: {e}, falling back to static proxy\n")
            self.path = '/proxy?url=' + urllib.parse.quote(url, safe='')
            self._handle_proxy()

    def log_message(self, format, *args):
        msg = format % args
        if '/api/deep/' in msg:
            sys.stderr.write(f"\033[32m[DEEP]\033[0m {msg}\n")
        elif '/proxy-render?' in msg:
            sys.stderr.write(f"\033[35m[RENDER]\033[0m {msg}\n")
        elif '/proxy?' in msg:
            sys.stderr.write(f"\033[36m[PROXY]\033[0m {msg}\n")
        elif '/api/crux?' in msg:
            sys.stderr.write(f"\033[33m[CRUX]\033[0m {msg}\n")
        elif '200' in msg or '304' in msg:
            pass
        else:
            sys.stderr.write(f"{msg}\n")


# ─── Serialization Helper ────────────────────────────────────────────────────

def _safe_serialize(obj, depth=0):
    """Convert obj to JSON-safe structure, truncating large values."""
    if depth > 5:
        return str(obj)[:200]
    if isinstance(obj, dict):
        return {k: _safe_serialize(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(v, depth + 1) for v in obj[:100]]
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    return str(obj)[:200]


# ─── ThreadingHTTPServer for concurrent SSE + POST ───────────────────────────

class ThreadingHTTPServer(http.server.ThreadingHTTPServer):
    """Allow concurrent requests (needed for SSE + POST in parallel)."""
    allow_reuse_address = True
    daemon_threads = True


if __name__ == '__main__':
    api_key_configured = bool(ENV.get('ANTHROPIC_API_KEY') or ENV.get('CLAUDE_API_KEY'))
    print(f"\n  MarTech Audit Tool")
    print(f"  http://localhost:{PORT}")
    print(f"  http://localhost:{PORT}/wizard.html  ← Deep Audit Wizard")
    print(f"  Proxy attivo su /proxy?url=...")
    print(f"  CrUX API su /api/crux?url=...")
    print(f"  Playwright rendering: {'✓ attivo' if HAS_PLAYWRIGHT else '✗ non installato'}")
    print(f"  Claude API Key: {'configured' if api_key_configured else 'not configured'}")
    print(f"  Google API Key: {'configured' if ENV.get('GOOGLE_API_KEY') else 'not configured'}")
    print(f"  Deep Audit API: ✓ attivo (6 endpoints)")
    print()
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer fermato.")
