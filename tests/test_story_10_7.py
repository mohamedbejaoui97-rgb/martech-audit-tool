"""Tests for Story 10.7: End-to-end sectional synthesis + report generation.

Validates the full pipeline: wizard data → sectional synthesis → report HTML.
Uses chiostrodisaronno.it-style realistic fixtures.

FRs: FR51-FR60.  NFRs: NFR4, NFR7, NFR10, NFR11, NFR17, NFR21, NFR22.
"""

import os
import sys
import json
import unittest
import tempfile
import shutil
from unittest.mock import patch, MagicMock

# Setup paths
TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_DIR = os.path.join(TOOL_DIR, 'cli')
sys.path.insert(0, CLI_DIR)

from deep.synthesis import (
    run_synthesis,
    _load_sections_config,
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
from deep.report_deep import (
    generate_deep_report,
    _build_radar_svg,
    _build_pillar_cards,
    _build_chain_html,
    _build_gap_table,
    _extract_synthesis_sections,
    _find_section,
    _md_to_html,
    _esc,
    TEMPLATE_PATH,
)


# ─── REALISTIC FIXTURES (chiostrodisaronno.it style) ──────────────────────

REALISTIC_BUSINESS_PROFILE = {
    "business_type": "ecommerce",
    "platforms": ["iubenda", "gtm", "gads", "meta", "gsc"],
    "url": "https://chiostrodisaronno.it",
    "client_name": "Chiostro di Saronno",
}

REALISTIC_IUBENDA = {
    "rejection_rate": 38,
    "consent_mode_v2": "basic",
    "triage_score": "C",
    "banner_type": "iubenda",
    "banner_services": 12,
    "l0_mismatches": ["Google Analytics presente in L0 ma non dichiarato nel banner"],
    "anomalies_detected": "Rejection rate 38% superiore alla media di settore (25%)",
    "operator_notes": "Banner carica lentamente, potrebbe influire su UX",
    "evidence_screenshots": [],
}

REALISTIC_GTM = {
    "tag_count": 18,
    "trigger_count": 12,
    "variable_count": 8,
    "uses_gtm": "Sì",
    "gap_analysis": {
        "missing_critical": ["conversion_linker"],
        "missing_recommended": ["google_ads_remarketing"],
        "duplicates": [],
    },
    "critical_checks": {
        "consent_mode_tags": 2,
        "all_pages_trigger": True,
    },
    "anomalies_detected": "Conversion Linker mancante — impatta tutte le conversioni Google Ads",
    "operator_notes": "Container non pubblicato da 45 giorni",
}

REALISTIC_GADS = {
    "conversions_total": 8,
    "conversions_primary": 3,
    "conversions_secondary": 5,
    "conversions_active": "Alcune",
    "inactive_days": 68,
    "consent_mode_status": "Needs attention",
    "enhanced_conversions_status": "Not set up",
    "attribution_model": "Data-driven",
    "cross_checks": {
        "gtm_conversion_linker": False,
        "ga4_gap": True,
    },
    "ga4_gap_critical": True,
    "funnel_events": {
        "missing": ["begin_checkout", "add_shipping_info"],
        "present": ["purchase", "add_to_cart", "view_item"],
    },
    "anomalies_detected": "3 conversioni primary inattive da 68 giorni, GA4 gap critico",
    "operator_notes": "Il cliente ha cambiato agenzia 3 mesi fa, possibile discontinuità tracking",
}

REALISTIC_META = {
    "pixel_id": "987654321",
    "pixel_found_l0": True,
    "capi_status": "pixel_only",
    "emq_score": 4,
    "events_by_type": {
        "Purchase": "pixel_only",
        "AddToCart": "pixel_only",
        "ViewContent": "pixel_only",
        "InitiateCheckout": "missing",
    },
    "gtm_cross_check": {
        "meta_tag_in_gtm": True,
        "consent_aware": False,
    },
    "anomalies_detected": "EMQ 4/10 — nessun CAPI, InitiateCheckout mancante",
    "operator_notes": "Pixel installato direttamente nel tema, non via GTM",
}

REALISTIC_GSC = {
    "sitemap_status": "submitted",
    "pages_indexed": 120,
    "pages_submitted": 185,
    "index_coverage_pct": 64.9,
    "sitemap_cross_check": {
        "robots_sitemap_url": "https://chiostrodisaronno.it/sitemap.xml",
        "gsc_sitemap_url": "https://chiostrodisaronno.it/sitemap_index.xml",
        "url_mismatch": True,
        "is_critical": True,
    },
    "robots_txt": {
        "raw_content": "User-agent: *\nDisallow: /wp-admin/\nSitemap: https://chiostrodisaronno.it/sitemap.xml",
        "sitemap_urls": ["https://chiostrodisaronno.it/sitemap.xml"],
        "disallow_rules": ["/wp-admin/"],
    },
    "trend_analysis": {
        "clicks_trend": "declining",
        "impressions_trend": "stable",
    },
    "anomalies_detected": "Sitemap mismatch tra robots.txt e GSC, 35% pagine non indicizzate",
    "operator_notes": "Migrazione dominio 6 mesi fa, redirect chain possibile",
}

REALISTIC_WIZARD_BLOCK = {
    "business_profile": REALISTIC_BUSINESS_PROFILE,
    "iubenda_data": REALISTIC_IUBENDA,
    "gtm_data": REALISTIC_GTM,
    "gads_data": REALISTIC_GADS,
    "meta_data": REALISTIC_META,
    "gsc_data": REALISTIC_GSC,
    "trust_score": {"score": 42, "grade": "D"},
    "gap_to_revenue": {
        "issues": [
            {"platform": "GTM", "issue": "Conversion Linker mancante", "severity": "critical",
             "impact_min": 3000, "impact_max": 7000, "is_leverage_node": True,
             "affects": ["Google Ads", "Meta"]},
            {"platform": "Google Ads", "issue": "Enhanced Conversions non configurate", "severity": "high",
             "impact_min": 1500, "impact_max": 3500, "is_leverage_node": False, "affects": []},
            {"platform": "Meta", "issue": "CAPI mancante, EMQ 4/10", "severity": "high",
             "impact_min": 1200, "impact_max": 2800, "is_leverage_node": False, "affects": []},
            {"platform": "Iubenda", "issue": "CM v2 Basic con 38% rejection", "severity": "high",
             "impact_min": 2000, "impact_max": 5000, "is_leverage_node": True,
             "affects": ["Google Ads", "Meta", "GA4"]},
            {"platform": "GSC", "issue": "35% pagine non indicizzate", "severity": "medium",
             "impact_min": 500, "impact_max": 1500, "is_leverage_node": False, "affects": []},
        ],
        "total_impact_min": 8200,
        "total_impact_max": 19800,
        "total_impact_label": "€8,200–€19,800/mese",
        "leverage_nodes": [
            {"issue": "Conversion Linker mancante", "affects": ["Google Ads", "Meta"]},
            {"issue": "CM v2 Basic con 38% rejection", "affects": ["Google Ads", "Meta", "GA4"]},
        ],
    },
    "consent_impact_chain": {
        "chain": [
            {"step": 1, "title": "Banner Iubenda", "detail": "38% rifiuto cookie"},
            {"step": 2, "title": "CM v2 Basic", "detail": "Nessuna modellazione avanzata"},
            {"step": 3, "title": "Conversion Linker Assente", "detail": "Cross-domain tracking rotto"},
            {"step": 4, "title": "Conversioni Perse", "detail": "~50% dati persi per Smart Bidding"},
        ],
        "triage_grade": "C",
    },
    "leverage_nodes": [
        {"issue": "Conversion Linker mancante", "affects": ["Google Ads", "Meta"]},
        {"issue": "CM v2 Basic", "affects": ["Google Ads", "Meta", "GA4"]},
    ],
    "attribution_comparison": {
        "gads_model": "Data-driven",
        "meta_window": "7d click, 1d view",
        "discrepancy_risk": "high",
    },
}

# Synthesis expects pillars as list (for iteration with .get('name'))
# Report expects pillars as dict (keyed by pillar_id)
REALISTIC_TRUST_PILLARS_LIST = [
    {"name": "Consent Health", "score": 35, "weight": 25},
    {"name": "Implementation Quality", "score": 40, "weight": 20},
    {"name": "Conversion Reliability", "score": 30, "weight": 25},
    {"name": "Event Match Quality", "score": 45, "weight": 15},
    {"name": "Data Foundation", "score": 60, "weight": 15},
]

REALISTIC_TRUST_PILLARS_DICT = {
    "consent_health": {"score": 35, "label": "Consent Health (Iubenda)", "weight_normalized": 0.25},
    "implementation_quality": {"score": 40, "label": "Implementation Quality (GTM)", "weight_normalized": 0.20},
    "conversion_reliability": {"score": 30, "label": "Conversion Reliability (Google Ads)", "weight_normalized": 0.25},
    "event_match_quality": {"score": 45, "label": "Event Match Quality (Meta)", "weight_normalized": 0.15},
    "data_foundation": {"score": 60, "label": "Data Foundation (GSC)", "weight_normalized": 0.15},
}

# For synthesis (list pillars)
REALISTIC_TRUST_FOR_SYNTHESIS = {
    "score": 42,
    "grade": "D",
    "coverage": 1.0,
    "coverage_label": "5/5 platforms",
    "pillars": REALISTIC_TRUST_PILLARS_LIST,
}

# For report (dict pillars)
REALISTIC_TRUST = {
    "score": 42,
    "grade": "D",
    "coverage": 1.0,
    "coverage_label": "5/5 platforms",
    "pillars": REALISTIC_TRUST_PILLARS_DICT,
}

REALISTIC_DISCOVERY = (
    "=== Auto-Discovery ===\n"
    "Google Tag Manager detected: GTM-XXXXXXX\n"
    "Meta Pixel detected: 987654321\n"
    "Google Ads tag detected\n"
    "Iubenda cookie banner detected\n"
    "Google Analytics GA4 detected\n"
    "Sitemap found: /sitemap.xml\n"
    "WordPress CMS detected\n"
)

REALISTIC_L2_RESULTS = {
    "performance": "LCP: 4.1s (Poor). FCP: 2.3s. TBT: 450ms. CLS: 0.12. Third-party scripts block main thread.",
    "cwv": "Core Web Vitals: LCP Poor, FID Good, CLS Needs Improvement. Mobile score 45/100.",
    "seo": "Title tag: OK. Meta description: presente ma troppo lunga (180 chars). H1 duplicato.",
    "seo_deep": "Schema.org: Product markup presente ma incompleto (manca offers.price). Hreflang mancante.",
    "robots": "Robots.txt standard. Sitemap dichiarato. Nessun blocco critico.",
    "sitemap": "Sitemap XML valido, 185 URL. 12 URL ritornano 404. Nessun lastmod.",
    "datalayer": "dataLayer presente. Evento purchase rilevato. Mancano begin_checkout e add_shipping_info.",
    "cro": "Form checkout con 6 step (media settore: 3-4). Nessun trust badge visibile. CTA poco visibili.",
    "advertising": "Google Ads conversion tag presente. Meta Pixel attivo. Nessun LinkedIn Insight Tag.",
}

# Mock API response for sectional synthesis
def _make_mock_response(section_text):
    return json.dumps({
        "content": [{"text": section_text}],
        "usage": {"input_tokens": 3000, "output_tokens": 1500},
    }).encode('utf-8')


MOCK_SECTION_RESPONSES = {
    "exec_summary": _make_mock_response(
        "## EXECUTIVE SUMMARY\nL'audit di chiostrodisaronno.it rivela un Trust Score di 42/100 (D). "
        "La catena consent → tracking → bidding è gravemente compromessa."
    ),
    "trust_analysis": _make_mock_response(
        "## TRUST ANALYSIS\nIl pilastro più debole è Conversion Reliability (30/100). "
        "Consent Health a 35/100 causa effetto cascata su tutte le piattaforme."
    ),
    "gap_roadmap": _make_mock_response(
        "## GAP-TO-REVENUE E ROADMAP\nImpatto stimato: €8,200-€19,800/mese.\n"
        "- Settimana 1-2: Aggiungere Conversion Linker\n"
        "- Settimana 2-3: Upgrade CM v2 ad Advanced\n"
        "- Mese 2: Implementare Meta CAPI\n"
        "- Mese 2: Configurare Enhanced Conversions"
    ),
    "platform_consent": _make_mock_response(
        "## CONSENT ANALYSIS\nIubenda con rejection rate 38%. CM v2 Basic non sufficiente. "
        "Upgrade ad Advanced necessario per modellazione."
    ),
    "platform_gtm": _make_mock_response(
        "## GTM ANALYSIS\n18 tag, 12 trigger, 8 variabili. "
        "Conversion Linker MANCANTE — problema critico. Container non pubblicato da 45 giorni."
    ),
    "platform_gads": _make_mock_response(
        "## GOOGLE ADS ANALYSIS\n8 conversioni (3 primary, 5 secondary). "
        "3 conversioni primary inattive da 68 giorni. Enhanced Conversions non configurate. "
        "GA4 gap critico rilevato."
    ),
    "platform_meta": _make_mock_response(
        "## META ANALYSIS\nPixel 987654321 attivo ma senza CAPI. EMQ 4/10 insufficiente. "
        "InitiateCheckout mancante nel funnel."
    ),
    "platform_seo": _make_mock_response(
        "## SEO ANALYSIS\n120/185 pagine indicizzate (64.9%). "
        "Sitemap mismatch tra robots.txt e GSC. 12 URL in sitemap ritornano 404."
    ),
    "technical_appendix": _make_mock_response(
        "## APPENDICE TECNICA\n### Conversion Linker\n1. Aprire GTM\n2. Nuovo Tag → Conversion Linker\n"
        "3. Trigger: All Pages\n4. Pubblicare\n\n### Enhanced Conversions\n1. Google Ads → Impostazioni\n"
        "2. Attivare Enhanced Conversions\n3. Configurare hash email"
    ),
}


# ─── TEST: E2E SYNTHESIS PIPELINE ─────────────────────────────────────────

class TestE2ESynthesisPipeline(unittest.TestCase):
    """End-to-end: wizard data → sectional synthesis → assembled result."""

    def _mock_urlopen(self, request, **kwargs):
        """Route mock API calls to section-specific responses."""
        body = json.loads(request.data.decode('utf-8'))
        user_msg = body.get("messages", [{}])[0].get("content", "")

        # Determine which section based on user message content
        for section_id, response in MOCK_SECTION_RESPONSES.items():
            # Phase 2 sections reference phase1 findings
            if section_id == "technical_appendix" and "FINDINGS" in user_msg:
                mock = MagicMock()
                mock.read.return_value = response
                return mock

        # Default response for any section
        mock = MagicMock()
        mock.read.return_value = _make_mock_response("## Section Output\nTest content for analysis.")
        return mock

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-e2e"})
    @patch('deep.synthesis.urllib.request.urlopen')
    def test_e2e_synthesis_with_all_platforms(self, mock_urlopen):
        """Full pipeline with 5 platforms → 9 sections synthesized."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = _make_mock_response("## Section\nAnalysis output")
        mock_urlopen.return_value = mock_resp

        result = run_synthesis(
            REALISTIC_WIZARD_BLOCK, REALISTIC_DISCOVERY,
            REALISTIC_L2_RESULTS, REALISTIC_TRUST_FOR_SYNTHESIS,
        )

        self.assertTrue(result["success"])
        self.assertIn("section_results", result)
        self.assertGreater(result["sections_ok"], 0)
        self.assertGreater(result["cost_usd"], 0)
        self.assertGreater(result["input_tokens"], 0)
        self.assertGreater(result["output_tokens"], 0)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-e2e"})
    @patch('deep.synthesis.urllib.request.urlopen')
    def test_e2e_all_9_sections_called(self, mock_urlopen):
        """With 5 platforms, all 9 sections should be synthesized."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = _make_mock_response("## Output\nContent")
        mock_urlopen.return_value = mock_resp

        result = run_synthesis(
            REALISTIC_WIZARD_BLOCK, REALISTIC_DISCOVERY,
            REALISTIC_L2_RESULTS, REALISTIC_TRUST_FOR_SYNTHESIS,
        )

        sr = result.get("section_results", {})
        expected = {"exec_summary", "trust_analysis", "gap_roadmap",
                    "platform_consent", "platform_gtm", "platform_gads",
                    "platform_meta", "platform_seo", "technical_appendix"}
        self.assertEqual(set(sr.keys()), expected)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-e2e"})
    @patch('deep.synthesis.urllib.request.urlopen')
    def test_e2e_phase2_runs_after_phase1(self, mock_urlopen):
        """technical_appendix (Phase 2) receives phase1 findings."""
        calls = []

        def track_calls(request, **kwargs):
            body = json.loads(request.data.decode('utf-8'))
            user_msg = body["messages"][0]["content"]
            calls.append(user_msg)
            mock = MagicMock()
            mock.read.return_value = _make_mock_response("## Output\nContent")
            return mock

        mock_urlopen.side_effect = track_calls

        result = run_synthesis(
            REALISTIC_WIZARD_BLOCK, REALISTIC_DISCOVERY,
            REALISTIC_L2_RESULTS, REALISTIC_TRUST_FOR_SYNTHESIS,
        )

        self.assertTrue(result["success"])
        # technical_appendix call should reference phase1 findings
        appendix_calls = [c for c in calls if "FINDINGS" in c]
        self.assertGreater(len(appendix_calls), 0,
                           "Phase 2 (technical_appendix) should receive phase1 findings")

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-e2e"})
    @patch('deep.synthesis.urllib.request.urlopen')
    def test_e2e_partial_api_failure(self, mock_urlopen):
        """Some sections fail → report still generated with partial data."""
        call_count = [0]

        def sometimes_fail(request, **kwargs):
            call_count[0] += 1
            if call_count[0] % 3 == 0:
                raise Exception("Simulated API failure")
            mock = MagicMock()
            mock.read.return_value = _make_mock_response("## Section\nOK content")
            return mock

        mock_urlopen.side_effect = sometimes_fail

        result = run_synthesis(
            REALISTIC_WIZARD_BLOCK, REALISTIC_DISCOVERY,
            REALISTIC_L2_RESULTS, REALISTIC_TRUST_FOR_SYNTHESIS,
        )

        # Should still succeed if at least one section is OK
        self.assertTrue(result["success"])
        self.assertGreater(result["sections_ok"], 0)
        self.assertLess(result["sections_ok"], result["sections_total"])

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-e2e"})
    @patch('deep.synthesis.urllib.request.urlopen')
    def test_e2e_total_api_failure(self, mock_urlopen):
        """All sections fail → graceful degradation (NFR17)."""
        mock_urlopen.side_effect = Exception("Total API failure")

        result = run_synthesis(
            REALISTIC_WIZARD_BLOCK, REALISTIC_DISCOVERY,
            REALISTIC_L2_RESULTS, REALISTIC_TRUST_FOR_SYNTHESIS,
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["sections_ok"], 0)


# ─── TEST: E2E DATA FLOW ─────────────────────────────────────────────────

class TestE2EDataFlow(unittest.TestCase):
    """Verify realistic data flows correctly through data slicer."""

    def test_anomalies_aggregated_from_all_wizards(self):
        """All wizard anomalies collected in exec_summary data."""
        payload = _build_section_data(
            "exec_summary", ["all_anomalies"],
            REALISTIC_WIZARD_BLOCK, REALISTIC_DISCOVERY,
            REALISTIC_L2_RESULTS, REALISTIC_TRUST_FOR_SYNTHESIS,
        )
        self.assertIn("Rejection rate 38%", payload)
        self.assertIn("Conversion Linker mancante", payload)
        self.assertIn("3 conversioni primary inattive", payload)
        self.assertIn("EMQ 4/10", payload)
        self.assertIn("Sitemap mismatch", payload)

    def test_operator_notes_aggregated(self):
        """All operator notes collected."""
        payload = _build_section_data(
            "exec_summary", ["all_operator_notes"],
            REALISTIC_WIZARD_BLOCK, REALISTIC_DISCOVERY,
            REALISTIC_L2_RESULTS, REALISTIC_TRUST_FOR_SYNTHESIS,
        )
        self.assertIn("Banner carica lentamente", payload)
        self.assertIn("Container non pubblicato da 45 giorni", payload)
        self.assertIn("cambiato agenzia", payload)
        self.assertIn("Pixel installato direttamente", payload)
        self.assertIn("Migrazione dominio", payload)

    def test_gads_section_has_full_conversion_data(self):
        """Google Ads section receives complete conversion details."""
        payload = _build_section_data(
            "platform_gads", ["gads_data", "l2_advertising", "l2_cro"],
            REALISTIC_WIZARD_BLOCK, REALISTIC_DISCOVERY,
            REALISTIC_L2_RESULTS, REALISTIC_TRUST_FOR_SYNTHESIS,
        )
        self.assertIn("GOOGLE ADS DATA", payload)
        self.assertIn("conversions_total: 8", payload)
        self.assertIn("inactive_days: 68", payload)
        self.assertIn("ga4_gap_critical: True", payload)
        self.assertIn("ADVERTISING", payload)

    def test_meta_section_has_emq_and_capi(self):
        """Meta section receives pixel/CAPI/EMQ data."""
        payload = _build_section_data(
            "platform_meta", ["meta_data", "l2_advertising"],
            REALISTIC_WIZARD_BLOCK, REALISTIC_DISCOVERY,
            REALISTIC_L2_RESULTS, REALISTIC_TRUST_FOR_SYNTHESIS,
        )
        self.assertIn("META DATA", payload)
        self.assertIn("emq_score: 4", payload)
        self.assertIn("capi_status: pixel_only", payload)
        self.assertIn("pixel_id: 987654321", payload)

    def test_consent_section_has_chain_data(self):
        """Consent section receives iubenda data + chain."""
        payload = _build_section_data(
            "platform_consent", ["iubenda_data", "consent_impact_chain"],
            REALISTIC_WIZARD_BLOCK, REALISTIC_DISCOVERY,
            REALISTIC_L2_RESULTS, REALISTIC_TRUST_FOR_SYNTHESIS,
        )
        self.assertIn("IUBENDA DATA", payload)
        self.assertIn("rejection_rate: 38", payload)
        self.assertIn("triage_score: C", payload)
        self.assertIn("CONSENT IMPACT CHAIN", payload)

    def test_seo_section_has_sitemap_crosscheck(self):
        """SEO section receives GSC + sitemap cross-check + robots."""
        payload = _build_section_data(
            "platform_seo", ["gsc_data", "sitemap_cross_check", "robots_txt", "l2_seo", "l2_sitemap"],
            REALISTIC_WIZARD_BLOCK, REALISTIC_DISCOVERY,
            REALISTIC_L2_RESULTS, REALISTIC_TRUST_FOR_SYNTHESIS,
        )
        self.assertIn("GSC DATA", payload)
        self.assertIn("pages_indexed: 120", payload)
        self.assertIn("SITEMAP CROSS-CHECK", payload)
        self.assertIn("url_mismatch", payload)
        self.assertIn("ROBOTS.TXT", payload)
        self.assertIn("Disallow: /wp-admin/", payload)

    def test_trust_score_summary_in_exec(self):
        """Executive summary receives trust score summary."""
        payload = _build_section_data(
            "exec_summary", ["trust_score_summary"],
            REALISTIC_WIZARD_BLOCK, REALISTIC_DISCOVERY,
            REALISTIC_L2_RESULTS, REALISTIC_TRUST_FOR_SYNTHESIS,
        )
        self.assertIn("42/100", payload)
        self.assertIn("5/5 platforms", payload)
        self.assertIn("Consent Health", payload)

    def test_wizard_summaries_overview(self):
        """Wizard summaries provide compact overview for exec section."""
        payload = _build_section_data(
            "exec_summary", ["wizard_summaries"],
            REALISTIC_WIZARD_BLOCK, REALISTIC_DISCOVERY,
            REALISTIC_L2_RESULTS, REALISTIC_TRUST_FOR_SYNTHESIS,
        )
        self.assertIn("[IUBENDA]", payload)
        self.assertIn("[GTM]", payload)
        self.assertIn("[GADS]", payload)
        self.assertIn("[META]", payload)
        self.assertIn("[GSC]", payload)
        self.assertIn("ANOMALIA", payload)


# ─── TEST: E2E REPORT GENERATION ──────────────────────────────────────────

class TestE2EReportGeneration(unittest.TestCase):
    """End-to-end: synthesis result → HTML report with realistic data."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _build_sectional_synthesis(self):
        """Build a realistic sectional synthesis result."""
        section_results = {}
        for sid, response_bytes in MOCK_SECTION_RESPONSES.items():
            data = json.loads(response_bytes.decode('utf-8'))
            section_results[sid] = {
                "success": True,
                "text": data["content"][0]["text"],
                "section_id": sid,
                "input_tokens": 3000,
                "output_tokens": 1500,
                "cost_usd": 0.06,
                "model": "claude-opus-4-6",
                "elapsed": 12.5,
            }

        order = ["exec_summary", "trust_analysis", "gap_roadmap",
                 "platform_consent", "platform_gtm", "platform_gads",
                 "platform_meta", "platform_seo", "technical_appendix"]

        return _assemble_synthesis(section_results, order)

    def test_e2e_report_success(self):
        """Full pipeline: realistic data → complete HTML report."""
        import deep.report_deep as mod
        orig = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = self.tmp_dir
        try:
            synthesis = self._build_sectional_synthesis()
            path = generate_deep_report(
                synthesis, REALISTIC_WIZARD_BLOCK, REALISTIC_TRUST,
                l2_results=REALISTIC_L2_RESULTS,
            )

            self.assertTrue(os.path.isfile(path))
            with open(path, "r") as f:
                content = f.read()

            # Basic structure
            self.assertIn("<!DOCTYPE html>", content)
            self.assertNotIn("{{", content, "Unresolved placeholders found")

            # Client data
            self.assertIn("chiostrodisaronno.it", content)
            self.assertIn("Chiostro di Saronno", content)
            self.assertIn("ecommerce", content)

            # Trust Score
            self.assertIn("42", content)
            self.assertIn("D", content)

            # Report size sanity check
            self.assertGreater(len(content), 5000, "Report too small")
        finally:
            mod.OUTPUT_DIR = orig

    def test_e2e_report_has_radar_chart(self):
        """Report includes SVG radar with 5 pillars."""
        import deep.report_deep as mod
        orig = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = self.tmp_dir
        try:
            synthesis = self._build_sectional_synthesis()
            path = generate_deep_report(
                synthesis, REALISTIC_WIZARD_BLOCK, REALISTIC_TRUST,
            )
            with open(path, "r") as f:
                content = f.read()

            self.assertIn("<svg", content)
            self.assertIn("polygon", content)
            self.assertIn("Consent Health", content)
            self.assertIn("Data Foundation", content)
        finally:
            mod.OUTPUT_DIR = orig

    def test_e2e_report_has_gap_table(self):
        """Report includes Gap-to-Revenue table with all issues."""
        import deep.report_deep as mod
        orig = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = self.tmp_dir
        try:
            synthesis = self._build_sectional_synthesis()
            path = generate_deep_report(
                synthesis, REALISTIC_WIZARD_BLOCK, REALISTIC_TRUST,
            )
            with open(path, "r") as f:
                content = f.read()

            self.assertIn("gap-table", content)
            self.assertIn("Conversion Linker mancante", content)
            self.assertIn("LEVA", content)
            self.assertIn("sev-critical", content)
            self.assertIn("sev-high", content)
            self.assertIn("TOTALE", content)
            self.assertIn("€8,200", content)
        finally:
            mod.OUTPUT_DIR = orig

    def test_e2e_report_has_consent_chain(self):
        """Report includes consent impact chain visualization."""
        import deep.report_deep as mod
        orig = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = self.tmp_dir
        try:
            synthesis = self._build_sectional_synthesis()
            path = generate_deep_report(
                synthesis, REALISTIC_WIZARD_BLOCK, REALISTIC_TRUST,
            )
            with open(path, "r") as f:
                content = f.read()

            self.assertIn("Banner Iubenda", content)
            self.assertIn("38%", content)
            self.assertIn("chain", content)
        finally:
            mod.OUTPUT_DIR = orig

    def test_e2e_report_has_platform_sections(self):
        """Report includes per-platform analysis from sectional synthesis."""
        import deep.report_deep as mod
        orig = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = self.tmp_dir
        try:
            synthesis = self._build_sectional_synthesis()
            path = generate_deep_report(
                synthesis, REALISTIC_WIZARD_BLOCK, REALISTIC_TRUST,
                l2_results=REALISTIC_L2_RESULTS,
            )
            with open(path, "r") as f:
                content = f.read()

            # Wizard data fallback sections
            self.assertIn("Iubenda", content)
            self.assertIn("GTM", content)
            self.assertIn("Google Ads", content)
            self.assertIn("Meta", content)
            self.assertIn("GSC", content)
        finally:
            mod.OUTPUT_DIR = orig

    def test_e2e_report_has_synthesis_sections(self):
        """Report uses sectional synthesis output (ADR-6)."""
        import deep.report_deep as mod
        orig = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = self.tmp_dir
        try:
            synthesis = self._build_sectional_synthesis()
            path = generate_deep_report(
                synthesis, REALISTIC_WIZARD_BLOCK, REALISTIC_TRUST,
            )
            with open(path, "r") as f:
                content = f.read()

            # Content from synthesis sections
            self.assertIn("Trust Score di 42/100", content)
            self.assertIn("Conversion Linker", content)
        finally:
            mod.OUTPUT_DIR = orig

    def test_e2e_report_filename_format(self):
        """Report filename includes domain and timestamp."""
        import deep.report_deep as mod
        orig = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = self.tmp_dir
        try:
            synthesis = self._build_sectional_synthesis()
            path = generate_deep_report(
                synthesis, REALISTIC_WIZARD_BLOCK, REALISTIC_TRUST,
            )
            filename = os.path.basename(path)
            self.assertTrue(filename.startswith("report_deep_"))
            self.assertIn("chiostrodisaronno", filename)
            self.assertTrue(filename.endswith(".html"))
        finally:
            mod.OUTPUT_DIR = orig

    def test_e2e_report_no_raw_data_leaked(self):
        """Client raw data (container JSON, CSV) not embedded (NFR8/NFR9)."""
        import deep.report_deep as mod
        orig = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = self.tmp_dir
        try:
            wb = json.loads(json.dumps(REALISTIC_WIZARD_BLOCK))
            wb["gtm_data"]["container_raw"] = {"very": "large", "json": "content", "tags": [1, 2, 3]}
            synthesis = self._build_sectional_synthesis()
            path = generate_deep_report(synthesis, wb, REALISTIC_TRUST)
            with open(path, "r") as f:
                content = f.read()
            self.assertNotIn("container_raw", content)
        finally:
            mod.OUTPUT_DIR = orig

    def test_e2e_report_xss_safe(self):
        """XSS payloads in wizard data are escaped."""
        import deep.report_deep as mod
        orig = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = self.tmp_dir
        try:
            wb = json.loads(json.dumps(REALISTIC_WIZARD_BLOCK))
            wb["business_profile"]["client_name"] = '<script>alert("xss")</script>'
            synthesis = self._build_sectional_synthesis()
            path = generate_deep_report(synthesis, wb, REALISTIC_TRUST)
            with open(path, "r") as f:
                content = f.read()
            self.assertNotIn("<script>alert", content)
        finally:
            mod.OUTPUT_DIR = orig

    def test_e2e_report_failed_synthesis_fallback(self):
        """Failed synthesis → report still generated with wizard data (NFR17)."""
        import deep.report_deep as mod
        orig = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = self.tmp_dir
        try:
            failed_synthesis = {
                "success": False,
                "synthesis_text": "",
                "error": "All 9 sections timed out",
                "cost_usd": 0,
                "model": "",
            }
            path = generate_deep_report(
                failed_synthesis, REALISTIC_WIZARD_BLOCK, REALISTIC_TRUST,
                l2_results=REALISTIC_L2_RESULTS,
            )

            self.assertTrue(os.path.isfile(path))
            with open(path, "r") as f:
                content = f.read()

            # Trust Score data present even without synthesis
            self.assertIn("42", content)
            # Error noted
            self.assertIn("timed out", content)
            # Wizard data fallback present
            self.assertIn("Iubenda", content)
            # No unresolved placeholders
            self.assertNotIn("{{", content)
        finally:
            mod.OUTPUT_DIR = orig

    def test_e2e_report_with_l2_results(self):
        """L2 results merged into report (Fix 17, 21)."""
        import deep.report_deep as mod
        orig = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = self.tmp_dir
        try:
            synthesis = self._build_sectional_synthesis()
            path = generate_deep_report(
                synthesis, REALISTIC_WIZARD_BLOCK, REALISTIC_TRUST,
                l2_results=REALISTIC_L2_RESULTS,
            )
            with open(path, "r") as f:
                content = f.read()

            # L2 results should appear in appendix or platform sections
            self.assertIn("LCP", content)
            self.assertIn("Core Web Vitals", content)
        finally:
            mod.OUTPUT_DIR = orig


# ─── TEST: E2E COST TRACKING ──────────────────────────────────────────────

class TestE2ECostTracking(unittest.TestCase):
    """Verify cost tracking across sectional synthesis (NFR21, NFR22)."""

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-cost"})
    @patch('deep.synthesis.urllib.request.urlopen')
    def test_cost_aggregated_across_sections(self, mock_urlopen):
        """Total cost = sum of all section costs."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "content": [{"text": "Output"}],
            "usage": {"input_tokens": 5000, "output_tokens": 2000},
        }).encode('utf-8')
        mock_urlopen.return_value = mock_resp

        result = run_synthesis(
            REALISTIC_WIZARD_BLOCK, REALISTIC_DISCOVERY,
            REALISTIC_L2_RESULTS, REALISTIC_TRUST_FOR_SYNTHESIS,
        )

        self.assertGreater(result["cost_usd"], 0)
        # Cost depends on model mix (Opus vs Sonnet per section config)
        self.assertGreater(result["cost_usd"], 0.5, "Cost too low for 9 sections")
        self.assertLess(result["cost_usd"], 5.0, "Cost too high for 9 sections")

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-cost"})
    @patch('deep.synthesis.urllib.request.urlopen')
    def test_tokens_aggregated(self, mock_urlopen):
        """Total tokens = sum across all sections."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "content": [{"text": "Output"}],
            "usage": {"input_tokens": 3000, "output_tokens": 1000},
        }).encode('utf-8')
        mock_urlopen.return_value = mock_resp

        result = run_synthesis(
            REALISTIC_WIZARD_BLOCK, REALISTIC_DISCOVERY,
            REALISTIC_L2_RESULTS, REALISTIC_TRUST_FOR_SYNTHESIS,
        )

        self.assertEqual(result["input_tokens"], 3000 * result["sections_ok"])
        self.assertEqual(result["output_tokens"], 1000 * result["sections_ok"])


# ─── TEST: E2E PLATFORM FILTERING ─────────────────────────────────────────

class TestE2EPlatformFiltering(unittest.TestCase):
    """Verify platform sections skipped when not in business_profile."""

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-filter"})
    @patch('deep.synthesis.urllib.request.urlopen')
    def test_minimal_platforms(self, mock_urlopen):
        """Only GTM + Google Ads → skip consent, meta, seo sections."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = _make_mock_response("## Output\nContent")
        mock_urlopen.return_value = mock_resp

        minimal_block = json.loads(json.dumps(REALISTIC_WIZARD_BLOCK))
        minimal_block["business_profile"]["platforms"] = ["gtm", "gads"]

        result = run_synthesis(
            minimal_block, REALISTIC_DISCOVERY,
            REALISTIC_L2_RESULTS, REALISTIC_TRUST_FOR_SYNTHESIS,
        )

        sr = result.get("section_results", {})
        self.assertIn("platform_gtm", sr)
        self.assertIn("platform_gads", sr)
        self.assertNotIn("platform_consent", sr)
        self.assertNotIn("platform_meta", sr)
        self.assertNotIn("platform_seo", sr)
        # Core sections always present
        self.assertIn("exec_summary", sr)
        self.assertIn("trust_analysis", sr)
        self.assertIn("gap_roadmap", sr)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-filter"})
    @patch('deep.synthesis.urllib.request.urlopen')
    def test_single_platform(self, mock_urlopen):
        """Only Iubenda → only consent platform section."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = _make_mock_response("## Output\nContent")
        mock_urlopen.return_value = mock_resp

        minimal_block = json.loads(json.dumps(REALISTIC_WIZARD_BLOCK))
        minimal_block["business_profile"]["platforms"] = ["iubenda"]

        result = run_synthesis(
            minimal_block, REALISTIC_DISCOVERY,
            REALISTIC_L2_RESULTS, REALISTIC_TRUST_FOR_SYNTHESIS,
        )

        sr = result.get("section_results", {})
        self.assertIn("platform_consent", sr)
        self.assertNotIn("platform_gtm", sr)
        self.assertNotIn("platform_gads", sr)
        self.assertNotIn("platform_meta", sr)
        self.assertNotIn("platform_seo", sr)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-filter"})
    @patch('deep.synthesis.urllib.request.urlopen')
    def test_fewer_api_calls_with_fewer_platforms(self, mock_urlopen):
        """Fewer platforms → fewer API calls → lower cost."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = _make_mock_response("## Output\nContent")
        mock_urlopen.return_value = mock_resp

        # Full platforms
        result_full = run_synthesis(
            REALISTIC_WIZARD_BLOCK, REALISTIC_DISCOVERY,
            REALISTIC_L2_RESULTS, REALISTIC_TRUST_FOR_SYNTHESIS,
        )
        calls_full = mock_urlopen.call_count

        mock_urlopen.reset_mock()

        # Minimal platforms
        minimal_block = json.loads(json.dumps(REALISTIC_WIZARD_BLOCK))
        minimal_block["business_profile"]["platforms"] = ["gtm"]

        result_minimal = run_synthesis(
            minimal_block, REALISTIC_DISCOVERY,
            REALISTIC_L2_RESULTS, REALISTIC_TRUST_FOR_SYNTHESIS,
        )
        calls_minimal = mock_urlopen.call_count

        self.assertGreater(calls_full, calls_minimal)


