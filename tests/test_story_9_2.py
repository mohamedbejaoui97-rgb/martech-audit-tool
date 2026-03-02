"""Tests for Story 9.2: McKinsey HTML report generation.

FRs: FR52-FR59.  NFRs: NFR10, NFR17.
"""

import os
import sys
import json
import unittest
import tempfile
import shutil
from unittest.mock import patch

# Setup paths
TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_DIR = os.path.join(TOOL_DIR, 'cli')
sys.path.insert(0, CLI_DIR)

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
    _italian_date,
    TEMPLATE_PATH,
)


# ─── FIXTURES ───────────────────────────────────────────────────────────────

SAMPLE_TRUST = {
    "score": 58,
    "grade": "C",
    "coverage": 0.8,
    "coverage_label": "4/5 platforms",
    "pillars": {
        "consent_health": {"score": 62, "label": "Consent Health (Iubenda)", "weight_normalized": 0.312},
        "implementation_quality": {"score": 45, "label": "Implementation Quality (GTM)", "weight_normalized": 0.25},
        "conversion_reliability": {"score": 70, "label": "Conversion Reliability (Google Ads)", "weight_normalized": 0.25},
        "event_match_quality": {"score": 55, "label": "Event Match Quality (Meta)", "weight_normalized": 0.188},
    },
}

SAMPLE_WIZARD_BLOCK = {
    "business_profile": {
        "business_type": "ecommerce",
        "platforms": ["iubenda", "gtm", "gads", "meta"],
        "url": "https://example.com",
        "client_name": "Test Client",
    },
    "iubenda_data": {"triage_score": "C", "rejection_rate": 42},
    "gtm_data": {"tag_count": 25},
    "gads_data": {"consent_mode_status": "Needs attention"},
    "meta_data": {"emq_score": 6},
    "consent_impact_chain": {
        "chain": [
            {"step": 1, "title": "Banner Cookie", "detail": "42% rifiuto"},
            {"step": 2, "title": "Consent Mode Basic", "detail": "Modellazione parziale"},
            {"step": 3, "title": "Conversioni Perse", "detail": "~42% perse"},
        ],
        "triage_grade": "C",
    },
    "gap_to_revenue": {
        "issues": [
            {"platform": "GTM", "issue": "Conversion Linker mancante", "severity": "critical",
             "impact_label": "Impatto critico su conversioni e revenue", "is_leverage_node": True, "affects": ["Google Ads", "Meta"]},
            {"platform": "Meta", "issue": "EMQ basso", "severity": "high",
             "impact_label": "Impatto alto su tracking e ottimizzazione", "is_leverage_node": False, "affects": []},
        ],
        "leverage_nodes": [
            {"issue": "Conversion Linker mancante", "affects": ["Google Ads", "Meta"]},
        ],
    },
}

SAMPLE_SYNTHESIS_SUCCESS = {
    "success": True,
    "synthesis_text": """## 1. EXECUTIVE SUMMARY
L'audit ha rivelato un Trust Score di 58/100 (C).
La fondazione consent è il punto debole principale.

## 2. IL FILO CONDUTTORE
Il 42% di rifiuto cookie con CM v2 Basic causa perdite significative.

## 3. MEASUREMENT TRUST SCORE ANALYSIS
Ogni pilastro mostra aree di miglioramento.

## 4. GAP-TO-REVENUE
2 problemi identificati, 1 nodo di leva. Impatto qualitativo su conversioni e tracking.

## 5. PRIORITY ROADMAP
- Settimana 1-2: Aggiungere Conversion Linker
- Settimana 3-4: Upgrade CM v2 ad Advanced

## 6. ANALISI PER PIATTAFORMA
Iubenda, GTM, Google Ads e Meta presentano problemi interconnessi.

## 7. APPENDICE TECNICA
Istruzioni per aggiungere Conversion Linker in GTM:
1. Aprire GTM
2. Nuovo tag > Conversion Linker
3. Trigger: All Pages""",
    "cost_usd": 0.225,
    "model": "claude-opus-4-6",
}

SAMPLE_SYNTHESIS_FAIL = {
    "success": False,
    "synthesis_text": "",
    "error": "API timeout",
    "cost_usd": 0,
    "model": "",
}


# ─── TEST: TEMPLATE EXISTS (ADR-4) ─────────────────────────────────────────

