"""Tests for Story 4.1: GTM container JSON upload and parsing."""

import json
import os
import sys
import unittest
from unittest.mock import patch
from io import StringIO

# Setup paths
TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_DIR = os.path.join(TOOL_DIR, 'cli')
sys.path.insert(0, CLI_DIR)

from deep.wizard_gtm import (
    _validate_gtm_json,
    _extract_container_version,
    parse_gtm_container,
    run_gap_analysis,
    run_wizard_gtm,
    _check_critical_tags,
    _check_no_consent_tags,
    _find_duplicate_tags,
    _check_datalayer_events,
    _tag_has_consent_check,
)


# ─── Fixtures ───────────────────────────────────────────────────────────────

def _make_tag(name, tag_type="html", consent=False):
    """Create a minimal GTM tag dict."""
    tag = {"name": name, "type": tag_type}
    if consent:
        tag["consentSettings"] = {"consentStatus": "needed"}
    return tag


def _make_container(tags=None, triggers=None, variables=None,
                     variant="direct", container_name="Test Container"):
    """Create a GTM container JSON string in the specified variant format."""
    cv = {
        "containerId": "GTM-TEST123",
        "container": {"name": container_name},
        "tag": tags or [],
        "trigger": triggers or [],
        "variable": variables or [],
        "builtInVariable": [],
    }

    if variant == "direct":
        data = {"containerVersion": cv}
    elif variant == "export":
        data = {"exportContainers": [{"containerVersion": cv}]}
    elif variant == "nested":
        data = {"container": {"containerVersion": cv}}
    else:
        data = {"containerVersion": cv}

    return json.dumps(data)


BUSINESS_ECOMMERCE = {"business_type": "ecommerce", "platforms": ["gtm"], "url": "https://example.com"}
BUSINESS_LEAD_GEN = {"business_type": "lead_gen", "platforms": ["gtm"], "url": "https://example.com"}
BUSINESS_BOTH = {"business_type": "both", "platforms": ["gtm"], "url": "https://example.com"}
EMPTY_DISCOVERY = {}


# ─── Validation Tests ───────────────────────────────────────────────────────

class TestValidateGtmJson(unittest.TestCase):

    def test_valid_direct_format(self):
        content = _make_container(variant="direct")
        valid, msg = _validate_gtm_json(content)
        self.assertTrue(valid)

    def test_valid_export_format(self):
        content = _make_container(variant="export")
        valid, msg = _validate_gtm_json(content)
        self.assertTrue(valid)

    def test_valid_nested_format(self):
        content = _make_container(variant="nested")
        valid, msg = _validate_gtm_json(content)
        self.assertTrue(valid)

    def test_invalid_json(self):
        valid, msg = _validate_gtm_json("not json at all {{{")
        self.assertFalse(valid)
        self.assertIn("JSON non valido", msg)

    def test_json_array_rejected(self):
        valid, msg = _validate_gtm_json("[1, 2, 3]")
        self.assertFalse(valid)
        self.assertIn("oggetto", msg)

    def test_no_container_version(self):
        valid, msg = _validate_gtm_json('{"something": "else"}')
        self.assertFalse(valid)
        self.assertIn("containerVersion", msg)

    def test_empty_export_containers(self):
        valid, msg = _validate_gtm_json('{"exportContainers": []}')
        self.assertFalse(valid)

    def test_export_containers_no_cv(self):
        valid, msg = _validate_gtm_json('{"exportContainers": [{"noCV": true}]}')
        self.assertFalse(valid)


# ─── Parsing Tests ──────────────────────────────────────────────────────────

