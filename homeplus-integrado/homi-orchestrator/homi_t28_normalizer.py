"""HOMI T28 - Normalizador pronunciable es-AR (V1).

Deterministic text normalization for TTS consumption.
Preserves display_text; produces spoken_text.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

NORMALIZER_VERSION = "t28-es-ar-1.0"
LEXICON_VERSION = "t28-lexicon-es-ar-1.0"
LOCALE_DEFAULT = "es-AR"

DIGIT_WORDS = {
    "0": "cero", "1": "uno", "2": "dos", "3": "tres", "4": "cuatro",
    "5": "cinco", "6": "seis", "7": "siete", "8": "ocho", "9": "nueve",
}

UNITS_0_19 = [
    "cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve",
    "diez", "once", "doce", "trece", "catorce", "quince", "dieciseis", "diecisiete",
    "dieciocho", "diecinueve",
]
TENS = ["", "", "veinte", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa"]
HUNDREDS = {
    1: "ciento", 2: "doscientos", 3: "trescientos", 4: "cuatrocientos",
    5: "quinientos", 6: "seiscientos", 7: "setecientos", 8: "ochocientos", 9: "novecientos",
}


def _int_to_words(n: int) -> str:
    if n < 0:
        return "menos " + _int_to_words(-n)
    if n < 20:
        return UNITS_0_19[n]
    if n < 100:
        t, u = divmod(n, 10)
        if u == 0:
            return TENS[t]
        if t == 2:
            return "veinti" + UNITS_0_19[u]
        return TENS[t] + " y " + UNITS_0_19[u]
    if n < 1000:
        h = n // 100
        r = n % 100
        if n == 100:
            return "cien"
        if r == 0:
            return HUNDREDS[h]
        return HUNDREDS[h] + " " + _int_to_words(r)
    if n < 1_000_000:
        thousands = n // 1000
        r = n % 1000
        if thousands == 1:
            head = "mil"
        else:
            head = _int_to_words(thousands) + " mil"
        if r == 0:
            return head
        return head + " " + _int_to_words(r)
    if n < 1_000_000_000:
        millions = n // 1_000_000
        r = n % 1_000_000
        if millions == 1:
            head = "un millon"
        else:
            head = _int_to_words(millions) + " millones"
        if r == 0:
            return head
        return head + " " + _int_to_words(r)
    # fallback for very large: speak digits
    return " ".join(DIGIT_WORDS.get(c, c) for c in str(n))


def _decimal_to_words(num_str: str) -> str:
    # num_str may contain comma or dot decimal separator
    s = num_str.strip()
    neg = s.startswith("-")
    if neg:
        s = s.lstrip("-").strip()
    if "," in s and "." in s:
        # assume dots thousands, comma decimal
        int_part, dec_part = s.split(",", 1)
        int_part = int_part.replace(".", "")
    elif "," in s:
        int_part, dec_part = s.split(",", 1)
    elif "." in s:
        # ambiguous: if last group 3 digits -> thousands
        parts = s.split(".")
        if len(parts) > 1 and len(parts[-1]) == 3 and all(len(p) == 3 for p in parts[1:]):
            int_part = s.replace(".", "")
            dec_part = ""
        else:
            int_part, dec_part = s.split(".", 1)
    else:
        int_part, dec_part = s, ""
    int_part = int_part.strip() or "0"
    try:
        int_words = _int_to_words(int(int_part))
    except ValueError:
        int_words = int_part
    if dec_part == "":
        result = int_words
    else:
        dec_words = " ".join(DIGIT_WORDS.get(c, c) for c in dec_part if c.isdigit())
        result = int_words + " coma " + dec_words
    if neg:
        result = "menos " + result
    return result


# Lexicon
LEXICON = {
    "homi": {"spoken": "Homi", "match": "word", "source": "task-t28", "certainty": "approved"},
    "homeplus": {"spoken": "Home Plus", "match": "word", "source": "task-t28", "certainty": "approved"},
    "edenor": {"spoken": "Edenor", "match": "word", "source": "task-t28", "certainty": "approved"},
    "playstation": {"spoken": "PlayStation", "match": "word", "source": "task-t28", "certainty": "approved"},
    "wi-fi": {"spoken": "Wi-Fi", "match": "word", "source": "task-t28", "certainty": "approved"},
    "wifi": {"spoken": "Wi-Fi", "match": "word", "source": "task-t28", "certainty": "approved"},
    "arba": {"spoken": "ARBA", "match": "word", "source": "task-t28", "certainty": "pending"},
    "cuil": {"spoken": "CUIL", "match": "word", "source": "task-t28", "certainty": "pending"},
}

UNITS = {
    "km": "kilometros", "kilometro": "kilometro", "kilometros": "kilometros",
    "m": "metros", "cm": "centimetros", "mm": "milimetros",
    "kg": "kilogramos", "g": "gramos", "mg": "miligramos",
    "gb": "gigabytes", "mb": "megabytes", "tb": "terabytes", "kb": "kilobytes",
    "l": "litros", "ml": "mililitros",
    "hs": "horas", "h": "horas", "min": "minutos", "seg": "segundos",
}

MONTHS = {
    "01": "enero", "1": "enero", "02": "febrero", "2": "febrero",
    "03": "marzo", "3": "marzo", "04": "abril", "4": "abril",
    "05": "mayo", "5": "mayo", "06": "junio", "6": "junio",
    "07": "julio", "7": "julio", "08": "agosto", "8": "agosto",
    "09": "septiembre", "9": "septiembre", "10": "octubre",
    "11": "noviembre", "12": "diciembre",
}


@dataclass
class NormalizationResult:
    display_text: str
    spoken_text: str
    locale: str = LOCALE_DEFAULT
    changes: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    normalizer_version: str = NORMALIZER_VERSION
    lexicon_version: str = LEXICON_VERSION


def _protect(text: str) -> tuple[str, dict[str, str]]:
    placeholders: dict[str, str] = {}
    counter = [0]

    def repl(m: re.Match) -> str:
        token = f"@@P{counter[0]}@@"
        counter[0] += 1
        placeholders[token] = m.group(0)
        return token

    patterns = [
        r"`[^`]*`",
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        r"https?://\S+",
        r"(?:[A-Za-z]:\\|\\\\)[^\s]*",
        r"(?:^|(?<=\s))/(?:[^\s]+)",
        r"\b(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9][A-Za-z0-9_-]{5,}\b",
        r"\b\d{5,}\b",
    ]
    out = text
    for pat in patterns:
        out = re.sub(pat, repl, out)
    return out, placeholders


def _restore(text: str, placeholders: dict[str, str]) -> str:
    for token, original in placeholders.items():
        text = text.replace(token, original)
    return text


def _apply_lexicon(text: str, changes: list, warnings: list) -> str:
    # word-boundary, case-insensitive replacements
    for key, entry in LEXICON.items():
        spoken = entry["spoken"]
        if spoken == key or spoken.lower() == key.lower():
            continue
        pattern = re.compile(r"(?<!\w)" + re.escape(key) + r"(?!\w)", re.IGNORECASE)
        def repl(m):
            changes.append({"rule": "lexicon", "from": m.group(0), "to": spoken, "source": entry.get("source")})
            return spoken
        text = pattern.sub(repl, text)
    return text


def _apply_currency(text: str, changes: list, warnings: list) -> str:
    # $ amount
    def repl_dollar(m):
        amount = m.group(1)
        try:
            words = _parse_currency_amount(amount)
        except Exception:
            warnings.append(f"ambiguous_currency:{amount}")
            return m.group(0)
        changes.append({"rule": "currency_dollar", "from": m.group(0), "to": words})
        return words + " pesos" if "pesos" not in words else words

    text = re.sub(r"\$\s*(-?[0-9][0-9\.,]*)", lambda m: _currency_replace(m, changes, warnings), text)
    # ARS amount
    text = re.sub(r"\bARS\s+(-?[0-9][0-9\.,]*)", lambda m: _currency_replace(m, changes, warnings, suffix=""), text)
    # amount pesos
    text = re.sub(r"(-?[0-9][0-9\.,]*)\s*pesos\b", lambda m: _currency_replace(m, changes, warnings, suffix=" pesos", already_pesos=True), text)
    return text


def _parse_currency_amount(amount: str) -> str:
    s = amount.strip()
    neg = s.startswith("-")
    if neg:
        s = s.lstrip("-").strip()
    if "," in s:
        int_part, dec_part = s.split(",", 1)
        int_part = int_part.replace(".", "")
        cents = dec_part.strip()
        # pad/truncate to 2
        cents = (cents + "00")[:2]
    else:
        # dots as thousands
        int_part = s.replace(".", "")
        cents = ""
    n = int(int_part) if int_part else 0
    words = _int_to_words(n)
    if cents and int(cents) != 0:
        c = int(cents)
        words = words + " pesos con " + _int_to_words(c) + (" centavo" if c == 1 else " centavos")
    else:
        words = words + " pesos"
    if neg:
        words = "menos " + words
    return words


def _currency_replace(m, changes, warnings, suffix="", already_pesos=False):
    amount = m.group(1)
    try:
        words = _parse_currency_amount(amount)
    except Exception:
        warnings.append(f"ambiguous_currency:{amount}")
        return m.group(0)
    result = words
    changes.append({"rule": "currency", "from": m.group(0), "to": result})
    return result


def _apply_percent(text: str, changes: list, warnings: list) -> str:
    def repl(m):
        num = m.group(1)
        words = _decimal_to_words(num)
        result = words + " por ciento"
        changes.append({"rule": "percent", "from": m.group(0), "to": result})
        return result
    return re.sub(r"(-?[0-9][0-9\.,]*)\s*%", repl, text)


def _apply_dates(text: str, changes: list, warnings: list) -> str:
    # ISO
    def iso_repl(m):
        y, mo, d = m.group(1), m.group(2), m.group(3)
        if mo in MONTHS and 1 <= int(d) <= 31:
            result = f"{_int_to_words(int(d))} de {MONTHS[mo]} de {_int_to_words(int(y))}"
            changes.append({"rule": "date_iso", "from": m.group(0), "to": result})
            return result
        warnings.append(f"ambiguous_date:{m.group(0)}")
        return m.group(0)
    text = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", iso_repl, text)

    # slash dd/mm/yyyy
    def slash_repl(m):
        d = m.group(1); mo = m.group(2); y = m.group(3)
        if y and len(y) == 4 and mo in MONTHS and 1 <= int(d) <= 31 and 1 <= int(mo) <= 12:
            result = f"{_int_to_words(int(d))} de {MONTHS[mo.zfill(2) if len(mo)==1 else mo]} de {_int_to_words(int(y))}"
            changes.append({"rule": "date_slash", "from": m.group(0), "to": result})
            return result
        warnings.append(f"ambiguous_date:{m.group(0)}")
        return m.group(0)
    text = re.sub(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", slash_repl, text)

    # dd/mm (no year) -> preserve (ambiguous) but warn
    def slash2_repl(m):
        warnings.append(f"ambiguous_date:{m.group(0)}")
        return m.group(0)
    text = re.sub(r"\b(\d{1,2})/(\d{1,2})\b", slash2_repl, text)
    return text


def _apply_times(text: str, changes: list, warnings: list) -> str:
    def repl(m):
        h = int(m.group(1)); mi = int(m.group(2)); sec = m.group(3)
        parts = [_int_to_words(h), _int_to_words(mi)] if mi != 0 else [_int_to_words(h)]
        # always include minutes as two-digit? speak "catorce treinta"
        parts = [_int_to_words(h), _int_to_words(mi)]
        if sec is not None:
            parts.append(_int_to_words(int(sec)))
        result = " ".join(parts)
        changes.append({"rule": "time", "from": m.group(0), "to": result})
        return result
    return re.sub(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b", repl, text)


def _apply_units(text: str, changes: list, warnings: list) -> str:
    def repl(m):
        num_str = m.group(1)
        unit_raw = m.group(2)
        unit_key = unit_raw.lower()
        unit_spoken = UNITS.get(unit_key)
        if unit_spoken is None:
            warnings.append(f"unknown_unit:{unit_raw}")
            return m.group(0)
        # parse number
        try:
            words = _decimal_to_words(num_str)
        except Exception:
            warnings.append(f"ambiguous_number:{num_str}")
            return m.group(0)
        result = words + " " + unit_spoken
        changes.append({"rule": "unit", "from": m.group(0), "to": result})
        return result
    # number + unit
    unit_alternatives = "|".join(sorted(UNITS.keys(), key=len, reverse=True))
    pattern = re.compile(r"\b([0-9][0-9\.,]*)\s*(" + unit_alternatives + r")\b", re.IGNORECASE)
    return pattern.sub(repl, text)


def _apply_safe_numbers(text: str, changes: list, warnings: list) -> str:
    # Only transform bare integers without separators and not part of identifiers (protected already)
    def repl(m):
        n_str = m.group(0)
        try:
            n = int(n_str)
        except ValueError:
            return m.group(0)
        if n > 999999:
            # too large, keep
            return m.group(0)
        words = _int_to_words(n)
        changes.append({"rule": "integer", "from": n_str, "to": words})
        return words
    # bare integer (no separators) not adjacent to word chars
    text = re.sub(r"(?<![\w.,/\-])(-?\d{1,6})(?![\w.,/\-])", lambda m: _int_repl(m, changes, warnings), text)
    return text


def _int_repl(m, changes, warnings):
    n_str = m.group(1) if m.group(1) else m.group(0)
    # group handling
    full = m.group(0)
    neg = full.startswith("-")
    digits = full.lstrip("-")
    try:
        n = int(digits)
    except ValueError:
        return full
    if n > 999999:
        return full
    words = _int_to_words(n)
    if neg:
        words = "menos " + words
    changes.append({"rule": "integer", "from": full, "to": words})
    return words


def normalize_text(text: str, locale: str = LOCALE_DEFAULT, context: Any = None) -> NormalizationResult:
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    original = text
    changes: list[dict[str, Any]] = []
    warnings: list[str] = []

    if locale != LOCALE_DEFAULT:
        warnings.append("unsupported_locale")
        return NormalizationResult(
            display_text=original,
            spoken_text=original if isinstance(original, str) else str(original),
            locale=locale,
            changes=changes,
            warnings=warnings,
        )

    if len(text) > 10000:
        text = text[:10000]
        warnings.append("input_truncated")

    protected, placeholders = _protect(text)

    # precedence: currency, percent, dates, times, units, safe numbers, lexicon
    protected = _apply_currency(protected, changes, warnings)
    protected = _apply_percent(protected, changes, warnings)
    protected = _apply_dates(protected, changes, warnings)
    protected = _apply_times(protected, changes, warnings)
    protected = _apply_units(protected, changes, warnings)
    protected = _apply_safe_numbers(protected, changes, warnings)
    protected = _apply_lexicon(protected, changes, warnings)

    spoken = _restore(protected, placeholders)
    # collapse spaces
    spoken = re.sub(r"\s+", " ", spoken).strip()

    return NormalizationResult(
        display_text=original,
        spoken_text=spoken,
        locale=locale,
        changes=changes,
        warnings=warnings,
    )


class EsArNormalizer:
    def __init__(self, locale: str = LOCALE_DEFAULT):
        self.locale = locale

    def normalize(self, text: str, context: Any = None) -> NormalizationResult:
        return normalize_text(text, locale=self.locale, context=context)


# Aliases for compatibility
Normalizer = EsArNormalizer
normalize = normalize_text


def to_dict(result: NormalizationResult) -> dict[str, Any]:
    return {
        "display_text": result.display_text,
        "spoken_text": result.spoken_text,
        "locale": result.locale,
        "changes": result.changes,
        "warnings": result.warnings,
        "normalizer_version": result.normalizer_version,
        "lexicon_version": result.lexicon_version,
    }


if __name__ == "__main__":
    import sys
    sample = " ".join(sys.argv[1:]) or "El total es $48.320."
    print(normalize_text(sample).spoken_text)
