"""Tests for Story 3.1: Iubenda wizard — consent data collection."""

import os
import sys
import unittest
from unittest.mock import patch, call
from io import StringIO

# Setup paths
TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_DIR = os.path.join(TOOL_DIR, 'cli')
sys.path.insert(0, CLI_DIR)

from deep.wizard_iubenda import (
    run_wizard_iubenda,
    _validate_rejection_rate,
    _warn_rejection_rate,
    _calculate_triage_score,
    _cross_check_l0,
    _get_rejection_bucket,
)


# ─── Fixtures ───────────────────────────────────────────────────────────────

BUSINESS_PROFILE_ECOMMERCE = {
    "business_type": "ecommerce",
    "platforms": ["iubenda", "gtm", "gads", "meta", "gsc"],
    "url": "https://example.com",
}

DISCOVERY_BLOCK_WITH_GA_AND_META = {
    "technologies": ["google_analytics", "gtm", "meta_pixel", "hotjar"],
    "scripts": ["gtag.js", "fbevents.js", "hotjar-123.js"],
}

EMPTY_DISCOVERY = {}


# ─── Validation Tests ───────────────────────────────────────────────────────

class TestValidateRejectionRate(unittest.TestCase):

    def test_valid_integer(self):
        valid, msg = _validate_rejection_rate("42")
        self.assertTrue(valid)

    def test_valid_float(self):
        valid, msg = _validate_rejection_rate("42.5")
        self.assertTrue(valid)

    def test_valid_comma_decimal(self):
        valid, msg = _validate_rejection_rate("42,5")
        self.assertTrue(valid)

    def test_zero(self):
        valid, msg = _validate_rejection_rate("0")
        self.assertTrue(valid)

    def test_hundred(self):
        valid, msg = _validate_rejection_rate("100")
        self.assertTrue(valid)

    def test_negative(self):
        valid, msg = _validate_rejection_rate("-5")
        self.assertFalse(valid)

    def test_over_hundred(self):
        valid, msg = _validate_rejection_rate("101")
        self.assertFalse(valid)

    def test_non_numeric(self):
        valid, msg = _validate_rejection_rate("abc")
        self.assertFalse(valid)

    def test_empty(self):
        valid, msg = _validate_rejection_rate("")
        self.assertFalse(valid)


# ─── Warning Tests ──────────────────────────────────────────────────────────

class TestWarnRejectionRate(unittest.TestCase):

    def test_low_value_warns(self):
        warning = _warn_rejection_rate("5")
        self.assertIsNotNone(warning)
        self.assertIn("insolito", warning)

    def test_high_value_warns(self):
        warning = _warn_rejection_rate("90")
        self.assertIsNotNone(warning)
        self.assertIn("molto alto", warning)

    def test_normal_value_no_warning(self):
        warning = _warn_rejection_rate("42")
        self.assertIsNone(warning)

    def test_boundary_10_no_warning(self):
        warning = _warn_rejection_rate("10")
        self.assertIsNone(warning)

    def test_boundary_85_no_warning(self):
        warning = _warn_rejection_rate("85")
        self.assertIsNone(warning)


# ─── Triage Score Tests ────────────────────────────────────────────────────

