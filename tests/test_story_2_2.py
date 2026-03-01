"""Tests for Story 2.2: Build _ask_select() and _ask_file_path() helpers."""

import os
import sys
import json
import tempfile
import unittest
from unittest.mock import patch
from io import StringIO

TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_DIR = os.path.join(TOOL_DIR, 'cli')
sys.path.insert(0, CLI_DIR)

from deep.input_helpers import _ask_select, _ask_file_path


# ═══════════════════════════════════════════════════════════════════════════
#  _ask_select — SINGLE SELECTION
# ═══════════════════════════════════════════════════════════════════════════

class TestAskSelectSingle(unittest.TestCase):
    """AC: _ask_select(prompt, options) → user enters number → option returned."""

    def test_select_first(self):
        with patch('builtins.input', return_value='1'):
            result = _ask_select("Scegli", ["A", "B", "C"])
        self.assertEqual(result, "A")

    def test_select_last(self):
        with patch('builtins.input', return_value='3'):
            result = _ask_select("Scegli", ["A", "B", "C"])
        self.assertEqual(result, "C")

    def test_select_middle(self):
        with patch('builtins.input', return_value='2'):
            result = _ask_select("CM v2", ["Assente", "Basic", "Advanced"])
        self.assertEqual(result, "Basic")


class TestAskSelectSingleErrors(unittest.TestCase):
    """AC: invalid number (out of range or non-numeric) → error + re-prompt (FR40, FR43)."""

    def test_out_of_range_then_valid(self):
        """Number > len(options) → error, then valid."""
        with patch('builtins.input', side_effect=['5', '1']):
            result = _ask_select("Scegli", ["A", "B", "C"])
        self.assertEqual(result, "A")

    def test_zero_then_valid(self):
        """0 is out of range (1-indexed)."""
        with patch('builtins.input', side_effect=['0', '2']):
            result = _ask_select("Scegli", ["A", "B"])
        self.assertEqual(result, "B")

    def test_negative_then_valid(self):
        with patch('builtins.input', side_effect=['-1', '1']):
            result = _ask_select("Scegli", ["A", "B"])
        self.assertEqual(result, "A")

    def test_non_numeric_then_valid(self):
        with patch('builtins.input', side_effect=['abc', '1']):
            result = _ask_select("Scegli", ["A", "B"])
        self.assertEqual(result, "A")

    def test_empty_then_valid(self):
        with patch('builtins.input', side_effect=['', '1']):
            result = _ask_select("Scegli", ["A", "B"])
        self.assertEqual(result, "A")

    def test_error_message_format(self):
        """Error uses ⚠ prefix."""
        with patch('builtins.input', side_effect=['abc', '1']):
            with patch('sys.stdout', new_callable=StringIO) as out:
                _ask_select("Test", ["A", "B"])
        self.assertIn("⚠", out.getvalue())


# ═══════════════════════════════════════════════════════════════════════════
#  _ask_select — MULTIPLE SELECTION
# ═══════════════════════════════════════════════════════════════════════════

class TestAskSelectMultiple(unittest.TestCase):
    """AC: allow_multiple=True → comma-separated numbers → list returned."""

    def test_select_all(self):
        with patch('builtins.input', return_value='1,2,3'):
            result = _ask_select("Scegli", ["A", "B", "C"], allow_multiple=True)
        self.assertEqual(result, ["A", "B", "C"])

    def test_select_subset(self):
        with patch('builtins.input', return_value='1,3'):
            result = _ask_select("Scegli", ["A", "B", "C"], allow_multiple=True)
        self.assertEqual(result, ["A", "C"])

    def test_select_single_in_multi_mode(self):
        with patch('builtins.input', return_value='2'):
            result = _ask_select("Scegli", ["A", "B", "C"], allow_multiple=True)
        self.assertEqual(result, ["B"])

    def test_spaces_in_input(self):
        """Handles spaces around commas."""
        with patch('builtins.input', return_value='1 , 3 , 2'):
            result = _ask_select("Scegli", ["A", "B", "C"], allow_multiple=True)
        self.assertEqual(result, ["A", "C", "B"])

    def test_duplicates_deduplicated(self):
        """Duplicate selections are deduplicated."""
        with patch('builtins.input', return_value='1,1,2'):
            result = _ask_select("Scegli", ["A", "B", "C"], allow_multiple=True)
        self.assertEqual(result, ["A", "B"])

    def test_echo_selection(self):
        """Multi-select echoes selected items."""
        with patch('builtins.input', return_value='1,3'):
            with patch('sys.stdout', new_callable=StringIO) as out:
                _ask_select("Scegli", ["A", "B", "C"], allow_multiple=True)
        self.assertIn("✓ Selezionato:", out.getvalue())
        self.assertIn("A", out.getvalue())
        self.assertIn("C", out.getvalue())