# ─── TEST: E2E WIZARD FORMATTERS WITH REALISTIC DATA ──────────────────────

class TestE2EWizardFormatters(unittest.TestCase):
    """Wizard formatters produce useful output with realistic data."""

    def test_gads_summary_captures_key_metrics(self):
        summary = _format_wizard_summary("gads_data", REALISTIC_GADS)
        self.assertIn("[GADS]", summary)
        self.assertIn("CM: Needs attention", summary)
        self.assertIn("Conv: 8", summary)
        self.assertIn("ANOMALIA", summary)
        self.assertIn("Note", summary)

    def test_meta_summary_captures_emq(self):
        summary = _format_wizard_summary("meta_data", REALISTIC_META)
        self.assertIn("[META]", summary)
        self.assertIn("EMQ: 4", summary)

    def test_iubenda_summary_captures_rejection(self):
        summary = _format_wizard_summary("iubenda_data", REALISTIC_IUBENDA)
        self.assertIn("[IUBENDA]", summary)
        self.assertIn("Triage: C", summary)
        self.assertIn("Rejection: 38%", summary)

    def test_full_format_preserves_nested_data(self):
        full = _format_wizard_full(REALISTIC_GTM)
        self.assertIn("tag_count: 18", full)
        self.assertIn("[gap_analysis]", full)
        self.assertIn("conversion_linker", full)

    def test_full_format_excludes_evidence(self):
        full = _format_wizard_full(REALISTIC_IUBENDA)
        self.assertNotIn("evidence_screenshots", full)


