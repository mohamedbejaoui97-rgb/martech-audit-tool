"""Tests for Story 6.1: Meta Pixel/CAPI setup and event collection."""

import os
import sys
import unittest
from unittest.mock import patch

TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_DIR = os.path.join(TOOL_DIR, 'cli')
sys.path.insert(0, CLI_DIR)

from deep.wizard_meta import (
    run_wizard_meta,
    _validate_emq,
    _warn_emq,
    _validate_pixel_id,
    _cross_check_pixel_l0,
    _collect_events,
    _check_capi_critical,
    _cross_check_gtm,
)


# ─── Fixtures ───────────────────────────────────────────────────────────────

BPROF_ECOM = {"business_type": "ecommerce", "platforms": ["meta"], "url": "https://ex.com"}
BPROF_LEAD = {"business_type": "lead_gen", "platforms": ["meta"], "url": "https://ex.com"}
BPROF_BOTH = {"business_type": "both", "platforms": ["meta"], "url": "https://ex.com"}
EMPTY_DISC = {}

DISC_WITH_PIXEL = {"scripts": ["fbevents.js"], "pixel_ids": ["123456789012345"]}
DISC_PIXEL_DIFFERENT = {"scripts": ["fbevents.js"], "pixel_ids": ["999999999999999"]}
DISC_NO_PIXEL = {"scripts": ["gtag.js"]}

GTM_BLOCK = {
    "gtm_data": {
        "container_raw": {
            "tag": [
                {"name": "Meta Purchase", "type": "html"},
                {"name": "Meta PageView", "type": "html"},
            ]
        }
    }
}


# ─── Validation Tests ───────────────────────────────────────────────────────