class TestTemplateExists(unittest.TestCase):
    """report_deep.html template file exists with expected placeholders (ADR-4)."""

    def test_template_file_exists(self):
        self.assertTrue(os.path.isfile(TEMPLATE_PATH))

    def test_template_has_placeholders(self):
        with open(TEMPLATE_PATH, "r") as f:
            content = f.read()
        required = [
            "{{client_name}}", "{{domain}}", "{{date}}", "{{business_type}}",
            "{{trust_score_value}}", "{{trust_grade}}", "{{trust_grade_color}}",
            "{{trust_radar_svg}}", "{{pillar_cards_html}}",
            "{{executive_summary}}", "{{consent_impact_chain}}",
            "{{gap_to_revenue_table}}", "{{priority_roadmap}}",
            "{{platform_analysis}}", "{{technical_appendix}}",
            "{{cost_l2}}", "{{cost_l3}}", "{{platforms_list}}",
        ]
        for ph in required:
            self.assertIn(ph, content, f"Missing placeholder: {ph}")

    def test_template_has_reading_levels(self):
        """3 reading levels: CEO, Marketing Manager, Developer (FR59)."""
        with open(TEMPLATE_PATH, "r") as f:
            content = f.read()
        self.assertIn("ceo", content.lower())
        self.assertIn("manager", content.lower())
        self.assertIn("dev", content.lower())

    def test_template_has_all_sections(self):
        """Report has all required sections (FR52-FR58)."""
        with open(TEMPLATE_PATH, "r") as f:
            content = f.read()
        self.assertIn("Executive Summary", content)         # FR52
        self.assertIn("Trust Score", content)                # FR53
        self.assertIn("Filo Conduttore", content)            # FR54
        self.assertIn("Gap-to-Revenue", content)             # FR55
        self.assertIn("Priority Roadmap", content)           # FR56
        self.assertIn("Piattaforma", content)                # FR57
        self.assertIn("Appendice Tecnica", content)          # FR58


# ─── TEST: RADAR SVG (FR53) ────────────────────────────────────────────────

class TestRadarSvg(unittest.TestCase):
    """Trust Score radar chart SVG generation (FR53)."""

    def test_svg_generated_with_pillars(self):
        svg = _build_radar_svg(SAMPLE_TRUST["pillars"])
        self.assertIn("<svg", svg)
        self.assertIn("</svg>", svg)
        self.assertIn("polygon", svg)

    def test_svg_has_labels(self):
        svg = _build_radar_svg(SAMPLE_TRUST["pillars"])
        self.assertIn("Consent Health", svg)
        self.assertIn("Implementation Quality", svg)

    def test_svg_has_score_values(self):
        svg = _build_radar_svg(SAMPLE_TRUST["pillars"])
        self.assertIn(">62<", svg)  # consent score
        self.assertIn(">45<", svg)  # implementation score

    def test_empty_pillars_fallback(self):
        svg = _build_radar_svg({})
        self.assertNotIn("<svg", svg)
        self.assertIn("insufficienti", svg)

    def test_two_pillars_fallback(self):
        """Radar needs at least 3 pillars."""
        two = {k: v for i, (k, v) in enumerate(SAMPLE_TRUST["pillars"].items()) if i < 2}
        svg = _build_radar_svg(two)
        self.assertNotIn("<svg", svg)


# ─── TEST: PILLAR CARDS ────────────────────────────────────────────────────

class TestPillarCards(unittest.TestCase):

    def test_cards_generated(self):
        html = _build_pillar_cards(SAMPLE_TRUST["pillars"])
        self.assertIn("pillar-card", html)
        self.assertIn("62", html)   # consent score
        self.assertIn("Consent Health", html)

    def test_empty_returns_empty(self):
        self.assertEqual(_build_pillar_cards({}), "")


# ─── TEST: CHAIN HTML (FR54) ───────────────────────────────────────────────

class TestChainHtml(unittest.TestCase):
    """Consent impact chain visualization (FR54)."""

    def test_chain_rendered(self):
        html = _build_chain_html(SAMPLE_WIZARD_BLOCK["consent_impact_chain"])
        self.assertIn("chain", html)
        self.assertIn("Banner Cookie", html)
        self.assertIn("42%", html)
        self.assertIn("&rarr;", html)

    def test_no_chain_graceful(self):
        html = _build_chain_html(None)
        self.assertIn("Nessun impatto", html)


# ─── TEST: GAP TABLE (FR55) ────────────────────────────────────────────────