class TestParseGtmContainer(unittest.TestCase):

    def test_parse_direct_format(self):
        tags = [_make_tag("Tag1"), _make_tag("Tag2")]
        triggers = [{"name": "Trigger1", "type": "pageview"}]
        content = _make_container(tags=tags, triggers=triggers, variant="direct")
        result = parse_gtm_container(content)

        self.assertEqual(result["tag_count"], 2)
        self.assertEqual(result["trigger_count"], 1)
        self.assertEqual(result["container_id"], "GTM-TEST123")

    def test_parse_export_format(self):
        tags = [_make_tag("Tag1")]
        content = _make_container(tags=tags, variant="export")
        result = parse_gtm_container(content)
        self.assertEqual(result["tag_count"], 1)

    def test_parse_nested_format(self):
        tags = [_make_tag("Tag1")]
        content = _make_container(tags=tags, variant="nested")
        result = parse_gtm_container(content)
        self.assertEqual(result["tag_count"], 1)

    def test_invalid_json_returns_empty(self):
        result = parse_gtm_container("not json")
        self.assertEqual(result, {})

    def test_no_container_version_returns_empty(self):
        result = parse_gtm_container('{"foo": "bar"}')
        self.assertEqual(result, {})

    def test_empty_container(self):
        content = _make_container()
        result = parse_gtm_container(content)
        self.assertEqual(result["tag_count"], 0)
        self.assertEqual(result["trigger_count"], 0)

    def test_container_name_extracted(self):
        content = _make_container(container_name="My Container")
        result = parse_gtm_container(content)
        self.assertEqual(result["container_name"], "My Container")

    def test_large_container_performance(self):
        """NFR1: <5 seconds for up to 500 tags."""
        import time
        tags = [_make_tag(f"Tag_{i}", "html") for i in range(500)]
        content = _make_container(tags=tags)
        start = time.time()
        result = parse_gtm_container(content)
        elapsed = time.time() - start
        self.assertEqual(result["tag_count"], 500)
        self.assertLess(elapsed, 5.0)


# ─── Critical Checks Tests ─────────────────────────────────────────────────

class TestCriticalChecks(unittest.TestCase):

    def test_conversion_linker_found_by_type(self):
        tags = [_make_tag("CL", "cvt_c")]
        results = _check_critical_tags(tags)
        self.assertTrue(results["conversion_linker"]["found"])

    def test_conversion_linker_found_by_name(self):
        tags = [_make_tag("Conversion Linker", "html")]
        results = _check_critical_tags(tags)
        self.assertTrue(results["conversion_linker"]["found"])

    def test_conversion_linker_missing(self):
        tags = [_make_tag("GA4 Event", "gaawc")]
        results = _check_critical_tags(tags)
        self.assertFalse(results["conversion_linker"]["found"])
        self.assertIn("mancante", results["conversion_linker"]["detail"])

    def test_enhanced_conversions_found_by_type(self):
        tags = [_make_tag("EC", "aec")]
        results = _check_critical_tags(tags)
        self.assertTrue(results["enhanced_conversions"]["found"])

    def test_enhanced_conversions_found_by_name(self):
        tags = [_make_tag("Enhanced Conversion Setup", "html")]
        results = _check_critical_tags(tags)
        self.assertTrue(results["enhanced_conversions"]["found"])

    def test_enhanced_conversions_missing(self):
        tags = [_make_tag("GA4 Event", "gaawc")]
        results = _check_critical_tags(tags)
        self.assertFalse(results["enhanced_conversions"]["found"])


# ─── Consent Check Tests ───────────────────────────────────────────────────

class TestConsentCheck(unittest.TestCase):

    def test_tag_with_consent_settings(self):
        tag = _make_tag("GA4", "gaawc", consent=True)
        self.assertTrue(_tag_has_consent_check(tag))

    def test_tag_without_consent(self):
        tag = _make_tag("Simple Tag", "html")
        self.assertFalse(_tag_has_consent_check(tag))

    def test_tag_with_consent_in_parameters(self):
        tag = {"name": "Tag", "type": "html", "parameter": [{"value": "ad_storage"}]}
        self.assertTrue(_tag_has_consent_check(tag))

    def test_no_consent_tags_detection(self):
        tags = [_make_tag("Hotjar Tracking", "html"), _make_tag("GA4 Event", "html", consent=True)]
        no_consent = _check_no_consent_tags(tags)
        names = [t["tag_name"] for t in no_consent]
        self.assertIn("Hotjar Tracking", names)
        self.assertNotIn("GA4 Event", names)


# ─── Duplicate Tags Tests ──────────────────────────────────────────────────

class TestDuplicateTags(unittest.TestCase):

    def test_no_duplicates(self):
        tags = [_make_tag("Tag1", "html"), _make_tag("Tag2", "gaawc")]
        self.assertEqual(len(_find_duplicate_tags(tags)), 0)

    def test_duplicate_detected(self):
        tags = [_make_tag("GA4 Event", "gaawc"), _make_tag("GA4 Event", "gaawc")]
        dupes = _find_duplicate_tags(tags)
        self.assertEqual(len(dupes), 1)

    def test_different_type_not_duplicate(self):
        tags = [_make_tag("Tag1", "html"), _make_tag("Tag1", "gaawc")]
        self.assertEqual(len(_find_duplicate_tags(tags)), 0)


