"""Tests for Story 9.1: Opus synthesis — mega-prompt orchestration.

FRs: FR51, FR60.  NFRs: NFR4, NFR7, NFR11, NFR17, NFR21, NFR22.
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

# Setup paths
TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_DIR = os.path.join(TOOL_DIR, 'cli')
sys.path.insert(0, CLI_DIR)

from deep.synthesis import (
    run_synthesis,
    _load_synthesis_config,
    _build_user_message,
    _fallback_result,
    _PRICE_INPUT,
    _PRICE_OUTPUT,
)


# ─── FIXTURES ───────────────────────────────────────────────────────────────

SAMPLE_WIZARD_BLOCK = {
    "business_profile": {
        "business_type": "ecommerce",
        "platforms": ["iubenda", "gtm", "gads", "meta", "gsc"],
        "url": "https://example.com",
    },
    "iubenda_data": {
        "rejection_rate": 42,
        "consent_mode_v2": "basic",
        "triage_score": "C",
        "l0_mismatches": [],
    },
    "gtm_data": {
        "tag_count": 25,
        "trigger_count": 18,
        "gap_analysis": {"missing_critical": ["conversion_linker"]},
    },
    "gads_data": {
        "consent_mode_status": "Needs attention",
        "enhanced_conversions_status": "Excellent",
        "attribution_model": "Data-driven",
        "cross_checks": {},
    },
    "meta_data": {
        "pixel_id": "123456",
        "capi_status": "pixel_capi",
        "emq_score": 6,
        "events": {"Purchase": "ok", "AddToCart": "ok"},
    },
    "gsc_data": {
        "sitemap_status": "ok",
        "pages_indexed": 150,
        "pages_submitted": 200,
    },
}

SAMPLE_TRUST_RESULT = {
    "score": 62,
    "grade": "C",
    "coverage": 1.0,
    "coverage_label": "5/5 platforms",
    "pillars": {},
}

SAMPLE_DISCOVERY = "=== Auto-Discovery ===\nGoogle Tag Manager detected\nMeta Pixel detected"

SAMPLE_L2_RESULTS = {
    "performance": "LCP: 3.2s, needs improvement",
    "seo": "Title tag present, meta description missing",
}

MOCK_API_RESPONSE = json.dumps({
    "content": [{"text": "## 1. EXECUTIVE SUMMARY\nTest synthesis output"}],
    "usage": {"input_tokens": 5000, "output_tokens": 2000},
}).encode('utf-8')


# ─── TEST: MODULE IMPORTABLE ────────────────────────────────────────────────

class TestSynthesisImport(unittest.TestCase):
    """synthesis.py module exists and is importable."""

    def test_module_importable(self):
        import deep.synthesis
        self.assertTrue(hasattr(deep.synthesis, 'run_synthesis'))

    def test_run_synthesis_callable(self):
        self.assertTrue(callable(run_synthesis))


# ─── TEST: CONFIG LOADER (ADR-3) ───────────────────────────────────────────

class TestConfigLoader(unittest.TestCase):
    """synthesis_prompt read from osmani-config.json (ADR-3)."""

    def test_config_has_synthesis_prompt(self):
        """osmani-config.json contains synthesis_prompt key (FR51)."""
        config = _load_synthesis_config()
        self.assertIsInstance(config, dict)
        self.assertIn("model", config)
        self.assertEqual(config["model"], "claude-opus-4-6")

    def test_config_has_system_prompt(self):
        config = _load_synthesis_config()
        self.assertIn("system_prompt", config)
        self.assertIsInstance(config["system_prompt"], str)
        self.assertGreater(len(config["system_prompt"]), 100)

    def test_config_has_user_template(self):
        config = _load_synthesis_config()
        self.assertIn("user_prompt_template", config)
        self.assertIn("{{data}}", config["user_prompt_template"])

    def test_config_temperature_zero(self):
        """Temperature 0 for consistency (FR51)."""
        config = _load_synthesis_config()
        self.assertEqual(config.get("temperature"), 0)

    def test_config_timeout_300s(self):
        """Default timeout 300s (NFR4)."""
        config = _load_synthesis_config()
        self.assertEqual(config.get("timeout_seconds"), 300)

    def test_config_max_retries_2(self):
        """Max 2 retries (NFR4)."""
        config = _load_synthesis_config()
        self.assertEqual(config.get("max_retries"), 2)

    def test_config_max_tokens_16000(self):
        config = _load_synthesis_config()
        self.assertEqual(config.get("max_tokens"), 16000)


# ─── TEST: PROMPT BUILDER (FR51) ───────────────────────────────────────────

class TestPromptBuilder(unittest.TestCase):
    """Mega-prompt populated with all collected data (FR51)."""

    def test_includes_business_profile(self):
        msg = _build_user_message(SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT)
        self.assertIn("BUSINESS PROFILE", msg)
        self.assertIn("ecommerce", msg)

    def test_includes_discovery_block(self):
        msg = _build_user_message(SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT)
        self.assertIn("DISCOVERY BLOCK", msg)
        self.assertIn("Google Tag Manager", msg)

    def test_includes_wizard_data(self):
        msg = _build_user_message(SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT)
        self.assertIn("WIZARD DATA", msg)
        self.assertIn("IUBENDA_DATA", msg)
        self.assertIn("GTM_DATA", msg)
        self.assertIn("GADS_DATA", msg)
        self.assertIn("META_DATA", msg)
        self.assertIn("GSC_DATA", msg)

    def test_includes_trust_score(self):
        msg = _build_user_message(SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT)
        self.assertIn("TRUST SCORE", msg)
        self.assertIn('"score": 62', msg)

    def test_includes_l2_results(self):
        msg = _build_user_message(SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT)
        self.assertIn("L2 AI ANALYSES", msg)
        self.assertIn("PERFORMANCE", msg)
        self.assertIn("LCP: 3.2s", msg)

    def test_empty_wizard_data_skipped(self):
        """Empty wizard data dicts are not included."""
        minimal_block = {"business_profile": {"business_type": "lead_gen"}}
        msg = _build_user_message(minimal_block, "", {}, {})
        self.assertNotIn("IUBENDA_DATA", msg)
        self.assertNotIn("GTM_DATA", msg)

    def test_discovery_string_capped(self):
        """Discovery block capped at 15000 chars to avoid token explosion."""
        long_discovery = "X" * 20000
        msg = _build_user_message({"business_profile": {}}, long_discovery, {}, {})
        # The discovery portion should be capped
        discovery_section = msg.split("=== WIZARD DATA")[0]
        self.assertLessEqual(len(discovery_section), 16000)  # with headers

    def test_l2_per_analysis_capped(self):
        """Each L2 analysis result capped at 5000 chars."""
        big_l2 = {"seo": "Y" * 10000}
        msg = _build_user_message({"business_profile": {}}, "", big_l2, {})
        # Find the SEO section content
        seo_start = msg.find("--- SEO ---")
        self.assertNotEqual(seo_start, -1)
        seo_content = msg[seo_start + 11:]
        self.assertLessEqual(len(seo_content.strip()), 5100)  # with some margin


# ─── TEST: FALLBACK RESULT (NFR17) ─────────────────────────────────────────

class TestFallbackResult(unittest.TestCase):
    """Partial report without narrative synthesis (NFR17)."""

    def test_fallback_structure(self):
        result = _fallback_result("test error")
        self.assertFalse(result["success"])
        self.assertEqual(result["synthesis_text"], "")
        self.assertEqual(result["error"], "test error")
        self.assertEqual(result["cost_usd"], 0)

    def test_fallback_has_all_keys(self):
        result = _fallback_result("reason")
        expected_keys = {"synthesis_text", "success", "error", "elapsed_seconds",
                         "input_tokens", "output_tokens", "cost_usd", "model"}
        self.assertEqual(set(result.keys()), expected_keys)


# ─── TEST: API KEY FROM ENV (NFR7) ─────────────────────────────────────────

class TestApiKeyFromEnv(unittest.TestCase):
    """API key from ANTHROPIC_API_KEY env var, never hardcoded (NFR7)."""

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False)
    def test_missing_api_key_returns_fallback(self):
        """Missing API key → fallback, no crash."""
        result = run_synthesis(SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT)
        self.assertFalse(result["success"])
        self.assertIn("API key", result["error"])

    @patch.dict(os.environ, {}, clear=True)
    def test_no_env_var_returns_fallback(self):
        """No env var at all → fallback."""
        result = run_synthesis(SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT)
        self.assertFalse(result["success"])


# ─── TEST: RUN SYNTHESIS SUCCESS ────────────────────────────────────────────

class TestRunSynthesisSuccess(unittest.TestCase):
    """Successful synthesis call (FR51, FR60, NFR21, NFR22)."""

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"})
    @patch('deep.synthesis.urllib.request.urlopen')
    def test_successful_synthesis(self, mock_urlopen):
        """Full successful synthesis returns expected structure."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = MOCK_API_RESPONSE
        mock_urlopen.return_value = mock_resp

        result = run_synthesis(SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT)

        self.assertTrue(result["success"])
        self.assertIn("EXECUTIVE SUMMARY", result["synthesis_text"])
        self.assertGreaterEqual(result["elapsed_seconds"], 0)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"})
    @patch('deep.synthesis.urllib.request.urlopen')
    def test_cost_calculated(self, mock_urlopen):
        """API cost logged correctly (FR60, NFR21)."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = MOCK_API_RESPONSE
        mock_urlopen.return_value = mock_resp

        result = run_synthesis(SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT)

        self.assertGreater(result["cost_usd"], 0)
        self.assertEqual(result["input_tokens"], 5000)
        self.assertEqual(result["output_tokens"], 2000)
        # Verify cost calculation: 5000 * $15/M + 2000 * $75/M
        expected = (5000 * _PRICE_INPUT) + (2000 * _PRICE_OUTPUT)
        self.assertAlmostEqual(result["cost_usd"], round(expected, 4), places=4)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"})
    @patch('deep.synthesis.urllib.request.urlopen')
    def test_model_in_result(self, mock_urlopen):
        """Model name included in result."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = MOCK_API_RESPONSE
        mock_urlopen.return_value = mock_resp

        result = run_synthesis(SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT)
        self.assertEqual(result["model"], "claude-opus-4-6")

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"})
    @patch('deep.synthesis.urllib.request.urlopen')
    def test_opus_model_used_in_payload(self, mock_urlopen):
        """Claude Opus 4.6 model used in API payload (FR51)."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = MOCK_API_RESPONSE
        mock_urlopen.return_value = mock_resp

        run_synthesis(SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT)

        # Check the request payload
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        payload = json.loads(req.data.decode('utf-8'))
        self.assertEqual(payload["model"], "claude-opus-4-6")
        self.assertEqual(payload["temperature"], 0)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"})
    @patch('deep.synthesis.urllib.request.urlopen')
    def test_system_prompt_from_config(self, mock_urlopen):
        """System prompt loaded from config (ADR-3)."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = MOCK_API_RESPONSE
        mock_urlopen.return_value = mock_resp

        run_synthesis(SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT)

        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        payload = json.loads(req.data.decode('utf-8'))
        self.assertIn("MarTech consultant", payload["system"])