class TestGapTable(unittest.TestCase):
    """Gap-to-Revenue table generation (FR55)."""

    def test_table_generated(self):
        html = _build_gap_table(SAMPLE_WIZARD_BLOCK["gap_to_revenue"])
        self.assertIn("gap-table", html)
        self.assertIn("Conversion Linker", html)
        self.assertIn("TOTALE", html)

    def test_leverage_nodes_shown(self):
        html = _build_gap_table(SAMPLE_WIZARD_BLOCK["gap_to_revenue"])
        self.assertIn("LEVA", html)
        self.assertIn("Nodi di Leva", html)

    def test_severity_css_classes(self):
        html = _build_gap_table(SAMPLE_WIZARD_BLOCK["gap_to_revenue"])
        self.assertIn("sev-critical", html)
        self.assertIn("sev-high", html)

    def test_empty_graceful(self):
        html = _build_gap_table(None)
        self.assertIn("non disponibili", html)


# ─── TEST: SYNTHESIS SECTION PARSER ─────────────────────────────────────────

class TestSynthesisParser(unittest.TestCase):

    def test_sections_extracted(self):
        sections = _extract_synthesis_sections(SAMPLE_SYNTHESIS_SUCCESS["synthesis_text"])
        self.assertGreater(len(sections), 0)

    def test_executive_summary_found(self):
        sections = _extract_synthesis_sections(SAMPLE_SYNTHESIS_SUCCESS["synthesis_text"])
        result = _find_section(sections, "EXECUTIVE", "SUMMARY")
        self.assertIn("Trust Score", result)

    def test_roadmap_found(self):
        sections = _extract_synthesis_sections(SAMPLE_SYNTHESIS_SUCCESS["synthesis_text"])
        result = _find_section(sections, "ROADMAP")
        self.assertIn("Conversion Linker", result)

    def test_appendix_found(self):
        sections = _extract_synthesis_sections(SAMPLE_SYNTHESIS_SUCCESS["synthesis_text"])
        result = _find_section(sections, "APPENDICE", "TECNICA")
        self.assertIn("GTM", result)

    def test_empty_text_returns_empty(self):
        self.assertEqual(_extract_synthesis_sections(""), {})
        self.assertEqual(_extract_synthesis_sections(None), {})

    def test_find_section_no_match(self):
        sections = {"FOO": "bar"}
        self.assertEqual(_find_section(sections, "NONEXIST"), "")


# ─── TEST: MD TO HTML ──────────────────────────────────────────────────────

class TestMdToHtml(unittest.TestCase):

    def test_bold_converted(self):
        self.assertIn("<strong>test</strong>", _md_to_html("**test**"))

    def test_inline_code(self):
        self.assertIn("<code>foo</code>", _md_to_html("`foo`"))

    def test_list_items(self):
        result = _md_to_html("- item one\n- item two")
        self.assertIn("<li>", result)
        self.assertIn("<ul>", result)

    def test_empty_returns_empty(self):
        self.assertEqual(_md_to_html(""), "")
        self.assertEqual(_md_to_html(None), "")

    def test_html_escaped(self):
        result = _md_to_html("<script>alert(1)</script>")
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)


# ─── TEST: GENERATE REPORT (INTEGRATION) ───────────────────────────────────

