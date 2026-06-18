#!/usr/bin/env python3
"""
scan-corpus.py — Optional pre-pass for the voice-analysis skill.

Counts n-gram frequencies (2-7 word phrases), single-word frequencies,
sentence-length stats, punctuation usage, and "avoided" word checks across
a corpus. Outputs JSON to stdout that the skill consumes alongside the
qualitative read of the source files.

USAGE
-----
    python3 scan-corpus.py <path-or-glob> [<path-or-glob> ...] \
        [--min-count 3] [--check-avoided word1,word2,...] \
        [--out scan-results.json]

The script does NOT replace reading the corpus — it gives the analyst a
fast, quantitative starting point. Phrase candidates from this output
still need qualitative review (e.g. is the phrase a quote from someone
else, is it a YAML key, is it noise?).

Exits 0 even if no input files match — the skill should handle that.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

# Words to skip when computing single-word frequencies. Not exhaustive;
# the skill's qualitative pass should catch what this misses.
COMMON_WORDS = {
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i",
    "it", "for", "not", "on", "with", "he", "as", "you", "do", "at",
    "this", "but", "his", "by", "from", "they", "we", "say", "her",
    "she", "or", "an", "will", "my", "one", "all", "would", "there",
    "their", "what", "so", "up", "out", "if", "about", "who", "get",
    "which", "go", "me", "when", "make", "can", "like", "time", "no",
    "just", "him", "know", "take", "people", "into", "year", "your",
    "good", "some", "could", "them", "see", "other", "than", "then",
    "now", "look", "only", "come", "its", "over", "think", "also",
    "back", "after", "use", "two", "how", "our", "work", "first",
    "well", "way", "even", "new", "want", "because", "any", "these",
    "give", "day", "most", "us", "is", "are", "was", "were", "been",
    "being", "has", "had", "having", "did", "does", "doing", "im",
    "ive", "id", "ill", "youre", "youve", "youll", "thats", "its",
    "dont", "doesnt", "didnt", "isnt", "wasnt", "werent",
}

DEFAULT_AVOIDED = [
    "leverage", "unlock", "delve", "elevate", "robust", "seamless",
    "navigate", "synergy", "ecosystem", "supercharge",
    # phrases checked separately
]
DEFAULT_AVOIDED_PHRASES = [
    "in today's fast-paced world",
    "in today's",
    "it's no secret that",
    "in this post",
    "the bottom line is",
    "at the end of the day",
    "without further ado",
]

# Match Markdown YAML frontmatter at the start of a file.
YAML_FM_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)
# Match fenced code blocks.
CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
# Match block quotes (lines starting with >). Common for quoted material.
BLOCKQUOTE_LINE_RE = re.compile(r"^\s*>\s.*$", re.MULTILINE)
# Match URLs/email/file paths so they don't pollute n-grams.
URL_RE = re.compile(r"https?://\S+|www\.\S+|\S+@\S+\.\S+|/[\w./-]+")
# Whisper artifacts.
WHISPER_NOISE_RE = re.compile(
    r"\[(inaudible|crosstalk|laughter|music|silence)\]", re.IGNORECASE
)
# Wiki-links — strip the brackets but keep the text since it may be the
# client's own phrasing.
WIKI_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
# Sentence splitter (rough; good enough for stats, not for citation).
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
# Word tokenizer (alphanumerics + apostrophes).
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’]*")


def clean_text(text: str) -> str:
    """Remove frontmatter, code, blockquotes, URLs, and Whisper artifacts."""
    text = YAML_FM_RE.sub("", text)
    text = CODE_FENCE_RE.sub("", text)
    text = BLOCKQUOTE_LINE_RE.sub("", text)
    text = URL_RE.sub("", text)
    text = WHISPER_NOISE_RE.sub("", text)
    # Strip wiki-link wrapping but keep the text.
    text = WIKI_LINK_RE.sub(r"\1", text)
    return text


def tokenize(text: str) -> list[str]:
    """Lowercase tokens for counting; preserve apostrophes."""
    return [tok.lower().replace("’", "'") for tok in WORD_RE.findall(text)]


def ngram_counts(tokens: list[str], n: int) -> Counter:
    """Return n-gram counter."""
    counts: Counter = Counter()
    if len(tokens) < n:
        return counts
    for i in range(len(tokens) - n + 1):
        counts[" ".join(tokens[i : i + n])] += 1
    return counts


def split_sentences(text: str) -> list[str]:
    """Rough sentence split on terminal punctuation."""
    parts = SENTENCE_SPLIT_RE.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def analyze_file(path: Path) -> dict:
    """Analyze a single file and return its stats."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"path": str(path), "error": str(exc)}

    cleaned = clean_text(raw)
    sentences = split_sentences(cleaned)
    tokens = tokenize(cleaned)

    # Punctuation counts on cleaned text.
    em_dash = cleaned.count("—") + cleaned.count("--")
    ellipsis = cleaned.count("…") + cleaned.count("...")
    exclaim = cleaned.count("!")
    questions = cleaned.count("?")

    sent_lengths = [len(WORD_RE.findall(s)) for s in sentences]
    avg_sent_len = (
        round(sum(sent_lengths) / len(sent_lengths), 2) if sent_lengths else 0.0
    )

    # First-person sentence-start rate.
    fp_starts = sum(
        1
        for s in sentences
        if re.match(r"^(I\b|I'|I’|My\b|We\b|We'|We’)", s.strip())
    )
    fp_rate = round(fp_starts / len(sentences), 3) if sentences else 0.0

    # Sentence-starting conjunctions.
    conj_starts = sum(
        1
        for s in sentences
        if re.match(
            r"^(And|But|So|Because|Or|Yet)\b",
            s.strip(),
            re.IGNORECASE,
        )
    )
    conj_rate = round(conj_starts / len(sentences), 3) if sentences else 0.0

    return {
        "path": str(path),
        "word_count": len(tokens),
        "sentence_count": len(sentences),
        "avg_sentence_length": avg_sent_len,
        "first_person_start_rate": fp_rate,
        "conjunction_start_rate": conj_rate,
        "punctuation": {
            "em_dash": em_dash,
            "ellipsis": ellipsis,
            "exclamation": exclaim,
            "question": questions,
        },
        "tokens": tokens,
    }


