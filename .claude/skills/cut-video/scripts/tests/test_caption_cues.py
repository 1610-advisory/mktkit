#!/usr/bin/env python3
"""Caption cue grouping (finish-reel.group_caption_cues, also used by resolve-reel's
house_graphics): no cue or line ends on a weak word, no one-word cue or line when
another layout fits, breaks at sentence ends and pauses, word times kept.

Synthetic sentences only. Run: python3 tests/test_caption_cues.py (or pytest).
"""
import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("finish_reel", SCRIPTS / "finish-reel.py")
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)

# The house settings both pipelines use.
HOUSE = dict(max_chars=32, max_dur=2.8, min_cue=0.83, max_lines=2, style="phrase")

SENTENCES = [
    "I think that's what people want out of a home when they come to us.",
    "The kitchen looks good but the island is what makes it work.",
    "The thing that I love most is designing a space for a person who cooks every night.",
    "We take the ideas from the client and design a plan around how they live in those spaces.",
    "If you want an open floor plan you can have it, but bigger is not always better.",
    "Every single room in this house should feel like it was made for one person.",
    "So when we sit down with a family we ask them what they want out of the next twenty years.",
]


def timed(text: str, span: int = 0, t0: float = 0.0, pause_after: dict | None = None):
    """Word tuples with speech-like times: longer words take longer, commas and
    full stops leave a short pause. pause_after maps a word index to an extra gap."""
    out, t = [], t0
    for i, w in enumerate(text.split()):
        d = 0.12 + 0.065 * len(w)
        out.append((round(t, 3), round(t + d, 3), w, span))
        gap = 0.3 if w[-1] in ",." else 0.04
        t += d + gap + (pause_after or {}).get(i, 0.0)
    return out


def texts(cues):
    return [t.replace("\n", " ") for _s, _e, t in cues]


def assert_clean(cues, max_chars: int, max_lines: int = 2) -> None:
    """No cue and no line ends on a weak word; no one-word cue; lines fit."""
    for _s, _e, text in cues:
        lines = text.split("\n")
        assert len(lines) <= max_lines, text
        words = text.split()
        assert len(words) > 1, f"one-word cue: {text!r}"
        assert not fr._is_weak_end(words[-1]), f"cue ends on weak word: {text!r}"
        for ln in lines[:-1]:
            assert not fr._is_weak_end(ln.split()[-1]), f"line ends on weak word: {text!r}"
        for ln in lines:
            assert len(ln) <= max_chars, f"line too long: {ln!r}"
        if len(lines) > 1:
            assert all(len(ln.split()) > 1 for ln in lines), f"lone word on a line: {text!r}"


def test_weak_word_list() -> None:
    for w in ["a", "an", "the", "of", "to", "in", "on", "at", "for", "from", "with",
              "and", "but", "or", "so", "that", "I", "you", "is", "are", "can", "will",
              "my", "your", "our", "it's", "It’s", "\"the"]:
        assert fr._is_weak_end(w), w
    for w in ["of.", "I.", "you,", "is?", "good", "person", "spaces.", "house"]:
        assert not fr._is_weak_end(w), w


def test_house_settings_no_weak_ends_no_orphans() -> None:
    for sentence in SENTENCES:
        words = timed(sentence)
        for max_chars in (18, 24, 32):
            cues = fr.group_caption_cues(words, **{**HOUSE, "max_chars": max_chars})
            assert_clean(cues, max_chars)
            # every word lands exactly once, in order
            assert " ".join(texts(cues)).split() == sentence.split(), texts(cues)


def test_reported_phrases() -> None:
    def cues_for(sentence, **kw):
        return texts(fr.group_caption_cues(timed(sentence), **{**HOUSE, **kw}))

    got = cues_for(SENTENCES[0])                         # "...want out of"
    assert not any(t.endswith((" of", " out of")) for t in got), got
    assert any("out of a home" in t for t in got), got

    got = cues_for(SENTENCES[1])                         # "looks / good", "but the"
    assert got[0] == "The kitchen looks good", got
    assert not any(t.endswith(" the") for t in got), got

    got = cues_for(SENTENCES[2])                         # "that I", "for a person"
    assert not any(t.endswith((" I", " is", " a")) for t in got), got

    got = cues_for(SENTENCES[3])                         # "from the", "design a", "spaces."
    assert not any(t.endswith((" the", " a", " from")) for t in got), got
    assert len(got[-1].split()) >= 2, got

    got = cues_for(SENTENCES[4])                         # "you / can", "bigger is"
    assert not any(t.endswith((" you", " is")) for t in got), got
    assert got[-1].startswith("but bigger is"), got

    got = cues_for(SENTENCES[5])                         # lone "person"
    assert got[-1].endswith("for one person."), got
    assert len(got[-1].split()) >= 3, got


