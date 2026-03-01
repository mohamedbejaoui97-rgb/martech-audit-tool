#!/usr/bin/env python3
"""
MarTech Audit Tool — CLI Edition
Genera un report HTML McKinsey-style da terminale.

Usage:
  python3 cli-audit.py <dominio> [--client "Nome Cliente"] [--output report.html] [--pages URL1,URL2,...]
"""

import sys, os, re, json, ssl, time, argparse, html
import urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

import shutil
import subprocess

# ─── COLORS & TERMINAL OUTPUT ───────────────────────────────────────────────

class C:
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    RESET = '\033[0m'

def log(icon, msg, color=C.RESET):
    print(f"  {icon}  {color}{msg}{C.RESET}")

def header(msg):
    print(f"\n{C.BOLD}{C.BLUE}{'─'*60}{C.RESET}")
    print(f"  {C.BOLD}{msg}{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}{'─'*60}{C.RESET}\n")

# ─── CONFIG LOADER ───────────────────────────────────────────────────────────

TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_config = None

def load_config():
    """Load osmani-config.json as single source of truth."""
    global _config
    if _config is not None:
        return _config
    config_path = os.path.join(TOOL_DIR, 'data', 'reference', 'osmani-config.json')
    try:
        with open(config_path, encoding='utf-8') as f:
            _config = json.load(f)
        return _config
    except Exception as e:
        print(f"  ⚠️  Config load failed ({e}), using inline fallbacks")
        _config = {}
        return _config


# ─── YAML CHECKLISTS ────────────────────────────────────────────────────────

_checklists = {}

def load_checklist(name):
    """Load a YAML checklist by name. Returns parsed dict or empty dict."""
    if not HAS_YAML:
        return {}
    if name in _checklists:
        return _checklists[name]
    path = os.path.join(TOOL_DIR, 'data', 'checklists', name)
    try:
        with open(path, encoding='utf-8') as f:
            _checklists[name] = yaml.safe_load(f)
        return _checklists[name]
    except Exception:
        return {}

YAML_MAPPING = {
    'datalayer': {
        'file': 'gtm-ecommerce-checklist.yaml',
        'trigger_key': 'a2_1_1',
        'sections': ['required_tags', 'ga4_ecommerce_events_checklist', 'consent_mode',
                     'enhanced_conversions', 'datalayer_variables', 'red_flags'],
    },
    'security': {
        'file': 'iubenda-consent-checklist.yaml',
        'trigger_key': 'a1_1_1',
        'sections': ['cmp_detection', 'banner_configuration', 'consent_mode_v2',
                     'prior_blocking', 'red_flags'],
    },
    'advertising': {
        'file': None,
        'trigger_key': None,
        'sections': [],
    },
    'seo': {
        'file': 'gsc-audit-checklist.yaml',
        'trigger_key': None,
        'sections': ['performance_report', 'page_indexing_report', 'core_web_vitals',
                     'rich_results', 'red_flags'],
    },
    'seo_deep': {
        'file': 'gsc-audit-checklist.yaml',
        'trigger_key': None,
        'sections': ['query_analysis', 'crawl_stats', 'ecommerce_specific',
                     'cross_referencing', 'red_flags'],
    },
}

def get_yaml_context(analysis_type, discovered):
    """Extract relevant YAML checklist sections for the given analysis type."""
    if not HAS_YAML:
        return ''

    blocks = []

    # Main mapping
    mapping = YAML_MAPPING.get(analysis_type)
    if mapping and mapping['file']:
        trigger = mapping['trigger_key']
        if trigger is None or (discovered and discovered.get(trigger, {}).get('value')):
            data = load_checklist(mapping['file'])
            if data:
                relevant = {k: data[k] for k in mapping['sections'] if k in data}
                if relevant:
                    blocks.append(f"=== CHECKLIST: {mapping['file']} ===\n{yaml.dump(relevant, default_flow_style=False, allow_unicode=True, width=200)[:8000]}")

    # Advertising: load both Google Ads + Meta Ads if detected
    if analysis_type == 'advertising':
        if discovered and discovered.get('a2_1_3', {}).get('value'):
            data = load_checklist('google-ads-audit-checklist.yaml')
            if data:
                relevant = {k: data[k] for k in ['conversion_tracking', 'red_flags', 'scoring_framework'] if k in data}
                if relevant:
                    blocks.append(f"=== CHECKLIST: Google Ads ===\n{yaml.dump(relevant, default_flow_style=False, allow_unicode=True, width=200)[:6000]}")
        if discovered and discovered.get('a2_3_1', {}).get('value'):
            data = load_checklist('meta-ads-audit-checklist.yaml')
            if data:
                relevant = {k: data[k] for k in ['meta_pixel', 'conversions_api', 'common_mistakes_and_red_flags', 'scoring'] if k in data}
                if relevant:
                    blocks.append(f"=== CHECKLIST: Meta Ads ===\n{yaml.dump(relevant, default_flow_style=False, allow_unicode=True, width=200)[:6000]}")

    # Consent checklist for datalayer analysis that touches consent
    if analysis_type == 'datalayer' and discovered:
        consent_detected = discovered.get('a1_1_1', {}).get('value')
        if consent_detected:
            data = load_checklist('iubenda-consent-checklist.yaml')
            if data:
                relevant = {k: data[k] for k in ['consent_mode_v2', 'red_flags'] if k in data}
                if relevant:
                    blocks.append(f"=== CHECKLIST: Consent/Iubenda ===\n{yaml.dump(relevant, default_flow_style=False, allow_unicode=True, width=200)[:4000]}")

    if not blocks:
        return ''
    return '\n\n'.join(blocks)

# ─── SQUIRRELSCAN (L0 Deep Crawl) ───────────────────────────────────────────

def _find_squirrel():
    """Locate squirrel binary. Returns path or None."""
    path = shutil.which('squirrel')
    if path:
        return path
    # Common install locations
    for candidate in [
        os.path.expanduser('~/.local/bin/squirrel'),
        os.path.expanduser('~/.squirrel/releases/latest/squirrel'),
    ]:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None

SQUIRREL_BIN = _find_squirrel()

def run_squirrelscan(domain, max_pages=100):
    """Run SquirrelScan crawl and return parsed JSON results, or empty dict on failure."""
    if not SQUIRREL_BIN:
        return {}
    url = f'https://{domain}' if not domain.startswith('http') else domain
    log('🐿️', f'SquirrelScan: crawling {url} (max {max_pages} pagine)...', C.CYAN)
    try:
        result = subprocess.run(
            [SQUIRREL_BIN, 'audit', url, '-m', str(max_pages), '-f', 'json', '-C', 'surface'],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            log('⚠️', f'SquirrelScan errore (exit {result.returncode})', C.YELLOW)
            return {}
        # SquirrelScan prints banner/logs before JSON — extract JSON portion
        output = result.stdout
        json_start = output.find('{')
        if json_start == -1:
            log('⚠️', 'SquirrelScan: nessun JSON nell\'output', C.YELLOW)
            return {}
        # Use strict=False to handle control characters in SquirrelScan output
        data = json.loads(output[json_start:], strict=False)
        issue_count = len(data.get('issues', []))
        log('✅', f'SquirrelScan completato: {issue_count} issue trovate', C.GREEN)
        return data
    except subprocess.TimeoutExpired:
        log('⚠️', 'SquirrelScan: timeout (>300s)', C.YELLOW)
        return {}
    except (json.JSONDecodeError, Exception) as e:
        log('⚠️', f'SquirrelScan: {e}', C.YELLOW)
        return {}

def verify_squirrelscan_urls(issues, max_checks=20):
    """Verify URLs reported as 'not crawlable' by SquirrelScan.
    Returns (verified_issues, crawler_limitations) where crawler_limitations
    are URLs that respond 200 but SquirrelScan couldn't reach."""
    verified = []
    limitations = []
    check_count = 0
    for issue in issues:
        checks = issue.get('checks', [])
        # Look for issues about unreachable/not-crawlable URLs
        name_lower = issue.get('name', '').lower()
        desc_lower = issue.get('description', '').lower()
        is_crawl_issue = any(kw in name_lower or kw in desc_lower
                           for kw in ['not crawl', 'unreachable', 'cannot access', 'non raggiungibile'])
        if is_crawl_issue and checks and check_count < max_checks:
            # Try HEAD request on first failing URL
            for check in checks[:3]:
                test_url = check.get('url', '')
                if not test_url or not test_url.startswith('http'):
                    continue
                check_count += 1
                try:
                    req = urllib.request.Request(test_url, method='HEAD', headers={
                        'User-Agent': 'Mozilla/5.0 (compatible; MarTechAudit/1.0)'
                    })
                    resp = urllib.request.urlopen(req, timeout=10, context=CTX)
                    if resp.status == 200:
                        issue_copy = dict(issue)
                        issue_copy['_crawler_limitation'] = True
                        limitations.append(issue_copy)
                        break
                except Exception:
                    pass
            else:
                verified.append(issue)
        else:
            verified.append(issue)
    return verified, limitations


def squirrelscan_to_discovery(scan_data, discovered):
    """Merge SquirrelScan results into the discovered dict."""
    if not scan_data:
        return
    issues = scan_data.get('issues', [])
    if not issues:
        return

    # Verify crawl-related issues (Bug 10)
    issues, crawler_limitations = verify_squirrelscan_urls(issues)

    # Categorize issues by severity
    by_severity = {}
    for issue in issues:
        sev = issue.get('severity', 'info')
        by_severity.setdefault(sev, []).append(issue)

    # Store raw summary in discovered
    summary_parts = []
    for sev in ['critical', 'error', 'warning', 'info']:
        count = len(by_severity.get(sev, []))
        if count:
            summary_parts.append(f'{sev}: {count}')

    discovered['_squirrelscan'] = {
        'value': True,
        'note': f'SquirrelScan: {", ".join(summary_parts)}',
        'issues': issues[:200],  # cap to avoid bloating
        'pages_crawled': scan_data.get('stats', {}).get('pages_crawled', 0),
    }

    # Store crawler limitations separately
    if crawler_limitations:
        discovered['_crawler_limitations'] = {
            'value': True,
            'note': f'{len(crawler_limitations)} URL raggiungibili ma non scansionate da SquirrelScan (limite crawler)',
            'items': [i.get('name', '') for i in crawler_limitations],
        }

    # Extract specific findings into relevant check IDs
    # SquirrelScan fields: ruleId, name, description, solution, category, severity, checks
    for issue in issues:
        category = issue.get('category', '').lower()
        rule_id = issue.get('ruleId', '').lower()
        sev = issue.get('severity', '')
        name = issue.get('name', '')

        # Broken links
        if 'broken' in rule_id or 'broken' in name.lower() or '404' in rule_id:
            discovered.setdefault('_broken_links', {'value': True, 'note': '', 'items': []})
            discovered['_broken_links']['items'].append(name)
            discovered['_broken_links']['note'] = f'{len(discovered["_broken_links"]["items"])} broken links'

        # Leaked secrets
        if 'secret' in rule_id or 'leak' in rule_id or 'exposed' in rule_id:
            discovered.setdefault('_leaked_secrets', {'value': True, 'note': '', 'items': []})
            discovered['_leaked_secrets']['items'].append(name)
            discovered['_leaked_secrets']['note'] = f'{len(discovered["_leaked_secrets"]["items"])} potenziali leak'

        # Security issues
        if category == 'security':
            discovered.setdefault('_security_issues', {'value': True, 'note': '', 'items': []})
            discovered['_security_issues']['items'].append(f'[{sev}] {name}')
            discovered['_security_issues']['note'] = f'{len(discovered["_security_issues"]["items"])} security issues'

# ─── PATTERN DETECTION ──────────────────────────────────────────────────────

def detect_by_patterns(html_lower, html_raw, entries):
    """Generic data-driven detection: loop over config entries, return list of matched names."""
    found = []
    for entry in entries:
        matched = False
        for pat in entry.get('patterns', []):
            if pat in html_lower:
                matched = True
                break
        if not matched and entry.get('regex'):
            if re.search(entry['regex'], html_raw, re.I):
                matched = True
        if matched and entry['name'] not in found:
            found.append(entry['name'])
    return found


# ─── SSL CONTEXTS ────────────────────────────────────────────────────────────
# Permissive context for scanning target sites (self-signed certs, etc.)
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# Secure context for API calls (Anthropic, Google) — credentials must travel safe
CTX_SECURE = ssl.create_default_context()

def fetch_url(url, timeout=15, secure=False):
    """Fetch URL and return (status_code, headers_dict, body_text).
    Use secure=True for API endpoints where credentials are sent."""
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'it-IT,it;q=0.9,en;q=0.8',
    })
    ctx = CTX_SECURE if secure else CTX
    try:
        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        body = resp.read().decode('utf-8', errors='replace')
        hdrs = {k.lower(): v for k, v in resp.getheaders()}
        return resp.status, hdrs, body
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace') if e.fp else ''
        return e.code, {}, body
    except Exception:
        return 0, {}, ''

# ─── MULTI-PAGE DISCOVERY & VALIDATION ────────────────────────────────────────

# These are loaded from config at runtime; inline fallbacks for backwards compat
_FALLBACK_PAGE_PATTERNS = {
    'category': re.compile(r'/(categori|collections|shop|c/|categoria|prodotti|products|catalog)', re.I),
    'product': re.compile(r'/(product|prodotto|p/|item|detail|dp/)', re.I),
    'blog': re.compile(r'/(blog|news|articol|journal|magazine|post)', re.I),
    'about': re.compile(r'/(about|chi-siamo|azienda|storia|about-us|pages/about)', re.I),
    'policy': re.compile(r'/(privacy|terms|policy|policies|condizioni|contatti|faq|legal)', re.I),
}
_FALLBACK_EXCLUDE_PATTERNS = re.compile(r'\.(js|css|png|jpg|jpeg|gif|svg|ico|xml|json|pdf|zip|woff|woff2|ttf|eot)(\?|$)', re.I)
_FALLBACK_EXCLUDE_PATHS = re.compile(r'/(cart|checkout|account|login|register|cookie|sitemap|search|wishlist|compare|reset|confirm|unsubscribe)', re.I)
_FALLBACK_SCHEMA_REQUIRED = {
    'Product': ['name', 'image', 'description', 'offers'],
    'Offer': ['price', 'priceCurrency', 'availability'],
    'Organization': ['name', 'url', 'logo'],
    'LocalBusiness': ['name', 'address', 'telephone'],
    'BreadcrumbList': ['itemListElement'],
    'FAQPage': ['mainEntity'],
    'Article': ['headline', 'author', 'datePublished', 'image'],
    'WebSite': ['name', 'url'],
}

