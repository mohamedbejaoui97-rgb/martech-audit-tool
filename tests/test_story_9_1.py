"""Tests for Story 9.1 + ADR-6: Sectional synthesis orchestration.

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
    _load_sections_config,
    _load_legacy_config,
    _build_section_data,
    _format_wizard_summary,
    _format_wizard_full,
    _synthesize_section,
    _assemble_synthesis,
    _fallback_result,
    _call_claude,
    _PRICES,
    WIZARD_KEYS,
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
        "operator_notes": "conversioni inattive da 68 giorni",
        "anomalies_detected": "3 conversioni primary inattive",
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
    "trust_score": {"score": 62, "grade": "C"},
    "gap_to_revenue": {"issues": [], "leverage_nodes": []},
    "consent_impact_chain": {"steps": ["consent", "tracking", "bidding"]},
    "leverage_nodes": [],
    "attribution_comparison": {},
}

SAMPLE_TRUST_RESULT = {
    "score": 62,
    "grade": "C",
    "coverage": 1.0,
    "coverage_label": "5/5 platforms",
    "pillars": [
        {"name": "Consent", "score": 45, "weight": 25},
        {"name": "Tracking", "score": 70, "weight": 25},
    ],
}

SAMPLE_DISCOVERY = "=== Auto-Discovery ===\nGoogle Tag Manager detected\nMeta Pixel detected"

SAMPLE_L2_RESULTS = {
    "performance": "LCP: 3.2s, needs improvement",
    "seo": "Title tag present, meta description missing",
    "advertising": "Google Ads tag detected, Meta Pixel detected",
}

MOCK_API_RESPONSE = json.dumps({
    "content": [{"text": "## 1. EXECUTIVE SUMMARY\nTest synthesis output"}],
    "usage": {"input_tokens": 5000, "output_tokens": 2000},
}).encode('utf-8')


# ─── TEST: MODULE IMPORTABLE ────────────────────────────────────────────────

class TestSynthesisImport(unittest.TestCase):
    def test_module_importable(self):
        import deep.synthesis
        self.assertTrue(hasattr(deep.synthesis, 'run_synthesis'))

    def test_run_synthesis_callable(self):
        self.assertTrue(callable(run_synthesis))


# ─── TEST: CONFIG LOADERS (ADR-3, ADR-6) ─────────────────────────────────

class TestConfigLoader(unittest.TestCase):
    def test_sections_config_exists(self):
        """osmani-config.json has synthesis_sections (ADR-6)."""
        config = _load_sections_config()
        self.assertIsNotNone(config)
        self.assertIn("sections", config)
        self.assertIn("section_order", config)

    def test_sections_config_has_all_sections(self):
        config = _load_sections_config()
        expected = {"exec_summary", "trust_analysis", "gap_roadmap",
                    "platform_consent", "platform_gtm", "platform_gads",
                    "platform_meta", "platform_seo", "technical_appendix"}
        self.assertEqual(set(config["sections"].keys()), expected)

    def test_each_section_has_required_fields(self):
        config = _load_sections_config()
        for sid, scfg in config["sections"].items():
            self.assertIn("max_tokens", scfg, f"{sid} missing max_tokens")
            self.assertIn("system_prompt", scfg, f"{sid} missing system_prompt")
            self.assertIn("data_keys", scfg, f"{sid} missing data_keys")
            self.assertGreater(len(scfg["system_prompt"]), 50, f"{sid} system_prompt too short")

    def test_shared_rules_present(self):
        config = _load_sections_config()
        self.assertIn("shared_rules", config)
        self.assertIn("REGOLE CRITICHE", config["shared_rules"])

    def test_legacy_config_still_exists(self):
        """Legacy synthesis_prompt preserved for backward compat."""
        config = _load_legacy_config()
        self.assertIsInstance(config, dict)
        self.assertIn("model", config)

    def test_section_order_matches_sections(self):
        config = _load_sections_config()
        order = config["section_order"]
        sections = config["sections"]
        for sid in order:
            self.assertIn(sid, sections, f"{sid} in order but not in sections")

    def test_platform_sections_have_requires_platform(self):
        config = _load_sections_config()
        for sid in ("platform_consent", "platform_gtm", "platform_gads", "platform_meta", "platform_seo"):
            self.assertIn("requires_platform", config["sections"][sid])

    def test_technical_appendix_is_phase_2(self):
        config = _load_sections_config()
        self.assertEqual(config["sections"]["technical_appendix"].get("phase"), 2)


# ─── TEST: WIZARD FORMATTERS (Story 10.2) ──────────────────────────────────

class TestWizardFormatters(unittest.TestCase):
    def test_summary_includes_key_fields(self):
        summary = _format_wizard_summary("gads_data", SAMPLE_WIZARD_BLOCK["gads_data"])
        self.assertIn("GADS", summary)
        self.assertIn("ANOMALIA", summary)
        self.assertIn("Note", summary)

    def test_summary_empty_data(self):
        self.assertEqual(_format_wizard_summary("gtm_data", {}), "")

    def test_full_format_readable(self):
        full = _format_wizard_full(SAMPLE_WIZARD_BLOCK["iubenda_data"])
        self.assertIn("rejection_rate: 42", full)
        self.assertIn("triage_score: C", full)

    def test_full_format_no_json_dumps_style(self):
        """Full format should NOT look like raw JSON."""
        full = _format_wizard_full(SAMPLE_WIZARD_BLOCK["iubenda_data"])
        self.assertNotIn('"rejection_rate":', full)

    def test_full_format_empty(self):
        self.assertEqual(_format_wizard_full({}), "(nessun dato)")

    def test_full_format_skips_evidence(self):
        data = {"field": "val", "evidence_screenshots": ["/path/img.png"]}
        full = _format_wizard_full(data)
        self.assertNotIn("evidence_screenshots", full)


# ─── TEST: DATA SLICER (Story 10.2) ────────────────────────────────────────

class TestDataSlicer(unittest.TestCase):
    def test_business_profile_key(self):
        payload = _build_section_data(
            "exec_summary", ["business_profile"],
            SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT,
        )
        self.assertIn("BUSINESS PROFILE", payload)
        self.assertIn("ecommerce", payload)

    def test_trust_score_summary_key(self):
        payload = _build_section_data(
            "exec_summary", ["trust_score_summary"],
            SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT,
        )
        self.assertIn("62/100", payload)
        self.assertIn("Consent", payload)

    def test_wizard_full_data_key(self):
        payload = _build_section_data(
            "platform_gads", ["gads_data"],
            SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT,
        )
        self.assertIn("GOOGLE ADS DATA", payload)
        self.assertIn("Data-driven", payload)

    def test_l2_result_key(self):
        payload = _build_section_data(
            "platform_gads", ["l2_advertising"],
            SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT,
        )
        self.assertIn("ADVERTISING", payload)

    def test_all_anomalies_collected(self):
        payload = _build_section_data(
            "exec_summary", ["all_anomalies"],
            SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT,
        )
        self.assertIn("3 conversioni primary inattive", payload)

    def test_all_operator_notes_collected(self):
        payload = _build_section_data(
            "exec_summary", ["all_operator_notes"],
            SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT,
        )
        self.assertIn("conversioni inattive da 68 giorni", payload)

    def test_phase1_findings_key(self):
        phase1 = {"exec_summary": {"success": True, "text": "Trust Score 62/100 indicates..."}}
        payload = _build_section_data(
            "technical_appendix", ["phase1_findings"],
            SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT,
            phase1_results=phase1,
        )
        self.assertIn("Trust Score 62/100", payload)

    def test_unknown_key_ignored(self):
        """Unknown data_keys don't crash."""
        payload = _build_section_data(
            "test", ["nonexistent_key"],
            SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT,
        )
        self.assertIsInstance(payload, str)


