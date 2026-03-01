"""Tests for Story 8.1+8.2: Trust Score, Gap-to-Revenue, cross-platform intelligence."""

import os
import sys
import time
import unittest

TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_DIR = os.path.join(TOOL_DIR, 'cli')
sys.path.insert(0, CLI_DIR)

from deep.trust_score import (
    calculate_trust_score,
    calculate_gap_to_revenue,
    build_consent_impact_chain,
    compare_attribution_windows,
    identify_leverage_nodes,
    score_to_grade,
    _score_consent_health,
    _score_implementation_quality,
    _score_conversion_reliability,
    _score_event_match_quality,
    _score_data_foundation,
)


# ─── Fixtures ───────────────────────────────────────────────────────────────

GOOD_IUBENDA = {
    "rejection_rate": 15, "consent_mode_v2": "advanced",
    "triage_score": "A", "banner_services": ["Google Analytics"], "l0_mismatches": [],
}
BAD_IUBENDA = {
    "rejection_rate": 60, "consent_mode_v2": "none",
    "triage_score": "F", "banner_services": [], "l0_mismatches": [
        {"type": "detected_not_in_banner", "service": "Hotjar", "detail": "..."}
    ],
}
MEDIUM_IUBENDA = {
    "rejection_rate": 35, "consent_mode_v2": "basic",
    "triage_score": "C", "banner_services": [], "l0_mismatches": [],
}

GOOD_GTM = {
    "tag_count": 30, "trigger_count": 15, "variable_count": 20,
    "gap_analysis": {
        "critical_checks": {}, "missing_critical": [],
        "missing_recommended": [], "no_consent_check": [], "duplicates": [],
    },
}
BAD_GTM = {
    "tag_count": 10, "trigger_count": 5, "variable_count": 3,
    "gap_analysis": {
        "critical_checks": {
            "conversion_linker": {"found": False, "severity": "critical",
                                  "detail": "Conversion Linker mancante"},
            "enhanced_conversions": {"found": False, "severity": "critical",
                                     "detail": "EC non configurate"},
        },
        "missing_critical": ["conversion_linker", "enhanced_conversions"],
        "missing_recommended": ["add_to_cart", "begin_checkout"],
        "no_consent_check": [{"tag_name": "Hotjar", "tag_type": "html"}] * 3,
        "duplicates": [{"tag_name": "GA4", "tag_type": "gaawc"}],
    },
}

GOOD_GADS = {
    "conversion_actions": [{"name": "Purchase", "is_primary": True}],
    "consent_mode_status": "Excellent",
    "enhanced_conversions_status": "Excellent",
    "attribution_model": "Data-driven",
    "cross_checks": {
        "primary_conflicts": {"has_conflict": False},
        "gtm_cross_check": {"available": False, "discrepancies": []},
        "missing_funnel_events": {"upper": [], "mid": [], "bottom": []},
        "source_discrepancies": [],
    },
}
BAD_GADS = {
    "conversion_actions": [{"name": "A", "is_primary": True}, {"name": "B", "is_primary": True}],
    "consent_mode_status": "Not set up",
    "enhanced_conversions_status": "Not set up",
    "attribution_model": "Last-click",
    "cross_checks": {
        "primary_conflicts": {"has_conflict": True, "detail": "2 primary in conflitto"},
        "gtm_cross_check": {"available": True, "discrepancies": [{"action_name": "A"}]},
        "missing_funnel_events": {"upper": ["view_item"], "mid": ["add_to_cart"], "bottom": []},
        "source_discrepancies": [{"type": "duplicate_source", "action_name": "Purchase"}],
    },
}

GOOD_META = {
    "pixel_id": "123", "pixel_id_match_l0": True, "capi_status": "pixel_capi",
    "emq_score": 8, "events": {"PageView": "ok", "Purchase": "ok"},
    "attribution_window": "7d_1d",
    "cross_checks": {"capi_critical": {"is_critical": False}, "gtm_cross_check": {"available": False}},
}
BAD_META = {
    "pixel_id": "123", "pixel_id_match_l0": False, "capi_status": "pixel_only",
    "emq_score": 2, "events": {"PageView": "ok", "Purchase": "missing", "Lead": "error"},
    "attribution_window": "1d_1d",
    "cross_checks": {"capi_critical": {"is_critical": True}, "gtm_cross_check": {"available": False}},
}

GOOD_GSC = {
    "sitemap_status": "ok", "pages_indexed": 400, "pages_submitted": 420,
    "indexing_issues": [], "opportunities": [{"page": "/shoes"}],
    "trend_analysis": {"top_pages": [], "opportunities": [{"page": "/shoes"}]},
}
BAD_GSC = {
    "sitemap_status": "not_submitted", "pages_indexed": 50, "pages_submitted": 200,
    "indexing_issues": ["Noindex"], "opportunities": [],
    "trend_analysis": {"top_pages": [], "opportunities": []},
}