class TestTriageScore(unittest.TestCase):

    def test_low_rejection_advanced_is_A(self):
        grade, _ = _calculate_triage_score(15.0, "advanced")
        self.assertEqual(grade, "A")

    def test_low_rejection_basic_is_B(self):
        grade, _ = _calculate_triage_score(15.0, "basic")
        self.assertEqual(grade, "B")

    def test_low_rejection_none_is_C(self):
        grade, _ = _calculate_triage_score(15.0, "none")
        self.assertEqual(grade, "C")

    def test_medium_rejection_advanced_is_B(self):
        grade, _ = _calculate_triage_score(35.0, "advanced")
        self.assertEqual(grade, "B")

    def test_medium_rejection_basic_is_C(self):
        grade, _ = _calculate_triage_score(35.0, "basic")
        self.assertEqual(grade, "C")

    def test_medium_rejection_none_is_D(self):
        grade, _ = _calculate_triage_score(35.0, "none")
        self.assertEqual(grade, "D")

    def test_high_rejection_advanced_is_C(self):
        grade, _ = _calculate_triage_score(60.0, "advanced")
        self.assertEqual(grade, "C")

    def test_high_rejection_basic_is_D(self):
        grade, _ = _calculate_triage_score(60.0, "basic")
        self.assertEqual(grade, "D")

    def test_high_rejection_none_is_F(self):
        grade, _ = _calculate_triage_score(60.0, "none")
        self.assertEqual(grade, "F")

    def test_detail_is_string(self):
        _, detail = _calculate_triage_score(42.0, "basic")
        self.assertIsInstance(detail, str)
        self.assertTrue(len(detail) > 0)


class TestRejectionBucket(unittest.TestCase):

    def test_low(self):
        self.assertEqual(_get_rejection_bucket(10), "low")

    def test_medium(self):
        self.assertEqual(_get_rejection_bucket(30), "medium")

    def test_high(self):
        self.assertEqual(_get_rejection_bucket(60), "high")

    def test_boundary_25_is_medium(self):
        self.assertEqual(_get_rejection_bucket(25), "medium")

    def test_boundary_50_is_medium(self):
        self.assertEqual(_get_rejection_bucket(50), "medium")

    def test_boundary_51_is_high(self):
        self.assertEqual(_get_rejection_bucket(51), "high")


# ─── L0 Cross-Check Tests ──────────────────────────────────────────────────

class TestCrossCheckL0(unittest.TestCase):

    def test_empty_discovery_no_mismatches(self):
        mismatches = _cross_check_l0(["Google Analytics"], EMPTY_DISCOVERY)
        self.assertEqual(mismatches, [])

    def test_service_in_banner_not_on_site(self):
        discovery = {"scripts": ["gtag.js"]}
        mismatches = _cross_check_l0(["LinkedIn Insight Tag"], discovery)
        in_banner = [m for m in mismatches if m["type"] == "in_banner_not_detected"]
        self.assertTrue(any("LinkedIn" in m["service"] for m in in_banner))

    def test_service_on_site_not_in_banner(self):
        discovery = {"technologies": ["hotjar"], "scripts": ["hotjar-123.js"]}
        mismatches = _cross_check_l0([], discovery)
        detected = [m for m in mismatches if m["type"] == "detected_not_in_banner"]
        self.assertTrue(any("Hotjar" in m["service"] for m in detected))

    def test_matching_services_no_mismatches_for_those(self):
        discovery = {"technologies": ["google_analytics"]}
        mismatches = _cross_check_l0(["Google Analytics"], discovery)
        ga_mismatches = [m for m in mismatches if "Google Analytics" in m["service"]]
        self.assertEqual(len(ga_mismatches), 0)

    def test_no_duplicate_detected_not_in_banner(self):
        # google_analytics has multiple keys: google_analytics, ga4, gtag
        discovery = {"technologies": ["google_analytics", "ga4", "gtag"]}
        mismatches = _cross_check_l0([], discovery)
        ga_detected = [m for m in mismatches if m["service"] == "Google Analytics"
                       and m["type"] == "detected_not_in_banner"]
        self.assertEqual(len(ga_detected), 1)


# ─── Full Wizard Integration Tests ─────────────────────────────────────────

