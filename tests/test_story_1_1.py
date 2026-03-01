"""Tests for Story 1.1: --mode flag and deep/ package skeleton."""

import os
import sys
import json
import signal
import unittest
from unittest.mock import patch, MagicMock

# Setup paths
TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_DIR = os.path.join(TOOL_DIR, 'cli')
sys.path.insert(0, CLI_DIR)


class TestModeFlag(unittest.TestCase):
    """Test --mode argparse flag (FR1, FR61, FR62)."""

    def test_deep_package_exists(self):
        """deep/ package directory exists with __init__.py."""
        deep_dir = os.path.join(CLI_DIR, 'deep')
        self.assertTrue(os.path.isdir(deep_dir))
        self.assertTrue(os.path.isfile(os.path.join(deep_dir, '__init__.py')))

    def test_deep_package_importable(self):
        """deep package can be imported."""
        import deep
        self.assertTrue(hasattr(deep, 'run_deep_mode'))

    def test_step_zero_importable(self):
        """step_zero module can be imported."""
        from deep.step_zero import run_step_zero
        self.assertTrue(callable(run_step_zero))

    def test_input_helpers_importable(self):
        """input_helpers module can be imported."""
        from deep.input_helpers import _ask_input, _ask_select, _ask_file_path
        self.assertTrue(callable(_ask_input))
        self.assertTrue(callable(_ask_select))
        self.assertTrue(callable(_ask_file_path))


class TestDeepOrchestrator(unittest.TestCase):
    """Test deep/__init__.py orchestrator."""

    def test_wizard_sequence_defined(self):
        """WIZARD_SEQUENCE contains all 5 platform wizards."""
        from deep import WIZARD_SEQUENCE
        platforms = [p for p, _, _ in WIZARD_SEQUENCE]
        self.assertEqual(platforms, ["iubenda", "gtm", "gads", "meta", "gsc"])

    def test_state_file_path(self):
        """STATE_FILE points to output/.deep_state_tmp.json."""
        from deep import STATE_FILE
        self.assertTrue(STATE_FILE.endswith('.deep_state_tmp.json'))
        self.assertIn('output', STATE_FILE)

    def test_save_and_delete_state(self):
        """save_state writes JSON, delete_state removes it."""
        from deep import save_state, delete_state, STATE_FILE
        test_data = {"test": True, "wizards_completed": []}
        save_state(test_data)
        self.assertTrue(os.path.exists(STATE_FILE))
        with open(STATE_FILE, encoding='utf-8') as f:
            loaded = json.load(f)
        self.assertEqual(loaded["test"], True)
        delete_state()
        self.assertFalse(os.path.exists(STATE_FILE))

    def test_signal_handler_registered(self):
        """run_deep_mode registers SIGINT handler."""
        from deep import run_deep_mode
        original = signal.getsignal(signal.SIGINT)

        # Mock step_zero to avoid interactive input
        with patch('deep.step_zero.run_step_zero', side_effect=KeyboardInterrupt):
            try:
                args = MagicMock()
                run_deep_mode("https://test.com", args)
            except (SystemExit, KeyboardInterrupt):
                pass

        # After run_deep_mode, original handler should be restored
        restored = signal.getsignal(signal.SIGINT)
        self.assertEqual(restored, original)


class TestInputHelpers(unittest.TestCase):
    """Test deep/input_helpers.py shared functions."""

    def test_ask_input_basic(self):
        """_ask_input returns user input."""
        from deep.input_helpers import _ask_input
        with patch('builtins.input', return_value='42'):
            result = _ask_input("Test")
        self.assertEqual(result, '42')

    def test_ask_input_validation_rejects_then_accepts(self):
        """_ask_input re-prompts on validation failure."""
        from deep.input_helpers import _ask_input
        def validate(val):
            try:
                v = float(val)
                if 0 <= v <= 100:
                    return True, ""
                return False, "Deve essere tra 0 e 100"
            except ValueError:
                return False, "Non è un numero"

        with patch('builtins.input', side_effect=['abc', '150', '42']):
            result = _ask_input("Percentuale", validation_fn=validate)
        self.assertEqual(result, '42')

    def test_ask_select_single(self):
        """_ask_select returns single selection."""
        from deep.input_helpers import _ask_select
        with patch('builtins.input', return_value='2'):
            result = _ask_select("Pick one", ["A", "B", "C"])
        self.assertEqual(result, "B")

    def test_ask_select_multiple(self):
        """_ask_select with allow_multiple returns list."""
        from deep.input_helpers import _ask_select
        with patch('builtins.input', return_value='1,3'):
            result = _ask_select("Pick", ["A", "B", "C"], allow_multiple=True)
        self.assertEqual(result, ["A", "C"])

    def test_ask_select_invalid_then_valid(self):
        """_ask_select re-prompts on invalid input."""
        from deep.input_helpers import _ask_select
        with patch('builtins.input', side_effect=['x', '5', '1']):
            result = _ask_select("Pick", ["A", "B"])
        self.assertEqual(result, "A")


class TestStepZero(unittest.TestCase):
    """Test deep/step_zero.py."""

    def test_run_step_zero_returns_profile(self):
        """run_step_zero returns business_profile dict."""
        from deep.step_zero import run_step_zero
        # Simulate: select Ecommerce (1), then platforms 1,2,3,4,5, confirm
        with patch('builtins.input', side_effect=['1', '1,2,3,4,5', 's']):
            profile = run_step_zero("https://test.com")

        self.assertEqual(profile["business_type"], "ecommerce")
        self.assertEqual(profile["platforms"], ["iubenda", "gtm", "gads", "meta", "gsc"])
        self.assertEqual(profile["url"], "https://test.com")

    def test_run_step_zero_lead_gen_partial(self):
        """run_step_zero with lead gen and partial platforms."""
        from deep.step_zero import run_step_zero
        with patch('builtins.input', side_effect=['2', '2,3', 's']):
            profile = run_step_zero("https://test.com")

        self.assertEqual(profile["business_type"], "lead_gen")
        self.assertEqual(profile["platforms"], ["gtm", "gads"])


if __name__ == '__main__':
    unittest.main()
