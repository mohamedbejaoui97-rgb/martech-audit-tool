"""Tests for Story 1.2: Step Zero — Business profiling and platform selection."""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock, call

# Setup paths
TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_DIR = os.path.join(TOOL_DIR, 'cli')
sys.path.insert(0, CLI_DIR)

from deep.step_zero import run_step_zero, BUSINESS_TYPES, PLATFORMS, PLATFORM_KEYS, PLATFORM_DESCRIPTIONS
from deep import save_state, delete_state, STATE_FILE, WIZARD_SEQUENCE


class TestBusinessTypeSelection(unittest.TestCase):
    """AC: operator is asked to select business type via numbered selection."""

    def test_ecommerce_selection(self):
        """Given deep mode → select Ecommerce → business_type = 'ecommerce'."""
        with patch('builtins.input', side_effect=['1', '1,2,3,4,5', 's']):
            profile = run_step_zero("https://test.com")
        self.assertEqual(profile["business_type"], "ecommerce")

    def test_lead_gen_selection(self):
        """Given deep mode → select Lead Generation → business_type = 'lead_gen'."""
        with patch('builtins.input', side_effect=['2', '1', 's']):
            profile = run_step_zero("https://test.com")
        self.assertEqual(profile["business_type"], "lead_gen")

    def test_both_selection(self):
        """Given deep mode → select Entrambi → business_type = 'both'."""
        with patch('builtins.input', side_effect=['3', '1,2', 's']):
            profile = run_step_zero("https://test.com")
        self.assertEqual(profile["business_type"], "both")


class TestPlatformSelection(unittest.TestCase):
    """AC: operator can select platforms via comma-separated numbers."""

    def test_all_platforms(self):
        """Select all 5 platforms → all keys in profile."""
        with patch('builtins.input', side_effect=['1', '1,2,3,4,5', 's']):
            profile = run_step_zero("https://test.com")
        self.assertEqual(profile["platforms"], ["iubenda", "gtm", "gads", "meta", "gsc"])

    def test_single_platform(self):
        """Select only GTM → only 'gtm' in platforms."""
        with patch('builtins.input', side_effect=['1', '2', 's']):
            profile = run_step_zero("https://test.com")
        self.assertEqual(profile["platforms"], ["gtm"])

    def test_partial_platforms(self):
        """Select GTM + Google Ads → ['gtm', 'gads']."""
        with patch('builtins.input', side_effect=['2', '2,3', 's']):
            profile = run_step_zero("https://test.com")
        self.assertEqual(profile["platforms"], ["gtm", "gads"])

    def test_at_least_one_platform_required(self):
        """Empty platform selection → re-prompt, then accept valid selection."""
        # First: empty input triggers re-prompt in _ask_select
        # Then valid input accepted
        with patch('builtins.input', side_effect=['1', '', '1', 's']):
            profile = run_step_zero("https://test.com")
        self.assertEqual(profile["platforms"], ["iubenda"])
        self.assertTrue(len(profile["platforms"]) >= 1)


class TestConfirmation(unittest.TestCase):
    """AC: operator confirms selections before proceeding."""

    def test_confirm_proceeds(self):
        """Confirm 's' → returns profile."""
        with patch('builtins.input', side_effect=['1', '1,2', 's']):
            profile = run_step_zero("https://test.com")
        self.assertIn("business_type", profile)
        self.assertIn("platforms", profile)

    def test_reject_restarts(self):
        """Confirm 'n' → restart, then 's' → returns profile."""
        with patch('builtins.input', side_effect=[
            '1', '1', 'n',      # first round: ecommerce, iubenda, reject
            '2', '2,3', 's',    # second round: lead gen, gtm+gads, confirm
        ]):
            profile = run_step_zero("https://test.com")
        # Should have the second round's values
        self.assertEqual(profile["business_type"], "lead_gen")
        self.assertEqual(profile["platforms"], ["gtm", "gads"])


