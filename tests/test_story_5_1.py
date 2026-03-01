"""Tests for Story 5.1: Google Ads conversion actions inventory."""

import os
import sys
import unittest
from unittest.mock import patch

# Setup paths
TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_DIR = os.path.join(TOOL_DIR, 'cli')
sys.path.insert(0, CLI_DIR)

from deep.wizard_gads import (
    run_wizard_gads,
    _check_primary_conflicts,
    _cross_check_gtm,
    _check_missing_funnel_events,
    _check_source_discrepancies,
    _validate_positive_int,
    _collect_conversion_actions,
)


# ─── Fixtures ───────────────────────────────────────────────────────────────

BPROF_ECOMMERCE = {"business_type": "ecommerce", "platforms": ["gads"], "url": "https://ex.com"}
BPROF_LEAD_GEN = {"business_type": "lead_gen", "platforms": ["gads"], "url": "https://ex.com"}
BPROF_BOTH = {"business_type": "both", "platforms": ["gads"], "url": "https://ex.com"}
EMPTY_DISCOVERY = {}

ACTION_PRIMARY_1 = {"name": "Purchase", "is_primary": True, "source": "Website", "status": "Attiva", "counting": "Ogni conversione"}
ACTION_PRIMARY_2 = {"name": "Lead", "is_primary": True, "source": "Website", "status": "Attiva", "counting": "Una conversione"}
ACTION_SECONDARY = {"name": "PageView", "is_primary": False, "source": "GA4 Import", "status": "Attiva", "counting": "Una conversione"}

GTM_BLOCK_WITH_PURCHASE = {
    "gtm_data": {
        "container_raw": {
            "tag": [{"name": "Purchase Tag", "type": "awct"}]
        }
    }
}
GTM_BLOCK_EMPTY = {"gtm_data": {}}


# ─── Validation Tests ───────────────────────────────────────────────────────

class TestValidatePositiveInt(unittest.TestCase):

    def test_valid(self):
        self.assertTrue(_validate_positive_int("3")[0])

    def test_zero(self):
        self.assertTrue(_validate_positive_int("0")[0])

    def test_negative(self):
        self.assertFalse(_validate_positive_int("-1")[0])

    def test_too_large(self):
        self.assertFalse(_validate_positive_int("101")[0])

    def test_non_numeric(self):
        self.assertFalse(_validate_positive_int("abc")[0])

    def test_float_rejected(self):
        self.assertFalse(_validate_positive_int("2.5")[0])


# ─── Primary Conflicts Tests (FR22) ────────────────────────────────────────

class TestPrimaryConflicts(unittest.TestCase):

    def test_no_conflict_single_primary(self):
        result = _check_primary_conflicts([ACTION_PRIMARY_1, ACTION_SECONDARY])
        self.assertFalse(result["has_conflict"])

    def test_conflict_multiple_primaries(self):
        result = _check_primary_conflicts([ACTION_PRIMARY_1, ACTION_PRIMARY_2])
        self.assertTrue(result["has_conflict"])
        self.assertEqual(result["count"], 2)
        self.assertIn("Purchase", result["names"])
        self.assertIn("Lead", result["names"])

    def test_no_primaries(self):
        result = _check_primary_conflicts([ACTION_SECONDARY])
        self.assertFalse(result["has_conflict"])

    def test_conflict_detail_message(self):
        result = _check_primary_conflicts([ACTION_PRIMARY_1, ACTION_PRIMARY_2])
        self.assertIn("conflitto", result["detail"])


# ─── GTM Cross-Check Tests (FR23) ──────────────────────────────────────────