def _get_page_patterns(cfg):
    pp = cfg.get('page_patterns')
    if pp:
        return {k: re.compile(v, re.I) for k, v in pp.items()}
    return _FALLBACK_PAGE_PATTERNS

def _get_exclude_patterns(cfg):
    ep = cfg.get('exclude_patterns')
    return re.compile(ep, re.I) if ep else _FALLBACK_EXCLUDE_PATTERNS

def _get_exclude_paths(cfg):
    ep = cfg.get('exclude_paths')
    return re.compile(ep, re.I) if ep else _FALLBACK_EXCLUDE_PATHS

def _get_schema_required(cfg):
    return cfg.get('schema_required', _FALLBACK_SCHEMA_REQUIRED)


def discover_pages(html_content, base_url, cfg=None):
    """Discover internal pages from homepage HTML."""
    pages = []
    if not html_content:
        return pages
    if cfg is None:
        cfg = load_config()
    page_patterns = _get_page_patterns(cfg)
    exclude_patterns = _get_exclude_patterns(cfg)
    exclude_paths = _get_exclude_paths(cfg)
    try:
        parsed = urllib.parse.urlparse(base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        seen = set()
        for m in re.finditer(r'href=["\'](/(?!/)[^"\'#?][^"\']*?)["\']', html_content):
            path = m.group(1)
            if path in seen:
                continue
            seen.add(path)
            # Strip query params for extension check
            clean_path = path.split('?')[0]
            if exclude_patterns.search(clean_path):
                continue
            page_type = 'other'
            for ptype, pattern in page_patterns.items():
                if pattern.search(path):
                    page_type = ptype
                    break
            if page_type == 'other' and exclude_paths.search(path):
                continue
            if page_type != 'other':
                pages.append({'url': origin + path, 'type': page_type})
        # Deduplicate by type (max 2 per type)
        by_type = {}
        result = []
        for p in pages:
            count = by_type.get(p['type'], 0)
            if count < 2:
                by_type[p['type']] = count + 1
                result.append(p)
        return result
    except Exception as e:
        return []


def validate_schema_fields(schema_obj, schema_type, cfg=None):
    """Validate schema object against required fields."""
    if cfg is None:
        cfg = load_config()
    schema_required = _get_schema_required(cfg)
    required = schema_required.get(schema_type, [])
    present = []
    missing = []
    for field in required:
        val = schema_obj.get(field) if isinstance(schema_obj, dict) else None
        if val is not None and val != '':
            present.append(field)
        else:
            missing.append(field)
    return {'total': len(required), 'present': len(present), 'missing': missing, 'complete': len(missing) == 0}


def detect_headings(html_content, page_url=''):
    """Detect and validate heading structure."""
    results = {}
    headings = []
    for m in re.finditer(r'<(h[1-6])[^>]*>([\s\S]*?)</\1>', html_content, re.I):
        level = int(m.group(1)[1])
        text = re.sub(r'<[^>]+>', '', m.group(2)).strip()[:100]
        if text:
            headings.append({'level': level, 'text': text})
    if not headings:
        return results

    h1s = [h for h in headings if h['level'] == 1]
    issues = []
    if len(h1s) == 0:
        issues.append('H1 assente')
    elif len(h1s) > 1:
        issues.append(f'{len(h1s)} H1 trovati (dovrebbe essere 1)')

    levels = [h['level'] for h in headings]
    for i in range(1, len(levels)):
        if levels[i] > levels[i-1] + 1:
            issues.append(f'Livello saltato: H{levels[i-1]} → H{levels[i]}')
            break

    path = ''
    try:
        path = urllib.parse.urlparse(page_url).path
    except (ValueError, AttributeError):
        pass

    if len(h1s) == 1:
        results['a4_3_3'] = {'value': True, 'note': f'H1: "{h1s[0]["text"]}"' + (f' ({path})' if path else '')}
    else:
        note = f'H1 assente{" su " + path if path else ""}' if len(h1s) == 0 else f'{len(h1s)} H1 trovati{" su " + path if path else ""}'
        results['a4_3_3'] = {'value': False, 'note': f'⚠️ {note}. Impatto: penalizzazione SEO. Fix: mantenere un solo H1 per pagina.'}

    if not issues:
        results['a4_3_4'] = {'value': True, 'note': f'Gerarchia heading corretta ({len(headings)} heading)' + (f' su {path}' if path else '')}
    else:
        results['a4_3_4'] = {'value': False, 'note': f'⚠️ {"; ".join(issues)}{" su " + path if path else ""}. Fix: rispettare gerarchia H1→H2→H3.'}

    return results


# ─── AUTO-DISCOVERY ENGINE ───────────────────────────────────────────────────

def auto_discover(domain, extra_urls=None, use_render=False):
    cfg = load_config()
    url = f'https://{domain}' if not domain.startswith('http') else domain
    discovered = {}

    log('🌐', f'Fetching {url}{"  (Playwright)" if use_render else ""}...', C.CYAN)
    if use_render:
        html_content, rendered = fetch_rendered(url)
        if rendered:
            log('🎭', 'JS rendering via Playwright', C.GREEN)
        status, headers, _ = fetch_url(url)  # still need headers
    else:
        status, headers, html_content = fetch_url(url)
    if not html_content:
        log('⚠️', 'Impossibile fetchare il sito', C.YELLOW)
        return discovered, '', {}, []

    lower = html_content.lower()
    detection = cfg.get('detection', {})

    # ── Data-driven Tech Stack Detection ──
    for category in ['cms', 'cdn', 'analytics', 'email', 'ab_testing', 'crm', 'chat']:
        cat_cfg = detection.get(category, {})
        entries = cat_cfg.get('entries', [])
        check_id = cat_cfg.get('check_id')
        if entries and check_id:
            found = detect_by_patterns(lower, html_content, entries)
            # CMS fallback: check meta generator
            if category == 'cms' and not found:
                gen = re.search(r'<meta[^>]*name=["\']generator["\'][^>]*content=["\']([^"\']+)["\']', html_content, re.I)
                if gen:
                    found.append(gen.group(1))
            if found:
                discovered[check_id] = {'value': True, 'note': ', '.join(found)}

    # ── Payments (regex-based, kept separate due to complexity) ──
    payments = []
    pay_patterns = [
        ('Stripe', r'js\.stripe\.com|Stripe\s*\('),
        ('Shopify Payments', r'shopify_pay/|ShopifyPay|shopifyPay'),
        ('PayPal', r'paypal\.com/sdk|paypalobjects\.com|paypal\.Buttons|paypal-checkout'),
        ('Adyen', r'adyen\.com/|AdyenCheckout'),
        ('Braintree', r'braintreegateway|braintree.*client'),
        ('Klarna', r'klarna\.com/|klarnaservices'),
        ('Scalapay', r'scalapay\.com'),
        ('Mollie', r'js\.mollie\.com|mollie\.com/paymentscreen'),
        ('Nexi/XPay', r'ecommerce\.nexi\.it|xpay\.nexigroup'),
        ('Satispay', r'satispay\.com/.*\.js'),
        ('Amazon Pay', r'pay\.amazon|amazonpay'),
        ('Apple Pay', r'apple-pay-shop|ApplePaySession'),
        ('Google Pay', r'pay\.google\.com/gp/p/js'),
        ('Shop Pay', r'shop\.app/checkouts'),
    ]
    for name, pattern in pay_patterns:
        if re.search(pattern, html_content, re.I) and name not in payments:
            payments.append(name)
    if payments: discovered['a0_1_3'] = {'value': True, 'note': ', '.join(payments)}

    # ── Tracking ──
    gtm = list(set(re.findall(r'GTM-[A-Z0-9]{5,8}', html_content)))
    if gtm: discovered['a2_1_1'] = {'value': True, 'note': ', '.join(gtm)}

    ga4 = list(set(re.findall(r'G-[A-Z0-9]{8,12}', html_content)))
    if ga4: discovered['a2_1_2'] = {'value': True, 'note': ', '.join(ga4)}

    ads = list(set(re.findall(r'AW-[0-9]{8,12}', html_content)))
    if ads: discovered['a2_1_3'] = {'value': True, 'note': ', '.join(ads)}

    if re.search(r'googletagmanager\.com/gtag/js', html_content, re.I):
        discovered['a2_1_4'] = {'value': True, 'note': 'gtag.js caricato direttamente'}

    ssgtm = [u for u in re.findall(r'https?://[a-z0-9.-]+/gtm\.js', html_content, re.I) if 'googletagmanager.com' not in u]
    if ssgtm:
        domains = list(set(urllib.parse.urlparse(u).hostname for u in ssgtm))
        discovered['a2_2_1'] = {'value': True, 'note': 'Server-side GTM: ' + ', '.join(domains)}
        discovered['a2_2_2'] = {'value': True, 'note': 'Dominio custom: ' + ', '.join(domains)}

    # ── Pixels ──
    # Meta Pixel: classic fbq(), connect.facebook.net, OR Shopify Web Pixel config
    meta_pixel_id = None
    fbq = re.search(r'fbq\s*\(\s*[\'"]init[\'"]\s*,\s*[\'"](\d+)[\'"]', html_content)
    if fbq:
        meta_pixel_id = fbq.group(1)
    else:
        # Shopify Web Pixel JSON config (may be double-escaped): \"pixel_id\":\"XXXXX\",\"pixel_type\":\"facebook_pixel\"
        shopify_fb = re.search(r'pixel_id[\\"\':\s]+(\d{10,20})[\\"\s,\']+pixel_type[\\"\':\s]+facebook_pixel', html_content)
        if shopify_fb:
            meta_pixel_id = shopify_fb.group(1)
    if meta_pixel_id:
        discovered['a2_3_1'] = {'value': True, 'note': f'Meta Pixel ID: {meta_pixel_id}'}
    elif 'fbq(' in lower or 'connect.facebook.net' in lower or 'facebook.com/tr' in lower:
        discovered['a2_3_1'] = {'value': True, 'note': 'Meta Pixel rilevato'}

    # Microsoft Clarity / Hotjar
    clarity_hotjar = []
    if 'clarity.ms' in lower:
        cm = re.search(r'clarity\.ms/tag/([a-z0-9]+)', html_content, re.I)
        clarity_hotjar.append(f'Clarity ID: {cm.group(1)}' if cm else 'Microsoft Clarity rilevato')
    if 'hotjar.com' in lower or 'static.hotjar.com' in lower:
        hj = re.search(r'hjid[\'"\s:]*(\d+)', html_content, re.I)
        clarity_hotjar.append(f'Hotjar ID: {hj.group(1)}' if hj else 'Hotjar rilevato')
    if clarity_hotjar:
        discovered['a2_3_2'] = {'value': True, 'note': ', '.join(clarity_hotjar)}

    # Helper: match Shopify Web Pixel config (handles double-escaped JSON)
    def shopify_pixel_match(pixel_type_pattern):
        return re.search(r'pixel_type[\\"\':,\s]+' + pixel_type_pattern, html_content, re.I)

    def shopify_pixel_id(pixel_type_pattern):
        m = re.search(r'pixel_id[\\"\':,\s]+([A-Za-z0-9]+)[\\"\':,\s]+pixel_type[\\"\':,\s]+' + pixel_type_pattern, html_content, re.I)
        return m.group(1) if m else None

    # LinkedIn Insight Tag: classic script OR Shopify Web Pixel
    if 'snap.licdn.com' in lower or 'linkedin.com/px' in lower or shopify_pixel_match('linkedin'):
        discovered['a2_3_3'] = {'value': True, 'note': 'LinkedIn Insight Tag rilevato'}

    # TikTok Pixel: classic ttq script OR Shopify Web Pixel
    tiktok_id = shopify_pixel_id('tiktok')
    if 'analytics.tiktok.com' in lower or 'ttq.' in lower or tiktok_id:
        discovered['a2_3_4'] = {'value': True, 'note': f'TikTok Pixel ID: {tiktok_id}' if tiktok_id else 'TikTok Pixel rilevato'}

    # Pinterest Tag
    if 'pintrk' in lower or 's.pinimg.com' in lower or shopify_pixel_match('pinterest'):
        discovered['a2_3_5'] = {'value': True, 'note': 'Pinterest Tag rilevato'}

    # Twitter/X Pixel
    if 'static.ads-twitter.com' in lower or 'twq(' in lower or 'platform.twitter.com/oct.js' in lower or shopify_pixel_match('twitter'):
        discovered['a2_3_6'] = {'value': True, 'note': 'Twitter/X Pixel rilevato'}

    # Criteo / RTB House
    criteo_rtb = []
    if 'criteo.com' in lower or 'criteo.net' in lower: criteo_rtb.append('Criteo')
    if 'creativecdn.com' in lower or 'rtbhouse' in lower: criteo_rtb.append('RTB House')
    if criteo_rtb:
        discovered['a2_3_8'] = {'value': True, 'note': ', '.join(criteo_rtb)}

    # Snapchat Pixel
    if 'sc-static.net' in lower or 'snaptr(' in lower or shopify_pixel_match('snapchat'):
        discovered.setdefault('a2_3_7', {'value': True, 'note': 'Snapchat Pixel rilevato'})

    # Generic Shopify Web Pixel detection — catch any pixel_type we haven't matched
    for m in re.finditer(r'pixel_id[\\"\':,\s]+([A-Za-z0-9_]+)[\\"\':,\s]+pixel_type[\\"\':,\s]+([A-Za-z0-9_]+)', html_content):
        pid, ptype = m.group(1), m.group(2)
        ptype_lower = ptype.lower()
        if ptype_lower not in ('facebook_pixel',) and pid:
            if ptype_lower not in ('tiktok','pinterest','twitter','snapchat','linkedin'):
                discovered.setdefault('a2_3_7', {'value': True, 'note': f'{ptype}: {pid}'})

    # ── Consent (data-driven) ──
    consent_entries = detection.get('consent', {}).get('entries', [])
    banners = detect_by_patterns(lower, html_content, consent_entries) if consent_entries else []
    if not banners:
        # Fallback for optanon
        if 'optanon' in lower:
            banners.append('OneTrust')
    if banners:
        discovered['a1_1_1'] = {'value': True, 'note': ', '.join(banners)}
        discovered['a1_1_2'] = {'value': True, 'note': 'Banner: ' + ', '.join(banners)}

    consent_m = re.search(r'gtag\s*\(\s*[\'"]consent[\'"]\s*,\s*[\'"]default[\'"]\s*,\s*(\{[^}]+\})', html_content, re.S)
    if consent_m:
        discovered['a1_2_1'] = {'value': True, 'note': 'Consent Mode v2 configurato'}
        block = consent_m.group(1)
        consent_map = {
            'ad_storage': 'a1_2_2', 'analytics_storage': 'a1_2_3', 'ad_user_data': 'a1_2_4',
            'ad_personalization': 'a1_2_5', 'functionality_storage': 'a1_2_6',
            'personalization_storage': 'a1_2_7', 'security_storage': 'a1_2_8',
        }
        for key, check_id in consent_map.items():
            sm = re.search(key + r'\s*[:=]\s*[\'"]?(denied|granted)[\'"]?', block)
            if sm: discovered[check_id] = {'value': True, 'note': f'{key}: {sm.group(1)}'}
    elif "gtag('consent'" in lower or 'gtag("consent"' in lower:
        discovered['a1_2_1'] = {'value': True, 'note': 'Consent Mode rilevato (parsing parziale)'}

    # ── Security Headers ──
    if url.startswith('https://'):
        discovered['a0_4_1'] = {'value': True, 'note': 'HTTPS attivo'}
    sec_checks = [
        ('strict-transport-security', 'a0_4_2', 'HSTS'),
        ('content-security-policy', 'a0_4_3', 'CSP presente'),
        ('x-frame-options', 'a0_4_4', 'X-Frame-Options'),
        ('x-content-type-options', 'a0_4_5', 'X-Content-Type-Options'),
        ('referrer-policy', 'a0_4_6', 'Referrer-Policy'),
    ]
    for hdr, cid, label in sec_checks:
        if hdr in headers:
            discovered[cid] = {'value': True, 'note': f'{label}: {headers[hdr]}'}
    if 'permissions-policy' in headers or 'feature-policy' in headers:
        discovered['a0_4_7'] = {'value': True, 'note': 'Permissions-Policy presente'}

    # ── Schema / Structured Data ──
    ld_json = re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>', html_content, re.I)
    schemas = []
    for block in ld_json:
        try:
            j = json.loads(block)
            types = [item.get('@type') for item in (j if isinstance(j, list) else [j])]
            schemas.extend(t for t in types if t)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    if schemas:
        unique = list(dict.fromkeys(schemas))
        discovered['a4_4_1'] = {'value': True, 'note': 'Schema: ' + ', '.join(unique)}
        if any('product' in t.lower() for t in unique): discovered['a4_4_2'] = {'value': True, 'note': 'Product schema rilevato'}
        if any('organization' in t.lower() for t in unique): discovered['a4_4_3'] = {'value': True, 'note': 'Organization schema rilevato'}
        if any('breadcrumb' in t.lower() for t in unique): discovered['a4_4_4'] = {'value': True, 'note': 'BreadcrumbList schema rilevato'}
        if any('faq' in t.lower() for t in unique): discovered['a4_4_5'] = {'value': True, 'note': 'FAQ schema rilevato'}

    # ── DataLayer ──
    if re.search(r'dataLayer\s*[=\[]', html_content) or 'dataLayer.push' in html_content:
        discovered['a3_1_1'] = {'value': True, 'note': 'dataLayer presente nel codice'}
        pushes = re.findall(r'dataLayer\.push\s*\(\s*\{[^}]*[\'"]event[\'"]\s*:\s*[\'"]([^\'"]+)[\'"]', html_content)
        if pushes:
            events = list(dict.fromkeys(pushes))
            discovered['a3_1_2'] = {'value': True, 'note': 'Eventi: ' + ', '.join(events)}

    # ── Heading Detection (homepage) ──
    heading_results = detect_headings(html_content, url)
    discovered.update(heading_results)

    # ── Deep Schema Validation ──
    schema_required = _get_schema_required(cfg)
    for block in ld_json:
        try:
            obj = json.loads(block)
            items = obj.get('@graph', [obj]) if isinstance(obj, dict) else obj
            if not isinstance(items, list):
                items = [items]
            for item in items:
                if not isinstance(item, dict):
                    continue
                schema_type = item.get('@type', '')
                types = schema_type if isinstance(schema_type, list) else [schema_type]
                for t in types:
                    if t in schema_required:
                        v = validate_schema_fields(item, t)
                        if v['missing']:
                            discovered['a4_4_9'] = {'value': False, 'note': f'⚠️ {t}: campi mancanti: {", ".join(v["missing"])}. Impatto: ridotta eligibilità rich results.'}
                        else:
                            discovered.setdefault('a4_4_9', {'value': True, 'note': f'{t}: tutti i campi obbligatori presenti'})
        except (json.JSONDecodeError, ValueError, TypeError, KeyError):
            pass

    if not schemas:
        discovered['a4_4_1'] = {'value': False, 'note': '⚠️ Nessuno schema JSON-LD. Impatto: -20-30% CTR in SERP. Fix: aggiungere JSON-LD Organization, Product, BreadcrumbList.'}

    # ── Osmani Validators: Resource Measurement + CrUX ──
    resources = measure_resources(html_content)
    if resources:
        log('📏', f'Resources: {resources["script_count"]} scripts, {resources["stylesheet_count"]} CSS, {resources["image_count"]} images, HTML {resources["html_size"]//1024}KB', C.DIM)

    # Try CrUX if Google API key available
    env_path = os.path.join(TOOL_DIR, 'credentials', '.env')
    google_key = ''
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.strip().startswith('GOOGLE_API_KEY='):
                    google_key = line.strip().split('=', 1)[1].strip()
    crux_data = fetch_crux(url, google_key) if google_key else None
    if crux_data:
        log('📊', 'CrUX field data fetched', C.GREEN)
    budget_findings = validate_budgets(resources, crux_data, cfg)
    discovered.update(budget_findings)

    # ── Multi-Page Crawling ──
    discovered_pages = [{'url': url, 'type': 'homepage'}]
    auto_pages = discover_pages(html_content, url, cfg)
    if extra_urls:
        for eu in extra_urls:
            full = eu if eu.startswith('http') else url.rstrip('/') + ('/' if not eu.startswith('/') else '') + eu
            if not any(p['url'] == full for p in auto_pages):
                auto_pages.append({'url': full, 'type': 'manual'})

    extra_htmls = []
    for page in auto_pages[:6]:
        log('🔍', f'Scanning {page["url"]} ({page["type"]})...', C.CYAN)
        discovered_pages.append({'url': page['url'], 'type': page['type'], 'discovered': True})
        try:
            s, _, page_html = fetch_url(page['url'])
            if s == 200 and page_html:
                extra_htmls.append((page['url'], page['type'], page_html))
                # Run detectors on extra pages
                page_headings = detect_headings(page_html, page['url'])
                for k, v in page_headings.items():
                    if k not in discovered or not discovered[k]['value']:
                        discovered[k] = v
                    elif v.get('note') and v['note'] not in discovered[k].get('note', ''):
                        discovered[k]['note'] += ' | ' + v['note']
                # Schema on extra pages
                page_ld = re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>', page_html, re.I)
                for pblock in page_ld:
                    try:
                        pj = json.loads(pblock)
                        pitems = pj.get('@graph', [pj]) if isinstance(pj, dict) else pj
                        if not isinstance(pitems, list):
                            pitems = [pitems]
                        for pitem in pitems:
                            if not isinstance(pitem, dict):
                                continue
                            pt = pitem.get('@type', '')
                            ptypes = pt if isinstance(pt, list) else [pt]
                            for ptype in ptypes:
                                if ptype and ptype not in schemas:
                                    schemas.append(ptype)
                                    log('  📌', f'Schema {ptype} trovato su {page["url"]}', C.DIM)
                    except (json.JSONDecodeError, ValueError, TypeError, KeyError):
                        pass
                if page_ld and not discovered.get('a4_4_1', {}).get('value'):
                    unique = list(dict.fromkeys(schemas))
                    if unique:
                        discovered['a4_4_1'] = {'value': True, 'note': 'Schema: ' + ', '.join(unique) + f' (trovati su pagine interne)'}
                        if any('product' in t.lower() for t in unique):
                            discovered['a4_4_2'] = {'value': True, 'note': 'Product schema rilevato su pagina interna'}
        except Exception as e:
            log('⚠️', f'Errore fetch {page["url"]}: {e}', C.YELLOW)

    discovered['_discovered_pages'] = discovered_pages

    count = len([k for k in discovered if not k.startswith('_')])
    log('✅', f'Auto-discovery completato: {count} elementi rilevati su {len(discovered_pages)} pagine', C.GREEN)
    return discovered, html_content, headers, extra_htmls


# ─── AI ANALYSIS (CLAUDE API) ───────────────────────────────────────────────

def _get_osmani_base(cfg=None):
    if cfg is None:
        cfg = load_config()
    prompts = cfg.get('prompts', {})
    return prompts.get('osmani_base', _FALLBACK_OSMANI_BASE)

def _get_prompts(cfg=None):
    if cfg is None:
        cfg = load_config()
    prompts = cfg.get('prompts', {})
    # Return all prompts except osmani_base
    result = {k: v for k, v in prompts.items() if k != 'osmani_base'}
    if not result:
        return _FALLBACK_PROMPTS
    return result

_FALLBACK_OSMANI_BASE = """You are a senior web quality auditor trained on Google Lighthouse internals and Addy Osmani's web quality methodology (150+ production audits). You provide specific, actionable findings categorized by severity. Always respond in ITALIAN.

For EVERY finding, use this exact format:
**FINDING [SEVERITY]:** Title
- Problema: detailed description of the current state
- Impatto: quantified business impact (e.g., -20% CTR, +0.5s LCP, €X lost revenue, legal risk)
- Fix: specific actionable recommendation with code snippets where applicable, and expected result after fix

Severity levels: CRITICO (immediate fix, revenue/legal impact), ALTO (fix within 1 month, significant impact), MEDIO (fix within 3 months), BASSO (nice to have).

When analyzing multi-page content, clearly indicate which page each finding applies to.

REGOLE CRITICHE:
1. Basa la tua analisi ESCLUSIVAMENTE sul contenuto HTML fornito. NON fare MAI assunzioni basate sul nome del dominio o del brand.
2. Quando ricevi una sezione "DATI SEO ESTRATTI PROGRAMMATICAMENTE", quei dati sono AUTORITATIVI e corretti al 100%. NON contraddirli MAI.
3. NON dire mai "non posso accedere" o "non posso verificare" se il contenuto è fornito nel prompt."""

_FALLBACK_PROMPTS = {
    'performance': """Esegui un audit performance completo basato su Lighthouse e Core Web Vitals.

BUDGET DI PERFORMANCE (soglie Osmani):
- Peso totale pagina: < 1.5MB
- JavaScript: < 300KB (compresso)
- CSS: < 100KB
- Immagini above-fold: < 500KB
- Font: < 100KB
- Script terze parti: < 200KB
- TTFB: < 800ms
- LCP: <= 2.5s (buono), 2.5-4s (migliorabile), >4s (scarso)
- INP: <= 200ms (buono), 200-500ms (migliorabile), >500ms (scarso)
- CLS: <= 0.1 (buono), 0.1-0.25 (migliorabile), >0.25 (scarso)

CHECKLIST:
1. SERVER: TTFB, compressione Brotli/Gzip, HTTP/2+, CDN, edge caching
2. RENDER-BLOCKING: Critical CSS inline < 14KB? Script defer/async? Font preload con font-display:swap?
3. IMMAGINI: Formati moderni (AVIF > WebP > PNG)? srcset responsive? Lazy loading below-fold? LCP image con fetchpriority="high"?
4. JAVASCRIPT: Code splitting? Tree shaking? Codice inutilizzato?
5. FONT: font-display impostato? Font preloaded? Subsetting unicode?
6. CACHING: Cache-Control headers? Immutable per asset hashati?
7. TERZE PARTI: Script async/defer? Facade pattern per embed pesanti?
8. IMPATTO GOOGLE ADS: Come le performance impattano Quality Score e CPC

Per ogni problema trovato indica: severità (CRITICO/ALTO/MEDIO/BASSO), impatto business, e fix specifico.""",

    'cwv': """Esegui un audit specializzato Core Web Vitals. Google misura al 75° percentile.

**LCP (Largest Contentful Paint) - Target: <= 2.5s:**
- TTFB lento (> 800ms)?
- Risorse render-blocking?
- LCP element: è preloaded? fetchpriority="high"? Nel HTML iniziale (non JS-rendered)?
- Critical CSS inline?
- Font con font-display:swap?

**INP (Interaction to Next Paint) - Target: <= 200ms:**
- Long tasks > 50ms sul main thread?
- Event handlers pesanti (visual feedback immediato? Lavoro non-critico deferito?)
- Script terze parti bloccanti?

**CLS (Cumulative Layout Shift) - Target: <= 0.1:**
- Immagini senza width/height o aspect-ratio?
- Embed/iframe senza spazio riservato?
- Contenuto iniettato dinamicamente sopra il viewport?
- Font che causano FOUT (font-display:optional o size-adjust)?
- Animazioni che usano layout (usare transform/opacity)?

Per ogni metrica: stato attuale, causa root, fix specifico con codice.""",

    'seo': """Esegui un audit SEO completo basato su Google Search guidelines e Lighthouse SEO.

IMPORTANTE: Prima di tutto, leggi i DATI SEO ESTRATTI PROGRAMMATICAMENTE. Quei dati sono CERTI al 100%.
- Se h1_count = 1, il H1 ESISTE. Non dire che manca.
- Se json_ld_schemas contiene oggetti, gli schema ESISTONO. Non dire che mancano.
- Analizza la qualità di ciò che c'è, non inventare assenze.

**APPROCCIO PROATTIVO:**
1. Leggi il testo visibile e i prodotti per capire COSA FA il sito (es: pasticceria, moda, tech)
2. Per ogni heading presente, spiega se è ottimizzato per SEO o come dovrebbe essere migliorato
3. Per il title, suggerisci un title ottimizzato specifico per il business del cliente

**SEO TECNICO:**
- robots.txt: analizza il contenuto FORNITO nel prompt
- Canonical URL, Meta robots, XML Sitemap, HTTPS, struttura URL

**ON-PAGE SEO (analizza ciò che ESISTE, non inventare assenze):**
- Title tag: lunghezza attuale, keyword presenti?, suggerisci versione ottimizzata
- Meta description: presente o assente? Se assente, proponi testo specifico per il business
- Heading hierarchy: analizza gli H1/H2/H3 PRESENTI, valuta se sono keyword-rich e ben strutturati
- Per ogni heading, spiega: cosa c'è ora → cosa dovrebbe essere → perché (impatto SEO)
- Image SEO: quante immagini, quante senza alt, impatto

**STRUCTURED DATA — ANALISI SCHEMA (segui questa metodologia):**
I dati JSON-LD sono forniti nel campo json_ld_schemas. Analizzali su 4 livelli:

Livello A — Presenza: Quali tipi schema sono implementati?
Livello B — Validità: I campi obbligatori sono presenti? Errori strutturali?
Livello C — Rich Results: Google può generare risultati avanzati? (Schema.org valido ≠ rich result eligible)
Livello D — Qualità: Campi raccomandati presenti? Il markup rappresenta il contenuto reale?

Per homepage verifica: Organization (name, url, logo, sameAs), WebSite (name, url, potentialAction/SearchAction)
Per prodotti: Product (name, image, description, offers/price/availability/currency), BreadcrumbList
Indica i CAMPI MANCANTI specifici e il loro impatto.

Se è presente anche una PAGINA PRODOTTO, analizza i suoi schema separatamente.

Concludi sempre con: "Markup strutturato tecnicamente valido ≠ garanzia di rich results. Serve verifica con Rich Results Test."

**MOBILE SEO:** Viewport, tap targets, font-size, horizontal scroll
**INTERNATIONAL SEO:** hreflang, html lang

Per ogni issue: severità, impatto su ranking/CTR, fix specifico con esempio concreto.""",

    'accessibility': """Esegui un audit accessibilità WCAG 2.1 AA completo seguendo i principi POUR.

**PERCEIVABLE:**
- Ogni <img> ha alt text significativo? Decorative con alt=""?
- Icon buttons hanno accessible name (aria-label o visually-hidden text)?
- Contrasto colori >= 4.5:1 testo normale, >= 3:1 testo grande?
- Colore non è unico indicatore (icone + testo)?
- Video con captions?

**OPERABLE:**
- Tutti gli elementi interattivi accessibili da tastiera?
- Nessuna keyboard trap? Modal con Escape per chiudere e focus management?
- Focus indicator visibile (:focus-visible)?
- Skip link "Skip to main content" presente?
- prefers-reduced-motion rispettato?
- Tap targets >= 48px?

**UNDERSTANDABLE:**
- <html lang> impostato?
- Form input con <label> associato?
- Errori form con aria-invalid + aria-describedby?
- Navigazione consistente con aria-current?

**ROBUST:**
- HTML valido (no ID duplicati, nesting corretto)?
- Elementi nativi preferiti su ARIA (button vs div role=button)?
- ARIA roles/properties usati correttamente?
- Live regions per contenuto dinamico (aria-live)?

Categorizza: CRITICO (fix immediato), ALTO (fix prima del lancio), MEDIO (fix presto).
Per ogni issue il fix specifico con codice.""",

    'security': """Esegui un audit security e best practices web.

**SECURITY:**
- HTTPS ovunque? No mixed content?
- HSTS header (Strict-Transport-Security)?
- Content Security Policy (CSP) configurata?
- Security headers: X-Frame-Options, X-Content-Type-Options (nosniff), Referrer-Policy, Permissions-Policy
- Nessuna libreria JS vulnerabile?

**BROWSER COMPATIBILITY:**
- HTML5 doctype?
- <meta charset="UTF-8"> primo elemento in <head>?
- Viewport meta tag?

**API DEPRECATE:**
- No document.write?
- No synchronous XHR?

**ERRORI & CODE QUALITY:**
- Error handling corretto?
- HTML semantico (header/nav/main/article)?
- No ID duplicati?

Per ogni issue: severità, rischio, fix specifico.""",

    'robots': """Analizza questo robots.txt come esperto SEO tecnico.

Verifica:
1. User-agent configurati (Googlebot, Bingbot, * minimo)
2. Sitemap reference presente
3. Disallow sensati (no blocco pagine importanti per errore)
4. Crawl-delay (sconsigliato per Googlebot)
5. Risorse CSS/JS non bloccate

Rispondi in ITALIANO con:
**STATO:** OK / Problemi trovati
**SITEMAP:** Presente/Assente + URL
**USER-AGENTS:** Lista configurati
**PROBLEMI:** (con severità CRITICO/ALTO/MEDIO/BASSO)
**RACCOMANDAZIONI:** miglioramenti specifici
**SCORE SUGGERITO:** /10""",

    'sitemap': """Analizza questa sitemap XML come esperto SEO tecnico.

Verifica:
1. Formato XML valido
2. Tipo: sitemap index o sitemap singola
3. Conteggio URL / sub-sitemap
4. lastmod: aggiornato o statico/assente
5. URL coerenti col dominio
6. Max 50K URL per file
7. Struttura logica

Rispondi in ITALIANO con:
**STATO:** OK / Problemi trovati
**TIPO:** Sitemap Index / Singola
**CONTEGGIO:** N URL o sub-sitemap
**LASTMOD:** Aggiornato/Statico/Assente
**PROBLEMI:** (con severità)
**RACCOMANDAZIONI:** miglioramenti specifici
**SCORE SUGGERITO:** /10""",

    'datalayer': """Analizza questo dataLayer ecommerce come esperto Google Tag Manager.

Verifica conformità con la documentazione ufficiale Google GA4 Ecommerce:
https://developers.google.com/analytics/devguides/collection/ga4/ecommerce

Per ogni evento controlla:
1. Nome evento corretto (add_to_cart, purchase, etc.)
2. Struttura oggetto ecommerce conforme
3. Campi obbligatori presenti: currency, value, items[]
4. Per items[]: item_id (string), item_name (string), price (number), quantity (number)
5. TIPI DATI: price e value devono essere NUMBER, item_id deve essere STRING
6. ecommerce:null push PRIMA dell'evento
7. transaction_id univoco per purchase

Rispondi in ITALIANO con:
**EVENTI TROVATI:** lista
**CONFORMITA:** % conforme a Google docs
**PROBLEMI:** (con severità e impatto su GA4/Google Ads)
**FIX SUGGERITI:** codice corretto per ogni problema""",

    'seo_deep': """Esegui un SEO AUDIT APPROFONDITO basato su Google Search Quality Rater Guidelines e E-E-A-T.

IMPORTANTE: Leggi i DATI SEO ESTRATTI — sono certi al 100%. NON contraddirli.
Leggi il testo visibile per capire il business reale del sito.

**APPROCCIO PROATTIVO:**
1. Identifica il settore del cliente dal contenuto visibile (es: pasticceria artigianale, moda, etc.)
2. Basati su questo per suggerimenti specifici di keyword, contenuti, e strategia

**E-E-A-T:**
- Autore identificabile? "Chi siamo" completa?
- Contenuti mostrano esperienza diretta?
- Trust: HTTPS, privacy policy, contatti chiari

**SCHEMA MARKUP APPROFONDITO:**
Se sono forniti dati di una PAGINA PRODOTTO, analizza:
- Product schema: name, image, description, offers con price/availability/currency presenti?
- BreadcrumbList presente?
- Confronta homepage vs prodotto: gap di implementazione?
- Campi mancanti che impediscono rich results (stelle, prezzo in SERP)
- Schema consigliati ma assenti per tipo pagina (FAQ, Review, HowTo se applicabili)

**SITE-TYPE SPECIFIC (Ecommerce):**
- Keyword cannibalization tra categorie/prodotti?
- Thin content: pagine prodotto con < 300 parole?
- Faceted navigation: canonical/noindex?

**CRAWL BUDGET:** Redirect chains, soft 404, pagine orfane
**CONTENT GAPS:** Blog? FAQ? Landing page per intent diversi?
**UTM CONVENTIONS:** Tracking plan consistente?

Per ogni issue: severità, impatto su ranking/traffico organico, fix specifico con esempio.""",

    'cro': """Esegui un audit CRO (Conversion Rate Optimization) completo della pagina.

**1. VALUE PROPOSITION (Above the Fold):**
- Il visitatore capisce COSA offri in 5 secondi?
- Headline specifica e outcome-driven?
- Visual hero: supporta il messaggio?

**2. CTA (Call-to-Action):**
- CTA primaria above-the-fold? Alto contrasto?
- Testo action-oriented e specifico?
- Micro-copy di supporto sotto CTA?

**3. TRUST SIGNALS & SOCIAL PROOF:**
- Recensioni con dettagli specifici?
- Rating aggregato visibile?
- Numeri concreti?
- Garanzie esplicite?

**4. FRICTION POINTS:**
- Checkout semplificato?
- Form con validazione inline?
- Loading speed percepito?

**5. PAGE-TYPE SPECIFIC:**
- Homepage, Categoria, Prodotto, Carrello, Checkout analysis

Per ogni area: problemi specifici con severità, fix concreto.""",

    'advertising': """Esegui un audit della readiness pubblicitaria del sito ecommerce.

**GOOGLE ADS READINESS:**
- Tag di Google presente e configurato?
- Conversion Linker attivo?
- Enhanced Conversions attive?
- Conversion tracking: purchase, add_to_cart tracciati?
- Google Merchant Center: structured data Product/Offer?

**META ADS READINESS:**
- Meta Pixel installato?
- Eventi standard configurati?
- Conversions API server-side?

**TRACKING QUALITY:**
- Deduplication eventi?
- Attribution: UTM/GCLID/FBCLID preservati?
- Cross-domain linker?
- Consent Mode per DMA?

**IMPATTO BUSINESS:**
- Quality Score: impatto performance su CPC
- ROAS tracking accuracy
- Audience building

Per ogni issue: severità, impatto su ROAS/CPC, fix specifico."""
}


def extract_seo_summary(html_content):
    """Extract structured SEO data from HTML so Claude doesn't have to parse raw HTML."""
    summary = {}

    # Title
    t = re.search(r'<title[^>]*>(.*?)</title>', html_content, re.I | re.S)
    summary['title'] = t.group(1).strip() if t else 'MANCANTE'
    summary['title_length'] = len(summary['title']) if t else 0

    # Meta description
    md = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']', html_content, re.I)
    summary['meta_description'] = md.group(1).strip() if md else 'MANCANTE'
    summary['meta_description_length'] = len(summary['meta_description']) if md else 0

    # Canonical
    c = re.search(r'<link[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']*)["\']', html_content, re.I)
    summary['canonical'] = c.group(1) if c else 'MANCANTE'

    # Lang
    l = re.search(r'<html[^>]*lang=["\']([^"\']*)["\']', html_content, re.I)
    summary['html_lang'] = l.group(1) if l else 'MANCANTE'

    # Viewport
    summary['viewport'] = bool(re.search(r'<meta[^>]*name=["\']viewport["\']', html_content, re.I))

    # Headings
    def clean(s): return re.sub(r'<[^>]+>', '', s).strip()
    for tag in ['h1', 'h2', 'h3', 'h4']:
        items = re.findall(f'<{tag}[^>]*>(.*?)</{tag}>', html_content, re.I | re.S)
        texts = [clean(h)[:120] for h in items if clean(h)]
        summary[f'{tag}_count'] = len(items)
        summary[f'{tag}_texts'] = texts[:10]

    # Images
    imgs = re.findall(r'<img[^>]*>', html_content, re.I)
    imgs_with_alt = [i for i in imgs if re.search(r'alt=["\'][^"\']+["\']', i, re.I)]
    summary['images_total'] = len(imgs)
    summary['images_with_alt'] = len(imgs_with_alt)
    summary['images_missing_alt'] = len(imgs) - len(imgs_with_alt)

    # hreflang
    hreflangs = re.findall(r'<link[^>]*hreflang=["\']([^"\']*)["\']', html_content, re.I)
    summary['hreflang'] = hreflangs if hreflangs else 'Non presenti'

    # Meta robots
    mr = re.search(r'<meta[^>]*name=["\']robots["\'][^>]*content=["\']([^"\']*)["\']', html_content, re.I)
    summary['meta_robots'] = mr.group(1) if mr else 'Non presente (default index,follow)'

    # Open Graph
    og_title = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']*)["\']', html_content, re.I)
    summary['og_title'] = og_title.group(1) if og_title else 'MANCANTE'

    # JSON-LD Structured Data (full extraction)
    ld_blocks = re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>', html_content, re.I)
    schema_objects = []
    for block in ld_blocks:
        try:
            obj = json.loads(block)
            schema_objects.append(obj)
        except (json.JSONDecodeError, ValueError):
            schema_objects.append({'_parse_error': True, '_raw': block[:500]})
    summary['json_ld_schemas'] = schema_objects
    summary['json_ld_types'] = [
        (o.get('@type') if isinstance(o, dict) else [i.get('@type') for i in o])
        for o in schema_objects
    ]

    # Visible text summary (what the site actually does)
    if html_content:
        body_m = re.search(r'<body[^>]*>([\s\S]*?)</body>', html_content, re.I)
        if body_m:
            vis = re.sub(r'<script[\s\S]*?</script>', '', body_m.group(1))
            vis = re.sub(r'<style[\s\S]*?</style>', '', vis)
            vis = re.sub(r'<[^>]+>', ' ', vis)
            vis = re.sub(r'\s+', ' ', vis).strip()
            summary['visible_text_excerpt'] = vis[:2000]

    return summary


