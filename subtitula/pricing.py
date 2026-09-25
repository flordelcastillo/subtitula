"""Precios por modelo, para que el panel muestre el costo real de cada sala.

Fuente: https://ai.google.dev/gemini-api/docs/pricing (plan pago, consultado el 25/09/2026).
USD por millón de tokens, (entrada, salida). El audio se cuenta a 25 tokens por segundo.
"""

from __future__ import annotations

import os

PRICES: dict[str, tuple[float, float]] = {
    # Live Translate: entra audio y sale audio (la voz traducida se genera y se cobra siempre).
    "gemini-3.5-live-translate-preview": (3.50, 21.00),  # US$ 0,0053/min + 0,0315/min
    "gemini-3.5-transcribe-live": (3.50, 21.00),
    "gemini-3.5-transcribe": (2.00, 12.00),  # US$ 0,003/min de audio
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-flash-lite-latest": (0.30, 2.50),
    "gemini-3.1-flash-lite": (0.50, 1.50),  # entrada de audio; la de texto es 0,25
}


def _fallback() -> tuple[float, float]:
    try:
        return (float(os.environ.get("SUBTITULA_PRICE_INPUT_PER_M", "0.30")),
                float(os.environ.get("SUBTITULA_PRICE_OUTPUT_PER_M", "2.50")))
    except ValueError:
        return 0.30, 2.50


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    if not model or model.startswith(("gemma", "fake", "local")):
        return 0.0  # Gemma por API no figura con precio; el motor local no paga API
    name = model.removeprefix("models/")
    price_in, price_out = PRICES.get(name) or next(
        (p for key, p in PRICES.items() if name.startswith(key)), _fallback())
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000