# ─── DataLayer Events Tests ────────────────────────────────────────────────

class TestDataLayerEvents(unittest.TestCase):

    def test_ecommerce_events_found(self):
        tags = [{"name": "Purchase Tag", "type": "html", "parameter": [{"value": "purchase"}]}]
        triggers = [{"name": "add_to_cart trigger", "type": "customEvent"}]
        result = _check_datalayer_events(tags, triggers, [], "ecommerce")
        self.assertIn("purchase", result["found_events"])
        self.assertIn("add_to_cart", result["found_events"])

    def test_ecommerce_events_missing(self):
        result = _check_datalayer_events([], [], [], "ecommerce")
        self.assertIn("purchase", result["missing_events"])
        self.assertIn("add_to_cart", result["missing_events"])

    def test_lead_gen_events(self):
        result = _check_datalayer_events([], [], [], "lead_gen")
        self.assertIn("generate_lead", result["missing_events"])
        self.assertNotIn("purchase", result["missing_events"])

    def test_both_business_type(self):
        result = _check_datalayer_events([], [], [], "both")
        self.assertIn("purchase", result["missing_events"])
        self.assertIn("generate_lead", result["missing_events"])


# ─── Gap Analysis Integration Tests ────────────────────────────────────────

class TestGapAnalysis(unittest.TestCase):

    def test_full_gap_analysis_structure(self):
        tags = [_make_tag("GA4 Event", "gaawc")]
        content = _make_container(tags=tags)
        parsed = parse_gtm_container(content)
        gap = run_gap_analysis(parsed, "ecommerce")

        self.assertIn("critical_checks", gap)
        self.assertIn("missing_critical", gap)
        self.assertIn("missing_recommended", gap)
        self.assertIn("no_consent_check", gap)
        self.assertIn("duplicates", gap)
        self.assertIn("datalayer_events", gap)

    def test_gap_analysis_missing_critical(self):
        tags = [_make_tag("Some Tag", "html")]
        content = _make_container(tags=tags)
        parsed = parse_gtm_container(content)
        gap = run_gap_analysis(parsed, "ecommerce")
        self.assertIn("conversion_linker", gap["missing_critical"])
        self.assertIn("enhanced_conversions", gap["missing_critical"])

    def test_gap_analysis_all_critical_present(self):
        tags = [_make_tag("Conversion Linker", "cvt_c"),
                _make_tag("Enhanced Conversions", "aec")]
        content = _make_container(tags=tags)
        parsed = parse_gtm_container(content)
        gap = run_gap_analysis(parsed, "ecommerce")
        self.assertEqual(gap["missing_critical"], [])


# ─── Full Wizard Integration Tests ─────────────────────────────────────────