LIGHT_ANALYSIS_TYPES = {'robots', 'sitemap', 'security', 'datalayer'}
MODEL_HAIKU = 'claude-haiku-4-5-20251001'
MODEL_SONNET = 'claude-sonnet-4-20250514'
MODEL_OPUS = 'claude-opus-4-6'


def call_claude(api_key, system_prompt, user_message, max_tokens=8000, model=None):
    """Call Claude API via urllib with error handling and retry for transient errors."""
    if model is None:
        model = MODEL_SONNET
    payload = json.dumps({
        'model': model,
        'max_tokens': max_tokens,
        'system': system_prompt,
        'messages': [{'role': 'user', 'content': user_message}]
    }).encode('utf-8')

    req = urllib.request.Request('https://api.anthropic.com/v1/messages', data=payload, headers={
        'Content-Type': 'application/json',
        'x-api-key': api_key,
        'anthropic-version': '2023-06-01',
    })

    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = urllib.request.urlopen(req, timeout=120, context=CTX_SECURE)
            data = json.loads(resp.read().decode('utf-8'))
            if 'content' not in data or not data['content']:
                raise ValueError(f"Unexpected API response structure: {list(data.keys())}")
            return data['content'][0]['text']
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace') if e.fp else ''
            if e.code in (429, 500, 502, 503, 529) and attempt < max_retries - 1:
                wait = (2 ** attempt) + (time.time() % 1)  # exponential backoff + jitter
                log('⏳', f'Claude API {e.code}, retry {attempt+1}/{max_retries} in {wait:.1f}s...', C.YELLOW)
                time.sleep(wait)
                # Rebuild request (body consumed)
                req = urllib.request.Request('https://api.anthropic.com/v1/messages', data=payload, headers={
                    'Content-Type': 'application/json',
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01',
                })
                continue
            raise RuntimeError(f"Claude API error {e.code}: {body[:500]}") from e
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            raise RuntimeError(f"Claude API response parse error: {e}") from e
    raise RuntimeError("Claude API: max retries exceeded")


