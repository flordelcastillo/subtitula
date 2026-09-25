"""Corrección determinista de la ortografía del glosario en el texto que se publica.

El reconocedor usa el glosario como vocabulario, pero la traducción del motor en vivo no lo ve:
puede escribir "kubernetes", "eleven labs" o "Nerd Earla". Antes de publicar, cada aparición se
lleva a la forma canónica del glosario. Es barato, predecible y aplica a todas las pistas.
"""

from __future__ import annotations

import re

_CAMEL = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")


def _pattern(term: str) -> re.Pattern | None:
    words = term.split()
    parts: list[str] = []
    for word in words:
        # "ElevenLabs" también matchea "Eleven Labs" y "eleven-labs".
        pieces = _CAMEL.findall(word) if word.isalnum() else [word]
        parts.append(r"[\s-]?".join(re.escape(p) for p in pieces if p) or re.escape(word))
    body = r"\s+".join(parts)
    if len(term) < 3 or not body:
        return None  # siglas de 1-2 letras darían falsos positivos
    return re.compile(rf"(?<![\w-]){body}(?![\w-])", re.IGNORECASE)


class GlossaryFixer:
    def __init__(self, terms: list[str]):
        self.rules = [(p, t) for t in sorted(set(terms), key=len, reverse=True) if (p := _pattern(t))]

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
