"""Tests for Story 2.1: Build _ask_input() with validation, warnings, and contextual help."""

import os
import sys
import unittest
from unittest.mock import patch, call
from io import StringIO

# Setup paths
TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_DIR = os.path.join(TOOL_DIR, 'cli')
sys.path.insert(0, CLI_DIR)

from deep.input_helpers import _ask_input


# ─── Reusable validators/warnings matching real wizard usage ────────────────

def validate_percentage(raw):
    """Validate rejection rate: 0-100 (FR40)."""
    try:
        val = float(raw)
        if 0 <= val <= 100:
            return True, ""
        return False, "Il valore deve essere tra 0 e 100"
    except ValueError:
        return False, "Inserisci un numero valido"


def validate_emq(raw):
    """Validate EMQ Score: 0-10 (FR40)."""
    try:
        val = float(raw)
        if 0 <= val <= 10:
            return True, ""
        return False, "EMQ è un valore da 0 a 10. Verifica in Events Manager > Dataset > Panoramica."
    except ValueError:
        return False, "Inserisci un numero valido (0-10)"


def warn_low_rejection(raw):
    """Warn if rejection rate < 10% — suspicious (FR41)."""
    try:
        val = float(raw)
        if val < 10:
            return f"Un tasso di rifiuto del {val:.0f}% è insolito — potrebbe indicare che il banner non blocca i cookie."
        return None
    except ValueError:
        return None


# ─── AC1: validation_fn fails → ⚠ {error} + re-prompt (FR43) ──────────────

class TestValidation(unittest.TestCase):
    """AC: Given _ask_input with validation_fn, When value fails, Then error shown and re-prompted."""

    def test_invalid_then_valid(self):
        """Non-numeric then valid → returns valid value."""
        with patch('builtins.input', side_effect=['abc', '42']):
            result = _ask_input("Tasso di rifiuto (%)", validation_fn=validate_percentage)
        self.assertEqual(result, '42')

    def test_out_of_range_then_valid(self):
        """Out of range then in range → returns valid value."""
        with patch('builtins.input', side_effect=['150', '-5', '75']):
            result = _ask_input("Tasso di rifiuto (%)", validation_fn=validate_percentage)
        self.assertEqual(result, '75')

    def test_emq_out_of_range(self):
        """EMQ 85 (wrong) then 6 (correct) → returns '6'."""
        with patch('builtins.input', side_effect=['85', '6']):
            result = _ask_input("EMQ Score", validation_fn=validate_emq)
        self.assertEqual(result, '6')

    def test_error_message_format(self):
        """Error message uses ⚠ prefix format."""
        with patch('builtins.input', side_effect=['abc', '50']):
            with patch('sys.stdout', new_callable=StringIO) as mock_out:
                _ask_input("Test", validation_fn=validate_percentage)
                output = mock_out.getvalue()
        self.assertIn("⚠", output)
        self.assertIn("Inserisci un numero valido", output)

    def test_multiple_failures_before_success(self):
        """5 failures then success → still returns correctly."""
        with patch('builtins.input', side_effect=['a', 'b', 'c', '-1', '999', '42']):
            result = _ask_input("Valore", validation_fn=validate_percentage)
        self.assertEqual(result, '42')

    def test_no_validation_fn_accepts_anything(self):
        """Without validation_fn, any non-empty input accepted."""
        with patch('builtins.input', return_value='qualsiasi cosa'):
            result = _ask_input("Test")
        self.assertEqual(result, 'qualsiasi cosa')


# ─── AC2: warning_fn suspicious value → warning + confirm s/n (FR41) ───────