def expand_inputs(inputs: list[str]) -> list[Path]:
    """Expand glob patterns and folder paths to a flat list of files."""
    seen: set[Path] = set()
    out: list[Path] = []
    for spec in inputs:
        # If it's a directory, walk it.
        p = Path(spec)
        if p.is_dir():
            matches = [
                f
                for f in p.rglob("*")
                if f.is_file() and f.suffix.lower() in {".md", ".txt"}
            ]
        else:
            matches = [Path(m) for m in glob.glob(spec, recursive=True)]
        for m in matches:
            if m.is_file() and m not in seen:
                seen.add(m)
                out.append(m)
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "inputs",
        nargs="+",
        help="File paths, folders, or glob patterns",
    )
    ap.add_argument(
        "--min-count",
        type=int,
        default=3,
        help="Minimum occurrences for an n-gram to be reported (default: 3)",
    )
    ap.add_argument(
        "--check-avoided",
        type=str,
        default="",
        help="Comma-separated extra words/phrases to check for absence",
    )
    ap.add_argument(
        "--out",
        type=str,
        default="",
        help="Write JSON to this path instead of stdout",
    )
    args = ap.parse_args()

    files = expand_inputs(args.inputs)
    if not files:
        print(json.dumps({"error": "no files matched", "inputs": args.inputs}))
        return 0

    per_file = []
    all_tokens: list[str] = []
    total_words = 0
    total_sentences = 0
    em_dash_total = 0
    ellipsis_total = 0
    exclaim_total = 0
    question_total = 0

    for f in files:
        stats = analyze_file(f)
        if "error" in stats:
            per_file.append(stats)
            continue
        per_file.append(
            {k: v for k, v in stats.items() if k != "tokens"}
        )
        all_tokens.extend(stats["tokens"])
        total_words += stats["word_count"]
        total_sentences += stats["sentence_count"]
        em_dash_total += stats["punctuation"]["em_dash"]
        ellipsis_total += stats["punctuation"]["ellipsis"]
        exclaim_total += stats["punctuation"]["exclamation"]
        question_total += stats["punctuation"]["question"]

    # Build n-gram tables.
    ngrams: dict[str, list[dict]] = {}
    for n in range(2, 8):
        c = ngram_counts(all_tokens, n)
        kept = [
            {"phrase": p, "count": ct}
            for p, ct in c.most_common()
            if ct >= args.min_count
        ]
        ngrams[f"{n}-gram"] = kept[:200]  # cap to keep output sane

    # Single-word frequencies, skipping common words.
    word_counts = Counter(t for t in all_tokens if t not in COMMON_WORDS)
    top_words = [
        {"word": w, "count": c}
        for w, c in word_counts.most_common(150)
        if c >= args.min_count
    ]

    # Avoided check — combine defaults + user list.
    extra = [s.strip() for s in args.check_avoided.split(",") if s.strip()]
    avoided_words = DEFAULT_AVOIDED + [
        e for e in extra if " " not in e and e not in DEFAULT_AVOIDED
    ]
    avoided_phrases = DEFAULT_AVOIDED_PHRASES + [
        e for e in extra if " " in e and e not in DEFAULT_AVOIDED_PHRASES
    ]

    avoided_results = []
    token_counter = Counter(all_tokens)
    joined_lower = " ".join(all_tokens)
    for w in avoided_words:
        avoided_results.append(
            {"term": w, "type": "word", "count": token_counter.get(w.lower(), 0)}
        )
    for p in avoided_phrases:
        avoided_results.append(
            {"term": p, "type": "phrase", "count": joined_lower.count(p.lower())}
        )

    summary = {
        "files_analyzed": len(files),
        "total_words": total_words,
        "total_sentences": total_sentences,
        "avg_sentence_length": (
            round(total_words / total_sentences, 2) if total_sentences else 0.0
        ),
        "punctuation": {
            "em_dash": em_dash_total,
            "ellipsis": ellipsis_total,
            "exclamation": exclaim_total,
            "question": question_total,
            "exclamation_per_1000_words": (
                round(exclaim_total / total_words * 1000, 3)
                if total_words
                else 0.0
            ),
            "em_dash_per_1000_words": (
                round(em_dash_total / total_words * 1000, 3)
                if total_words
                else 0.0
            ),
        },
        "min_count_threshold": args.min_count,
    }

    output = {
        "summary": summary,
        "per_file": per_file,
        "ngrams": ngrams,
        "top_words": top_words,
        "avoided_check": avoided_results,
    }

    payload = json.dumps(output, indent=2)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