def run_analysis(analysis_type, url, api_key, google_key, homepage_html, extra_htmls=None, discovered=None):
    """Run a single AI analysis. Returns (type, result_text) or (type, error_string)."""
    try:
        content = ''
        clean_url = url.rstrip('/')

        if analysis_type == 'robots':
            _, _, content = fetch_url(clean_url + '/robots.txt')
        elif analysis_type == 'sitemap':
            # Try common sitemap URLs
            for path in ['/sitemap.xml', '/sitemap_index.xml']:
                s, _, body = fetch_url(clean_url + path)
                if s == 200 and body.strip():
                    content = body[:50000]
                    break
            if not content:
                content = 'Sitemap non trovata ai path comuni.'
            else:
                # Parse sitemap XML programmatically
                try:
                    sitemap_urls = re.findall(r'<loc>\s*(.*?)\s*</loc>', content, re.I)
                    sitemap_lastmods = re.findall(r'<lastmod>\s*(.*?)\s*</lastmod>', content, re.I)
                    is_index = '<sitemapindex' in content.lower()
                    unique_domains = set()
                    for u in sitemap_urls:
                        try:
                            unique_domains.add(urllib.parse.urlparse(u).netloc)
                        except Exception:
                            pass

                    # If sitemap index, fetch sub-sitemaps to count total URLs
                    total_urls = 0
                    sub_sitemaps = []
                    if is_index:
                        sub_sitemaps = [u for u in sitemap_urls if u.endswith('.xml')]
                        for sub_url in sub_sitemaps[:20]:  # cap at 20 sub-sitemaps
                            try:
                                s_status, _, s_body = fetch_url(sub_url, timeout=10)
                                if s_status == 200 and s_body:
                                    sub_urls = re.findall(r'<loc>\s*(.*?)\s*</loc>', s_body, re.I)
                                    total_urls += len(sub_urls)
                            except Exception:
                                pass

                    sitemap_data = {
                        'tipo': 'Sitemap Index' if is_index else 'Sitemap singola',
                        'sub_sitemap_count': len(sub_sitemaps) if is_index else 0,
                        'sub_sitemap_names': [u.split('/')[-1] for u in sub_sitemaps] if is_index else [],
                        'url_count_in_index': len(sitemap_urls),
                        'total_urls_across_all_sitemaps': total_urls if is_index else len(sitemap_urls),
                        'domini_unici': list(unique_domains),
                        'lastmod_count': len(sitemap_lastmods),
                        'lastmod_recente': sitemap_lastmods[0] if sitemap_lastmods else 'N/A',
                        'lastmod_meno_recente': sitemap_lastmods[-1] if sitemap_lastmods else 'N/A',
                    }
                    content = f"=== DATI SITEMAP ESTRATTI PROGRAMMATICAMENTE (DATI CERTI) ===\n{json.dumps(sitemap_data, indent=2, ensure_ascii=False)}\n\n=== SITEMAP XML RAW ===\n{content}"
                except Exception:
                    pass
        elif analysis_type in ('performance', 'cwv'):
            # Bug 6: Use shared PSI data from discovered instead of fetching again
            if discovered and discovered.get('_shared_psi', {}).get('value'):
                shared = discovered['_shared_psi']['data']
                content = f"=== DATI OGGETTIVI MISURATI (PageSpeed Insights — DATI CERTI, usa SOLO questi valori) ===\n{json.dumps(shared, indent=2, ensure_ascii=False)}"
            elif google_key:
                psi_url = f'https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={urllib.parse.quote(url, safe="")}&strategy=mobile&category=performance&category=accessibility&category=seo&category=best-practices&key={google_key}'
                _, _, body = fetch_url(psi_url, timeout=60, secure=True)
                try:
                    data = json.loads(body)
                    lr = data.get('lighthouseResult', {})
                    cats = lr.get('categories', {})
                    audits = lr.get('audits', {})
                    content = json.dumps({
                        'scores': {k: round((cats.get(k, {}).get('score', 0) or 0) * 100) for k in ['performance', 'accessibility', 'seo', 'best-practices']},
                        'metrics': {
                            'lcp': audits.get('largest-contentful-paint', {}).get('displayValue', 'N/A'),
                            'inp': audits.get('interaction-to-next-paint', {}).get('displayValue', 'N/A'),
                            'cls': audits.get('cumulative-layout-shift', {}).get('displayValue', 'N/A'),
                            'fcp': audits.get('first-contentful-paint', {}).get('displayValue', 'N/A'),
                            'tbt': audits.get('total-blocking-time', {}).get('displayValue', 'N/A'),
                            'ttfb': audits.get('server-response-time', {}).get('displayValue', 'N/A'),
                        },
                        'opportunities': [
                            {'title': v.get('title'), 'savings': v.get('displayValue'), 'score': v.get('score')}
                            for k, v in audits.items()
                            if v.get('score') is not None and v.get('score', 1) < 1 and v.get('details', {}).get('type') == 'opportunity'
                        ][:10]
                    }, indent=2, ensure_ascii=False)
                except (json.JSONDecodeError, KeyError, TypeError):
                    content = body[:20000]
            else:
                content = 'Google PageSpeed API key non disponibile. Analizza il sito basandoti sull\'HTML fornito.'
                if homepage_html:
                    head = re.search(r'<head[^>]*>([\s\S]*?)</head>', homepage_html, re.I)
                    content += f'\n\nHEAD:\n{head.group(1)[:8000]}' if head else ''
        elif analysis_type == 'cro':
            if homepage_html:
                head = re.search(r'<head[^>]*>([\s\S]*?)</head>', homepage_html, re.I)
                body_m = re.search(r'<body[^>]*>([\s\S]*?)</body>', homepage_html, re.I)
                seo_data = extract_seo_summary(homepage_html)
                content = f"""=== DATI PAGINA ESTRATTI PROGRAMMATICAMENTE (DATI CERTI) ===
{json.dumps(seo_data, indent=2, ensure_ascii=False)}

HEAD:\n{(head.group(1) if head else '')[:5000]}
BODY (first 15000 chars):\n{(body_m.group(1) if body_m else '')[:15000]}"""
            else:
                content = 'HTML homepage non disponibile.'
        else:
            # seo, seo_deep, accessibility, security, advertising
            if homepage_html:
                head = re.search(r'<head[^>]*>([\s\S]*?)</head>', homepage_html, re.I)
                body_m = re.search(r'<body[^>]*>([\s\S]*?)</body>', homepage_html, re.I)
                homepage_content = f"HEAD:\n{(head.group(1) if head else '')[:5000]}\nBODY (first 10000 chars):\n{(body_m.group(1) if body_m else '')[:10000]}"

                # Pre-extract structured SEO data so Claude doesn't hallucinate
                if analysis_type in ('seo', 'seo_deep', 'accessibility', 'cro'):
                    seo_data = extract_seo_summary(homepage_html)
                    homepage_content = f"""=== DATI SEO ESTRATTI PROGRAMMATICAMENTE (DATI CERTI) ===
{json.dumps(seo_data, indent=2, ensure_ascii=False)}

=== HTML HOMEPAGE ===
{homepage_content}"""

                content = f"=== HOMEPAGE ===\n{homepage_content}"

                # Add extra pages content
                if extra_htmls:
                    for ep_url, ep_type, ep_html in extra_htmls[:2]:
                        ep_head = re.search(r'<head[^>]*>([\s\S]*?)</head>', ep_html, re.I)
                        ep_body = re.search(r'<body[^>]*>([\s\S]*?)</body>', ep_html, re.I)
                        ep_content = f"URL: {ep_url}\nHEAD (first 3000 chars):\n{(ep_head.group(1) if ep_head else '')[:3000]}\nBODY (first 8000 chars):\n{(ep_body.group(1) if ep_body else '')[:8000]}"
                        if analysis_type in ('seo', 'seo_deep'):
                            ep_seo = extract_seo_summary(ep_html)
                            ep_content = f"DATI SEO:\n{json.dumps(ep_seo, indent=2, ensure_ascii=False)[:5000]}\n{ep_content}"
                        content += f"\n\n=== PAGINA {ep_type.upper()} ===\n{ep_content}"
            else:
                content = 'HTML non disponibile.'
            # For SEO analyses, also fetch robots.txt, sitemap, and a product page
            if analysis_type in ('seo', 'seo_deep'):
                try:
                    _, _, robots_body = fetch_url(clean_url + '/robots.txt')
                    if robots_body:
                        content += f"\n\n=== ROBOTS.TXT ===\n{robots_body[:5000]}"
                except Exception:
                    pass
                try:
                    _, _, sitemap_body = fetch_url(clean_url + '/sitemap.xml')
                    if sitemap_body:
                        content += f"\n\n=== SITEMAP.XML (first 5000 chars) ===\n{sitemap_body[:5000]}"
                except Exception:
                    pass
                # Fetch a product page to analyze its schema markup
                if homepage_html:
                    try:
                        product_patterns = r'/(?:products?|prodott[oi]|p)/[^"\'#?\s]+'
                        product_links = list(set(re.findall(product_patterns, homepage_html, re.I)))
                        if product_links:
                            prod_url = clean_url + product_links[0]
                            _, _, prod_html = fetch_url(prod_url)
                            if prod_html:
                                prod_seo = extract_seo_summary(prod_html)
                                content += f"\n\n=== PAGINA PRODOTTO: {product_links[0]} ===\n"
                                content += f"DATI SEO PRODOTTO:\n{json.dumps(prod_seo, indent=2, ensure_ascii=False)[:8000]}"
                    except Exception:
                        pass

        prompts = _get_prompts()
        prompt = prompts.get(analysis_type, prompts.get('seo', ''))
        discovery_block = ''
        if discovered:
            discovery_block = f"\n=== DATI AUTO-DISCOVERY (FASE 1) ===\n{json.dumps(discovered, indent=2, ensure_ascii=False, default=str)[:10000]}\n=== FINE DATI AUTO-DISCOVERY ===\n\n"

        # Bug 6: Inject shared PSI metrics into ALL analyses for consistency
        if discovered and discovered.get('_shared_psi', {}).get('value') and analysis_type not in ('performance', 'cwv'):
            shared = discovered['_shared_psi']['data']
            discovery_block += f"\n=== DATI OGGETTIVI MISURATI (PageSpeed Insights — riferimento, NON duplicare nell'analisi performance) ===\n{json.dumps(shared.get('metrics', {}), indent=2, ensure_ascii=False)}\nScores: {json.dumps(shared.get('scores', {}), ensure_ascii=False)}\n=== FINE DATI OGGETTIVI ===\n"

        # Add YAML checklist context
        yaml_context = get_yaml_context(analysis_type, discovered)
        if yaml_context:
            discovery_block += f"\n=== KNOWLEDGE BASE (usa come riferimento per i check) ===\n{yaml_context}\n=== FINE KNOWLEDGE BASE ===\n"

        # Add SquirrelScan deep crawl results (relevant to analysis type)
        if discovered and discovered.get('_squirrelscan', {}).get('value'):
            ss_issues = discovered['_squirrelscan'].get('issues', [])
            # Filter issues by category + ruleId matching analysis type
            # SquirrelScan categories: Core SEO, Accessibility, Performance, Security,
            # Links, Images, Content, Crawlability, Structured Data, E-E-A-T, Mobile
            ss_category_map = {
                'seo': ('core seo', 'crawlability', 'structured data', 'content', 'e-e-a-t', 'images'),
                'seo_deep': ('core seo', 'crawlability', 'structured data', 'content', 'e-e-a-t', 'links', 'images', 'mobile'),
                'security': ('security',),
                'performance': ('performance', 'images'),
                'cwv': ('performance',),
                'accessibility': ('accessibility',),
                'datalayer': ('core seo', 'structured data'),
                'advertising': ('core seo', 'performance', 'structured data'),
                'cro': ('core seo', 'performance', 'accessibility', 'links', 'mobile', 'images'),
                'robots': ('crawlability', 'core seo'),
                'sitemap': ('crawlability', 'core seo'),
            }
            match_cats = ss_category_map.get(analysis_type, ())
            if match_cats:
                filtered = [i for i in ss_issues if i.get('category', '').lower() in match_cats]
            else:
                filtered = ss_issues[:30]
            if filtered:
                ss_block = json.dumps(filtered[:50], indent=1, ensure_ascii=False, default=str)[:6000]
                crawler_note = ""
                if discovered.get('_crawler_limitations', {}).get('value'):
                    crawler_note = "\nNOTA: Le URL contrassegnate come 'limite crawler' sono raggiungibili (HTTP 200) ma non scansionate da SquirrelScan. NON segnalarle come problemi del sito.\n"
                discovery_block += f"\n=== SQUIRRELSCAN DEEP CRAWL ({len(filtered)} issue rilevanti) ==={crawler_note}\n{ss_block}\n=== FINE SQUIRRELSCAN ===\n"

        content_limit = 20000
        user_msg = f"Audit del sito: {url}\n\nTipo analisi: {analysis_type}\n\n{discovery_block}{prompt}\n\nContenuto recuperato:\n```\n{content[:content_limit]}\n```"

        # Use Haiku for deterministic/simple analyses, Opus for qualitative ones
        model = MODEL_HAIKU if analysis_type in LIGHT_ANALYSIS_TYPES else MODEL_OPUS
        tokens = 6000 if analysis_type in LIGHT_ANALYSIS_TYPES else 8000
        result = call_claude(api_key, _get_osmani_base(), user_msg, max_tokens=tokens, model=model)
        return (analysis_type, result)
    except Exception as e:
        return (analysis_type, f'ERRORE: {e}')


