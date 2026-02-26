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

# Optional: Playwright for JS rendering
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

PORT = 8080
TOOL_DIR = os.path.dirname(os.path.abspath(__file__))

def load_env():
    """Load .env file from tool directory"""
    env = {}
    env_path = os.path.join(os.path.dirname(TOOL_DIR), 'credentials', '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env[key.strip()] = value.strip()
    return env

ENV = load_env()

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
        elif self.path == '/api/keys':
            self._handle_keys()
        else:
            # Block access to .env file
            if '.env' in self.path:
                self.send_response(403)
                self.end_headers()
                return
            super().do_GET()

    def _handle_keys(self):
        """Serve API keys from .env to the frontend"""
        keys = {
            'claude_key': ENV.get('CLAUDE_API_KEY', ''),
            'google_key': ENV.get('GOOGLE_API_KEY', '')
        }
        self.send_response(200)
        self._cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(keys).encode())

    def _handle_proxy_headers(self):
        url = self.path.split('/proxy-headers?url=', 1)[1]
        url = urllib.parse.unquote(url)
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            })
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                headers_dict = {k: v for k, v in resp.headers.items()}
            self.send_response(200)
            self._cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(headers_dict).encode())
        except Exception as e:
            self.send_response(502)
            self._cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def _handle_proxy(self):
        url = self.path.split('/proxy?url=', 1)[1]
        url = urllib.parse.unquote(url)
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'it-IT,it;q=0.9,en;q=0.8',
            })
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                body = resp.read()
                content_type = resp.headers.get('Content-Type', 'text/html')

            self.send_response(200)
            self._cors_headers()
            self.send_header('Content-Type', content_type)
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_response(502)
            self._cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def _handle_crux(self):
        """Proxy to Chrome UX Report API using GOOGLE_API_KEY from .env"""
        url = self.path.split('/api/crux?url=', 1)[1]
        url = urllib.parse.unquote(url)
        google_key = ENV.get('GOOGLE_API_KEY', '')
        if not google_key:
            self.send_response(503)
            self._cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'GOOGLE_API_KEY not configured'}).encode())
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
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                data = resp.read()
            self.send_response(200)
            self._cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_response(502)
            self._cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def _handle_proxy_render(self):
        """Render URL with Playwright (headless Chromium). Falls back to static proxy."""
        url = self.path.split('/proxy-render?url=', 1)[1]
        url = urllib.parse.unquote(url)

        if not HAS_PLAYWRIGHT:
            # Fallback to static proxy
            self.path = '/proxy?url=' + urllib.parse.quote(url, safe='')
            return self._handle_proxy()

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                page.goto(url, wait_until='domcontentloaded', timeout=30000)
                page.wait_for_timeout(3000)
                html = page.content()
                browser.close()

            body = html.encode('utf-8')
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
        self.send_header('Access-Control-Allow-Origin', '*')
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
    if ENV.get('CLAUDE_API_KEY'):
        print(f"  Claude API Key: ...{ENV['CLAUDE_API_KEY'][-8:]}")
    if ENV.get('GOOGLE_API_KEY'):
        print(f"  Google API Key: ...{ENV['GOOGLE_API_KEY'][-8:]}")
    print()
    server = http.server.HTTPServer(('', PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer fermato.")
