"""Shared input helpers for all deep mode wizards.

Provides uniform UX: validation, warnings, contextual help, re-prompt on error.
All user-facing text in Italian, code in English.
"""

import os
import shutil


def _ask_input(prompt, validation_fn=None, warning_fn=None, help_text=None,
               coerce_fn=None, allow_empty=False):
    """Standard input pattern for all wizards (FR40-FR43).

    Validation flow: empty check → validation_fn → warning_fn → coerce_fn → return.
    User-facing text is in Italian. Re-prompts on any failure.

    Args:
        prompt: Question text (Italian)
        validation_fn: callable(raw) -> (bool, error_msg). If invalid, shows
            '⚠ {error_msg}' and re-prompts (FR43)
        warning_fn: callable(raw) -> warning_msg or None. If warning returned,
            shows '⚠ Attenzione: {warning}' and asks 'Confermi questo valore? (s/n)' (FR41)
        help_text: Contextual instruction displayed as 'ℹ {help_text}' above
            the prompt on first display (FR42)
        coerce_fn: callable(raw) -> converted_value. Applied after validation
            passes. E.g. float for percentages, int for counts
        allow_empty: If True, accept empty string without re-prompting

    Returns:
        Validated (and optionally coerced) user input
    """
    first_prompt = True
    while True:
        # Show help text only on first prompt (FR42)
        if help_text and first_prompt:
            print(f"  ℹ {help_text}")
        first_prompt = False

        try:
            raw = input(f"  → {prompt}: ").strip()
        except (EOFError, KeyboardInterrupt):
            return "" if not coerce_fn else None

        # Auto-strip common formatting artifacts (%, trailing commas)
        raw = raw.rstrip('%').strip()
        # Replace comma decimal separator with dot for numeric inputs
        if coerce_fn and ',' in raw and '.' not in raw:
            raw = raw.replace(',', '.')

        if not raw and not allow_empty:
            print("  ⚠ Input richiesto. Riprova.")
            continue

        # Validation gate (FR40, FR43)
        if validation_fn:
            valid, error_msg = validation_fn(raw)
            if not valid:
                print(f"  ⚠ {error_msg}")
                continue

        # Suspicious value warning (FR41)
        if warning_fn:
            warning = warning_fn(raw)
            if warning:
                print(f"  ⚠ Attenzione: {warning}")
                try:
                    confirm = input("  → Confermi questo valore? (s/n): ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    continue
                if confirm != 's':
                    continue

        # Type coercion
        if coerce_fn:
            try:
                return coerce_fn(raw)
            except (ValueError, TypeError) as e:
                print(f"  ⚠ Valore non valido: {e}")
                continue

        return raw


def _ask_select(prompt, options, allow_multiple=False, help_text=None):
    """Standard selection pattern for all wizards (FR40, FR43).

    Displays numbered options. Single mode returns one option string.
    Multiple mode accepts comma-separated numbers and returns a list.
    Re-prompts on invalid or out-of-range input.

    Args:
        prompt: Question text (Italian)
        options: List of option strings
        allow_multiple: If True, allow comma-separated selection (FR3)
        help_text: Contextual instruction shown on first prompt (FR42)

    Returns:
        Selected option string (single) or list of strings (multiple)
    """
    first_prompt = True
    while True:
        if help_text and first_prompt:
            print(f"  ℹ {help_text}")
        first_prompt = False

        print(f"\n  {prompt}")
        for i, opt in enumerate(options, 1):
            print(f"    {i}. {opt}")

        try:
            if allow_multiple:
                raw = input("  → Seleziona (numeri separati da virgola): ").strip()
                if not raw:
                    print("  ⚠ Seleziona almeno un'opzione.")
                    continue
                try:
                    parts = [x.strip() for x in raw.split(",")]
                    indices = []
                    bad_parts = []
                    for p in parts:
                        try:
                            idx = int(p) - 1
                            if 0 <= idx < len(options):
                                indices.append(idx)
                            else:
                                bad_parts.append(p)
                        except ValueError:
                            bad_parts.append(p)
                    if bad_parts:
                        print(f"  ⚠ Valori ignorati (fuori range o non validi): {', '.join(bad_parts)}")
                    if not indices:
                        print(f"  ⚠ Nessuna opzione valida selezionata. Scegli numeri tra 1 e {len(options)}.")
                        continue
                    # Deduplicate preserving order
                    seen = set()
                    unique_indices = []
                    for idx in indices:
                        if idx not in seen:
                            seen.add(idx)
                            unique_indices.append(idx)
                    selected = [options[i] for i in unique_indices]
                    # Echo selection
                    print(f"  ✓ Selezionato: {', '.join(selected)}")
                    return selected
                except Exception:
                    print("  ⚠ Input non valido. Inserisci numeri separati da virgola.")
                    continue
            else:
                raw = input("  → Seleziona (numero): ").strip()
                if not raw:
                    print("  ⚠ Inserisci un numero.")
                    continue
                try:
                    idx = int(raw) - 1
                    if 0 <= idx < len(options):
                        return options[idx]
                    else:
                        print(f"  ⚠ Seleziona un numero tra 1 e {len(options)}.")
                        continue
                except ValueError:
                    print("  ⚠ Inserisci un numero valido.")
                    continue
        except (EOFError, KeyboardInterrupt):
            return [] if allow_multiple else ""


def _ask_operator_notes():
    """Collect optional free-text operator notes (max 2000 chars).

    Returns:
        str or "" if skipped
    """
    print("\n  ── Note libere operatore (opzionale, max 2000 caratteri) ──")
    try:
        raw = input("  → Note (Invio per saltare): ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""
    if not raw:
        return ""
    if len(raw) > 2000:
        raw = raw[:2000]
        print("  ℹ Note troncate a 2000 caratteri.")
    return raw


def _ask_evidence_screenshots(wizard_name):
    """Collect optional evidence screenshots for a wizard.

    Copies images to output/evidence/{wizard_name}/.
    Accepts multiple files until user stops.

    Args:
        wizard_name: str, e.g. "iubenda", "gtm", "gads", "meta", "gsc"

    Returns:
        list of saved file paths, or []
    """
    ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}

    try:
        choice = input("\n  → Vuoi allegare screenshot come prova? (s/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return []

    if choice != 's':
        return []

    # Setup evidence directory
    cli_dir = os.path.dirname(os.path.abspath(__file__))
    tool_dir = os.path.dirname(os.path.dirname(cli_dir))
    evidence_dir = os.path.join(tool_dir, "output", "evidence", wizard_name)
    os.makedirs(evidence_dir, exist_ok=True)

    saved_paths = []
    print("  ℹ Inserisci i percorsi delle immagini, uno per volta. 'fine' per terminare.")

    while True:
        try:
            raw = input("  → Percorso immagine (o 'fine'): ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not raw or raw.lower() in ('fine', 'done', 'stop', 'no'):
            break

        path = raw.strip('"').strip("'")
        path = os.path.expanduser(path)

        if not os.path.isfile(path):
            print(f"  ⚠ File non trovato: {path}")
            continue

        ext = os.path.splitext(path)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            print(f"  ⚠ Formato non supportato: {ext}. Accettati: {', '.join(ALLOWED_EXTENSIONS)}")
            continue

        try:
            dest = os.path.join(evidence_dir, f"evidence_{len(saved_paths)+1}{ext}")
            shutil.copy2(path, dest)
            saved_paths.append(dest)
            print(f"  ✓ Screenshot salvato: {os.path.basename(dest)}")
        except Exception as e:
            print(f"  ⚠ Errore copia file: {e}")

    if saved_paths:
        print(f"  ✓ {len(saved_paths)} screenshot allegati")

    return saved_paths


def _ask_file_path(prompt, validation_fn=None, help_text=None):
    """Standard file path input for wizards (FR44, NFR18).

    Checks file existence, reads content (with encoding fallback),
    and validates structure via validation_fn. User can type 'skip'
    to skip the wizard at any point.

    Args:
        prompt: Question text (Italian)
        validation_fn: callable(file_content_str) -> (bool, error_msg).
            Validates file structure (e.g. JSON GTM has containerVersion,
            CSV GSC has expected headers) (FR44)
        help_text: Contextual instruction shown on first prompt (FR42)

    Returns:
        Tuple (file_path, file_content) or (None, None) if skipped (NFR18)
    """
    first_prompt = True
    while True:
        if help_text and first_prompt:
            print(f"  ℹ {help_text}")
        first_prompt = False

        try:
            raw = input(f"  → {prompt} (o 'skip' per saltare): ").strip()
        except (EOFError, KeyboardInterrupt):
            return None, None

        SKIP_SYNONYMS = {'skip', 'no', 'non disponibile', 'non ce l\'ho', 'n/a', 'nessuno'}
        if raw.lower() in SKIP_SYNONYMS:
            print("  ○ Wizard saltato.")
            return None, None

        if not raw:
            print("  ⚠ Inserisci un percorso file o 'skip' per saltare.")
            continue

        # Strip surrounding quotes (common when drag-dropping files)
        path = raw.strip('"').strip("'")
        path = os.path.expanduser(path)

        if not os.path.exists(path):
            print(f"  ⚠ File non trovato: {path}")
            try:
                retry = input("  → Riprovare o 'skip' per saltare? ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return None, None
            if retry in SKIP_SYNONYMS:
                print("  ○ Wizard saltato.")
                return None, None
            continue

        if not os.path.isfile(path):
            print(f"  ⚠ Il percorso non è un file: {path}")
            continue

        # Read with encoding fallback (NFR14)
        content = None
        for encoding in ('utf-8', 'utf-8-sig', 'latin-1', 'cp1252'):
            try:
                with open(path, encoding=encoding) as f:
                    content = f.read()
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
            except Exception as e:
                print(f"  ⚠ Errore lettura file: {e}")
                break

        if content is None:
            print(f"  ⚠ Impossibile leggere il file con nessun encoding supportato.")
            try:
                retry = input("  → Riprovare con un altro file? (s/n): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return None, None
            if retry != 's':
                return None, None
            continue

        # Structure validation (FR44)
        if validation_fn:
            valid, error_msg = validation_fn(content)
            if not valid:
                print(f"  ⚠ {error_msg}")
                try:
                    retry = input("  → Riprovare con un altro file? (s/n): ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    return None, None
                if retry != 's':
                    print("  ○ Wizard saltato.")
                    return None, None
                continue

        print(f"  ✓ File caricato: {os.path.basename(path)}")
        return path, content