# ─── OSMANI VALIDATORS (Programmatic) ────────────────────────────────────────

def measure_resources(html_content):
    """Measure page resources from HTML: count scripts, stylesheets, images, estimate sizes."""
    if not html_content:
        return {}
    scripts = re.findall(r'<script[^>]*src=["\']([^"\']+)["\']', html_content, re.I)
    stylesheets = re.findall(r'<link[^>]*rel=["\']stylesheet["\'][^>]*href=["\']([^"\']+)["\']', html_content, re.I)
    images = re.findall(r'<img[^>]*src=["\']([^"\']+)["\']', html_content, re.I)
    inline_scripts = re.findall(r'<script(?![^>]*src=)[^>]*>([\s\S]*?)</script>', html_content, re.I)
    inline_styles = re.findall(r'<style[^>]*>([\s\S]*?)</style>', html_content, re.I)

    return {
        'html_size': len(html_content.encode('utf-8', errors='replace')),
        'script_count': len(scripts),
        'stylesheet_count': len(stylesheets),
        'image_count': len(images),
        'inline_script_bytes': sum(len(s.encode('utf-8', errors='replace')) for s in inline_scripts),
        'inline_style_bytes': sum(len(s.encode('utf-8', errors='replace')) for s in inline_styles),
        'external_scripts': scripts,
        'external_stylesheets': stylesheets,
        'images': images,
    }


