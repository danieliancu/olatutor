"""Explicit Unicode normalisation. Every accepted character is listed here.

NFKC is deliberately not used: it would silently turn `1½` into `11⁄2`, which reads as 11/2.
Characters missing from these tables reach the tokeniser unchanged, and are refused there.
"""

ASCII_DIGITS = frozenset("0123456789")
ASCII_NUMBER_CONTINUATION = ASCII_DIGITS | {".", "/", ","}

CHARACTER_MAP = {
    "−": "-",  # minus sign
    "–": "-",  # en dash, commonly typed as a minus
    "*": "×",
    "⁄": "/",  # fraction slash
    "∕": "/",  # division slash
    " ": " ",  # no-break space
    "\t": " ",
}

VULGAR_FRACTIONS = {
    "½": "1/2",
    "⅓": "1/3",
    "⅔": "2/3",
    "¼": "1/4",
    "¾": "3/4",
    "⅕": "1/5",
    "⅖": "2/5",
    "⅗": "3/5",
    "⅘": "4/5",
    "⅙": "1/6",
    "⅚": "5/6",
    "⅛": "1/8",
    "⅜": "3/8",
    "⅝": "5/8",
    "⅞": "7/8",
}


def normalize(text: str) -> str:
    """Applies the tables and collapses spaces. Keeps what it cannot map for the tokeniser."""
    mapped = "".join(CHARACTER_MAP.get(char, char) for char in text)
    pieces: list[str] = []
    for position, char in enumerate(mapped):
        fraction = VULGAR_FRACTIONS.get(char)
        following = mapped[position + 1 : position + 2]
        if fraction is None or following in ASCII_NUMBER_CONTINUATION:
            # `½3` must not become `1/23`. The tokeniser refuses the unmapped character.
            pieces.append(char)
            continue
        previous = mapped[position - 1 : position]
        pieces.append(f" {fraction}" if previous in ASCII_DIGITS else fraction)
    return " ".join(part for part in "".join(pieces).split(" ") if part)
