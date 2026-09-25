"""Corrección determinista de la ortografía del glosario en el texto que se publica.

El reconocedor usa el glosario como vocabulario, pero la traducción del motor en vivo no lo ve:
puede escribir "kubernetes", "eleven labs", "11 labs" o "Nerd Earla". Antes de publicar, cada
aparición se lleva a la forma canónica del glosario. Es barato, predecible y aplica a todas las pistas.

Un término puede traer alias explícitos: "ElevenLabs = 11 labs, Eleven Laps". Además, los números
escritos con letras matchean también en dígitos ("Eleven" ↔ "11").
"""

from __future__ import annotations

import re

_CAMEL = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
_NUMBERS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
    "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
    "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18", "nineteen": "19", "twenty": "20",
    "thirty": "30", "forty": "40", "fifty": "50", "sixty": "60", "hundred": "100", "thousand": "1000",
    "uno": "1", "dos": "2", "tres": "3", "cuatro": "4", "cinco": "5", "seis": "6", "siete": "7", "ocho": "8",
    "nueve": "9", "diez": "10", "once": "11", "doce": "12", "veinte": "20", "cien": "100", "mil": "1000",
}
_DIGITS = {v: k for k, v in _NUMBERS.items()}


def _piece(p: str) -> str:
    low = p.lower()
    if low in _NUMBERS:
        return f"(?:{re.escape(p)}|{_NUMBERS[low]})"
    if p in _DIGITS:
        return f"(?:{p}|{_DIGITS[p]})"
    return re.escape(p)


def _pattern(term: str) -> re.Pattern | None:
    words = term.split()
    parts: list[str] = []
    for word in words:
        # "ElevenLabs" también matchea "Eleven Labs", "eleven-labs" y "11 labs".
        pieces = _CAMEL.findall(word) if word.isalnum() else [word]
        parts.append(r"[\s-]?".join(_piece(p) for p in pieces if p) or re.escape(word))
    body = r"\s+".join(parts)
    if len(term) < 3 or not body:
        return None  # siglas de 1-2 letras darían falsos positivos
    return re.compile(rf"(?<![\w-]){body}(?![\w-])", re.IGNORECASE)


def parse_term(entry: str) -> tuple[str, list[str]]:
    """'ElevenLabs = 11 labs, Eleven Laps' → ('ElevenLabs', ['11 labs', 'Eleven Laps'])."""
    canonical, _, aliases = entry.partition("=")
    return canonical.strip(), [a.strip() for a in aliases.split(",") if a.strip()]


def canonical_terms(terms: list[str]) -> list[str]:
    """Sólo las formas canónicas, para el vocabulario del reconocedor y el prompt de traducción."""
    return [parse_term(t)[0] for t in terms if parse_term(t)[0]]


class GlossaryFixer:
    def __init__(self, terms: list[str]):
        rules: list[tuple[re.Pattern, str]] = []
        for entry in sorted(set(terms), key=len, reverse=True):
            canonical, aliases = parse_term(entry)
            for form in [canonical, *aliases]:
                pattern = _pattern(form)
                if pattern and canonical:
                    rules.append((pattern, canonical))
        self.rules = rules

    def fix(self, text: str) -> str:
        for pattern, canonical in self.rules:
            text = pattern.sub(lambda m, c=canonical: _keep_initial(m, c), text)
        return text


_SENTENCE_START = re.compile(r"(^|[.?!¿¡]\s*)$")


def _keep_initial(match: re.Match, canonical: str) -> str:
    # "Open source" a principio de oración no pierde la mayúscula por un término en minúscula.
    found = match.group(0)
    at_start = _SENTENCE_START.search(match.string[: match.start()]) is not None
    if at_start and found[:1].isupper() and canonical[:1].islower():
        return canonical[:1].upper() + canonical[1:]
    return canonical