# ─── TEST: ASSEMBLER (Story 10.4) ──────────────────────────────────────────

class TestAssembler(unittest.TestCase):
    def test_assembles_successful_sections(self):
        results = {
            "exec_summary": {"success": True, "text": "Summary text", "input_tokens": 1000,
                             "output_tokens": 500, "cost_usd": 0.05, "model": "claude-opus-4-6"},
            "trust_analysis": {"success": True, "text": "Trust text", "input_tokens": 800,
                               "output_tokens": 400, "cost_usd": 0.03, "model": "claude-opus-4-6"},
        }
        assembled = _assemble_synthesis(results, ["exec_summary", "trust_analysis"])
        self.assertTrue(assembled["success"])
        self.assertIn("Summary text", assembled["synthesis_text"])
        self.assertIn("Trust text", assembled["synthesis_text"])
        self.assertEqual(assembled["sections_ok"], 2)
        self.assertEqual(assembled["input_tokens"], 1800)
        self.assertEqual(assembled["output_tokens"], 900)

    def test_partial_failure(self):
        results = {
            "exec_summary": {"success": True, "text": "OK", "input_tokens": 100,
                             "output_tokens": 50, "cost_usd": 0.01, "model": "opus"},
            "trust_analysis": {"success": False, "text": "", "input_tokens": 0,
                               "output_tokens": 0, "cost_usd": 0, "model": "opus"},
        }
        assembled = _assemble_synthesis(results, ["exec_summary", "trust_analysis"])
        self.assertTrue(assembled["success"])  # at least one section OK
        self.assertEqual(assembled["sections_ok"], 1)
        self.assertEqual(assembled["sections_total"], 2)

    def test_total_failure(self):
        results = {
            "exec_summary": {"success": False, "text": "", "input_tokens": 0,
                             "output_tokens": 0, "cost_usd": 0, "model": ""},
        }
        assembled = _assemble_synthesis(results, ["exec_summary"])
        self.assertFalse(assembled["success"])

    def test_cost_aggregation(self):
        results = {
            "a": {"success": True, "text": "A", "input_tokens": 100, "output_tokens": 50,
                   "cost_usd": 0.01, "model": "opus"},
            "b": {"success": True, "text": "B", "input_tokens": 200, "output_tokens": 100,
                   "cost_usd": 0.02, "model": "sonnet"},
        }
        assembled = _assemble_synthesis(results, ["a", "b"])
        self.assertAlmostEqual(assembled["cost_usd"], 0.03)
        self.assertIn("opus", assembled["model"])
        self.assertIn("sonnet", assembled["model"])