class TestAskSelectMultipleErrors(unittest.TestCase):
    """AC: invalid in multi-select → error + re-prompt."""

    def test_empty_then_valid(self):
        with patch('builtins.input', side_effect=['', '1,2']):
            result = _ask_select("Scegli", ["A", "B", "C"], allow_multiple=True)
        self.assertEqual(result, ["A", "B"])

    def test_all_out_of_range_then_valid(self):
        """All indices out of range → re-prompt."""
        with patch('builtins.input', side_effect=['8,9', '1']):
            result = _ask_select("Scegli", ["A", "B"], allow_multiple=True)
        self.assertEqual(result, ["A"])

    def test_partial_invalid_warns_but_accepts_valid(self):
        """Mix of valid and invalid indices → warns about bad, accepts good."""
        with patch('builtins.input', return_value='1,99,2'):
            with patch('sys.stdout', new_callable=StringIO) as out:
                result = _ask_select("Scegli", ["A", "B", "C"], allow_multiple=True)
        self.assertEqual(result, ["A", "B"])
        self.assertIn("⚠", out.getvalue())
        self.assertIn("99", out.getvalue())

    def test_non_numeric_mixed_warns(self):
        """Non-numeric mixed with valid → warns about bad."""
        with patch('builtins.input', return_value='1,abc,2'):
            with patch('sys.stdout', new_callable=StringIO) as out:
                result = _ask_select("Scegli", ["A", "B", "C"], allow_multiple=True)
        self.assertEqual(result, ["A", "B"])
        self.assertIn("abc", out.getvalue())


# ═══════════════════════════════════════════════════════════════════════════
#  _ask_select — HELP TEXT
# ═══════════════════════════════════════════════════════════════════════════

class TestAskSelectHelpText(unittest.TestCase):
    """help_text shown on first prompt only."""

    def test_help_text_displayed(self):
        with patch('builtins.input', return_value='1'):
            with patch('sys.stdout', new_callable=StringIO) as out:
                _ask_select("Test", ["A"], help_text="Istruzione contestuale")
        self.assertIn("ℹ", out.getvalue())
        self.assertIn("Istruzione contestuale", out.getvalue())

    def test_help_text_shown_once(self):
        """Help text not repeated on re-prompt."""
        with patch('builtins.input', side_effect=['abc', '1']):
            with patch('sys.stdout', new_callable=StringIO) as out:
                _ask_select("Test", ["A", "B"], help_text="Aiuto")
        self.assertEqual(out.getvalue().count("Aiuto"), 1)


# ═══════════════════════════════════════════════════════════════════════════
#  _ask_file_path — FILE EXISTS & CONTENT RETURNED
# ═══════════════════════════════════════════════════════════════════════════