class TestValidateEmq(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(_validate_emq("7")[0])

    def test_valid_float(self):
        self.assertTrue(_validate_emq("6.5")[0])

    def test_valid_comma(self):
        self.assertTrue(_validate_emq("6,5")[0])

    def test_zero(self):
        self.assertTrue(_validate_emq("0")[0])

    def test_ten(self):
        self.assertTrue(_validate_emq("10")[0])

    def test_negative(self):
        self.assertFalse(_validate_emq("-1")[0])

    def test_over_ten(self):
        self.assertFalse(_validate_emq("11")[0])

    def test_non_numeric(self):
        self.assertFalse(_validate_emq("abc")[0])


class TestWarnEmq(unittest.TestCase):
    def test_low_warns(self):
        self.assertIsNotNone(_warn_emq("2"))

    def test_normal_no_warn(self):
        self.assertIsNone(_warn_emq("7"))

    def test_boundary_3_no_warn(self):
        self.assertIsNone(_warn_emq("3"))


class TestValidatePixelId(unittest.TestCase):
    def test_valid_15_digits(self):
        self.assertTrue(_validate_pixel_id("123456789012345")[0])

    def test_non_numeric(self):
        self.assertFalse(_validate_pixel_id("abc123")[0])

    def test_too_short(self):
        self.assertFalse(_validate_pixel_id("12345")[0])

    def test_too_long(self):
        self.assertFalse(_validate_pixel_id("1" * 25)[0])

    def test_empty(self):
        self.assertFalse(_validate_pixel_id("")[0])


# ─── L0 Cross-Check Tests (FR26) ───────────────────────────────────────────

class TestPixelL0CrossCheck(unittest.TestCase):
    def test_empty_discovery(self):
        r = _cross_check_pixel_l0("123456789012345", EMPTY_DISC)
        self.assertFalse(r["checked"])

    def test_pixel_match(self):
        r = _cross_check_pixel_l0("123456789012345", DISC_WITH_PIXEL)
        self.assertTrue(r["match"])

    def test_pixel_detected_different_id(self):
        r = _cross_check_pixel_l0("123456789012345", DISC_PIXEL_DIFFERENT)
        self.assertFalse(r["match"])
        self.assertIn("ID diverso", r["detail"])

    def test_no_pixel_detected(self):
        r = _cross_check_pixel_l0("123456789012345", DISC_NO_PIXEL)
        self.assertFalse(r["match"])
        self.assertIn("Nessun Meta Pixel", r["detail"])


# ─── CAPI Critical Tests (FR31) ────────────────────────────────────────────

class TestCapiCritical(unittest.TestCase):
    def test_pixel_only_lead_gen_critical(self):
        r = _check_capi_critical("pixel_only", "lead_gen")
        self.assertTrue(r["is_critical"])

    def test_pixel_only_both_critical(self):
        r = _check_capi_critical("pixel_only", "both")
        self.assertTrue(r["is_critical"])

    def test_pixel_only_ecommerce_not_critical(self):
        r = _check_capi_critical("pixel_only", "ecommerce")
        self.assertFalse(r["is_critical"])

    def test_pixel_capi_lead_gen_not_critical(self):
        r = _check_capi_critical("pixel_capi", "lead_gen")
        self.assertFalse(r["is_critical"])


# ─── GTM Cross-Check Tests (FR32) ──────────────────────────────────────────

class TestGtmCrossCheck(unittest.TestCase):
    def test_no_gtm_data(self):
        r = _cross_check_gtm({"Purchase": "ok"}, {})
        self.assertFalse(r["available"])

    def test_matching_event(self):
        r = _cross_check_gtm({"Purchase": "ok"}, GTM_BLOCK)
        self.assertTrue(r["available"])
        self.assertEqual(len(r["discrepancies"]), 0)

    def test_missing_event_in_gtm(self):
        r = _cross_check_gtm({"AddToCart": "ok"}, GTM_BLOCK)
        self.assertEqual(len(r["discrepancies"]), 1)
        self.assertIn("AddToCart", r["discrepancies"][0]["event"])

    def test_missing_event_status_skipped(self):
        """Events with status 'missing' should not trigger GTM discrepancy."""
        r = _cross_check_gtm({"AddToCart": "missing"}, GTM_BLOCK)
        self.assertEqual(len(r["discrepancies"]), 0)

    def test_error_event_not_checked(self):
        """Events with 'error' status are not cross-checked (only 'ok' events)."""
        r = _cross_check_gtm({"AddToCart": "error"}, GTM_BLOCK)
        self.assertEqual(len(r["discrepancies"]), 0)


# ─── Event Collection Tests ────────────────────────────────────────────────

class TestCollectEvents(unittest.TestCase):
    @patch('builtins.input')
    def test_ecommerce_6_events(self, mock_input):
        # 6 ecommerce events, all "Funziona" (option 1)
        mock_input.side_effect = ["1"] * 6
        events = _collect_events("ecommerce")
        self.assertEqual(len(events), 6)
        self.assertIn("PageView", events)
        self.assertIn("Purchase", events)
        self.assertEqual(events["PageView"], "ok")

    @patch('builtins.input')
    def test_lead_gen_5_events(self, mock_input):
        mock_input.side_effect = ["1"] * 5
        events = _collect_events("lead_gen")
        self.assertEqual(len(events), 5)
        self.assertIn("Lead", events)
        self.assertNotIn("Purchase", events)

    @patch('builtins.input')
    def test_mixed_statuses(self, mock_input):
        # PageView=ok, ViewContent=error, AddToCart=missing, rest=ok
        mock_input.side_effect = ["1", "2", "3", "1", "1", "1"]
        events = _collect_events("ecommerce")
        self.assertEqual(events["PageView"], "ok")
        self.assertEqual(events["ViewContent"], "error")
        self.assertEqual(events["AddToCart"], "missing")


# ─── Full Wizard Integration Tests ─────────────────────────────────────────

class TestRunWizardMeta(unittest.TestCase):

    @patch('builtins.input')
    def test_happy_path_ecommerce(self, mock_input):
        mock_input.side_effect = [
            "123456789012345",   # pixel ID
            "2",                 # CAPI: Pixel + CAPI
            "1", "1", "1", "1", "1", "1",  # 6 events all ok
            "7",                 # EMQ
            "1",                 # Attribution: 7d+1d
        ]
        result = run_wizard_meta(BPROF_ECOM, EMPTY_DISC)

        self.assertIsInstance(result, dict)
        self.assertEqual(result["pixel_id"], "123456789012345")
        self.assertEqual(result["capi_status"], "pixel_capi")
        self.assertEqual(result["emq_score"], 7.0)
        self.assertEqual(result["attribution_window"], "7d_1d")
        self.assertEqual(len(result["events"]), 6)
        self.assertIn("cross_checks", result)

    @patch('builtins.input')
    def test_lead_gen_pixel_only_capi_critical(self, mock_input):
        mock_input.side_effect = [
            "123456789012345",
            "1",                 # Solo Pixel
            "1", "1", "1", "1", "1",  # 5 lead gen events
            "5",                 # EMQ
            "2",                 # Attribution: 1d+1d
        ]
        result = run_wizard_meta(BPROF_LEAD, EMPTY_DISC)
        self.assertTrue(result["cross_checks"]["capi_critical"]["is_critical"])

    @patch('builtins.input')
    def test_with_gtm_cross_check(self, mock_input):
        mock_input.side_effect = [
            "123456789012345",
            "2",
            "1", "1", "3", "1", "1", "1",  # AddToCart=missing
            "6",
            "1",
        ]
        result = run_wizard_meta(BPROF_ECOM, EMPTY_DISC, GTM_BLOCK)
        gtm = result["cross_checks"]["gtm_cross_check"]
        self.assertTrue(gtm["available"])

    @patch('builtins.input')
    def test_pixel_l0_match(self, mock_input):
        mock_input.side_effect = [
            "123456789012345",
            "2",
            "1", "1", "1", "1", "1", "1",
            "7",
            "1",
        ]
        result = run_wizard_meta(BPROF_ECOM, DISC_WITH_PIXEL)
        self.assertTrue(result["pixel_id_match_l0"])

    @patch('builtins.input')
    def test_emq_comma_decimal(self, mock_input):
        mock_input.side_effect = [
            "123456789012345",
            "2",
            "1", "1", "1", "1", "1", "1",
            "6,5",
            "1",
        ]
        result = run_wizard_meta(BPROF_ECOM, EMPTY_DISC)
        self.assertEqual(result["emq_score"], 6.5)


if __name__ == '__main__':
    unittest.main()