# ─── TEST: FALLBACK RESULT (NFR17) ─────────────────────────────────────────

class TestFallbackResult(unittest.TestCase):
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
    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False)
    def test_missing_api_key_returns_fallback(self):
        result = run_synthesis(SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT)
        self.assertFalse(result["success"])
        self.assertIn("API key", result["error"])

    @patch.dict(os.environ, {}, clear=True)
    def test_no_env_var_returns_fallback(self):
        result = run_synthesis(SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT)
        self.assertFalse(result["success"])


# ─── TEST: RUN SYNTHESIS SECTIONAL (ADR-6) ────────────────────────────────

class TestRunSynthesisSectional(unittest.TestCase):
    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"})
    @patch('deep.synthesis.urllib.request.urlopen')
    def test_sectional_returns_section_results(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = MOCK_API_RESPONSE
        mock_urlopen.return_value = mock_resp

        result = run_synthesis(SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT)

        self.assertTrue(result["success"])
        self.assertIn("section_results", result)
        self.assertGreater(result["cost_usd"], 0)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"})
    @patch('deep.synthesis.urllib.request.urlopen')
    def test_multiple_api_calls_made(self, mock_urlopen):
        """Sectional synthesis makes multiple API calls (not 1 monolithic)."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = MOCK_API_RESPONSE
        mock_urlopen.return_value = mock_resp

        run_synthesis(SAMPLE_WIZARD_BLOCK, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT)

        # With 5 platforms + exec + trust + gap + appendix = 9 calls
        self.assertGreater(mock_urlopen.call_count, 1)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"})
    @patch('deep.synthesis.urllib.request.urlopen')
    def test_skips_platform_not_in_profiles(self, mock_urlopen):
        """Platform sections skipped if platform not selected."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = MOCK_API_RESPONSE
        mock_urlopen.return_value = mock_resp

        # Only 2 platforms
        minimal_block = dict(SAMPLE_WIZARD_BLOCK)
        minimal_block["business_profile"] = {
            "business_type": "ecommerce",
            "platforms": ["gtm", "gads"],
            "url": "https://example.com",
        }

        result = run_synthesis(minimal_block, SAMPLE_DISCOVERY, SAMPLE_L2_RESULTS, SAMPLE_TRUST_RESULT)

        self.assertTrue(result["success"])
        sr = result.get("section_results", {})
        # Should NOT have consent, meta, seo sections
        self.assertNotIn("platform_consent", sr)
        self.assertNotIn("platform_meta", sr)
        self.assertNotIn("platform_seo", sr)
        # Should have gtm and gads
        self.assertIn("platform_gtm", sr)
        self.assertIn("platform_gads", sr)


# ─── TEST: PRICING (ADR-6) ───────────────────────────────────────────────

class TestPricing(unittest.TestCase):
    def test_opus_prices(self):
        self.assertAlmostEqual(_PRICES["claude-opus-4-6"]["input"], 15.0 / 1_000_000)
        self.assertAlmostEqual(_PRICES["claude-opus-4-6"]["output"], 75.0 / 1_000_000)

    def test_sonnet_prices(self):
        self.assertAlmostEqual(_PRICES["claude-sonnet-4-6"]["input"], 3.0 / 1_000_000)
        self.assertAlmostEqual(_PRICES["claude-sonnet-4-6"]["output"], 15.0 / 1_000_000)


if __name__ == '__main__':
    unittest.main()