FULL_GOOD = {
    "business_profile": {"business_type": "ecommerce"},
    "iubenda_data": GOOD_IUBENDA, "gtm_data": GOOD_GTM,
    "gads_data": GOOD_GADS, "meta_data": GOOD_META, "gsc_data": GOOD_GSC,
}
FULL_BAD = {
    "business_profile": {"business_type": "ecommerce"},
    "iubenda_data": BAD_IUBENDA, "gtm_data": BAD_GTM,
    "gads_data": BAD_GADS, "meta_data": BAD_META, "gsc_data": BAD_GSC,
}
PARTIAL = {
    "business_profile": {"business_type": "lead_gen"},
    "iubenda_data": GOOD_IUBENDA, "gtm_data": GOOD_GTM,
}


# ─── Grade Tests ───────────────────────────────────────────────────────────

class TestScoreToGrade(unittest.TestCase):
    def test_A(self):  self.assertEqual(score_to_grade(95), "A")
    def test_B(self):  self.assertEqual(score_to_grade(80), "B")
    def test_C(self):  self.assertEqual(score_to_grade(65), "C")
    def test_D(self):  self.assertEqual(score_to_grade(45), "D")
    def test_F(self):  self.assertEqual(score_to_grade(30), "F")
    def test_boundary_90(self): self.assertEqual(score_to_grade(90), "A")
    def test_boundary_75(self): self.assertEqual(score_to_grade(75), "B")
    def test_boundary_60(self): self.assertEqual(score_to_grade(60), "C")
    def test_boundary_40(self): self.assertEqual(score_to_grade(40), "D")
    def test_boundary_39(self): self.assertEqual(score_to_grade(39), "F")


# ─── Pillar Scoring Tests ─────────────────────────────────────────────────

class TestPillarScoring(unittest.TestCase):
    def test_consent_good(self):
        s = _score_consent_health(GOOD_IUBENDA)
        self.assertGreaterEqual(s, 80)

    def test_consent_bad(self):
        s = _score_consent_health(BAD_IUBENDA)
        self.assertLessEqual(s, 20)

    def test_gtm_good(self):
        s = _score_implementation_quality(GOOD_GTM)
        self.assertEqual(s, 100)

    def test_gtm_bad(self):
        s = _score_implementation_quality(BAD_GTM)
        self.assertLessEqual(s, 40)

    def test_gads_good(self):
        s = _score_conversion_reliability(GOOD_GADS)
        self.assertGreaterEqual(s, 90)

    def test_gads_bad(self):
        s = _score_conversion_reliability(BAD_GADS)
        self.assertLessEqual(s, 30)

    def test_meta_good(self):
        s = _score_event_match_quality(GOOD_META)
        self.assertGreaterEqual(s, 80)

    def test_meta_bad(self):
        s = _score_event_match_quality(BAD_META)
        self.assertLessEqual(s, 30)

    def test_gsc_good(self):
        s = _score_data_foundation(GOOD_GSC)
        self.assertGreaterEqual(s, 85)

    def test_gsc_bad(self):
        s = _score_data_foundation(BAD_GSC)
        self.assertLessEqual(s, 50)

    def test_all_scores_0_100(self):
        for scorer, good, bad in [
            (_score_consent_health, GOOD_IUBENDA, BAD_IUBENDA),
            (_score_implementation_quality, GOOD_GTM, BAD_GTM),
            (_score_conversion_reliability, GOOD_GADS, BAD_GADS),
            (_score_event_match_quality, GOOD_META, BAD_META),
            (_score_data_foundation, GOOD_GSC, BAD_GSC),
        ]:
            s_good = scorer(good)
            s_bad = scorer(bad)
            self.assertGreaterEqual(s_good, 0)
            self.assertLessEqual(s_good, 100)
            self.assertGreaterEqual(s_bad, 0)
            self.assertLessEqual(s_bad, 100)


# ─── Trust Score Calculation Tests (FR45, FR46) ───────────────────────────

class TestCalculateTrustScore(unittest.TestCase):
    def test_full_good_high_score(self):
        result = calculate_trust_score(FULL_GOOD)
        self.assertGreaterEqual(result["score"], 80)
        self.assertIn(result["grade"], ("A", "B"))
        self.assertEqual(result["coverage"], 1.0)
        self.assertEqual(result["coverage_label"], "5/5 platforms")

    def test_full_bad_low_score(self):
        result = calculate_trust_score(FULL_BAD)
        self.assertLessEqual(result["score"], 40)
        self.assertIn(result["grade"], ("D", "F"))

    def test_partial_weight_redistribution(self):
        result = calculate_trust_score(PARTIAL)
        self.assertEqual(result["coverage_label"], "2/5 platforms")
        self.assertGreater(result["score"], 0)
        # Weights should sum to ~1.0 after redistribution
        total_w = sum(p["weight_normalized"] for p in result["pillars"].values())
        self.assertAlmostEqual(total_w, 1.0, places=2)

    def test_empty_data_returns_zero(self):
        result = calculate_trust_score({"business_profile": {}})
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["grade"], "F")
        self.assertEqual(result["coverage"], 0.0)

    def test_single_platform(self):
        data = {"iubenda_data": GOOD_IUBENDA}
        result = calculate_trust_score(data)
        self.assertEqual(result["coverage_label"], "1/5 platforms")
        self.assertGreater(result["score"], 0)

    def test_pillars_detail(self):
        result = calculate_trust_score(FULL_GOOD)
        for pillar_name, pillar_data in result["pillars"].items():
            self.assertIn("score", pillar_data)
            self.assertIn("weight_original", pillar_data)
            self.assertIn("weight_normalized", pillar_data)
            self.assertIn("label", pillar_data)

    def test_performance_nfr3(self):
        """NFR3: Trust Score calculation <1 second."""
        start = time.time()
        for _ in range(100):
            calculate_trust_score(FULL_GOOD)
        elapsed = time.time() - start
        self.assertLess(elapsed / 100, 1.0)