class TestGtmCrossCheck(unittest.TestCase):

    def test_no_gtm_data(self):
        result = _cross_check_gtm([ACTION_PRIMARY_1], {})
        self.assertFalse(result["available"])

    def test_gtm_empty_data(self):
        result = _cross_check_gtm([ACTION_PRIMARY_1], GTM_BLOCK_EMPTY)
        self.assertFalse(result["available"])

    def test_matching_tag_no_discrepancy(self):
        result = _cross_check_gtm([ACTION_PRIMARY_1], GTM_BLOCK_WITH_PURCHASE)
        self.assertTrue(result["available"])
        self.assertEqual(len(result["discrepancies"]), 0)

    def test_missing_tag_flagged(self):
        action = {"name": "SignUp", "is_primary": True, "source": "Website",
                  "status": "Attiva", "counting": "Una conversione"}
        result = _cross_check_gtm([action], GTM_BLOCK_WITH_PURCHASE)
        self.assertEqual(len(result["discrepancies"]), 1)
        self.assertIn("SignUp", result["discrepancies"][0]["action_name"])

    def test_ga4_import_source_not_checked(self):
        """GA4 Import conversions don't need GTM tags."""
        result = _cross_check_gtm([ACTION_SECONDARY], GTM_BLOCK_WITH_PURCHASE)
        self.assertEqual(len(result["discrepancies"]), 0)


# ─── Missing Funnel Events Tests (FR24) ────────────────────────────────────

class TestMissingFunnelEvents(unittest.TestCase):

    def test_ecommerce_missing_all(self):
        result = _check_missing_funnel_events([], "ecommerce")
        self.assertIn("purchase", result["bottom"])
        self.assertIn("add_to_cart", result["mid"])

    def test_ecommerce_purchase_present(self):
        actions = [{"name": "purchase"}]
        result = _check_missing_funnel_events(actions, "ecommerce")
        self.assertNotIn("purchase", result["bottom"])

    def test_lead_gen_missing_all(self):
        result = _check_missing_funnel_events([], "lead_gen")
        self.assertIn("generate_lead", result["bottom"])
        self.assertNotIn("purchase", result.get("bottom", []))

    def test_both_includes_all(self):
        result = _check_missing_funnel_events([], "both")
        self.assertIn("purchase", result["bottom"])
        self.assertIn("generate_lead", result["bottom"])

    def test_no_missing_when_all_present(self):
        actions = [{"name": "purchase"}, {"name": "add_to_cart"},
                   {"name": "begin_checkout"}, {"name": "view_item"},
                   {"name": "view_item_list"}, {"name": "add_payment_info"}]
        result = _check_missing_funnel_events(actions, "ecommerce")
        self.assertEqual(result["bottom"], [])
        self.assertEqual(result["mid"], [])


# ─── Source Discrepancies Tests (FR25) ─────────────────────────────────────

class TestSourceDiscrepancies(unittest.TestCase):

    def test_no_overlap(self):
        actions = [
            {"name": "Purchase", "source": "Website"},
            {"name": "Lead", "source": "GA4 Import"},
        ]
        result = _check_source_discrepancies(actions)
        self.assertEqual(len(result), 0)

    def test_duplicate_source_detected(self):
        actions = [
            {"name": "Purchase", "source": "Website"},
            {"name": "Purchase", "source": "GA4 Import"},
        ]
        result = _check_source_discrepancies(actions)
        self.assertEqual(len(result), 1)
        self.assertIn("doppio conteggio", result[0]["detail"])

    def test_case_insensitive_match(self):
        actions = [
            {"name": "PURCHASE", "source": "Website"},
            {"name": "purchase", "source": "GA4 Import"},
        ]
        result = _check_source_discrepancies(actions)
        self.assertEqual(len(result), 1)


# ─── Conversion Collection Tests ───────────────────────────────────────────

class TestCollectConversionActions(unittest.TestCase):

    @patch('builtins.input')
    def test_collect_single_action(self, mock_input):
        # name, primary(1), source Website(1), status Attiva(1), counting Ogni(1)
        mock_input.side_effect = ["Purchase", "1", "1", "1", "1"]
        actions = _collect_conversion_actions(1)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["name"], "Purchase")
        self.assertTrue(actions[0]["is_primary"])
        self.assertEqual(actions[0]["source"], "Website")

    @patch('builtins.input')
    def test_collect_two_actions(self, mock_input):
        mock_input.side_effect = [
            "Purchase", "1", "1", "1", "1",  # action 1
            "Lead", "2", "2", "1", "2",       # action 2: secondary, GA4 Import
        ]
        actions = _collect_conversion_actions(2)
        self.assertEqual(len(actions), 2)
        self.assertFalse(actions[1]["is_primary"])
        self.assertEqual(actions[1]["source"], "GA4 Import")