class TestAskFilePathBasic(unittest.TestCase):
    """AC: file path provided → check existence, read, return (path, content)."""

    def test_valid_file_returns_tuple(self):
        """Existing file → returns (path, content)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"containerVersion": {"tag": []}}')
            tmp_path = f.name
        try:
            with patch('builtins.input', return_value=tmp_path):
                path, content = _ask_file_path("Percorso file JSON GTM")
            self.assertEqual(path, tmp_path)
            self.assertIn("containerVersion", content)
        finally:
            os.unlink(tmp_path)

    def test_success_echo(self):
        """Loaded file shows ✓ confirmation."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            tmp_path = f.name
        try:
            with patch('builtins.input', return_value=tmp_path):
                with patch('sys.stdout', new_callable=StringIO) as out:
                    _ask_file_path("File")
            self.assertIn("✓ File caricato", out.getvalue())
        finally:
            os.unlink(tmp_path)

    def test_quoted_path_stripped(self):
        """Paths with surrounding quotes are handled."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('test')
            tmp_path = f.name
        try:
            with patch('builtins.input', return_value=f'"{tmp_path}"'):
                path, content = _ask_file_path("File")
            self.assertEqual(path, tmp_path)
            self.assertEqual(content, 'test')
        finally:
            os.unlink(tmp_path)


# ═══════════════════════════════════════════════════════════════════════════
#  _ask_file_path — VALIDATION (FR44)
# ═══════════════════════════════════════════════════════════════════════════

class TestAskFilePathValidation(unittest.TestCase):
    """AC: validation_fn checks file structure (FR44)."""

    def _gtm_validator(self, content):
        """Validate GTM JSON has containerVersion key."""
        try:
            data = json.loads(content)
            if "containerVersion" in data:
                return True, ""
            return False, "File JSON non contiene 'containerVersion'. Verifica che sia un export del container GTM."
        except json.JSONDecodeError:
            return False, "File non è un JSON valido."

    def test_valid_structure_passes(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"containerVersion": {"tag": []}}, f)
            tmp_path = f.name
        try:
            with patch('builtins.input', return_value=tmp_path):
                path, content = _ask_file_path("JSON GTM", validation_fn=self._gtm_validator)
            self.assertIsNotNone(path)
        finally:
            os.unlink(tmp_path)

    def test_invalid_structure_retry_then_skip(self):
        """Invalid structure → error → retry 'n' → returns (None, None)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"wrong_key": True}, f)
            tmp_path = f.name
        try:
            with patch('builtins.input', side_effect=[tmp_path, 'n']):
                with patch('sys.stdout', new_callable=StringIO) as out:
                    path, content = _ask_file_path("JSON GTM", validation_fn=self._gtm_validator)
            self.assertIsNone(path)
            self.assertIsNone(content)
            self.assertIn("containerVersion", out.getvalue())
        finally:
            os.unlink(tmp_path)

    def test_invalid_structure_retry_then_valid(self):
        """Invalid → retry 's' → provide valid file → success."""
        bad = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump({"wrong": True}, bad)
        bad.close()

        good = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump({"containerVersion": {"tag": []}}, good)
        good.close()

        try:
            with patch('builtins.input', side_effect=[bad.name, 's', good.name]):
                path, content = _ask_file_path("JSON GTM", validation_fn=self._gtm_validator)
            self.assertEqual(path, good.name)
            self.assertIn("containerVersion", content)
        finally:
            os.unlink(bad.name)
            os.unlink(good.name)

    def test_not_json_fails_validation(self):
        """Non-JSON file fails GTM validator."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("this is not json")
            tmp_path = f.name
        try:
            with patch('builtins.input', side_effect=[tmp_path, 'n']):
                path, content = _ask_file_path("JSON GTM", validation_fn=self._gtm_validator)
            self.assertIsNone(path)
        finally:
            os.unlink(tmp_path)


# ═══════════════════════════════════════════════════════════════════════════
#  _ask_file_path — FILE NOT FOUND (NFR18)
# ═══════════════════════════════════════════════════════════════════════════

class TestAskFilePathNotFound(unittest.TestCase):
    """AC: file doesn't exist → error, user can retry or skip (NFR18)."""

    def test_not_found_retry_then_valid(self):
        """File not found → retry → provide valid path."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            tmp_path = f.name
        try:
            with patch('builtins.input', side_effect=['/nonexistent/file.json', '', tmp_path]):
                path, content = _ask_file_path("File")
            self.assertEqual(path, tmp_path)
        finally:
            os.unlink(tmp_path)

    def test_not_found_then_skip(self):
        """File not found → skip → returns (None, None)."""
        with patch('builtins.input', side_effect=['/nonexistent/file.json', 'skip']):
            path, content = _ask_file_path("File")
        self.assertIsNone(path)
        self.assertIsNone(content)

    def test_not_found_error_message(self):
        """Shows ⚠ File non trovato."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            tmp_path = f.name
        try:
            with patch('builtins.input', side_effect=['/no/such/file.json', '', tmp_path]):
                with patch('sys.stdout', new_callable=StringIO) as out:
                    _ask_file_path("File")
            self.assertIn("File non trovato", out.getvalue())
        finally:
            os.unlink(tmp_path)


# ═══════════════════════════════════════════════════════════════════════════
#  _ask_file_path — SKIP
# ═══════════════════════════════════════════════════════════════════════════

class TestAskFilePathSkip(unittest.TestCase):
    """AC: user types 'skip' → returns (None, None)."""

    def test_skip_immediately(self):
        with patch('builtins.input', return_value='skip'):
            path, content = _ask_file_path("File JSON GTM")
        self.assertIsNone(path)
        self.assertIsNone(content)

    def test_skip_case_insensitive(self):
        with patch('builtins.input', return_value='SKIP'):
            path, content = _ask_file_path("File")
        self.assertIsNone(path)

    def test_skip_shows_message(self):
        with patch('builtins.input', return_value='skip'):
            with patch('sys.stdout', new_callable=StringIO) as out:
                _ask_file_path("File")
        self.assertIn("saltato", out.getvalue())