class TestRunWizardGtm(unittest.TestCase):

    @patch('deep.wizard_gtm._ask_evidence_screenshots', return_value=[])
    @patch('deep.wizard_gtm._ask_operator_notes', return_value="")
    @patch('deep.wizard_gtm._ask_multiline', return_value="")
    @patch('deep.wizard_gtm._ask_file_path')
    @patch('deep.wizard_gtm._ask_select', return_value="Sì")
    def test_wizard_happy_path(self, mock_select, mock_file, mock_ml, mock_notes, mock_ev):
        tags = [_make_tag("Conversion Linker", "cvt_c"),
                _make_tag("GA4 Event", "gaawc", consent=True)]
        content = _make_container(tags=tags)
        mock_file.return_value = ("/tmp/container.json", content)

        result = run_wizard_gtm(BUSINESS_ECOMMERCE, EMPTY_DISCOVERY)

        self.assertIsInstance(result, dict)
        self.assertEqual(result["tag_count"], 2)
        self.assertIn("gap_analysis", result)
        self.assertEqual(result["gtm_usage"], "yes")

    @patch('deep.wizard_gtm._ask_evidence_screenshots', return_value=[])
    @patch('deep.wizard_gtm._ask_operator_notes', return_value="")
    @patch('deep.wizard_gtm._ask_multiline', return_value="")
    @patch('deep.wizard_gtm._ask_file_path')
    @patch('deep.wizard_gtm._ask_select', return_value="Sì")
    def test_wizard_skip_returns_empty(self, mock_select, mock_file, mock_ml, mock_notes, mock_ev):
        mock_file.return_value = (None, None)
        result = run_wizard_gtm(BUSINESS_ECOMMERCE, EMPTY_DISCOVERY)
        self.assertEqual(result, {})

    @patch('deep.wizard_gtm._ask_evidence_screenshots', return_value=[])
    @patch('deep.wizard_gtm._ask_operator_notes', return_value="")
    @patch('deep.wizard_gtm._ask_multiline', return_value="")
    @patch('deep.wizard_gtm._ask_file_path')
    @patch('deep.wizard_gtm._ask_select', return_value="Sì")
    def test_wizard_malformed_json_returns_empty(self, mock_select, mock_file, mock_ml, mock_notes, mock_ev):
        mock_file.return_value = ("/tmp/bad.json", "not json")
        result = run_wizard_gtm(BUSINESS_ECOMMERCE, EMPTY_DISCOVERY)
        self.assertEqual(result, {})

    @patch('deep.wizard_gtm._ask_evidence_screenshots', return_value=[])
    @patch('deep.wizard_gtm._ask_operator_notes', return_value="")
    @patch('deep.wizard_gtm._ask_multiline', return_value="")
    @patch('deep.wizard_gtm._ask_file_path')
    @patch('deep.wizard_gtm._ask_select', return_value="Sì")
    def test_wizard_returns_parse_time(self, mock_select, mock_file, mock_ml, mock_notes, mock_ev):
        content = _make_container(tags=[_make_tag("T1")])
        mock_file.return_value = ("/tmp/c.json", content)
        result = run_wizard_gtm(BUSINESS_ECOMMERCE, EMPTY_DISCOVERY)
        self.assertIn("parse_time_seconds", result)
        self.assertIsInstance(result["parse_time_seconds"], float)

    @patch('deep.wizard_gtm._ask_evidence_screenshots', return_value=[])
    @patch('deep.wizard_gtm._ask_operator_notes', return_value="")
    @patch('deep.wizard_gtm._ask_multiline', return_value="")
    @patch('deep.wizard_gtm._ask_file_path')
    @patch('deep.wizard_gtm._ask_select', return_value="Sì")
    def test_wizard_lead_gen_business_type(self, mock_select, mock_file, mock_ml, mock_notes, mock_ev):
        content = _make_container(tags=[_make_tag("Form Submit", "html")])
        mock_file.return_value = ("/tmp/c.json", content)
        result = run_wizard_gtm(BUSINESS_LEAD_GEN, EMPTY_DISCOVERY)
        missing = result["gap_analysis"]["missing_recommended"]
        # Should NOT check for ecommerce events
        self.assertNotIn("purchase", missing)

    @patch('deep.wizard_gtm._ask_evidence_screenshots', return_value=[])
    @patch('deep.wizard_gtm._ask_operator_notes', return_value="test notes")
    @patch('deep.wizard_gtm._ask_input', return_value="Usa Tealium")
    @patch('deep.wizard_gtm._ask_select', return_value="No")
    def test_wizard_no_gtm(self, mock_select, mock_input, mock_notes, mock_ev):
        result = run_wizard_gtm(BUSINESS_ECOMMERCE, EMPTY_DISCOVERY)
        self.assertEqual(result["gtm_usage"], "no")
        self.assertEqual(result["gtm_skip_reason"], "Usa Tealium")
        self.assertEqual(result["operator_notes"], "test notes")

    @patch('deep.wizard_gtm._ask_evidence_screenshots', return_value=[])
    @patch('deep.wizard_gtm._ask_operator_notes', return_value="")
    @patch('deep.wizard_gtm._ask_file_path', return_value=(None, None))
    @patch('deep.wizard_gtm._ask_input', return_value="Solo analytics via GTM")
    @patch('deep.wizard_gtm._ask_select', return_value="Parzialmente")
    def test_wizard_partial_gtm_skip_file(self, mock_select, mock_input, mock_file, mock_notes, mock_ev):
        result = run_wizard_gtm(BUSINESS_ECOMMERCE, EMPTY_DISCOVERY)
        self.assertEqual(result["gtm_usage"], "partial")
        self.assertIn("gtm_partial_notes", result)


if __name__ == '__main__':
    unittest.main()