# ─── Full Wizard Integration Tests ─────────────────────────────────────────

class TestRunWizardGads(unittest.TestCase):

    @patch('builtins.input')
    def test_summary_mode_happy_path(self, mock_input):
        mock_input.side_effect = [
            "3",      # num actions
            "2",      # primary
            "1",      # secondary
            "1",      # EC: Excellent
            "1",      # CM: Excellent
            "1",      # Attribution: Data-driven
            "1",      # Conversions active: Sì
            "1",      # GA4 match: Sì
            "1",      # Detail mode: No (sommario)
            "",        # anomalies (skip)
            "",        # operator notes (skip)
            "n",       # evidence screenshots
        ]
        result = run_wizard_gads(BPROF_ECOMMERCE, EMPTY_DISCOVERY)

        self.assertIsInstance(result, dict)
        self.assertEqual(result["summary"]["total"], 3)
        self.assertEqual(result["summary"]["primary"], 2)
        self.assertEqual(result["consent_mode_status"], "Excellent")
        self.assertIn("cross_checks", result)
        self.assertFalse(result["detail_mode"])

    @patch('builtins.input')
    def test_zero_actions(self, mock_input):
        mock_input.side_effect = [
            "0",   # num actions
            "",    # operator notes (skip)
            "n",   # evidence
        ]
        result = run_wizard_gads(BPROF_ECOMMERCE, EMPTY_DISCOVERY)
        self.assertEqual(result["conversion_actions"], [])
        self.assertEqual(result["consent_mode_status"], "")

    @patch('builtins.input')
    def test_detail_mode_with_actions(self, mock_input):
        mock_input.side_effect = [
            "1",      # num actions
            "1",      # primary
            "0",      # secondary
            "1",      # EC
            "1",      # CM
            "1",      # Attribution
            "1",      # Conversions active: Sì
            "1",      # GA4 match: Sì
            "2",      # Detail mode: Sì (dettaglio)
            "Purchase", "1", "1", "1", "1",  # action detail
            "",        # anomalies
            "",        # operator notes
            "n",       # evidence
        ]
        result = run_wizard_gads(BPROF_ECOMMERCE, EMPTY_DISCOVERY)
        self.assertTrue(result["detail_mode"])
        self.assertEqual(len(result["conversion_actions"]), 1)

    @patch('builtins.input')
    def test_ga4_gap_critical_flag(self, mock_input):
        mock_input.side_effect = [
            "2",      # num actions
            "1",      # primary
            "1",      # secondary
            "1",      # EC
            "1",      # CM
            "1",      # Attribution
            "2",      # Conversions active: No
            "7",      # inactive days
            "1",      # GA4 match: Sì → critical gap
            "1",      # Detail: No
            "",        # anomalies
            "",        # operator notes
            "n",       # evidence
        ]
        result = run_wizard_gads(BPROF_ECOMMERCE, EMPTY_DISCOVERY)
        self.assertTrue(result["ga4_gap_critical"])

    @patch('builtins.input')
    def test_operator_notes_and_anomalies(self, mock_input):
        mock_input.side_effect = [
            "1",      # num actions
            "1",      # primary
            "0",      # secondary
            "1",      # EC
            "1",      # CM
            "1",      # Attribution
            "1",      # Active: Sì
            "1",      # GA4: Sì
            "1",      # Detail: No
            "CPC troppo alto",  # anomalies
            "Notare il gap",    # operator notes
            "n",                # evidence
        ]
        result = run_wizard_gads(BPROF_ECOMMERCE, EMPTY_DISCOVERY)
        self.assertEqual(result["anomalies_detected"], "CPC troppo alto")
        self.assertEqual(result["operator_notes"], "Notare il gap")


if __name__ == '__main__':
    unittest.main()