def fetch_crux(url, api_key):
    """Fetch Chrome UX Report (CrUX) field data for a URL. Falls back to origin-level if URL-level unavailable."""
    if not api_key:
        return None
    # Try URL-level first, then origin-level
    parsed = urllib.parse.urlparse(url)
    origin = f'{parsed.scheme}://{parsed.netloc}'
    for query_params in [{'url': url}, {'origin': origin}]:
        try:
            payload = json.dumps({
                **query_params,
                'formFactor': 'PHONE',
                'metrics': ['largest_contentful_paint', 'interaction_to_next_paint',
                            'cumulative_layout_shift', 'experimental_time_to_first_byte']
            }).encode('utf-8')
            req = urllib.request.Request(
                f'https://chromeuxreport.googleapis.com/v1/records:queryRecord?key={api_key}',
                data=payload,
                headers={'Content-Type': 'application/json'}
            )
            resp = urllib.request.urlopen(req, timeout=15, context=CTX_SECURE)
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('record', {}).get('metrics'):
                level = 'URL' if 'url' in query_params else 'origin'
                log('📊', f'CrUX {level}-level data disponibili', C.DIM)
                return data
        except Exception:
            continue
    return None


def validate_budgets(resources, crux_data, cfg=None):
    """Validate resources and CrUX data against Osmani performance budgets. Returns findings dict."""
    if cfg is None:
        cfg = load_config()
    budgets = cfg.get('performance_budgets', {})
    findings = {}

    # HTML size check
    if resources:
        html_kb = resources.get('html_size', 0) / 1024
        budget_kb = budgets.get('page_weight', 1500000) / 1024
        if html_kb > budget_kb:
            findings['a0_2_1'] = {
                'value': False,
                'note': f'⚠️ HTML {html_kb:.0f}KB supera budget {budget_kb:.0f}KB. Impatto: LCP degradato. Fix: ottimizzare risorse, compressione.'
            }
        else:
            findings['a0_2_1'] = {'value': True, 'note': f'HTML {html_kb:.0f}KB entro budget {budget_kb:.0f}KB'}

        # Script count warning
        if resources.get('script_count', 0) > 15:
            findings['a0_2_2'] = {
                'value': False,
                'note': f'⚠️ {resources["script_count"]} script esterni. Impatto: main thread bloccato, INP degradato. Fix: consolidare, defer/async.'
            }

        # Image count without lazy loading hint
        if resources.get('image_count', 0) > 20:
            findings['a0_2_3'] = {
                'value': False,
                'note': f'⚠️ {resources["image_count"]} immagini. Verificare lazy loading below-fold e formati moderni (WebP/AVIF).'
            }

    # CrUX validation
    if crux_data and crux_data.get('record', {}).get('metrics'):
        metrics = crux_data['record']['metrics']

        cwv_checks = {
            'largest_contentful_paint': ('a0_2_4', 'LCP', budgets.get('lcp', {})),
            'interaction_to_next_paint': ('a0_2_5', 'INP', budgets.get('inp', {})),
            'cumulative_layout_shift': ('a0_2_6', 'CLS', budgets.get('cls', {})),
            'experimental_time_to_first_byte': ('a0_2_7', 'TTFB', None),
        }

        for metric_key, (check_id, label, thresholds) in cwv_checks.items():
            metric = metrics.get(metric_key, {})
            p75 = metric.get('percentiles', {}).get('p75')
            if p75 is None:
                continue

            if metric_key == 'experimental_time_to_first_byte':
                ttfb_budget = budgets.get('ttfb', 800)
                if p75 > ttfb_budget:
                    findings[check_id] = {
                        'value': False,
                        'note': f'⚠️ TTFB p75={p75}ms > {ttfb_budget}ms. Impatto: LCP ritardato. Fix: ottimizzare server, CDN, edge caching.'
                    }
                else:
                    findings[check_id] = {'value': True, 'note': f'TTFB p75={p75}ms ✓'}
            elif thresholds:
                good = thresholds.get('good', 0)
                if metric_key == 'cumulative_layout_shift':
                    val_str = f'{p75:.2f}'
                else:
                    val_str = f'{p75}ms'
                if p75 <= good:
                    findings[check_id] = {'value': True, 'note': f'{label} p75={val_str} (buono ✓)'}
                elif p75 <= thresholds.get('needs_improvement', good):
                    findings[check_id] = {
                        'value': False,
                        'note': f'⚠️ {label} p75={val_str} (migliorabile). Target: {good}{"" if metric_key == "cumulative_layout_shift" else "ms"}.'
                    }
                else:
                    findings[check_id] = {
                        'value': False,
                        'note': f'⚠️ {label} p75={val_str} (scarso). Target: {good}{"" if metric_key == "cumulative_layout_shift" else "ms"}. Intervento urgente.'
                    }

    return findings


# ─── PLAYWRIGHT RENDERING (Optional) ────────────────────────────────────────

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


def fetch_rendered(url, timeout=30000):
    """Fetch URL with Playwright (JS rendering). Returns (html, True) or falls back to fetch_url."""
    if not HAS_PLAYWRIGHT:
        status, headers, body = fetch_url(url)
        return body, False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
                page.goto(url, wait_until='domcontentloaded', timeout=timeout)
                # Wait for JS to render (SPAs keep connections open, networkidle hangs)
                page.wait_for_timeout(3000)
                html = page.content()
                return html, True
            finally:
                browser.close()
    except Exception:
        # Fallback to static fetch
        status, headers, body = fetch_url(url)
        return body, False


# ─── REPORT GENERATOR ───────────────────────────────────────────────────────

def parse_findings(ai_results):
    """Extract structured findings from AI analysis text."""
    findings = []
    for atype, text in ai_results.items():
        if text.startswith('ERRORE:'): continue
        # Parse **FINDING [SEVERITY]:** patterns
        blocks = re.split(r'\*\*FINDING\s*\[', text)
        for block in blocks[1:]:
            sev_m = re.match(r'(CRITICO|ALTO|MEDIO|BASSO)\]\s*:\*\*\s*(.*?)(?:\n|$)', block)
            if not sev_m: continue
            severity = sev_m.group(1)
            title = sev_m.group(2).strip()

            desc = ''
            impact = ''
            fix = ''
            for line in block.split('\n'):
                line = line.strip('- ').strip()
                if line.lower().startswith('problema:'):
                    desc = line[len('problema:'):].strip()
                elif line.lower().startswith('impatto:'):
                    impact = line[len('impatto:'):].strip()
                elif line.lower().startswith('fix:'):
                    fix = line[len('fix:'):].strip()

            findings.append({
                'severity': severity,
                'title': title,
                'description': desc,
                'impact': impact,
                'recommendation': fix,
                'source': atype,
            })
    return findings


def estimate_scores(findings, ai_results):
    """Estimate scores per area based on findings severity."""
    area_map = {
        'consent': ['consent'],
        'tracking': ['tracking', 'datalayer'],
        'ecommerce': ['datalayer'],
        'seo': ['seo', 'seo_deep', 'robots', 'sitemap'],
        'accessibility': ['accessibility'],
        'advertising': ['advertising', 'performance', 'cwv'],
    }
    scores = {}
    for area_id, sources in area_map.items():
        area_findings = [f for f in findings if f['source'] in sources]
        # Start at 10, deduct for severity
        score = 10
        for f in area_findings:
            if f['severity'] == 'CRITICO': score -= 3
            elif f['severity'] == 'ALTO': score -= 2
            elif f['severity'] == 'MEDIO': score -= 1
            elif f['severity'] == 'BASSO': score -= 0.5
        scores[area_id] = max(0, min(10, round(score)))

    # Try to extract score from robots/sitemap AI output
    for key in ('robots', 'sitemap'):
        text = ai_results.get(key, '')
        m = re.search(r'SCORE[^:]*:\s*(\d+)\s*/\s*10', text)
        if m:
            if key == 'robots': scores['seo'] = min(10, max(0, int(m.group(1))))

    return scores