class TestRunWizardIubenda(unittest.TestCase):

    @patch('builtins.input')
    def test_full_wizard_happy_path(self, mock_input):
        # rejection rate=42, CM v2=Basic(2), banner=1,2,3 (GA, GAds, Meta), anomalies, notes
        mock_input.side_effect = ["42", "2", "1,2,3", "", "", "n"]
        result = run_wizard_iubenda(BUSINESS_PROFILE_ECOMMERCE, EMPTY_DISCOVERY)

        self.assertIsInstance(result, dict)
        self.assertEqual(result["rejection_rate"], 42.0)
        self.assertEqual(result["consent_mode_v2"], "basic")
        self.assertEqual(len(result["banner_services"]), 3)
        self.assertIn("triage_score", result)
        self.assertIn("triage_detail", result)
        self.assertIn("l0_mismatches", result)

    @patch('builtins.input')
    def test_wizard_returns_correct_triage(self, mock_input):
        # 60% rejection + none (Assente=1) → should be F
        mock_input.side_effect = ["60", "1", "1", "", "", "n"]
        result = run_wizard_iubenda(BUSINESS_PROFILE_ECOMMERCE, EMPTY_DISCOVERY)
        self.assertEqual(result["triage_score"], "F")

    @patch('builtins.input')
    def test_wizard_returns_dict_on_empty_discovery(self, mock_input):
        mock_input.side_effect = ["30", "3", "1,2", "", "", "n"]
        result = run_wizard_iubenda(BUSINESS_PROFILE_ECOMMERCE, EMPTY_DISCOVERY)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["l0_mismatches"], [])

    @patch('builtins.input')
    def test_wizard_with_l0_cross_check(self, mock_input):
        # Select only Google Analytics (1) but discovery has hotjar too
        mock_input.side_effect = ["42", "2", "1", "", "", "n"]
        result = run_wizard_iubenda(
            BUSINESS_PROFILE_ECOMMERCE,
            DISCOVERY_BLOCK_WITH_GA_AND_META
        )
        self.assertIsInstance(result["l0_mismatches"], list)

    @patch('builtins.input')
    def test_wizard_consent_mode_advanced(self, mock_input):
        mock_input.side_effect = ["20", "3", "1", "", "", "n"]  # Advanced=3
        result = run_wizard_iubenda(BUSINESS_PROFILE_ECOMMERCE, EMPTY_DISCOVERY)
        self.assertEqual(result["consent_mode_v2"], "advanced")

    @patch('builtins.input')
    def test_wizard_comma_decimal_rejection(self, mock_input):
        # Italian comma notation: 42,5%
        mock_input.side_effect = ["42,5", "2", "1", "", "", "n"]
        result = run_wizard_iubenda(BUSINESS_PROFILE_ECOMMERCE, EMPTY_DISCOVERY)
        self.assertEqual(result["rejection_rate"], 42.5)

    @patch('builtins.input')
    def test_wizard_with_operator_notes(self, mock_input):
        mock_input.side_effect = ["42", "2", "1", "Banner non blocca", "Nota test", "n"]
        result = run_wizard_iubenda(BUSINESS_PROFILE_ECOMMERCE, EMPTY_DISCOVERY)
        self.assertEqual(result["anomalies_detected"], "Banner non blocca")
        self.assertEqual(result["operator_notes"], "Nota test")

    @patch('builtins.input')
    def test_wizard_percent_strip(self, mock_input):
        # "55%" should be stripped to "55"
        mock_input.side_effect = ["55%", "2", "1", "", "", "n"]
        result = run_wizard_iubenda(BUSINESS_PROFILE_ECOMMERCE, EMPTY_DISCOVERY)
        self.assertEqual(result["rejection_rate"], 55.0)

    @patch('builtins.input')
    def test_wizard_gtm_mismatch_message(self, mock_input):
        # GTM is in platforms → mismatch message should mention GTM
        mock_input.side_effect = ["42", "2", "5", "", "", "n"]  # banner=TikTok(5)
        result = run_wizard_iubenda(BUSINESS_PROFILE_ECOMMERCE, EMPTY_DISCOVERY)
        tiktok_mismatch = [m for m in result["l0_mismatches"] if "TikTok" in m["service"]]
        if tiktok_mismatch:
            self.assertIn("GTM", tiktok_mismatch[0]["detail"])


if __name__ == '__main__':
    unittest.main()