# ─── Gap-to-Revenue Tests (FR47) ─────────────────────────────────────────

class TestGapToRevenue(unittest.TestCase):
    def test_bad_setup_has_issues(self):
        result = calculate_gap_to_revenue(FULL_BAD)
        self.assertGreater(len(result["issues"]), 0)
        self.assertGreater(result["total_impact_min"], 0)
        self.assertGreater(result["total_impact_max"], result["total_impact_min"])

    def test_good_setup_fewer_issues(self):
        result_good = calculate_gap_to_revenue(FULL_GOOD)
        result_bad = calculate_gap_to_revenue(FULL_BAD)
        self.assertLess(len(result_good["issues"]), len(result_bad["issues"]))

    def test_each_issue_has_impact(self):
        result = calculate_gap_to_revenue(FULL_BAD)
        for issue in result["issues"]:
            self.assertIn("impact_min", issue)
            self.assertIn("impact_max", issue)
            self.assertGreater(issue["impact_max"], 0)

    def test_total_label_format(self):
        result = calculate_gap_to_revenue(FULL_BAD)
        self.assertIn("€", result["total_impact_label"])
        self.assertIn("/mese", result["total_impact_label"])

    def test_empty_data(self):
        result = calculate_gap_to_revenue({})
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["total_impact_min"], 0)


# ─── Consent Impact Chain Tests (FR48) ────────────────────────────────────

class TestConsentImpactChain(unittest.TestCase):
    def test_bad_consent_has_chain(self):
        result = build_consent_impact_chain({"iubenda_data": BAD_IUBENDA})
        self.assertIsNotNone(result)
        self.assertGreater(len(result["chain"]), 2)

    def test_good_consent_no_chain(self):
        result = build_consent_impact_chain({"iubenda_data": GOOD_IUBENDA})
        self.assertIsNone(result)

    def test_no_iubenda_no_chain(self):
        result = build_consent_impact_chain({})
        self.assertIsNone(result)

    def test_medium_consent_has_chain(self):
        result = build_consent_impact_chain({"iubenda_data": MEDIUM_IUBENDA})
        self.assertIsNotNone(result)

    def test_chain_steps_ordered(self):
        result = build_consent_impact_chain({"iubenda_data": BAD_IUBENDA})
        steps = [s["step"] for s in result["chain"]]
        self.assertEqual(steps, sorted(steps))


# ─── Attribution Window Comparison Tests (FR50) ───────────────────────────

class TestAttributionWindows(unittest.TestCase):
    def test_inconsistency_detected(self):
        data = {"gads_data": {"attribution_model": "Data-driven"},
                "meta_data": {"attribution_window": "1d_1d"}}
        result = compare_attribution_windows(data)
        self.assertTrue(result["has_inconsistency"])

    def test_no_inconsistency(self):
        data = {"gads_data": {"attribution_model": "Data-driven"},
                "meta_data": {"attribution_window": "7d_1d"}}
        result = compare_attribution_windows(data)
        self.assertFalse(result["has_inconsistency"])

    def test_missing_platform_returns_none(self):
        self.assertIsNone(compare_attribution_windows({"gads_data": GOOD_GADS}))
        self.assertIsNone(compare_attribution_windows({"meta_data": GOOD_META}))
        self.assertIsNone(compare_attribution_windows({}))


# ─── Leverage Nodes Tests (FR49) ─────────────────────────────────────────

class TestLeverageNodes(unittest.TestCase):
    def test_bad_has_leverage_nodes(self):
        g2r = calculate_gap_to_revenue(FULL_BAD)
        nodes = identify_leverage_nodes(g2r)
        self.assertGreater(len(nodes), 0)
        self.assertTrue(any(n["is_leverage_node"] for n in nodes))

    def test_leverage_nodes_have_affects(self):
        g2r = calculate_gap_to_revenue(FULL_BAD)
        nodes = identify_leverage_nodes(g2r)
        for node in nodes:
            self.assertIn("affects", node)


if __name__ == '__main__':
    unittest.main()