class TestBusinessProfile(unittest.TestCase):
    """AC: business_profile dict with business_type, platforms, url."""

    def test_profile_structure(self):
        """Profile contains all required keys."""
        with patch('builtins.input', side_effect=['1', '1,2,3', 's']):
            profile = run_step_zero("https://clienteabc.it")
        self.assertIn("business_type", profile)
        self.assertIn("platforms", profile)
        self.assertIn("url", profile)
        self.assertEqual(profile["url"], "https://clienteabc.it")

    def test_profile_values_types(self):
        """Profile values have correct types."""
        with patch('builtins.input', side_effect=['1', '1,2', 's']):
            profile = run_step_zero("https://test.com")
        self.assertIsInstance(profile["business_type"], str)
        self.assertIsInstance(profile["platforms"], list)
        self.assertIsInstance(profile["url"], str)
        self.assertIn(profile["business_type"], ["ecommerce", "lead_gen", "both"])


class TestStateFileUpdate(unittest.TestCase):
    """AC: state file is updated with Step Zero data."""

    def test_state_file_after_step_zero(self):
        """Orchestrator saves state after step_zero completes."""
        with patch('builtins.input', side_effect=['1', '1,2,3,4,5', 's']):
            profile = run_step_zero("https://test.com")

        # Simulate orchestrator saving state (as done in __init__.py)
        collected_data = {"business_profile": profile, "wizards_completed": []}
        save_state(collected_data)

        self.assertTrue(os.path.exists(STATE_FILE))
        with open(STATE_FILE, encoding='utf-8') as f:
            state = json.load(f)
        self.assertEqual(state["business_profile"]["business_type"], "ecommerce")
        self.assertEqual(state["business_profile"]["platforms"], ["iubenda", "gtm", "gads", "meta", "gsc"])

        # Cleanup
        delete_state()


class TestProgressiveDisclosure(unittest.TestCase):
    """AC: orchestrator proceeds to run only the wizards for selected platforms (FR4)."""

    def test_only_selected_wizards_run(self):
        """Only wizards for selected platforms are in the execution list."""
        with patch('builtins.input', side_effect=['2', '2,3', 's']):
            profile = run_step_zero("https://test.com")

        selected = profile["platforms"]  # ['gtm', 'gads']
        wizards_to_run = [
            (p, m, f) for p, m, f in WIZARD_SEQUENCE
            if p in selected
        ]
        self.assertEqual(len(wizards_to_run), 2)
        self.assertEqual(wizards_to_run[0][0], "gtm")
        self.assertEqual(wizards_to_run[1][0], "gads")

    def test_skipped_wizards_not_run(self):
        """Wizards for unselected platforms are excluded."""
        with patch('builtins.input', side_effect=['1', '1,4', 's']):
            profile = run_step_zero("https://test.com")

        selected = profile["platforms"]  # ['iubenda', 'meta']
        skipped = [p for p, _, _ in WIZARD_SEQUENCE if p not in selected]
        self.assertIn("gtm", skipped)
        self.assertIn("gads", skipped)
        self.assertIn("gsc", skipped)
        self.assertNotIn("iubenda", skipped)
        self.assertNotIn("meta", skipped)


class TestConstants(unittest.TestCase):
    """Verify constants align with architecture spec."""

    def test_business_types_count(self):
        self.assertEqual(len(BUSINESS_TYPES), 3)

    def test_platforms_count(self):
        self.assertEqual(len(PLATFORMS), 5)
        self.assertEqual(len(PLATFORM_KEYS), 5)

    def test_platform_descriptions_complete(self):
        """Every platform key has a description."""
        for key in PLATFORM_KEYS:
            self.assertIn(key, PLATFORM_DESCRIPTIONS)

    def test_platform_keys_match_wizard_sequence(self):
        """PLATFORM_KEYS align with WIZARD_SEQUENCE platforms."""
        wizard_platforms = [p for p, _, _ in WIZARD_SEQUENCE]
        self.assertEqual(PLATFORM_KEYS, wizard_platforms)


if __name__ == '__main__':
    unittest.main()
