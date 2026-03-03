"""Tests for Story 7.1: GSC sitemap and indexing assessment + CSV parsing."""

import os
import sys
import time
import unittest
from unittest.mock import patch

TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_DIR = os.path.join(TOOL_DIR, 'cli')
sys.path.insert(0, CLI_DIR)

from deep.wizard_gsc import (
    run_wizard_gsc,
    _validate_pages_count,
    _validate_csv_content,
    _detect_delimiter,
    _normalize_headers,
    _parse_numeric,
    parse_gsc_csv,
    analyze_trends,
)


# ─── Fixtures ───────────────────────────────────────────────────────────────

BPROF = {"business_type": "ecommerce", "platforms": ["gsc"], "url": "https://ex.com"}
EMPTY_DISC = {}

CSV_EN_COMMA = """Top queries,Clicks,Impressions,CTR,Position
shoes,500,10000,5%,3.2
boots,200,8000,2.5%,7.1
sandals,50,5000,1%,12.3
hats,10,200,5%,4.0
"""

CSV_IT_TAB = "Query principali\tClic\tImpressioni\tCTR\tPosizione\n" \
             "scarpe\t500\t10000\t5%\t3,2\n" \
             "stivali\t200\t8000\t2,5%\t7,1\n"

CSV_PAGES_EN = """Top pages,Clicks,Impressions,CTR,Position
https://ex.com/shoes,500,10000,5%,3.2
https://ex.com/boots,200,8000,2.5%,7.1
https://ex.com/sandals,50,5000,1%,12.3
"""

CSV_MINIMAL = "query,clicks\ntest,10\n"

CSV_EMPTY_HEADER = "just a header\n"


# ─── Validation Tests ───────────────────────────────────────────────────────

class TestValidatePageCount(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(_validate_pages_count("340")[0])

    def test_zero(self):
        self.assertTrue(_validate_pages_count("0")[0])

    def test_negative(self):
        self.assertFalse(_validate_pages_count("-5")[0])

    def test_non_numeric(self):
        self.assertFalse(_validate_pages_count("abc")[0])


class TestValidateCsvContent(unittest.TestCase):
    def test_valid_csv(self):
        self.assertTrue(_validate_csv_content(CSV_EN_COMMA)[0])

    def test_valid_tab_csv(self):
        self.assertTrue(_validate_csv_content(CSV_IT_TAB)[0])

    def test_single_line_rejected(self):
        self.assertFalse(_validate_csv_content("just headers")[0])

    def test_no_delimiter_rejected(self):
        self.assertFalse(_validate_csv_content("no delimiter\nrow data")[0])


# ─── Delimiter Detection ───────────────────────────────────────────────────

class TestDetectDelimiter(unittest.TestCase):
    def test_tab(self):
        self.assertEqual(_detect_delimiter("col1\tcol2\tcol3"), "\t")

    def test_comma(self):
        self.assertEqual(_detect_delimiter("col1,col2,col3"), ",")

    def test_no_tab_defaults_comma(self):
        self.assertEqual(_detect_delimiter("col1 col2"), ",")


# ─── Header Normalization (NFR15) ──────────────────────────────────────────

class TestNormalizeHeaders(unittest.TestCase):
    def test_english_headers(self):
        m = _normalize_headers(["Top queries", "Clicks", "Impressions", "CTR", "Position"])
        vals = set(m.values())
        self.assertIn("query", vals)
        self.assertIn("clicks", vals)
        self.assertIn("impressions", vals)
        self.assertIn("position", vals)

    def test_italian_headers(self):
        m = _normalize_headers(["Query principali", "Clic", "Impressioni", "CTR", "Posizione"])
        vals = set(m.values())
        self.assertIn("query", vals)
        self.assertIn("clicks", vals)

    def test_german_headers(self):
        m = _normalize_headers(["Top-Suchanfragen", "Klicks", "Impressionen", "CTR", "Position"])
        vals = set(m.values())
        self.assertIn("query", vals)
        self.assertIn("clicks", vals)

    def test_page_headers(self):
        m = _normalize_headers(["Top pages", "Clicks", "Impressions", "CTR", "Position"])
        vals = set(m.values())
        self.assertIn("page", vals)


# ─── Numeric Parsing ───────────────────────────────────────────────────────

class TestParseNumeric(unittest.TestCase):
    def test_integer(self):
        self.assertEqual(_parse_numeric("500"), 500.0)

    def test_float(self):
        self.assertEqual(_parse_numeric("3.2"), 3.2)

    def test_comma_decimal(self):
        self.assertEqual(_parse_numeric("3,2"), 3.2)

    def test_percentage(self):
        self.assertEqual(_parse_numeric("5%"), 5.0)

    def test_thousands_separator(self):
        self.assertEqual(_parse_numeric("1.000,5"), 1000.5)

    def test_empty(self):
        self.assertEqual(_parse_numeric(""), 0.0)

    def test_dash(self):
        self.assertEqual(_parse_numeric("--"), 0.0)

    def test_non_breaking_space(self):
        self.assertEqual(_parse_numeric("1\xa0000"), 1000.0)


# ─── CSV Parsing ───────────────────────────────────────────────────────────

class TestParseGscCsv(unittest.TestCase):
    def test_english_comma_csv(self):
        rows = parse_gsc_csv(CSV_EN_COMMA)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["query"], "shoes")
        self.assertEqual(rows[0]["clicks"], 500.0)

    def test_italian_tab_csv(self):
        rows = parse_gsc_csv(CSV_IT_TAB)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["clicks"], 500.0)
        self.assertAlmostEqual(rows[0]["position"], 3.2, places=1)

    def test_pages_csv(self):
        rows = parse_gsc_csv(CSV_PAGES_EN)
        self.assertEqual(len(rows), 3)
        self.assertIn("page", rows[0])

    def test_empty_csv(self):
        rows = parse_gsc_csv("")
        self.assertEqual(rows, [])

    def test_header_only(self):
        rows = parse_gsc_csv("query,clicks\n")
        self.assertEqual(rows, [])

    def test_performance_nfr2(self):
        """NFR2: <3 seconds for up to 50,000 rows."""
        # Generate large CSV
        lines = ["Top queries,Clicks,Impressions,CTR,Position"]
        for i in range(50000):
            lines.append(f"query_{i},{i},{i*10},{i/100}%,{i/1000}")
        content = "\n".join(lines)

        start = time.time()
        rows = parse_gsc_csv(content)
        elapsed = time.time() - start

        self.assertEqual(len(rows), 50000)
        self.assertLess(elapsed, 3.0)