def generate_report_html(domain, client_name, scores, findings, discovered, ai_results, template):
    """Generate the full McKinsey-style HTML report."""
    total = sum(scores.values())
    level = {'label': 'N/A', 'color': '#999'}
    for l in template['scoring']['levels']:
        if l['min'] <= total <= l['max']:
            level = l
            break

    date_str = datetime.now().strftime('%d %B %Y')
    # Italian month names
    months_it = {'January':'Gennaio','February':'Febbraio','March':'Marzo','April':'Aprile','May':'Maggio','June':'Giugno','July':'Luglio','August':'Agosto','September':'Settembre','October':'Ottobre','November':'Novembre','December':'Dicembre'}
    for en, it in months_it.items():
        date_str = date_str.replace(en, it)

    sev_counts = {'CRITICO': 0, 'ALTO': 0, 'MEDIO': 0, 'BASSO': 0}
    for f in findings:
        if f['severity'] in sev_counts: sev_counts[f['severity']] += 1

    by_sev = {'CRITICO': [], 'ALTO': [], 'MEDIO': [], 'BASSO': []}
    for f in findings:
        if f['severity'] in by_sev: by_sev[f['severity']].append(f)

    def esc(s):
        return html.escape(str(s)) if s else ''

    # Build score cards
    score_cards_html = ''
    for a in template['scoring']['areas']:
        sv = scores.get(a['id'], 0)
        score_cards_html += f'''
        <div class="score-card">
          <div class="score-value">{sv}</div>
          <div class="score-label">{esc(a["name"])} (/{a["max"]})</div>
        </div>'''

    # Build findings HTML
    findings_html = ''
    for sev in ['CRITICO', 'ALTO', 'MEDIO', 'BASSO']:
        for f in by_sev[sev]:
            sev_low = sev.lower()
            findings_html += f'''
      <div class="finding {sev_low}">
        <div class="severity {sev_low}">{sev}</div>
        <h4>{esc(f["title"])}</h4>
        {f'<p>{esc(f["description"])}</p>' if f["description"] else ''}
        {f'<p><strong>Impatto Business:</strong> {esc(f["impact"])}</p>' if f["impact"] else ''}
        {f'<p><strong>Raccomandazione:</strong> {esc(f["recommendation"])}</p>' if f["recommendation"] else ''}
      </div>'''

    # Build checklist HTML
    checks = {k: v.get('value', False) for k, v in discovered.items() if isinstance(v, dict) and not k.startswith('_')}
    notes = {k: v.get('note', '') for k, v in discovered.items() if isinstance(v, dict) and not k.startswith('_')}

    checklist_html = ''
    for phase in template['phases']:
        checklist_html += f'<h3>{phase["icon"]} {phase["id"]} - {esc(phase["name"])}</h3>\n<div class="checklist-summary"><table><tr><th>Check</th><th>Stato</th><th>Note</th></tr>'
        for s in phase['sections']:
            for item in s['items']:
                iid = item['id']
                ok = checks.get(iid, False)
                cls = 'status-ok' if ok else 'status-miss'
                sym = '&#10003;' if ok else '&#10007;'
                checklist_html += f'<tr><td>{esc(item["label"])}</td><td class="{cls}">{sym}</td><td>{esc(notes.get(iid, "-"))}</td></tr>'
        checklist_html += '</table></div>\n'

    # Build roadmap HTML
    roadmap_html = ''
    for f in by_sev['CRITICO']:
        roadmap_html += f'<div class="roadmap-item"><span class="roadmap-priority p1">URGENTE</span><span>{esc(f["title"])} — {esc(f["recommendation"] or "Intervento immediato richiesto")}</span></div>'
    for f in by_sev['ALTO']:
        roadmap_html += f'<div class="roadmap-item"><span class="roadmap-priority p2">1 MESE</span><span>{esc(f["title"])} — {esc(f["recommendation"] or "Intervento a breve termine")}</span></div>'
    for f in by_sev['MEDIO']:
        roadmap_html += f'<div class="roadmap-item"><span class="roadmap-priority p3">3 MESI</span><span>{esc(f["title"])} — {esc(f["recommendation"] or "Ottimizzazione consigliata")}</span></div>'

    # Build AI analysis sections
    ai_sections_html = ''
    appendix_html = ''
    appendix_types = {'accessibility', 'security'}
    analysis_labels = {
        'performance': ('⚡', 'Performance & Core Web Vitals'),
        'cwv': ('📊', 'Core Web Vitals Dettaglio'),
        'seo': ('🔎', 'SEO Tecnico'),
        'seo_deep': ('🔬', 'SEO Approfondito & E-E-A-T'),
        'accessibility': ('♿', 'Accessibility WCAG 2.1'),
        'security': ('🔒', 'Security & Best Practices'),
        'robots': ('🤖', 'Analisi robots.txt'),
        'sitemap': ('🗺️', 'Analisi Sitemap'),
        'datalayer': ('📦', 'DataLayer & Ecommerce Tracking'),
        'cro': ('🎯', 'CRO & Conversion Optimization'),
        'advertising': ('📢', 'Advertising Readiness'),
    }
    for atype, text in ai_results.items():
        if text.startswith('ERRORE:'): continue
        icon, label = analysis_labels.get(atype, ('📋', atype))
        # Convert markdown bold to HTML
        formatted = esc(text)
        formatted = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', formatted)
        formatted = formatted.replace('\n', '<br>\n')
        section_block = f'''
  <div class="ai-section">
    <h3>{icon} {label}</h3>
    <div class="ai-content">{formatted}</div>
  </div>'''
        if atype in appendix_types:
            appendix_html += section_block
        else:
            ai_sections_html += section_block

    # Tech stack summary table
    tech_categories = [
        ('CMS / Framework', 'a0_1_1'), ('CDN', 'a0_1_2'), ('Payment Gateway', 'a0_1_3'),
        ('Analytics', 'a0_1_4'), ('Email Marketing', 'a0_1_5'), ('A/B Testing', 'a0_1_6'),
        ('CRM', 'a0_1_7'), ('Chat / Support', 'a0_1_8'),
        ('GTM', 'a2_1_1'), ('GA4', 'a2_1_2'), ('Google Ads', 'a2_1_3'),
        ('Meta Pixel', 'a2_3_1'), ('Clarity/Hotjar', 'a2_3_2'),
        ('Cookie Banner', 'a1_1_1'), ('Consent Mode', 'a1_2_1'),
        ('Schema Markup', 'a4_4_1'), ('DataLayer', 'a3_1_1'),
    ]
    tech_rows = ''
    for label, key in tech_categories:
        if key in discovered and isinstance(discovered[key], dict):
            tech_rows += f'<tr><td><strong>{esc(label)}</strong></td><td class="status-ok">&#10003;</td><td>{esc(discovered[key].get("note", ""))}</td></tr>'

    # Pages analyzed section
    disc_pages = discovered.get('_discovered_pages', [])
    if disc_pages:
        pages_rows = ''
        for p in disc_pages:
            ptype = esc(p.get('type', 'unknown')).capitalize()
            purl = esc(p.get('url', ''))
            auto_tag = ' <span style="font-size:11px;color:#9ca3af">(auto-discovered)</span>' if p.get('discovered') else ''
            pages_rows += f'<div style="padding:6px 12px;border-left:3px solid #e5e7eb;margin:4px 0;font-size:14px"><strong style="color:#0f3460;margin-right:8px">{ptype}</strong> <a href="{purl}" target="_blank">{purl}</a>{auto_tag}</div>'
        pages_html = f'<h2>Pagine Analizzate ({len(disc_pages)})</h2>\n<div style="margin:12px 0">{pages_rows}</div>'
    else:
        pages_html = ''

    # Radar chart data
    radar_labels = json.dumps([a['name'] for a in template['scoring']['areas']])
    radar_data = json.dumps([scores.get(a['id'], 0) for a in template['scoring']['areas']])

    report = f'''<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MarTech Audit Report — {esc(client_name)}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Inter', -apple-system, sans-serif; color: #1a1a2e; line-height: 1.7; background: #fff; }}
  .page {{ max-width: 860px; margin: 0 auto; padding: 48px 40px; }}

  /* COVER */
  .cover {{ text-align: center; padding: 100px 60px; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 40%, #0f3460 100%); color: white; border-radius: 16px; margin-bottom: 48px; position: relative; overflow: hidden; }}
  .cover::before {{ content: ''; position: absolute; top: -50%; left: -50%; width: 200%; height: 200%; background: radial-gradient(circle, rgba(255,255,255,0.03) 0%, transparent 60%); }}
  .cover .logo {{ font-size: 13px; letter-spacing: 4px; text-transform: uppercase; opacity: 0.6; margin-bottom: 24px; }}
  .cover h1 {{ font-size: 38px; font-weight: 800; margin-bottom: 8px; letter-spacing: -0.5px; }}
  .cover .subtitle {{ font-size: 18px; opacity: 0.75; margin-bottom: 40px; font-weight: 300; }}
  .cover .domain {{ font-size: 22px; background: rgba(255,255,255,0.12); padding: 12px 32px; border-radius: 12px; display: inline-block; margin: 16px 0; font-weight: 600; backdrop-filter: blur(4px); border: 1px solid rgba(255,255,255,0.1); }}
  .cover .meta {{ font-size: 14px; opacity: 0.6; margin-top: 32px; }}
  .cover .meta p {{ margin: 4px 0; }}

  h2 {{ font-size: 24px; font-weight: 700; margin: 48px 0 20px; padding-bottom: 12px; border-bottom: 3px solid #0f3460; color: #0f3460; }}
  h3 {{ font-size: 17px; font-weight: 600; margin: 28px 0 12px; color: #1a1a2e; }}

  /* EXEC SUMMARY */
  .exec-summary {{ background: linear-gradient(135deg, #f8fafc, #eef2ff); padding: 32px; border-radius: 12px; margin-bottom: 40px; border-left: 5px solid #0f3460; }}
  .exec-summary p {{ margin-bottom: 10px; font-size: 15px; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-top: 20px; }}
  .kpi-card {{ background: white; padding: 16px; border-radius: 8px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .kpi-card .kpi-value {{ font-size: 28px; font-weight: 800; }}
  .kpi-card .kpi-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #666; margin-top: 4px; }}

  /* SCORES */
  .scores-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 24px 0; }}
  .score-card {{ background: #f8fafc; padding: 24px 16px; border-radius: 12px; text-align: center; border: 1px solid #e5e7eb; transition: transform 0.2s; }}
  .score-card .score-value {{ font-size: 40px; font-weight: 800; color: #0f3460; }}
  .score-card .score-label {{ font-size: 12px; color: #666; margin-top: 4px; font-weight: 500; }}
  .total-card {{ grid-column: span 3; background: linear-gradient(135deg, #1a1a2e, #0f3460); color: white; padding: 32px; border-radius: 12px; text-align: center; }}
  .total-card .score-value {{ font-size: 56px; font-weight: 800; }}
  .maturity-badge {{ display: inline-block; padding: 6px 20px; border-radius: 24px; font-weight: 700; font-size: 14px; margin-top: 8px; letter-spacing: 1px; }}

  /* RADAR */
  .radar-container {{ text-align: center; margin: 32px 0; }}
  canvas#radar {{ max-width: 420px; margin: 0 auto; }}

  /* TECH STACK TABLE */
  .tech-table {{ width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 14px; }}
  .tech-table th, .tech-table td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #e5e7eb; }}
  .tech-table th {{ background: #f1f5f9; font-weight: 600; color: #0f3460; }}
  .tech-table tr:hover {{ background: #f8fafc; }}

  /* FINDINGS */
  .finding {{ padding: 20px; margin: 14px 0; border-radius: 10px; border-left: 5px solid; }}
  .finding.critico {{ background: #fef2f2; border-color: #ef4444; }}
  .finding.alto {{ background: #fff7ed; border-color: #f59e0b; }}
  .finding.medio {{ background: #fefce8; border-color: #eab308; }}
  .finding.basso {{ background: #f0fdf4; border-color: #22c55e; }}
  .finding .severity {{ font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; }}
  .finding .severity.critico {{ color: #ef4444; }}
  .finding .severity.alto {{ color: #f59e0b; }}
  .finding .severity.medio {{ color: #eab308; }}
  .finding .severity.basso {{ color: #22c55e; }}
  .finding h4 {{ font-size: 15px; margin-bottom: 8px; }}
  .finding p {{ font-size: 14px; color: #444; margin: 4px 0; line-height: 1.6; }}

  /* AI ANALYSIS SECTIONS */
  .ai-section {{ margin: 24px 0; padding: 24px; background: #f8fafc; border-radius: 12px; border: 1px solid #e5e7eb; }}
  .ai-section h3 {{ margin-top: 0; color: #0f3460; }}
  .ai-content {{ font-size: 14px; line-height: 1.8; color: #333; }}

  /* CHECKLIST */
  .checklist-summary {{ margin: 16px 0; }}
  .checklist-summary table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  .checklist-summary th, .checklist-summary td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #e5e7eb; }}
  .checklist-summary th {{ background: #f1f5f9; font-weight: 600; color: #0f3460; }}
  .status-ok {{ color: #22c55e; font-weight: 700; }}
  .status-miss {{ color: #ef4444; font-weight: 700; }}

  /* ROADMAP */
  .roadmap {{ margin: 20px 0; }}
  .roadmap-item {{ display: flex; gap: 16px; padding: 14px 0; border-bottom: 1px solid #f0f0f0; align-items: flex-start; }}
  .roadmap-priority {{ min-width: 90px; font-weight: 700; font-size: 12px; padding: 4px 12px; border-radius: 6px; text-align: center; }}
  .roadmap-priority.p1 {{ color: #ef4444; background: #fef2f2; }}
  .roadmap-priority.p2 {{ color: #f59e0b; background: #fff7ed; }}
  .roadmap-priority.p3 {{ color: #3b82f6; background: #eff6ff; }}
  .roadmap-item span:last-child {{ font-size: 14px; }}

  .footer {{ text-align: center; margin-top: 64px; padding-top: 24px; border-top: 2px solid #e5e7eb; font-size: 12px; color: #999; }}
  .footer p {{ margin: 4px 0; }}

  @media print {{
    .page {{ padding: 20px; }}
    .cover {{ page-break-after: always; }}
    h2 {{ page-break-before: always; }}
    .finding, .ai-section {{ break-inside: avoid; }}
    .radar-container {{ page-break-inside: avoid; }}
  }}
</style>
</head>
<body>
<div class="page">

  <!-- COVER -->
  <div class="cover">
    <div class="logo">Mr Tech</div>
    <h1>MarTech Audit Report</h1>
    <div class="subtitle">Analisi Tecnica &amp; Raccomandazioni Strategiche</div>
    <div class="domain">{esc(domain)}</div>
    <div class="meta">
      <p><strong>Cliente:</strong> {esc(client_name)}</p>
      <p><strong>Data:</strong> {date_str}</p>
      <p><strong>Tipo:</strong> Audit Senza Accessi (External Recon)</p>
    </div>
  </div>

  <!-- EXECUTIVE SUMMARY -->
  <h2>Executive Summary</h2>
  <div class="exec-summary">
    <p>L'audit MarTech del dominio <strong>{esc(domain)}</strong> ha evidenziato un livello di maturit&agrave;
    <strong style="color:{level['color']}">{level['label']}</strong> con un punteggio complessivo di
    <strong>{total}/60</strong>.</p>
    {'<p>&#128308; Sono stati identificati <strong>' + str(sev_counts["CRITICO"]) + ' problemi critici</strong> che richiedono intervento immediato.</p>' if sev_counts['CRITICO'] else ''}
    {'<p>&#128992; <strong>' + str(sev_counts["ALTO"]) + ' problemi ad alta priorit&agrave;</strong> con impatto significativo.</p>' if sev_counts['ALTO'] else ''}
    <div class="kpi-grid">
      <div class="kpi-card"><div class="kpi-value" style="color:#ef4444">{sev_counts['CRITICO']}</div><div class="kpi-label">Critici</div></div>
      <div class="kpi-card"><div class="kpi-value" style="color:#f59e0b">{sev_counts['ALTO']}</div><div class="kpi-label">Alti</div></div>
      <div class="kpi-card"><div class="kpi-value" style="color:#eab308">{sev_counts['MEDIO']}</div><div class="kpi-label">Medi</div></div>
      <div class="kpi-card"><div class="kpi-value" style="color:#22c55e">{sev_counts['BASSO']}</div><div class="kpi-label">Bassi</div></div>
    </div>
  </div>

  <!-- SCORING DASHBOARD -->
  <h2>Scoring Dashboard</h2>
  <div class="scores-grid">
    {score_cards_html}
    <div class="total-card">
      <div class="score-value">{total}<span style="font-size:24px;opacity:0.6">/60</span></div>
      <div class="score-label">Punteggio Complessivo</div>
      <div class="maturity-badge" style="background:{level['color']};color:white">{level['label']}</div>
    </div>
  </div>

  <div class="radar-container">
    <canvas id="radar" width="420" height="420"></canvas>
  </div>

  <!-- PAGINE ANALIZZATE -->
  {pages_html}

  <!-- TECH STACK -->
  <h2>Tech Stack Rilevato</h2>
  <table class="tech-table">
    <tr><th>Categoria</th><th>Stato</th><th>Dettaglio</th></tr>
    {tech_rows}
  </table>

  <!-- AI ANALYSIS SECTIONS -->
  <h2>Analisi AI Dettagliata</h2>
  {ai_sections_html}

  <!-- FINDINGS -->
  <h2>Findings per Severit&agrave;</h2>
  {findings_html if findings_html else '<p style="color:#666">Nessun finding strutturato estratto. Consulta le sezioni di analisi AI sopra per i dettagli.</p>'}

  <!-- CHECKLIST -->
  <h2>Checklist Audit Completata</h2>
  {checklist_html}

  <!-- ROADMAP -->
  <h2>Roadmap di Interventi</h2>
  <div class="roadmap">
    {roadmap_html if roadmap_html else '<p style="color:#666">Consulta le sezioni di analisi per la prioritizzazione degli interventi.</p>'}
  </div>

  <!-- APPENDICE -->
  <h2>Appendice — Security &amp; Accessibility</h2>
  {appendix_html if appendix_html else '<p style="color:#666">Nessun dato di appendice disponibile.</p>'}

  <div class="footer">
    <p><strong>Report generato da MarTech Audit Tool — Mr Tech</strong></p>
    <p>{date_str}</p>
    <p style="margin-top:8px;opacity:0.6">Powered by Claude AI &amp; Addy Osmani Web Quality Methodology</p>
  </div>

</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script>
  const ctx = document.getElementById('radar');
  if (ctx) {{
    new Chart(ctx, {{
      type: 'radar',
      data: {{
        labels: {radar_labels},
        datasets: [{{
          label: 'Score',
          data: {radar_data},
          backgroundColor: 'rgba(15, 52, 96, 0.15)',
          borderColor: '#0f3460',
          pointBackgroundColor: '#0f3460',
          pointBorderColor: '#fff',
          pointRadius: 5,
          borderWidth: 2.5
        }}]
      }},
      options: {{
        scales: {{
          r: {{ min: 0, max: 10, ticks: {{ stepSize: 2, font: {{ size: 11 }} }}, pointLabels: {{ font: {{ size: 12, weight: '600' }} }} }}
        }},
        plugins: {{ legend: {{ display: false }} }}
      }}
    }});
  }}
</script>
</body>
</html>'''

    return report


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='MarTech Audit Tool — CLI Edition')
    parser.add_argument('domain', help='Dominio da analizzare (es: example.com)')
    parser.add_argument('--client', default=None, help='Nome del cliente')
    parser.add_argument('--output', default=None, help='Path file output HTML')
    parser.add_argument('--pages', default=None, help='URL aggiuntive da scansionare (separate da virgola)')
    parser.add_argument('--render', action='store_true', help='Usa Playwright per JS rendering (richiede: pip install playwright && playwright install chromium)')
    parser.add_argument('--mode', choices=['quick', 'deep'], default='quick', help='Modalità audit: quick (default) o deep')
    args = parser.parse_args()

    domain = args.domain.strip().replace('https://', '').replace('http://', '').rstrip('/')
    client_name = args.client or domain
    url = f'https://{domain}'

    print(f"\n{C.BOLD}{C.MAGENTA}")
    print("  ███╗   ███╗██████╗    ████████╗███████╗ ██████╗██╗  ██╗")
    print("  ████╗ ████║██╔══██╗   ╚══██╔══╝██╔════╝██╔════╝██║  ██║")
    print("  ██╔████╔██║██████╔╝      ██║   █████╗  ██║     ███████║")
    print("  ██║╚██╔╝██║██╔══██╗      ██║   ██╔══╝  ██║     ██╔══██║")
    print("  ██║ ╚═╝ ██║██║  ██║      ██║   ███████╗╚██████╗██║  ██║")
    print("  ╚═╝     ╚═╝╚═╝  ╚═╝      ╚═╝   ╚══════╝ ╚═════╝╚═╝  ╚═╝")
    print(f"{C.RESET}")
    print(f"  {C.DIM}MarTech Audit Tool — CLI Edition{C.RESET}")
    print(f"  {C.DIM}Dominio: {C.BOLD}{domain}{C.RESET}  |  {C.DIM}Cliente: {C.BOLD}{client_name}{C.RESET}\n")

    # ── MODE GATE ──
    if args.mode == 'deep':
        from deep import run_deep_mode
        run_deep_mode(url, args)
        return

    # Load API keys: environment variables first, then .env file as fallback
    api_key = os.environ.get('CLAUDE_API_KEY', '')
    google_key = os.environ.get('GOOGLE_API_KEY', '')
    if not api_key or not google_key:
        env_path = os.path.join(TOOL_DIR, 'credentials', '.env')
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if not api_key and line.startswith('CLAUDE_API_KEY='):
                        api_key = line.split('=', 1)[1].strip()
                    elif not google_key and line.startswith('GOOGLE_API_KEY='):
                        google_key = line.split('=', 1)[1].strip()

    if not api_key:
        print(f"  {C.RED}ERRORE: CLAUDE_API_KEY non trovata. Imposta la variabile d'ambiente o il file credentials/.env{C.RESET}")
        sys.exit(1)

    log('🔑', 'API key caricata', C.GREEN)
    if google_key:
        log('🔑', 'Google API key caricata (PageSpeed)', C.GREEN)

    # Load template
    template_path = os.path.join(TOOL_DIR, 'data', 'checklists', 'audit-template.json')
    try:
        with open(template_path, encoding='utf-8') as f:
            template = json.load(f)
    except FileNotFoundError:
        print(f"  {C.RED}ERRORE: Template non trovato: {template_path}{C.RESET}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"  {C.RED}ERRORE: Template JSON malformato: {e}{C.RESET}")
        sys.exit(1)
    log('📋', 'Template audit caricato', C.GREEN)

    # ── PHASE 1: Auto-Discovery ──
    extra_urls = [u.strip() for u in args.pages.split(',')] if args.pages else []

    header('FASE 1 — Auto-Discovery & Scanning')
    if args.render and HAS_PLAYWRIGHT:
        log('🎭', 'Playwright rendering abilitato', C.GREEN)
    elif args.render:
        log('⚠️', 'Playwright non installato. Usa: pip install playwright && playwright install chromium', C.YELLOW)
    # Run auto_discover and SquirrelScan in parallel
    squirrel_future = None
    if SQUIRREL_BIN:
        squirrel_executor = ThreadPoolExecutor(max_workers=1)
        squirrel_future = squirrel_executor.submit(run_squirrelscan, domain, 100)

    discovered, homepage_html, resp_headers, extra_htmls = auto_discover(domain, extra_urls, use_render=args.render)

    # Merge SquirrelScan results
    if squirrel_future:
        try:
            scan_data = squirrel_future.result(timeout=310)
            squirrelscan_to_discovery(scan_data, discovered)
        except Exception as e:
            log('⚠️', f'SquirrelScan: {e}', C.YELLOW)
        squirrel_executor.shutdown(wait=False)
    elif not SQUIRREL_BIN:
        log('💡', 'SquirrelScan non installato — installa con: curl -fsSL https://squirrelscan.com/install | bash', C.DIM)

    for key, val in discovered.items():
        if key.startswith('_'):
            continue
        log('  📌', f'{key}: {val["note"]}', C.DIM)

    # ── PHASE 1.5: Shared PSI/CrUX Data (Bug 6 — fetch ONCE, share everywhere) ──
    if google_key:
        log('📊', 'Fetching PSI/CrUX dati condivisi...', C.CYAN)
        try:
            psi_url = f'https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={urllib.parse.quote(url, safe="")}&strategy=mobile&category=performance&category=accessibility&category=seo&category=best-practices&key={google_key}'
            _, _, psi_body = fetch_url(psi_url, timeout=60, secure=True)
            psi_data = json.loads(psi_body)
            lr = psi_data.get('lighthouseResult', {})
            cats = lr.get('categories', {})
            audits = lr.get('audits', {})
            shared_metrics = {
                'scores': {k: round((cats.get(k, {}).get('score', 0) or 0) * 100) for k in ['performance', 'accessibility', 'seo', 'best-practices']},
                'metrics': {
                    'lcp': audits.get('largest-contentful-paint', {}).get('displayValue', 'N/A'),
                    'inp': audits.get('interaction-to-next-paint', {}).get('displayValue', 'N/A'),
                    'cls': audits.get('cumulative-layout-shift', {}).get('displayValue', 'N/A'),
                    'fcp': audits.get('first-contentful-paint', {}).get('displayValue', 'N/A'),
                    'tbt': audits.get('total-blocking-time', {}).get('displayValue', 'N/A'),
                    'ttfb': audits.get('server-response-time', {}).get('displayValue', 'N/A'),
                },
                'opportunities': [
                    {'title': v.get('title'), 'savings': v.get('displayValue'), 'score': v.get('score')}
                    for k, v in audits.items()
                    if v.get('score') is not None and v.get('score', 1) < 1 and v.get('details', {}).get('type') == 'opportunity'
                ][:10]
            }
            discovered['_shared_psi'] = {
                'value': True,
                'note': f'PSI scores: perf={shared_metrics["scores"].get("performance", "N/A")}, seo={shared_metrics["scores"].get("seo", "N/A")}',
                'data': shared_metrics,
            }
            log('✅', f'PSI dati condivisi: performance={shared_metrics["scores"].get("performance", "N/A")}/100', C.GREEN)
        except Exception as e:
            log('⚠️', f'PSI fetch condiviso fallito: {e}', C.YELLOW)

    # ── PHASE 2: AI Analysis ──
    header('FASE 2 — Analisi AI (Claude)')
    analysis_types = ['performance', 'cwv', 'seo', 'seo_deep', 'accessibility', 'security', 'robots', 'sitemap', 'datalayer', 'cro', 'advertising']
    ai_results = {}

    log('🚀', f'Avvio {len(analysis_types)} analisi in parallelo...', C.CYAN)
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(run_analysis, atype, url, api_key, google_key, homepage_html, extra_htmls, discovered): atype
            for atype in analysis_types
        }
        done_count = 0
        for future in as_completed(futures):
            atype = futures[future]
            done_count += 1
            try:
                result_type, result_text = future.result()
                ai_results[result_type] = result_text
                if result_text.startswith('ERRORE:'):
                    log('❌', f'[{done_count}/{len(analysis_types)}] {result_type}: {result_text}', C.RED)
                else:
                    log('✅', f'[{done_count}/{len(analysis_types)}] {result_type} completato ({len(result_text)} chars)', C.GREEN)
            except Exception as e:
                ai_results[atype] = f'ERRORE: {e}'
                log('❌', f'[{done_count}/{len(analysis_types)}] {atype}: {e}', C.RED)

    elapsed = time.time() - start_time
    log('⏱️', f'Analisi completata in {elapsed:.1f}s', C.CYAN)

    # ── PHASE 2.5: Self-Validation ──
    header('FASE 2.5 — Validazione Output')
    validation_issues = []

    # 1. Verify site content was actually fetched
    if not homepage_html:
        validation_issues.append('CRITICO: HTML homepage non fetchato')
    else:
        log('✅', f'HTML homepage fetchato ({len(homepage_html)} chars)', C.GREEN)

    # 2. Extract what the site actually sells from visible text
    if homepage_html:
        body_m = re.search(r'<body[^>]*>([\s\S]*?)</body>', homepage_html, re.I)
        if body_m:
            visible = re.sub(r'<script[\s\S]*?</script>', '', body_m.group(1))
            visible = re.sub(r'<style[\s\S]*?</style>', '', visible)
            visible = re.sub(r'<[^>]+>', ' ', visible)
            visible = re.sub(r'\s+', ' ', visible).strip()[:3000].lower()
            log('🔍', f'Testo visibile estratto per validazione ({len(visible)} chars)', C.DIM)

    # 3. Check for 429 errors and retry failed analyses
    failed_types = [t for t, r in ai_results.items() if r.startswith('ERRORE:')]
    if failed_types:
        log('🔄', f'Retry analisi fallite: {", ".join(failed_types)}', C.YELLOW)
        for ft in failed_types:
            time.sleep(3)  # Wait before retry
            try:
                result_type, result_text = run_analysis(ft, url, api_key, google_key, homepage_html, extra_htmls)
                ai_results[result_type] = result_text
                if result_text.startswith('ERRORE:'):
                    log('❌', f'Retry {ft} fallito: {result_text}', C.RED)
                else:
                    log('✅', f'Retry {ft} completato ({len(result_text)} chars)', C.GREEN)
            except Exception as e:
                log('❌', f'Retry {ft}: {e}', C.RED)

    # 4. Verify robots.txt was fetched for SEO analysis (after retry)
    robots_text = ai_results.get('robots', '')
    if robots_text.startswith('ERRORE:'):
        validation_issues.append('WARN: analisi robots.txt fallita')
    else:
        log('✅', 'robots.txt analizzato correttamente', C.GREEN)

    sitemap_text = ai_results.get('sitemap', '')
    if sitemap_text.startswith('ERRORE:'):
        validation_issues.append('WARN: analisi sitemap fallita')
    else:
        log('✅', 'sitemap analizzata correttamente', C.GREEN)

    # 5. Verify CMS detection consistency
    cms_note = discovered.get('a0_1_1', {}).get('note', '')
    if cms_note:
        log('✅', f'CMS rilevato: {cms_note}', C.GREEN)
    else:
        log('⚠️', 'Nessun CMS rilevato', C.YELLOW)

    # 7. Verify payment detection
    pay_note = discovered.get('a0_1_3', {}).get('note', '')
    if pay_note:
        log('✅', f'Payment gateway: {pay_note}', C.GREEN)
    else:
        log('⚠️', 'Nessun payment gateway rilevato', C.YELLOW)

    # 8. Verify pixel detection
    pixel_note = discovered.get('a2_3_1', {}).get('note', '')
    if pixel_note:
        log('✅', f'Meta Pixel: {pixel_note}', C.GREEN)
    else:
        log('⚠️', 'Meta Pixel non rilevato', C.YELLOW)

    if validation_issues:
        for vi in validation_issues:
            log('⚠️', vi, C.YELLOW)
    else:
        log('✅', 'Tutti i check di validazione passati', C.GREEN)

    # ── PHASE 2.6: Post-Analysis Deduplication ──
    findings_raw = parse_findings(ai_results)
    # Deduplicate findings by normalized title similarity
    seen_titles = {}
    dedup_removed = 0
    findings_deduped = []
    for f in findings_raw:
        # Normalize: lowercase, strip punctuation, collapse whitespace
        norm = re.sub(r'[^\w\s]', '', f['title'].lower())
        norm = re.sub(r'\s+', ' ', norm).strip()
        # Check for exact or very similar titles (first 40 chars)
        key = norm[:40]
        if key in seen_titles:
            dedup_removed += 1
            continue
        seen_titles[key] = True
        findings_deduped.append(f)
    if dedup_removed:
        log('🔄', f'Deduplicazione: {dedup_removed} finding duplicati rimossi ({len(findings_raw)} → {len(findings_deduped)})', C.CYAN)

    # ── PHASE 3: Generate Report ──
    header('FASE 3 — Generazione Report HTML')

    findings = findings_deduped
    log('📊', f'{len(findings)} findings strutturati estratti', C.CYAN)

    scores = estimate_scores(findings, ai_results)
    total = sum(scores.values())
    log('📈', f'Score totale: {total}/60', C.CYAN)

    report_html = generate_report_html(domain, client_name, scores, findings, discovered, ai_results, template)

    # Save report
    reports_dir = os.path.join(TOOL_DIR, 'output')
    os.makedirs(reports_dir, exist_ok=True)

    if args.output:
        output_path = args.output
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_domain = re.sub(r'[^a-zA-Z0-9.-]', '_', domain)
        output_path = os.path.join(reports_dir, f'report_{safe_domain}_{timestamp}.html')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report_html)

    log('💾', f'Report salvato: {output_path}', C.GREEN)
    log('📄', f'Dimensione: {len(report_html) // 1024} KB', C.DIM)

    print(f"\n  {C.BOLD}{C.GREEN}{'─'*60}{C.RESET}")
    print(f"  {C.BOLD}{C.GREEN}✅ AUDIT COMPLETATO CON SUCCESSO{C.RESET}")
    print(f"  {C.BOLD}{C.GREEN}{'─'*60}{C.RESET}")
    print(f"\n  {C.DIM}Report: {C.BOLD}{output_path}{C.RESET}")
    print(f"  {C.DIM}Apri nel browser per visualizzare il report McKinsey-style.{C.RESET}\n")


if __name__ == '__main__':
    main()