def test_line_breaks_are_balanced() -> None:
    assert fr.wrap_cue_lines("The kitchen looks good", 18, 2) == "The kitchen\nlooks good"
    assert fr.wrap_cue_lines("the thing that I love most", 16, 2) == "the thing\nthat I love most"
    assert fr.wrap_cue_lines("a space for one person", 16, 2) == "a space\nfor one person"
    assert fr.wrap_cue_lines("if you want it you can have it", 18, 2) == \
        "if you want it\nyou can have it"
    # fits one line: stays one line
    assert fr.wrap_cue_lines("looks good", 32, 2) == "looks good"
    # cannot fit two lines: keeps the old overflow behaviour (rest on the last line)
    assert fr.wrap_cue_lines("aaaa bbbb cccc dddd", 4, 2) == "aaaa\nbbbb cccc dddd"


def test_breaks_prefer_sentence_ends_and_pauses() -> None:
    cues = fr.group_caption_cues(
        timed("We gutted it. Then we rebuilt the whole kitchen from scratch."), **HOUSE)
    assert texts(cues)[0] == "We gutted it.", texts(cues)

    # A 0.4 s pause after "room" moves the break there.
    sentence = "we kept the old brick wall in the dining room open to the kitchen"
    flat = texts(fr.group_caption_cues(timed(sentence), **HOUSE))
    assert "in the dining room" not in flat, flat
    idx = sentence.split().index("room")
    cues = fr.group_caption_cues(timed(sentence, pause_after={idx: 0.4}), **HOUSE)
    assert "in the dining room" in texts(cues), texts(cues)


def test_last_word_merges_with_modest_overrun() -> None:
    # Two words 3.1 s apart: one cue (past max_dur by 0.3 s) beats two one-word cues.
    words = [(0.0, 0.4, "Big", 0), (2.7, 3.1, "spaces.", 0)]
    cues = fr.group_caption_cues(words, **HOUSE)
    assert texts(cues) == ["Big spaces."], cues
    # Past max_dur + 0.6 s the words split.
    words = [(0.0, 0.4, "Big", 0), (3.1, 3.5, "spaces.", 0)]
    cues = fr.group_caption_cues(words, **HOUSE)
    assert texts(cues) == ["Big", "spaces."], cues


def test_timing_and_spans_kept() -> None:
    a = timed("We gutted the whole first floor and started over.", span=0)
    b = timed("The new kitchen opens onto the porch.", span=1, t0=a[-1][1] + 0.5)
    words = a + b
    cues = fr.group_caption_cues(words, **HOUSE)
    starts = {w[0]: w for w in words}
    ends = {w[1] for w in words}
    for s, e, text in cues:
        assert s in starts, (s, text)                      # starts on a word start
        assert e in ends or e - s >= HOUSE["min_cue"] - 1e-9, (e, text)
        assert e - s >= HOUSE["min_cue"] - 1e-9, (s, e, text)
    # no cue spans the keep-range join
    first_b = b[0][2]
    assert any(t.startswith(first_b) for t in texts(cues)), texts(cues)
    joined = [t for t in texts(cues) if "over." in t]
    assert joined and joined[0].endswith("over."), texts(cues)


def test_min_cue_rule_kept() -> None:
    words = [(0.0, 0.2, "Wow.", 0), (2.0, 2.5, "Look", 0), (2.55, 3.0, "here.", 0)]
    cues = fr.group_caption_cues(words, **{**HOUSE, "max_dur": 1.5})
    assert cues[0][0] == 0.0 and cues[0][1] >= HOUSE["min_cue"] - 1e-9, cues


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