class TestGenerateReport(unittest.TestCase):
    """Full report generation integration test."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.orig_output_dir = None

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch('deep.report_deep.OUTPUT_DIR')
    def test_report_generated_success(self, mock_dir):
        """Successful synthesis → full report (FR52-FR59)."""
        import deep.report_deep as mod
        orig = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = self.tmp_dir
        try:
            path = generate_deep_report(
                SAMPLE_SYNTHESIS_SUCCESS, SAMPLE_WIZARD_BLOCK, SAMPLE_TRUST,
            )
            self.assertTrue(os.path.isfile(path))
            with open(path, "r") as f:
                content = f.read()

            # Verify key sections present
            self.assertIn("<!DOCTYPE html>", content)
            self.assertIn("example.com", content)
            self.assertIn("Test Client", content)
            self.assertIn("58", content)  # trust score
            self.assertIn("ecommerce", content)

            # No unresolved placeholders
            self.assertNotIn("{{", content)

            # Saved in correct directory (NFR10)
            self.assertTrue(path.startswith(self.tmp_dir))
        finally:
            mod.OUTPUT_DIR = orig

    @patch('deep.report_deep.OUTPUT_DIR')
    def test_report_generated_failed_synthesis(self, mock_dir):
        """Failed synthesis → partial report with data (NFR17)."""
        import deep.report_deep as mod
        orig = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = self.tmp_dir
        try:
            path = generate_deep_report(
                SAMPLE_SYNTHESIS_FAIL, SAMPLE_WIZARD_BLOCK, SAMPLE_TRUST,
            )
            self.assertTrue(os.path.isfile(path))
            with open(path, "r") as f:
                content = f.read()

            # Should still have structural data
            self.assertIn("58", content)  # trust score
            self.assertIn("API timeout", content)  # error noted
            self.assertNotIn("{{", content)
        finally:
            mod.OUTPUT_DIR = orig

    @patch('deep.report_deep.OUTPUT_DIR')
    def test_report_filename_format(self, mock_dir):
        """Report saved as report_deep_{domain}_{timestamp}.html (NFR10)."""
        import deep.report_deep as mod
        orig = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = self.tmp_dir
        try:
            path = generate_deep_report(
                SAMPLE_SYNTHESIS_SUCCESS, SAMPLE_WIZARD_BLOCK, SAMPLE_TRUST,
            )
            filename = os.path.basename(path)
            self.assertTrue(filename.startswith("report_deep_"))
            self.assertTrue(filename.endswith(".html"))
            self.assertIn("example.com", filename)
        finally:
            mod.OUTPUT_DIR = orig

    @patch('deep.report_deep.OUTPUT_DIR')
    def test_radar_svg_in_report(self, mock_dir):
        """Report includes SVG radar chart (FR53)."""
        import deep.report_deep as mod
        orig = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = self.tmp_dir
        try:
            path = generate_deep_report(
                SAMPLE_SYNTHESIS_SUCCESS, SAMPLE_WIZARD_BLOCK, SAMPLE_TRUST,
            )
            with open(path, "r") as f:
                content = f.read()
            self.assertIn("<svg", content)
            self.assertIn("polygon", content)
        finally:
            mod.OUTPUT_DIR = orig

    @patch('deep.report_deep.OUTPUT_DIR')
    def test_gap_table_in_report(self, mock_dir):
        """Report includes Gap-to-Revenue table (FR55)."""
        import deep.report_deep as mod
        orig = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = self.tmp_dir
        try:
            path = generate_deep_report(
                SAMPLE_SYNTHESIS_SUCCESS, SAMPLE_WIZARD_BLOCK, SAMPLE_TRUST,
            )
            with open(path, "r") as f:
                content = f.read()
            self.assertIn("gap-table", content)
            self.assertIn("Conversion Linker", content)
        finally:
            mod.OUTPUT_DIR = orig

    @patch('deep.report_deep.OUTPUT_DIR')
    def test_chain_in_report(self, mock_dir):
        """Report includes consent impact chain (FR54)."""
        import deep.report_deep as mod
        orig = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = self.tmp_dir
        try:
            path = generate_deep_report(
                SAMPLE_SYNTHESIS_SUCCESS, SAMPLE_WIZARD_BLOCK, SAMPLE_TRUST,
            )
            with open(path, "r") as f:
                content = f.read()
            self.assertIn("Banner Cookie", content)
        finally:
            mod.OUTPUT_DIR = orig

    @patch('deep.report_deep.OUTPUT_DIR')
    def test_no_client_files_embedded(self, mock_dir):
        """Client files (GTM JSON, GSC CSV) not embedded (NFR8, NFR9)."""
        import deep.report_deep as mod
        orig = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = self.tmp_dir
        try:
            # Add raw container data to wizard block
            wb = dict(SAMPLE_WIZARD_BLOCK)
            wb["gtm_data"] = {"container_raw": {"very": "large", "json": "data"}, "tag_count": 25}
            path = generate_deep_report(
                SAMPLE_SYNTHESIS_SUCCESS, wb, SAMPLE_TRUST,
            )
            with open(path, "r") as f:
                content = f.read()
            # Raw container data should NOT appear
            self.assertNotIn("container_raw", content)
        finally:
            mod.OUTPUT_DIR = orig


# ─── TEST: ITALIAN DATE ────────────────────────────────────────────────────

class TestItalianDate(unittest.TestCase):

    def test_returns_string(self):
        date = _italian_date()
        self.assertIsInstance(date, str)
        self.assertGreater(len(date), 5)


# ─── TEST: HTML ESCAPE ─────────────────────────────────────────────────────

class TestEscape(unittest.TestCase):

    def test_xss_prevention(self):
        result = _esc('<script>alert("xss")</script>')
        self.assertNotIn("<script>", result)

    def test_none_safe(self):
        self.assertEqual(_esc(None), "")

    def test_empty_safe(self):
        self.assertEqual(_esc(""), "")


# ─── TEST: MODULE IMPORTABLE ───────────────────────────────────────────────

class TestModuleImport(unittest.TestCase):

    def test_importable(self):
        import deep.report_deep
        self.assertTrue(hasattr(deep.report_deep, 'generate_deep_report'))


if __name__ == '__main__':
    unittest.main()
