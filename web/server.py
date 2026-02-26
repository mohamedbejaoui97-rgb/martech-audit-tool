#!/usr/bin/env python3
"""MarTech Audit Tool - Local server with CORS proxy, CrUX API, and Playwright rendering"""
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

# Optional: Playwright for JS rendering
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

PORT = int(os.environ.get('PORT', 8080))
TOOL_DIR = os.path.dirname(os.path.abspath(__file__))

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
        # Resolve hostname to IP and check against blocked ranges
        for info in socket.getaddrinfo(hostname, None):
            addr = ipaddress.ip_address(info[4][0])
            for network in _BLOCKED_NETWORKS:
                if addr in network:
                    return False
        return True
    except (ValueError, socket.gaierror, OSError):
        return False


def load_env():
    """Load .env file from tool directory"""
    env = {}
    env_path = os.path.join(os.path.dirname(TOOL_DIR), 'credentials', '.env')
    if os.path.exists(env_path):
        with open(env_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env[key.strip()] = value.strip()
    return env

ENV = load_env()

# SSL contexts
_CTX_SCAN = ssl.create_default_context()
_CTX_SCAN.check_hostname = False
_CTX_SCAN.verify_mode = ssl.CERT_NONE

_CTX_SECURE = ssl.create_default_context()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=TOOL_DIR, **kwargs)

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path.startswith('/proxy-render?url='):
            self._handle_proxy_render()
        elif self.path.startswith('/proxy?url='):
            self._handle_proxy()
        elif self.path.startswith('/proxy-headers?url='):
            self._handle_proxy_headers()
        elif self.path.startswith('/api/crux?url='):
            self._handle_crux()
        else:
            # Block access to sensitive files (.env, credentials, etc.)
            normalized = urllib.parse.unquote(self.path)
            if '.env' in normalized or 'credentials' in normalized:
                self.send_response(403)
                self.end_headers()
                return
            super().do_GET()

    def _send_error(self, status_code, message):
        """Send a JSON error response with CORS headers."""
        self.send_response(status_code)
        self._cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'error': message}).encode())

    def _extract_url(self, prefix):
        """Extract and validate URL from query string. Returns URL or None (sends error)."""
        url = self.path.split(prefix, 1)[1]
        url = urllib.parse.unquote(url)
        if not _is_safe_url(url):
            self._send_error(403, 'URL blocked: private/internal addresses are not allowed')
            return None
        return url

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
        """Proxy to Chrome UX Report API using GOOGLE_API_KEY from .env"""
        url = self.path.split('/api/crux?url=', 1)[1]
        url = urllib.parse.unquote(url)
        google_key = ENV.get('GOOGLE_API_KEY', '')
        if not google_key:
            self._send_error(503, 'GOOGLE_API_KEY not configured')
            return
        try:
            payload = json.dumps({
                'url': url,
                'formFactor': 'PHONE',
                'metrics': [
                    'largest_contentful_paint',
                    'interaction_to_next_paint',
                    'cumulative_layout_shift',
                    'experimental_time_to_first_byte'
                ]
            }).encode('utf-8')
            crux_url = f'https://chromeuxreport.googleapis.com/v1/records:queryRecord?key={google_key}'
            req = urllib.request.Request(crux_url, data=payload, headers={
                'Content-Type': 'application/json'
            })
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
        """Render URL with Playwright (headless Chromium). Falls back to static proxy."""
        url = self._extract_url('/proxy-render?url=')
        if not url:
            return

        if not HAS_PLAYWRIGHT:
            # Fallback to static proxy
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
            # Fallback to static proxy
            self.path = '/proxy?url=' + urllib.parse.quote(url, safe='')
            self._handle_proxy()

    def _cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', 'http://localhost:' + str(PORT))
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')

    def log_message(self, format, *args):
        msg = format % args
        if '/proxy-render?' in msg:
            sys.stderr.write(f"\033[35m[RENDER]\033[0m {msg}\n")
        elif '/proxy?' in msg:
            sys.stderr.write(f"\033[36m[PROXY]\033[0m {msg}\n")
        elif '/api/crux?' in msg:
            sys.stderr.write(f"\033[33m[CRUX]\033[0m {msg}\n")
        elif '200' in msg or '304' in msg:
            pass  # silence static file logs
        else:
            sys.stderr.write(f"{msg}\n")

if __name__ == '__main__':
    print(f"\n  MarTech Audit Tool")
    print(f"  http://localhost:{PORT}")
    print(f"  Proxy attivo su /proxy?url=...")
    print(f"  CrUX API su /api/crux?url=...")
    print(f"  Playwright rendering: {'✓ attivo' if HAS_PLAYWRIGHT else '✗ non installato (pip install playwright && playwright install chromium)'}")
    print(f"  Claude API Key: {'configured' if ENV.get('CLAUDE_API_KEY') else 'not configured'}")
    print(f"  Google API Key: {'configured' if ENV.get('GOOGLE_API_KEY') else 'not configured'}")
    print()
    server = http.server.HTTPServer(('127.0.0.1', PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer fermato.")