class TestWarnings(unittest.TestCase):
    """AC: Given _ask_input with warning_fn, When suspicious value, Then warning + confirm."""

    def test_warning_confirmed(self):
        """Suspicious value + confirm 's' → accepts value."""
        with patch('builtins.input', side_effect=['5', 's']):
            result = _ask_input("Tasso di rifiuto (%)",
                                validation_fn=validate_percentage,
                                warning_fn=warn_low_rejection)
        self.assertEqual(result, '5')

    def test_warning_rejected_then_new_value(self):
        """Suspicious value + reject 'n' → re-prompt → new value accepted."""
        with patch('builtins.input', side_effect=['5', 'n', '42']):
            result = _ask_input("Tasso di rifiuto (%)",
                                validation_fn=validate_percentage,
                                warning_fn=warn_low_rejection)
        self.assertEqual(result, '42')

    def test_warning_message_format(self):
        """Warning uses '⚠ Attenzione:' prefix."""
        with patch('builtins.input', side_effect=['3', 's']):
            with patch('sys.stdout', new_callable=StringIO) as mock_out:
                _ask_input("Test", validation_fn=validate_percentage,
                           warning_fn=warn_low_rejection)
                output = mock_out.getvalue()
        self.assertIn("⚠ Attenzione:", output)
        self.assertIn("insolito", output)

    def test_confirm_prompt_format(self):
        """Confirm prompt says 'Confermi questo valore? (s/n)'."""
        calls = []
        def fake_input(prompt):
            calls.append(prompt)
            if len(calls) == 1:
                return '5'  # suspicious value
            return 's'  # confirm

        with patch('builtins.input', side_effect=fake_input):
            _ask_input("Test", validation_fn=validate_percentage,
                       warning_fn=warn_low_rejection)

        confirm_prompts = [c for c in calls if 'Confermi' in c]
        self.assertEqual(len(confirm_prompts), 1)
        self.assertIn("s/n", confirm_prompts[0])

    def test_no_warning_for_normal_value(self):
        """Normal value (42%) → no warning triggered."""
        with patch('builtins.input', return_value='42') as mock_in:
            result = _ask_input("Test", validation_fn=validate_percentage,
                                warning_fn=warn_low_rejection)
        # Should only be called once (the value input, no confirm prompt)
        mock_in.assert_called_once()
        self.assertEqual(result, '42')

    def test_validation_runs_before_warning(self):
        """Invalid value → validation error (no warning). Then suspicious → warning."""
        with patch('builtins.input', side_effect=['abc', '5', 's']):
            with patch('sys.stdout', new_callable=StringIO) as mock_out:
                result = _ask_input("Test", validation_fn=validate_percentage,
                                    warning_fn=warn_low_rejection)
                output = mock_out.getvalue()
        # First error should be validation, not warning
        lines = output.strip().split('\n')
        first_error = [l for l in lines if '⚠' in l][0]
        self.assertIn("numero valido", first_error)
        self.assertEqual(result, '5')


# ─── AC3: help_text → ℹ {help_text} above prompt (FR42) ───────────────────

class TestHelpText(unittest.TestCase):
    """AC: Given _ask_input with help_text, When prompt displayed, Then ℹ {help_text} shown."""

    def test_help_text_displayed(self):
        """Help text shown with ℹ prefix."""
        help_msg = "Vai su Dashboard > Cookie Solution > Statistiche"
        with patch('builtins.input', return_value='42'):
            with patch('sys.stdout', new_callable=StringIO) as mock_out:
                _ask_input("Tasso di rifiuto (%)", help_text=help_msg)
                output = mock_out.getvalue()
        self.assertIn("ℹ", output)
        self.assertIn(help_msg, output)

    def test_help_text_shown_only_once(self):
        """Help text shown on first prompt only, not on re-prompt after error."""
        help_msg = "Istruzione contestuale"
        with patch('builtins.input', side_effect=['abc', '42']):
            with patch('sys.stdout', new_callable=StringIO) as mock_out:
                _ask_input("Test", validation_fn=validate_percentage,
                           help_text=help_msg)
                output = mock_out.getvalue()
        # Count occurrences of help text
        count = output.count(help_msg)
        self.assertEqual(count, 1, f"Help text should appear once, appeared {count} times")

    def test_no_help_text_when_none(self):
        """No help_text → no ℹ line printed."""
        with patch('builtins.input', return_value='42'):
            with patch('sys.stdout', new_callable=StringIO) as mock_out:
                _ask_input("Test")
                output = mock_out.getvalue()
        self.assertNotIn("ℹ", output)


# ─── Empty input handling ──────────────────────────────────────────────────

class TestEmptyInput(unittest.TestCase):
    """Empty input re-prompts with error message."""

    def test_empty_then_valid(self):
        """Empty input → re-prompt → valid input accepted."""
        with patch('builtins.input', side_effect=['', '  ', '42']):
            result = _ask_input("Test")
        self.assertEqual(result, '42')

    def test_empty_error_message(self):
        """Empty input shows appropriate error."""
        with patch('builtins.input', side_effect=['', '42']):
            with patch('sys.stdout', new_callable=StringIO) as mock_out:
                _ask_input("Test")
                output = mock_out.getvalue()
        self.assertIn("⚠", output)
        self.assertIn("Input richiesto", output)

    def test_allow_empty(self):
        """allow_empty=True accepts empty string."""
        with patch('builtins.input', return_value=''):
            result = _ask_input("Test (opzionale)", allow_empty=True)
        self.assertEqual(result, '')


