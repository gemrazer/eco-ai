"""Contador de tokens usando tiktoken (cl100k_base — tokenizador de GPT-4).

Nota: Claude usa un vocabulario BPE distinto; los recuentos son una aproximación.
Para conteos exactos en Claude, usa el endpoint de conteo de tokens de la API de Anthropic.
"""

from functools import lru_cache


@lru_cache(maxsize=1)
def _get_encoder():
    try:
        import tiktoken
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


def count_tokens(text: str) -> int:
    """
    Cuenta tokens del texto.
    Usa tiktoken si está disponible; si no, aproxima con palabras×1.3.
    """
    enc = _get_encoder()
    if enc is not None:
        return len(enc.encode(text))
    # Aproximación: los LLMs generan ~1.3 tokens por palabra en inglés/español
    words = len(text.split())
    return max(1, int(words * 1.3))


def tokenizer_source() -> str:
    if _get_encoder() is not None:
        return "tiktoken (cl100k_base)"
    return "aproximación (tiktoken no disponible)"
