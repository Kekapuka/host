"""Text normalisation and fuzzy comparison tuned for short spoken commands (RU/EN)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache

_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)

# Words that carry little meaning in a command. They weigh less when phrases are compared.
STOPWORDS = frozenset(
    """
    в во на и с со к ко по за из у о об от до для а же ли бы то ка мне меня мой мою мои мое моё
    эй ну пожалуйста плиз давай ка ок окей слушай
    the a an to in on of for at by and my me please hey ok okay
    """.split()
)

# Prepositions stripped from the edges of captured {placeholders}: "найди котиков на ютубе".
EDGE_WORDS = frozenset("в во на с со к по за из у о об от до для the a an to in on at for of from by".split())

FILLERS = frozenset("эй ну пожалуйста плиз давай ка ок окей слушай hey ok okay please".split())

NEGATIONS = frozenset("не нет not dont don".split())

_NEGATING_PREFIXES = ("вы", "dis", "un")


@dataclass(frozen=True)
class Token:
    norm: str
    start: int
    end: int


def normalize(text: str) -> str:
    return " ".join(t.norm for t in tokenize(text))


def tokenize(text: str) -> list[Token]:
    """Words with their offsets in the original text (lowercase, ё→е, no punctuation)."""
    if not text:
        return []
    return [
        Token(m.group(0).lower().replace("ё", "е"), m.start(), m.end())
        for m in _WORD_RE.finditer(text)
    ]


def words(text: str) -> list[str]:
    return [t.norm for t in tokenize(text)]


def is_stop(word: str) -> bool:
    return word in STOPWORDS


def _common_prefix(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


@lru_cache(maxsize=65536)
def word_sim(a: str, b: str) -> float:
    """Similarity of two normalised words in [0, 1]; 0 when they clearly differ.

    Short words and numbers must match exactly. Russian inflections ("музыку"/"музыка",
    "открой"/"открыть") share a long common prefix and score 0.9.
    """
    if a == b:
        return 1.0
    la, lb = len(a), len(b)
    if min(la, lb) <= 2 or a.isdigit() or b.isdigit():
        return 0.0
    # Prefixes that flip the meaning: включи/выключи, врубай/вырубай, mute/unmute, enable/disable.
    for neg in _NEGATING_PREFIXES:
        if a.startswith(neg) != b.startswith(neg):
            return 0.0
    prefix = _common_prefix(a, b)
    if prefix >= 4 and prefix >= min(la, lb) - 2:
        return 0.9
    if min(la, lb) == 3 and prefix < 2:
        return 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    return ratio if ratio >= 0.75 else 0.0


def _weight(word: str) -> float:
    return 0.35 if word in STOPWORDS else 1.0


def phrase_score(text_words: list[str], trigger_words: list[str]) -> tuple[float, float]:
    """Compare a spoken phrase with a trigger phrase (bag of words, fuzzy).

    Returns (score, coverage) where coverage is the weighted share of trigger words found in
    the phrase and score additionally rewards phrases without extra words.
    """
    if not text_words or not trigger_words:
        return 0.0, 0.0
    if text_words == trigger_words:
        return 1.0, 1.0
    tw = [_weight(w) for w in trigger_words]
    coverage = sum(
        w * max(word_sim(t, x) for x in text_words) for t, w in zip(trigger_words, tw)
    ) / sum(tw)
    xw = [_weight(w) for w in text_words]
    precision = sum(
        w * max(word_sim(x, t) for t in trigger_words) for x, w in zip(text_words, xw)
    ) / sum(xw)
    # "не открывай хром" must not run "открой хром"
    if NEGATIONS.intersection(text_words) and not NEGATIONS.intersection(trigger_words):
        coverage *= 0.5
    return 0.8 * coverage + 0.2 * precision, coverage


# --- phonetic comparison (wake word, app names spoken in another script) -----------------

_CYR2LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "ch",
    "ш": "sh", "щ": "sh", "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "u", "я": "a",
}
_PHONETIC_STEPS = (
    ("dzh", "j"), ("dj", "j"), ("zh", "j"), ("ph", "f"), ("ck", "k"), ("qu", "kv"),
    ("x", "ks"), ("w", "v"), ("y", "i"), ("ee", "i"), ("oo", "u"), ("ou", "u"),
)


@lru_cache(maxsize=8192)
def phonetic(word: str) -> str:
    s = "".join(_CYR2LAT.get(c, c) for c in word.lower().replace("ё", "е"))
    for src, dst in _PHONETIC_STEPS:
        s = s.replace(src, dst)
    s = re.sub(r"c(?=[ei])", "s", s).replace("c", "k")
    return re.sub(r"(.)\1+", r"\1", s)


def phonetic_sim(a: str, b: str) -> float:
    pa, pb = phonetic(a), phonetic(b)
    if not pa or not pb:
        return 0.0
    if pa == pb:
        return 1.0
    ratio = SequenceMatcher(None, pa, pb).ratio()
    # inflected forms: "джарвису" -> "jarvisu"
    if len(pa) > len(pb) >= 4 and pa.startswith(pb):
        ratio = max(ratio, 0.9)
    return ratio


def phrase_phonetic_sim(a: str, b: str) -> float:
    """Similarity of two short phrases ignoring spaces and script (хром ~ chrome)."""
    pa = phonetic("".join(words(a)))
    pb = phonetic("".join(words(b)))
    if not pa or not pb:
        return 0.0
    if pa == pb:
        return 1.0
    return SequenceMatcher(None, pa, pb).ratio()


# --- numbers --------------------------------------------------------------------------------

_RU_NUMBERS = {
    "ноль": 0, "нуль": 0, "один": 1, "одна": 1, "одну": 1, "два": 2, "две": 2, "три": 3,
    "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
    "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14,
    "пятнадцать": 15, "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18,
    "девятнадцать": 19, "двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50,
    "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80, "девяносто": 90, "сто": 100,
    "половина": 50, "половину": 50, "максимум": 100, "максимальная": 100, "минимум": 0,
}
_EN_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100, "half": 50, "max": 100,
    "maximum": 100, "min": 0, "minimum": 0,
}


def parse_number(text: str) -> int | None:
    """'50', '50%', 'пятьдесят пять', 'forty two' -> int; None when no number is found."""
    if text is None:
        return None
    m = re.search(r"-?\d+", str(text))
    if m:
        return int(m.group(0))
    total, found = 0, False
    for w in words(str(text)):
        value = _RU_NUMBERS.get(w, _EN_NUMBERS.get(w))
        if value is not None:
            total += value
            found = True
    return total if found else None