# ─── TEST: E2E REPORT COMPONENTS WITH REALISTIC DATA ─────────────────────

class TestE2EReportComponents(unittest.TestCase):
    """Report components render correctly with realistic data."""

    def test_radar_5_pillars(self):
        svg = _build_radar_svg(REALISTIC_TRUST["pillars"])
        self.assertIn("<svg", svg)
        self.assertIn("polygon", svg)
        # All 5 labels present
        self.assertIn("Consent Health", svg)
        self.assertIn("Implementation Quality", svg)
        self.assertIn("Conversion Reliability", svg)
        self.assertIn("Event Match Quality", svg)
        self.assertIn("Data Foundation", svg)
        # Score values
        self.assertIn(">35<", svg)
        self.assertIn(">40<", svg)
        self.assertIn(">30<", svg)

    def test_gap_table_sorted_by_impact(self):
        html = _build_gap_table(REALISTIC_WIZARD_BLOCK["gap_to_revenue"])
        # First row should be highest impact (Conversion Linker: 7000 max)
        linker_pos = html.find("Conversion Linker")
        emq_pos = html.find("EMQ")
        self.assertGreater(emq_pos, linker_pos, "Issues should be sorted by impact_max descending")

    def test_gap_table_leverage_nodes(self):
        html = _build_gap_table(REALISTIC_WIZARD_BLOCK["gap_to_revenue"])
        self.assertEqual(html.count("LEVA"), 2, "Should have 2 leverage badges")
        self.assertIn("Nodi di Leva", html)

    def test_chain_4_steps(self):
        html = _build_chain_html(REALISTIC_WIZARD_BLOCK["consent_impact_chain"])
        self.assertEqual(html.count("chain-step"), 4)
        self.assertEqual(html.count("&rarr;"), 3)  # 3 arrows between 4 steps
        self.assertIn("Banner Iubenda", html)
        self.assertIn("Conversioni Perse", html)

    def test_pillar_cards_all_5(self):
        html = _build_pillar_cards(REALISTIC_TRUST["pillars"])
        self.assertEqual(html.count("pillar-card"), 5)
        self.assertIn("35", html)  # consent score
        self.assertIn("30", html)  # conversion reliability score


if __name__ == '__main__':
    unittest.main()
