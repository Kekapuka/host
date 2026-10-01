"""Matching recognised phrases to user commands.

Trigger phrases may contain placeholders: "найди {query} на ютубе", "открой {app}".
A phrase may chain several commands: "открой хром и включи музыку в вк".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from .textproc import (
    EDGE_WORDS,
    FILLERS,
    NEGATIONS,
    STOPWORDS,
    Token,
    phonetic_sim,
    phrase_score,
    tokenize,
    word_sim,
    words,
)

_PLACEHOLDER = re.compile(r"\{(\w+)\}")

LITERAL_MIN_COVERAGE = 0.8
LITERAL_MIN_SCORE = 0.75
WORD_MATCH_MIN = 0.75


@dataclass
class Trigger:
    raw: str
    words: list[str]
    # for placeholder triggers: list of ("lit", [words]) / ("ph", name)
    segments: list[tuple[str, Any]] | None = None

    @property
    def is_template(self) -> bool:
        return self.segments is not None


def parse_trigger(raw: str) -> Trigger | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    parts = _PLACEHOLDER.split(raw)
    if len(parts) == 1:
        w = words(raw)
        return Trigger(raw, w) if w else None
    segments: list[tuple[str, Any]] = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            w = words(part)
            if w:
                segments.append(("lit", w))
        else:
            if segments and segments[-1][0] == "ph":
                # two placeholders in a row cannot be separated reliably: keep the first one
                continue
            segments.append(("ph", part.lower()))
    if not any(kind == "lit" for kind, _ in segments):
        return None  # "{query}" alone would match everything
    return Trigger(raw, [w for kind, v in segments if kind == "lit" for w in v], segments)


@dataclass
class CommandEntry:
    """A command as seen by the matcher (built by the command store)."""

    path: str
    name: str
    triggers: list[Trigger]
    data: dict[str, Any] = field(default_factory=dict)
    order: int = 0


@dataclass
class Match:
    command: CommandEntry
    score: float
    trigger: str
    captures: dict[str, str]
    text: str
    template: bool = False


@dataclass
class PlanStep:
    text: str
    match: Match | None


# --- placeholder matching -------------------------------------------------------------------

def _content(ws: list[str]) -> list[str]:
    content = [w for w in ws if w not in STOPWORDS]
    return content or ws


def _occurrences(lit: list[str], toks: list[Token], start: int) -> list[tuple[int, int, float, int]]:
    """Where the literal words occur in toks[start:] in order; stopwords in the text may be
    skipped between them. Returns (first_index, last_index, avg_sim, chars)."""
    content = _content(lit)
    found = []
    n = len(toks)
    for i in range(start, n):
        sim = word_sim(content[0], toks[i].norm)
        if sim < WORD_MATCH_MIN:
            continue
        sims = [sim]
        j = i
        ok = True
        for w in content[1:]:
            j += 1
            while j < n and toks[j].norm in STOPWORDS and word_sim(w, toks[j].norm) < WORD_MATCH_MIN:
                j += 1
            if j >= n:
                ok = False
                break
            s = word_sim(w, toks[j].norm)
            if s < WORD_MATCH_MIN:
                ok = False
                break
            sims.append(s)
        if ok:
            found.append((i, j, sum(sims) / len(sims), sum(len(w) for w in content)))
    return found


def _capture(text: str, toks: list[Token], a: int, b: int) -> str | None:
    """Original text of toks[a..b] without prepositions on the edges."""
    if a > b:
        return None
    while a < b and toks[a].norm in EDGE_WORDS:
        a += 1
    while b > a and toks[b].norm in EDGE_WORDS:
        b -= 1
    value = text[toks[a].start:toks[b].end].strip()
    return value or None


def match_template(trigger: Trigger, text: str, toks: list[Token]) -> tuple[float, dict[str, str]] | None:
    segs = trigger.segments or []
    n = len(toks)
    best: tuple[float, dict[str, str]] | None = None

    def finish(captures: dict[str, str], lit_chars: int, sims: list[float], skips: int) -> None:
        nonlocal best
        cap_chars = sum(len(v.replace(" ", "")) for v in captures.values())
        coverage = lit_chars / max(1, lit_chars + cap_chars)
        avg = sum(sims) / len(sims) if sims else 1.0
        score = (0.86 + 0.1 * coverage) * (0.9 + 0.1 * avg) - 0.04 * skips
        if best is None or score > best[0]:
            best = (score, dict(captures))

    def walk(si: int, pos: int, pending: str | None, pend_start: int,
             captures: dict[str, str], lit_chars: int, sims: list[float], skips: int) -> None:
        if si == len(segs):
            if pending is not None:
                value = _capture(text, toks, pend_start, n - 1)
                if value is None:
                    return
                captures = {**captures, pending: value}
            else:
                # trailing words after the last literal: allow fillers/stopwords and one extra word
                extra = [t for t in toks[pos:] if t.norm not in STOPWORDS and t.norm not in FILLERS]
                if len(extra) > 1:
                    return
                skips += len(extra)
            finish(captures, lit_chars, sims, skips)
            return
        kind, value = segs[si]
        if kind == "ph":
            walk(si + 1, pos + 1, value, pos, captures, lit_chars, sims, skips)
            return
        for first, last, avg, chars in _occurrences(value, toks, pos):
            new_caps = captures
            new_skips = skips
            if pending is not None:
                if first <= pend_start:
                    continue
                cap = _capture(text, toks, pend_start, first - 1)
                if cap is None:
                    continue
                new_caps = {**captures, pending: cap}
            elif si == 0:
                lead = [t for t in toks[:first] if t.norm not in FILLERS]
                if len(lead) > 2:
                    continue
                new_skips += len(lead)
            elif first != pos:
                # two literal segments without a placeholder between them
                gap = [t for t in toks[pos:first] if t.norm not in STOPWORDS]
                if gap:
                    continue
            walk(si + 1, last + 1, None, 0, new_caps, lit_chars + chars, sims + [avg], new_skips)

    if n == 0:
        return None
    walk(0, 0, None, 0, {}, 0, [], 0)
    return best


# --- matcher --------------------------------------------------------------------------------

class Matcher:
    def __init__(self, commands: Iterable[CommandEntry]):
        self.commands = list(commands)

    def match(self, text: str) -> Match | None:
        toks = [t for t in tokenize(text)]
        if not toks:
            return None
        text_words = [t.norm for t in toks if t.norm not in FILLERS] or [t.norm for t in toks]
        negated = bool(NEGATIONS.intersection(text_words))
        best: Match | None = None
        best_key: tuple | None = None
        for cmd in self.commands:
            for trig in cmd.triggers:
                if trig.is_template:
                    if negated and not NEGATIONS.intersection(trig.words):
                        continue
                    res = match_template(trig, text, toks)
                    if not res:
                        continue
                    score, caps = res
                    m = Match(cmd, score, trig.raw, caps, text, template=True)
                else:
                    score, coverage = phrase_score(text_words, trig.words)
                    if coverage < LITERAL_MIN_COVERAGE or score < LITERAL_MIN_SCORE:
                        continue
                    m = Match(cmd, score, trig.raw, {}, text, template=False)
                key = (round(m.score, 4), not m.template, len(trig.words), -cmd.order)
                if best_key is None or key > best_key:
                    best, best_key = m, key
        return best

    def plan(self, text: str, chain_words: Iterable[str] = ()) -> list[PlanStep]:
        """Split a phrase into commands and match each of them."""
        text = (text or "").strip()
        if not text:
            return []
        full = self.match(text)
        parts = split_chain(text, chain_words)
        if len(parts) <= 1:
            return [PlanStep(text, full)]
        if full and not full.template and full.score >= 0.95:
            return [PlanStep(text, full)]
        steps: list[PlanStep] = []
        prev_match: Match | None = None
        prev_lead: str | None = None
        for part in parts:
            m = self.match(part)
            if m is None and prev_match and prev_lead and not _captures_free_text(prev_match):
                # "открой хром и телеграм" -> "открой телеграм"
                candidate = f"{prev_lead} {part}"
                m2 = self.match(candidate)
                if m2:
                    m = m2
                    part = candidate
            steps.append(PlanStep(part, m))
            prev_match = m
            lead_words = [w for w in words(part) if w not in FILLERS]
            prev_lead = lead_words[0] if lead_words else None
        if all(s.match for s in steps):
            return steps
        if full:
            return [PlanStep(text, full)]
        return steps


FREE_TEXT_PLACEHOLDERS = frozenset({"text", "query", "q", "message", "prompt", "question"})


def _captures_free_text(m: Match) -> bool:
    return any(name in FREE_TEXT_PLACEHOLDERS for name in m.captures)


def split_chain(text: str, chain_words: Iterable[str]) -> list[str]:
    """Split by chain words ("и", "затем", "потом", "а потом"...), keeping original text."""
    toks = tokenize(text)
    chains = sorted({tuple(words(c)) for c in chain_words if words(c)}, key=len, reverse=True)
    if not toks or not chains:
        return [text.strip()] if text.strip() else []
    parts: list[str] = []
    start = 0
    i = 0
    n = len(toks)
    while i < n:
        hit = None
        for chain in chains:
            k = len(chain)
            if i + k <= n and tuple(t.norm for t in toks[i:i + k]) == chain:
                hit = k
                break
        if hit and i > start and i + hit < n:
            parts.append(text[toks[start].start:toks[i - 1].end])
            start = i + hit
            i += hit
            continue
        if hit and i == start:
            # chain word at the very beginning of a part: skip it
            start = i + hit
            i += hit
            continue
        i += 1
    if start < n:
        parts.append(text[toks[start].start:toks[-1].end])
    return [p.strip() for p in parts if p.strip()]


# --- wake word, confirmations ---------------------------------------------------------------

def find_wake_word(text: str, wake_word: str, threshold: float = 0.74) -> tuple[bool, str]:
    """Detect the wake word at the start (or end) of a phrase.

    Returns (found, rest_of_text). "Джарвис, открой хром" -> (True, "открой хром").
    """
    toks = tokenize(text)
    wake = words(wake_word)
    if not toks or not wake:
        return False, text.strip()
    k = len(wake)

    def matches_at(i: int) -> bool:
        if i < 0 or i + k > len(toks):
            return False
        return all(phonetic_sim(toks[i + j].norm, wake[j]) >= threshold for j in range(k))

    # at the beginning, possibly after fillers ("эй джарвис", "окей джарвис")
    for i in range(0, min(3, len(toks))):
        if matches_at(i) and all(t.norm in FILLERS for t in toks[:i]):
            rest = text[toks[i + k - 1].end:] if i + k <= len(toks) else ""
            return True, _strip_punct(rest)
    # at the end: "открой хром, джарвис"
    i = len(toks) - k
    if i > 0 and matches_at(i):
        return True, _strip_punct(text[:toks[i].start])
    return False, text.strip()


def _strip_punct(s: str) -> str:
    return s.strip(" \t\n,.!?;:—-–")


def match_word_list(text: str, phrases: Iterable[str], strict: bool = False) -> bool:
    """Is the phrase one of the given short answers ("да", "подтверждаю", "отмена")?"""
    raw_words = words(text)
    filtered = [w for w in raw_words if w not in FILLERS]
    for phrase in phrases:
        pw = words(phrase)
        if not pw:
            continue
        # a filler-like answer ("давай", "ок") is compared with the unfiltered phrase
        text_words = raw_words if all(w in FILLERS for w in pw) else filtered
        if not text_words:
            continue
        if text_words == pw:
            return True
        if strict:
            continue
        # "да конечно", "да, подтверждаю"
        if text_words[: len(pw)] == pw and len(text_words) <= len(pw) + 2:
            return True
        if len(text_words) <= len(pw) + 1:
            score, coverage = phrase_score(text_words, pw)
            if coverage >= 0.85 and score >= 0.85:
                return True
    return False