# ═══════════════════════════════════════════════════════════════════════════
#  _ask_file_path — ENCODING FALLBACK
# ═══════════════════════════════════════════════════════════════════════════

class TestAskFilePathEncoding(unittest.TestCase):
    """Handles non-UTF8 files with fallback encoding."""

    def test_latin1_file(self):
        """Latin-1 encoded file (common for GSC CSV on Windows)."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as f:
            f.write("pagina,clic,impressioni\n/caffè,100,5000\n".encode('latin-1'))
            tmp_path = f.name
        try:
            with patch('builtins.input', return_value=tmp_path):
                path, content = _ask_file_path("CSV GSC")
            self.assertIsNotNone(path)
            self.assertIn("caffè", content)
        finally:
            os.unlink(tmp_path)

    def test_utf8_bom_file(self):
        """UTF-8 BOM file (common for Excel exports)."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as f:
            f.write(b'\xef\xbb\xbfpage,clicks\n/home,100\n')
            tmp_path = f.name
        try:
            with patch('builtins.input', return_value=tmp_path):
                path, content = _ask_file_path("CSV GSC")
            self.assertIsNotNone(path)
            self.assertIn("page", content)
        finally:
            os.unlink(tmp_path)


# ═══════════════════════════════════════════════════════════════════════════
#  _ask_file_path — HELP TEXT
# ═══════════════════════════════════════════════════════════════════════════

class TestAskFilePathHelpText(unittest.TestCase):
    """help_text shown on first prompt only."""

    def test_help_text_displayed(self):
        with patch('builtins.input', return_value='skip'):
            with patch('sys.stdout', new_callable=StringIO) as out:
                _ask_file_path("File", help_text="Esporta da GTM > Admin > Export Container")
        self.assertIn("ℹ", out.getvalue())
        self.assertIn("Esporta da GTM", out.getvalue())

    def test_help_text_shown_once(self):
        """Not shown again after error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            tmp_path = f.name
        try:
            with patch('builtins.input', side_effect=['/no/file', '', tmp_path]):
                with patch('sys.stdout', new_callable=StringIO) as out:
                    _ask_file_path("File", help_text="Aiuto")
            self.assertEqual(out.getvalue().count("Aiuto"), 1)
        finally:
            os.unlink(tmp_path)


# ═══════════════════════════════════════════════════════════════════════════
#  INTEGRATION: Real wizard scenarios
# ═══════════════════════════════════════════════════════════════════════════

class TestRealScenarios(unittest.TestCase):
    """Integration tests matching Journey 1 (Marco) and Journey 3 (Luca)."""

    def test_cm_v2_selection(self):
        """Iubenda wizard: select CM v2 status."""
        options = ["Assente", "Basic", "Advanced"]
        with patch('builtins.input', return_value='3'):
            result = _ask_select("Stato Consent Mode v2", options)
        self.assertEqual(result, "Advanced")

    def test_banner_services_multi_select(self):
        """Iubenda wizard: multi-select banner services."""
        services = ["Google Analytics", "Google Ads", "Meta Pixel", "LinkedIn", "TikTok", "Hotjar"]
        with patch('builtins.input', return_value='1,2,3'):
            result = _ask_select("Servizi nel banner Iubenda", services, allow_multiple=True)
        self.assertEqual(result, ["Google Analytics", "Google Ads", "Meta Pixel"])

    def test_gtm_json_upload_valid(self):
        """GTM wizard: upload valid container JSON."""
        container = {"containerVersion": {"tag": [{"name": "GA4"}], "trigger": [], "variable": []}}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(container, f)
            tmp_path = f.name

        def validate_gtm(content):
            try:
                data = json.loads(content)
                if "containerVersion" in data:
                    return True, ""
                return False, "Manca 'containerVersion'"
            except json.JSONDecodeError:
                return False, "JSON non valido"

        try:
            with patch('builtins.input', return_value=tmp_path):
                path, content = _ask_file_path(
                    "Percorso file JSON container GTM",
                    validation_fn=validate_gtm,
                    help_text="Esporta da GTM > Admin > Export Container"
                )
            self.assertIsNotNone(path)
            data = json.loads(content)
            self.assertIn("containerVersion", data)
        finally:
            os.unlink(tmp_path)

    def test_attribution_model_selection(self):
        """Google Ads wizard: attribution model."""
        options = ["Data-driven", "Last-click", "Altro"]
        with patch('builtins.input', return_value='1'):
            result = _ask_select("Modello di attribuzione", options)
        self.assertEqual(result, "Data-driven")


if __name__ == '__main__':
    unittest.main()