# ─── Trend Analysis (FR37, FR38) ──────────────────────────────────────────

class TestAnalyzeTrends(unittest.TestCase):
    def test_empty_rows(self):
        result = analyze_trends([])
        self.assertEqual(result["top_pages"], [])
        self.assertEqual(result["opportunities"], [])

    def test_top_pages_sorted(self):
        rows = [
            {"query": "a", "clicks": 100, "impressions": 1000, "ctr": 10, "position": 2},
            {"query": "b", "clicks": 500, "impressions": 5000, "ctr": 10, "position": 1},
            {"query": "c", "clicks": 200, "impressions": 2000, "ctr": 10, "position": 3},
        ]
        result = analyze_trends(rows)
        self.assertEqual(result["top_pages"][0]["clicks"], 500)

    def test_high_impressions_low_ctr_opportunity(self):
        rows = [
            {"query": "opportunity", "clicks": 5, "impressions": 5000,
             "ctr": 0.1, "position": 8},
        ]
        result = analyze_trends(rows)
        hi_lo = [o for o in result["opportunities"] if o["type"] == "high_impressions_low_ctr"]
        self.assertTrue(len(hi_lo) > 0)

    def test_striking_distance_opportunity(self):
        rows = [
            {"query": "near page 1", "clicks": 30, "impressions": 200,
             "ctr": 15, "position": 11},
        ]
        result = analyze_trends(rows)
        sd = [o for o in result["opportunities"] if o["type"] == "striking_distance"]
        self.assertTrue(len(sd) > 0)

    def test_no_opportunity_for_low_impressions(self):
        rows = [
            {"query": "low vol", "clicks": 1, "impressions": 10,
             "ctr": 10, "position": 8},
        ]
        result = analyze_trends(rows)
        self.assertEqual(len(result["opportunities"]), 0)

    def test_opportunities_capped_at_20(self):
        rows = [{"query": f"q{i}", "clicks": 1, "impressions": 5000,
                 "ctr": 0.02, "position": 10} for i in range(30)]
        result = analyze_trends(rows)
        self.assertLessEqual(len(result["opportunities"]), 20)


# ─── Full Wizard Integration Tests ─────────────────────────────────────────

MOCK_ROBOTS = {
    "raw_content": "User-agent: *\nDisallow: /admin\nSitemap: https://example.com/sitemap.xml",
    "sitemap_urls": ["https://example.com/sitemap.xml"],
    "disallow_rules": [{"user_agent": "*", "path": "/admin"}],
    "user_agents": ["*"],
    "fetch_error": None,
}