# ─── Type coercion ─────────────────────────────────────────────────────────

class TestCoercion(unittest.TestCase):
    """coerce_fn converts validated input to target type."""

    def test_float_coercion(self):
        """coerce_fn=float returns float value."""
        with patch('builtins.input', return_value='42.5'):
            result = _ask_input("Percentuale", validation_fn=validate_percentage,
                                coerce_fn=float)
        self.assertIsInstance(result, float)
        self.assertEqual(result, 42.5)

    def test_int_coercion(self):
        """coerce_fn=int returns int value."""
        with patch('builtins.input', return_value='7'):
            result = _ask_input("EMQ", validation_fn=validate_emq,
                                coerce_fn=int)
        self.assertIsInstance(result, int)
        self.assertEqual(result, 7)

    def test_coercion_failure_reprompts(self):
        """If coerce_fn raises, re-prompt (e.g. int('3.5') fails)."""
        with patch('builtins.input', side_effect=['3.5', '3']):
            result = _ask_input("Numero intero", coerce_fn=int)
        self.assertEqual(result, 3)


# ─── Combined flow: real wizard scenario ───────────────────────────────────

class TestRealWizardScenario(unittest.TestCase):
    """Integration: simulate Iubenda rejection rate input as in Journey 3 (Luca)."""

    def test_luca_scenario(self):
        """Luca enters invalid → error, then suspicious 5% → warning + confirm, accepts."""
        with patch('builtins.input', side_effect=['centocinquanta', '5', 's']):
            result = _ask_input(
                "Tasso di rifiuto cookie (%)",
                validation_fn=validate_percentage,
                warning_fn=warn_low_rejection,
                help_text="Vai su Dashboard > Cookie Solution > Statistiche",
                coerce_fn=float,
            )
        self.assertEqual(result, 5.0)

    def test_luca_rejects_suspicious_then_corrects(self):
        """Luca enters 5%, rejects warning, enters 42% → accepted."""
        with patch('builtins.input', side_effect=['5', 'n', '42']):
            result = _ask_input(
                "Tasso di rifiuto cookie (%)",
                validation_fn=validate_percentage,
                warning_fn=warn_low_rejection,
                coerce_fn=float,
            )
        self.assertEqual(result, 42.0)

    def test_full_flow_with_help_validation_warning(self):
        """All features combined: help shown once, validation, warning, coercion."""
        help_msg = "Controlla in Events Manager"
        with patch('builtins.input', side_effect=['abc', '85', '6']):
            with patch('sys.stdout', new_callable=StringIO) as mock_out:
                result = _ask_input(
                    "EMQ Score",
                    validation_fn=validate_emq,
                    help_text=help_msg,
                    coerce_fn=float,
                )
                output = mock_out.getvalue()

        self.assertEqual(result, 6.0)
        # Help text shown once
        self.assertEqual(output.count(help_msg), 1)
        # Two error messages (abc invalid, 85 out of range)
        error_lines = [l for l in output.split('\n') if '⚠' in l]
        self.assertEqual(len(error_lines), 2)


# ─── Italian text verification ─────────────────────────────────────────────

class TestItalianUX(unittest.TestCase):
    """AC: All user-facing text is in Italian."""

    def test_empty_input_message_italian(self):
        with patch('builtins.input', side_effect=['', 'ok']):
            with patch('sys.stdout', new_callable=StringIO) as mock_out:
                _ask_input("Test")
                output = mock_out.getvalue()
        self.assertIn("Input richiesto", output)

    def test_confirm_prompt_italian(self):
        calls = []
        def fake_input(prompt):
            calls.append(prompt)
            return '5' if len(calls) == 1 else 's'
        with patch('builtins.input', side_effect=fake_input):
            _ask_input("Test", warning_fn=lambda v: "sospetto" if v == '5' else None)
        self.assertTrue(any("Confermi questo valore" in c for c in calls))

    def test_prompt_arrow_prefix(self):
        """Prompt uses → prefix per architecture spec."""
        calls = []
        def fake_input(prompt):
            calls.append(prompt)
            return '42'
        with patch('builtins.input', side_effect=fake_input):
            _ask_input("Percentuale")
        self.assertTrue(calls[0].strip().startswith("→"))


if __name__ == '__main__':
    unittest.main()