# ─── TEST: ERROR HANDLING & RETRY (NFR4, NFR17) ────────────────────────────

class TestErrorHandling(unittest.TestCase):
    """Retry logic and graceful fallback (NFR4, NFR17)."""

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"})
    @patch('deep.synthesis.urllib.request.urlopen')
    @patch('deep.synthesis.time.sleep')
    def test_api_error_returns_fallback(self, mock_sleep, mock_urlopen):
        """API errors → fallback result, no crash (NFR17)."""
        import urllib.error
        mock_urlopen.side_effect = RuntimeError("Connection refused")

        result = run_synthesis(SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT)

        self.assertFalse(result["success"])
        self.assertIn("Connection refused", result["error"])

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"})
    @patch('deep.synthesis.urllib.request.urlopen')
    @patch('deep.synthesis.time.sleep')
    def test_retry_on_429(self, mock_sleep, mock_urlopen):
        """429 triggers retry (NFR4)."""
        import urllib.error

        error_resp = MagicMock()
        error_resp.read.return_value = b'rate limited'
        http_error = urllib.error.HTTPError('url', 429, 'Too Many', {}, error_resp)

        success_resp = MagicMock()
        success_resp.read.return_value = MOCK_API_RESPONSE

        mock_urlopen.side_effect = [http_error, success_resp]

        result = run_synthesis(SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT)

        self.assertTrue(result["success"])
        self.assertEqual(mock_urlopen.call_count, 2)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"})
    @patch('deep.synthesis.urllib.request.urlopen')
    @patch('deep.synthesis.time.sleep')
    def test_max_retries_exhausted(self, mock_sleep, mock_urlopen):
        """All retries exhausted → fallback (NFR4, NFR17)."""
        import urllib.error

        error_resp = MagicMock()
        error_resp.read.return_value = b'overloaded'
        http_error = urllib.error.HTTPError('url', 529, 'Overloaded', {}, error_resp)

        mock_urlopen.side_effect = http_error

        result = run_synthesis(SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT)

        self.assertFalse(result["success"])
        # 1 initial + 2 retries = 3 calls
        self.assertEqual(mock_urlopen.call_count, 3)


# ─── TEST: PRICING CONSTANTS ───────────────────────────────────────────────

class TestPricing(unittest.TestCase):
    """Opus pricing constants are correct."""

    def test_input_price(self):
        self.assertAlmostEqual(_PRICE_INPUT, 15.0 / 1_000_000)

    def test_output_price(self):
        self.assertAlmostEqual(_PRICE_OUTPUT, 75.0 / 1_000_000)


if __name__ == '__main__':
    unittest.main()