class TestRunWizardGsc(unittest.TestCase):

    @patch('deep.wizard_gsc._ask_evidence_screenshots', return_value=[])
    @patch('deep.wizard_gsc._ask_operator_notes', return_value="")
    @patch('deep.wizard_gsc._ask_multiline', return_value="")
    @patch('deep.wizard_gsc.fetch_robots_txt', return_value=MOCK_ROBOTS)
    @patch('deep.wizard_gsc._ask_folder_path')
    @patch('builtins.input')
    def test_happy_path_with_csvs(self, mock_input, mock_folder, mock_robots, mock_ml, mock_notes, mock_ev):
        mock_input.side_effect = [
            "1",    # sitemap: OK
            "340",  # pages indexed
            "412",  # pages submitted
            "1,3",  # indexing issues: Crawled not indexed, Noindex
            "",     # robots sitemap confirm (auto)
            "https://example.com/sitemap.xml",  # gsc sitemap urls
            "1",    # gsc sitemap status: Operazione riuscita
            "",     # gsc last read
            "",     # csv_date_range (ADR-7: no date column in test CSV)
        ]
        mock_folder.side_effect = [
            ("/tmp/perf", {"Query.csv": CSV_EN_COMMA, "Pages.csv": CSV_PAGES_EN}),
            (None, {}),  # coverage folder skipped
        ]

        result = run_wizard_gsc(BPROF, EMPTY_DISC)

        self.assertIsInstance(result, dict)
        self.assertEqual(result["sitemap_status"], "ok")
        self.assertEqual(result["gsc_pages_indexed"], 340)
        self.assertEqual(result["gsc_pages_total_in_property"], 412)
        self.assertIsInstance(result["indexing_issues"], list)
        self.assertIn("trend_analysis", result)
        self.assertIn("opportunities", result)
        self.assertIn("robots_txt", result)
        self.assertIn("sitemap_cross_check", result)

    @patch('deep.wizard_gsc._ask_evidence_screenshots', return_value=[])
    @patch('deep.wizard_gsc._ask_operator_notes', return_value="")
    @patch('deep.wizard_gsc._ask_multiline', return_value="")
    @patch('deep.wizard_gsc.fetch_robots_txt', return_value=MOCK_ROBOTS)
    @patch('deep.wizard_gsc._ask_folder_path')
    @patch('builtins.input')
    def test_skip_csvs(self, mock_input, mock_folder, mock_robots, mock_ml, mock_notes, mock_ev):
        mock_input.side_effect = [
            "1", "100", "100", "1",  # sitemap, indexed, submitted, issues
            "", "", "1", "",         # robots confirm, gsc sitemaps, status, last read
        ]
        mock_folder.side_effect = [(None, {}), (None, {})]

        result = run_wizard_gsc(BPROF, EMPTY_DISC)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("csv_performance"), {})
        self.assertEqual(result.get("csv_pages"), {})

    @patch('deep.wizard_gsc._ask_evidence_screenshots', return_value=[])
    @patch('deep.wizard_gsc._ask_operator_notes', return_value="")
    @patch('deep.wizard_gsc._ask_multiline', return_value="")
    @patch('deep.wizard_gsc.fetch_robots_txt', return_value=MOCK_ROBOTS)
    @patch('deep.wizard_gsc._ask_folder_path')
    @patch('builtins.input')
    def test_sitemap_errors(self, mock_input, mock_folder, mock_robots, mock_ml, mock_notes, mock_ev):
        mock_input.side_effect = [
            "2", "50", "100", "1",   # sitemap=Errori
            "", "", "1", "",         # robots, gsc sitemaps, status, last read
        ]
        mock_folder.side_effect = [(None, {}), (None, {})]

        result = run_wizard_gsc(BPROF, EMPTY_DISC)
        self.assertEqual(result["sitemap_status"], "errors")

    @patch('deep.wizard_gsc._ask_evidence_screenshots', return_value=[])
    @patch('deep.wizard_gsc._ask_operator_notes', return_value="")
    @patch('deep.wizard_gsc._ask_multiline', return_value="")
    @patch('deep.wizard_gsc.fetch_robots_txt', return_value=MOCK_ROBOTS)
    @patch('deep.wizard_gsc._ask_folder_path')
    @patch('builtins.input')
    def test_only_performance_csv(self, mock_input, mock_folder, mock_robots, mock_ml, mock_notes, mock_ev):
        mock_input.side_effect = [
            "1", "200", "250", "1",  # sitemap, indexed, submitted, issues
            "", "", "1", "",         # robots, gsc sitemaps, status, last read
            "",                      # csv_date_range (ADR-7: no date column)
        ]
        mock_folder.side_effect = [
            ("/tmp/perf", {"Query.csv": CSV_EN_COMMA}),
            (None, {}),
        ]

        result = run_wizard_gsc(BPROF, EMPTY_DISC)
        self.assertGreater(result["csv_performance"]["total_rows"], 0)
        self.assertEqual(result.get("csv_pages"), {})

    @patch('deep.wizard_gsc._ask_evidence_screenshots', return_value=[])
    @patch('deep.wizard_gsc._ask_operator_notes', return_value="")
    @patch('deep.wizard_gsc._ask_multiline', return_value="")
    @patch('deep.wizard_gsc.fetch_robots_txt', return_value=MOCK_ROBOTS)
    @patch('deep.wizard_gsc._ask_folder_path')
    @patch('builtins.input')
    def test_sitemap_mismatch_critical(self, mock_input, mock_folder, mock_robots, mock_ml, mock_notes, mock_ev):
        mock_input.side_effect = [
            "1", "100", "100", "1",
            "",                                         # confirm robots sitemap
            "https://example.com/other-sitemap.xml",    # different GSC sitemap
            "2",                                        # status: Impossibile recuperare
            "",                                         # last read
        ]
        mock_folder.side_effect = [(None, {}), (None, {})]

        result = run_wizard_gsc(BPROF, EMPTY_DISC)
        self.assertTrue(result["sitemap_cross_check"]["is_critical"])


if __name__ == '__main__':
    unittest.main()
