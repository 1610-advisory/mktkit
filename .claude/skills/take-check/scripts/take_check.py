#!/usr/bin/env python3
"""Score raw talking-head takes on the spoken word, before any edit.

Layer 1 measures the whisper word stream (pauses, fillers, restarts, slate
chatter, hook length, silence). Layer 2 asks a model to judge structure.
Nothing in the input folder is written. Exit 0 done, 2 bad input or no
takes, 3 when --fail-on trips.

    python3 take_check.py PATH [PATH ...] --out-dir DIR [--report FILE.md]
"""

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0.0"
HERE = Path(__file__).resolve().parent
PROMPT_PATH = HERE.parent / "resources" / "judge-prompt.md"
EXAMPLE_CONFIG = HERE.parent / "resources" / "take-check.example.json"

DEFAULTS = {
    "pause_s": 1.2,
    "restart_window_s": 10,
    "setup_window_s": 8,
    "hook_max_s": 6,
    "min_speech_s": 4,
    "min_words": 4,
    "fillers_per_min_max": 4,
    "low_confidence_max": 0.15,
    "low_word_prob": 0.5,
    "longest_pause_s": 2.5,
    "no_speech_prob_min": 0.6,
    "fillers": ["um", "uh", "er", "ah", "hmm", "you know", "i mean"],
    "setup_cues": [
        "ready", "yep", "rolling", "all right", "alright", "okay", "ok",
        "go", "action", "are we good",
    ],
    "silence_phrases": ["thank you", "thanks for watching", "you"],
    "prefixes": ["ARoll-", "CB-"],
    "judge_cmd": [
        "pi", "-p", "--no-tools", "--no-mcp",
        "--model", "xai/grok-4.7", "--thinking", "low",
    ],
    "judge_timeout_s": 180,
    "jobs": 3,
}

JUDGE_RUNNER = None  # tests inject a fake judge here; production leaves this None

PROBLEM_TYPES = {
    "contradiction", "restart", "ramble", "filler",
    "dangling_end", "off_topic", "context_missing", "other",
}
USES = {"cut", "trim", "reshoot", "blooper", "voiceover"}
VERDICTS = {"green", "yellow", "red"}
VERDICT_RANK = {"green": 0, "yellow": 1, "red": 2}
SENTENCE_END = (".", "?", "!", ";")
SPOKEN_END = (".", "?", "!")
_SUFFIX = re.compile(r"-(?:Take\d+|BCam|PRIMARY|Phone|False-Start)$")
_VIDEO_EXTS = (".MP4", ".mp4", ".MOV", ".mov")


class InputError(Exception):
    pass


def load_config(path):
    cfg = deepcopy(DEFAULTS)
    if not path:
        return cfg
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise InputError(f"config: {e}") from e
    if not isinstance(raw, dict):
        raise InputError("config must be a JSON object")
    block = raw["take_check"] if isinstance(raw.get("take_check"), dict) else raw
    unknown = [k for k in block if k not in DEFAULTS and not str(k).startswith("_")]
    for key in DEFAULTS:
        if key in block:
            cfg[key] = block[key]
    cfg["_unknown"] = unknown
    return cfg


def config_hash(cfg):
    payload = {k: cfg[k] for k in DEFAULTS}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def token(word):
    return re.sub(r"^[^\w']+|[^\w']+$", "", str(word).strip().lower(), flags=re.UNICODE)


def norm_phrase(text):
    text = str(text).lower().replace("'", "'")
    text = re.sub(r"[^\w\s']+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def r3(value):
    if value is None:
        return None
    return round(float(value), 3)


def iter_words(data):
    for seg in data.get("segments") or []:
        for word in seg.get("words") or []:
            if str(word.get("word", "")).strip():
                yield word


def take_text(data, words):
    joined = "".join(str(w.get("word", "")) for w in words).strip()
    top = str(data.get("text") or "").strip()
    return top or joined


def phrases(items):
    out = []
    for item in items:
        parts = tuple(p for p in (token(p) for p in str(item).split()) if p)
        if parts:
            out.append(parts)
    out.sort(key=len, reverse=True)
    return out


def match_phrases(words, norms, phrase_list, window=None):
    """Left-to-right non-overlapping phrase hits. window limits word start."""
    hits = []
    i = 0
    n = len(words)
    while i < n:
        if window is not None and float(words[i].get("start", 0)) >= window:
            break
        matched = None
        for phrase in phrase_list:
            k = len(phrase)
            if i + k <= n and tuple(norms[i:i + k]) == phrase:
                if window is None or float(words[i].get("start", 0)) < window:
                    matched = k
                    break
        if matched:
            hits.append((i, i + matched))
            i += matched
        else:
            i += 1
    return hits


def find_restarts(words, norms, window):
    found = []
    covered = []
    n = len(words)
    for size in (5, 4, 3):
        grams = {}
        for i in range(n - size + 1):
            gram = tuple(norms[i:i + size])
            if not all(gram):
                continue
            grams.setdefault(gram, []).append(i)
        for gram, idxs in grams.items():
            for a, b in zip(idxs, idxs[1:]):
                if b < a + size:
                    continue
                if float(words[b]["start"]) - float(words[a]["start"]) > window:
                    continue
                if any(s0 <= a and a + size <= s1 and t0 <= b and b + size <= t1
                       for s0, s1, t0, t1 in covered):
                    continue
                covered.append((a, a + size, b, b + size))
                found.append({
                    "ngram": " ".join(gram),
                    "n": size,
                    "first": {"start": r3(words[a]["start"]), "end": r3(words[a + size - 1]["end"])},
                    "second": {"start": r3(words[b]["start"]), "end": r3(words[b + size - 1]["end"])},
                })
    return found


def sentences_of(words):
    groups = []
    buf = []
    for word in words:
        buf.append(word)
        raw = str(word.get("word", "")).rstrip()
        if raw.endswith(SENTENCE_END):
            groups.append(buf)
            buf = []
    if buf:
        groups.append(buf)
    out = []
    for buf in groups:
        raw_last = str(buf[-1].get("word", "")).rstrip()
        out.append({
            "text": "".join(str(w.get("word", "")) for w in buf).strip(),
            "start": r3(buf[0]["start"]),
            "end": r3(buf[-1]["end"]),
            "complete": raw_last.endswith(SENTENCE_END),
        })
    return out


def analyze(data, cfg, video_duration=None):
    words = list(iter_words(data))
    norms = [token(w.get("word", "")) for w in words]
    text = take_text(data, words)
    norm_text = norm_phrase(text)
    joined_norm = norm_phrase("".join(str(w.get("word", "")) for w in words))
    flags = []

    silent_reason = None
    phrases_set = {norm_phrase(p) for p in cfg["silence_phrases"]}
    if norm_text in phrases_set or joined_norm in phrases_set:
        silent_reason = f"known silence hallucination ({norm_text or joined_norm or 'empty'})"
    else:
        segs = data.get("segments") or []
        if segs and all(float(s.get("no_speech_prob", 0) or 0) > float(cfg["no_speech_prob_min"])
                       for s in segs):
            silent_reason = f"every segment no_speech_prob > {cfg['no_speech_prob_min']}"
        elif len(words) < int(cfg["min_words"]):
            silent_reason = f"fewer than {cfg['min_words']} words"
    silent = silent_reason is not None

    if not words:
        metrics = {
            "speech_start": None, "speech_end": None, "lead_silence_s": None,
            "tail_silence_s": r3(video_duration) if video_duration is not None else None,
            "speaking_span_s": 0.0, "word_count": 0, "wpm": None,
            "pauses": [], "longest_pause_s": 0.0,
            "fillers": {"count": 0, "per_min": None, "hits": []},
            "immediate_repeats": [], "restarts": [], "setup_cues": [],
            "clean_in": None, "time_to_first_sentence_end": None,
            "ends_on_sentence": False, "low_confidence_ratio": 0.0,
            "silent": True, "silent_reason": silent_reason or "fewer than 4 words",
        }
        flags.append({"code": "silent", "level": "red", "reason": metrics["silent_reason"]})
        return {
            "metrics": metrics, "flags": flags, "sentences": [], "words": [],
            "text": text, "metrics_verdict": "red", "silent": True,
        }

    speech_start = float(words[0]["start"])
    speech_end = float(words[-1]["end"])
    span = max(0.0, speech_end - speech_start)
    lead = speech_start
    tail = None if video_duration is None else float(video_duration) - speech_end

    pauses = []
    for prev, nxt in zip(words, words[1:]):
        gap = float(nxt["start"]) - float(prev["end"])
        if gap > float(cfg["pause_s"]):
            pauses.append({
                "start": r3(prev["end"]), "end": r3(nxt["start"]), "duration_s": r3(gap),
            })
    longest = max((float(nxt["start"]) - float(prev["end"]) for prev, nxt in zip(words, words[1:])), default=0.0)
    if longest < 0:
        longest = 0.0

    filler_hits_idx = match_phrases(words, norms, phrases(cfg["fillers"]))
    filler_hits = []
    for a, b in filler_hits_idx:
        filler_hits.append({
            "phrase": " ".join(norms[a:b]),
            "start": r3(words[a]["start"]),
            "end": r3(words[b - 1]["end"]),
        })
    per_min = None if span <= 0 else len(filler_hits) / (span / 60.0)

    repeats = []
    i = 1
    while i < len(norms):
        if norms[i] and norms[i] == norms[i - 1]:
            j = i
            while j < len(norms) and norms[j] == norms[i]:
                j += 1
            repeats.append({
                "word": norms[i],
                "start": r3(words[i - 1]["start"]),
                "end": r3(words[j - 1]["end"]),
            })
            i = j
        else:
            i += 1

    restarts = find_restarts(words, norms, float(cfg["restart_window_s"]))
    setup_idx = match_phrases(words, norms, phrases(cfg["setup_cues"]), window=float(cfg["setup_window_s"]))
    setup = [{
        "phrase": " ".join(norms[a:b]),
        "start": r3(words[a]["start"]),
        "end": r3(words[b - 1]["end"]),
    } for a, b in setup_idx]
    if setup_idx and setup_idx[-1][1] < len(words):
        clean_in = float(words[setup_idx[-1][1]]["start"])
    elif setup_idx:
        clean_in = float(words[-1]["end"])
    else:
        clean_in = speech_start

    sents = sentences_of(words)
    hook = None
    for sent in sents:
        if sent["complete"] and float(sent["end"]) > clean_in + 1e-6:
            hook = float(sent["end"]) - clean_in
            break
    if hook is None:
        hook = speech_end - clean_in
    last_raw = str(words[-1].get("word", "")).rstrip()
    ends = last_raw.endswith(SPOKEN_END)

    probs = [float(w["probability"]) for w in words if "probability" in w and w["probability"] is not None]
    low_cut = float(cfg["low_word_prob"])
    low_ratio = 0.0 if not probs else sum(1 for p in probs if p < low_cut) / len(probs)
    wpm = None if span <= 0 else len(words) / (span / 60.0)

    if silent:
        flags.append({"code": "silent", "level": "red", "reason": silent_reason})
    if span < float(cfg["min_speech_s"]):
        flags.append({
            "code": "short_speech", "level": "red",
            "reason": f"speaking span {span:.1f}s (min {cfg['min_speech_s']}s)",
        })
    if per_min is not None and per_min > float(cfg["fillers_per_min_max"]):
        flags.append({
            "code": "fillers_per_min", "level": "yellow",
            "reason": f"{per_min:.1f} fillers/min (max {cfg['fillers_per_min_max']})",
        })
    if low_ratio > float(cfg["low_confidence_max"]):
        flags.append({
            "code": "low_confidence", "level": "yellow",
            "reason": f"{low_ratio:.0%} of words below {low_cut} probability (max {float(cfg['low_confidence_max']):.0%})",
        })
    if longest > float(cfg["longest_pause_s"]):
        flags.append({
            "code": "long_pause", "level": "yellow",
            "reason": f"longest pause {longest:.1f}s (max {cfg['longest_pause_s']}s)",
        })
    if hook is not None and hook > float(cfg["hook_max_s"]):
        flags.append({
            "code": "long_hook", "level": "yellow",
            "reason": f"first sentence ends {hook:.1f}s after clean-in (max {cfg['hook_max_s']}s)",
        })
    if not ends:
        flags.append({
            "code": "no_sentence_end", "level": "yellow",
            "reason": "last word does not end a sentence",
        })
    if restarts:
        flags.append({
            "code": "restart", "level": "yellow",
            "reason": f"{len(restarts)} restart(s); first \"{restarts[0]['ngram']}\"",
        })

    levels = {f["level"] for f in flags}
    if "red" in levels:
        metrics_verdict = "red"
    elif "yellow" in levels:
        metrics_verdict = "yellow"
    else:
        metrics_verdict = "green"

    metrics = {
        "speech_start": r3(speech_start),
        "speech_end": r3(speech_end),
        "lead_silence_s": r3(lead),
        "tail_silence_s": r3(tail) if tail is not None else None,
        "speaking_span_s": r3(span),
        "word_count": len(words),
        "wpm": None if wpm is None else round(wpm, 1),
        "pauses": pauses,
        "longest_pause_s": r3(longest),
        "fillers": {
            "count": len(filler_hits),
            "per_min": None if per_min is None else round(per_min, 2),
            "hits": filler_hits,
        },
        "immediate_repeats": repeats,
        "restarts": restarts,
        "setup_cues": setup,
        "clean_in": r3(clean_in),
        "time_to_first_sentence_end": r3(hook),
        "ends_on_sentence": ends,
        "low_confidence_ratio": round(low_ratio, 4),
        "silent": silent,
        "silent_reason": silent_reason,
    }
    return {
        "metrics": metrics, "flags": flags, "sentences": sents, "words": words,
        "text": text, "metrics_verdict": metrics_verdict, "silent": silent,
    }


def fmt_ts(value):
    if value is None:
        return "-"
    tenths = int(round(max(0.0, float(value)) * 10))
    minutes, rem = divmod(tenths, 600)
    return f"{minutes:02d}:{rem / 10:04.1f}"


def piece_key(stem):
    prev = None
    while prev != stem:
        prev = stem
        stem = _SUFFIX.sub("", stem)
    return stem


def filler_count_of(row):
    if "filler_count" in row:
        return row["filler_count"]
    return ((row.get("metrics") or {}).get("fillers") or {}).get("count", 0)


def structure_of(row):
    if row.get("structure_score") is not None:
        return row["structure_score"]
    judge = row.get("judge") or {}
    return judge.get("structure_score")


def best_row(rows):
    return min(rows, key=lambda row: (
        VERDICT_RANK.get(row.get("verdict"), 9),
        -(structure_of(row) if structure_of(row) is not None else -1),
        filler_count_of(row),
        row.get("stem", ""),
    ))


def group_results(rows):
    groups = {}
    for row in rows:
        groups.setdefault(piece_key(row["stem"]), []).append(row)
    return {key: value for key, value in groups.items() if len(value) > 1}


def extract_json(text):
    if not text:
        raise ValueError("empty judge reply")
    decoder = json.JSONDecoder()
    start = 0
    while True:
        i = text.find("{", start)
        if i < 0:
            raise ValueError("no JSON object in reply")
        try:
            obj, _ = decoder.raw_decode(text[i:])
        except json.JSONDecodeError:
            start = i + 1
            continue
        if isinstance(obj, dict):
            return obj
        start = i + 1


def _score(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be an integer 1-5")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{name} must be an integer 1-5")
    number = int(value)
    if number < 1 or number > 5:
        raise ValueError(f"{name} must be an integer 1-5")
    return number


def _num(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    return float(value)


def validate_judge(obj):
    if not isinstance(obj, dict):
        raise ValueError("judge reply is not an object")
    required = [
        "hook", "main_point", "single_idea", "payoff", "problems",
        "suggested_in", "suggested_out", "structure_score", "verdict", "use", "reason",
    ]
    missing = [key for key in required if key not in obj]
    if missing:
        raise ValueError("missing " + ", ".join(missing))
    hook = obj["hook"]
    if not isinstance(hook, dict):
        raise ValueError("hook must be an object")
    for key in ("quote", "start", "end", "score"):
        if key not in hook:
            raise ValueError(f"hook.{key} missing")
    if not isinstance(hook["quote"], str) or not hook["quote"].strip():
        raise ValueError("hook.quote must be a non-empty string")
    if not isinstance(obj["main_point"], str) or not obj["main_point"].strip():
        raise ValueError("main_point must be a non-empty string")
    if not isinstance(obj["single_idea"], bool):
        raise ValueError("single_idea must be a boolean")
    payoff = obj["payoff"]
    if payoff is not None:
        if not isinstance(payoff, dict):
            raise ValueError("payoff must be an object or null")
        for key in ("quote", "start", "end"):
            if key not in payoff:
                raise ValueError(f"payoff.{key} missing")
        if not isinstance(payoff["quote"], str) or not payoff["quote"].strip():
            raise ValueError("payoff.quote must be a non-empty string")
    if not isinstance(obj["problems"], list):
        raise ValueError("problems must be a list")
    clean_problems = []
    for i, problem in enumerate(obj["problems"]):
        if not isinstance(problem, dict):
            raise ValueError(f"problems[{i}] must be an object")
        for key in ("type", "quote", "start", "end", "note"):
            if key not in problem:
                raise ValueError(f"problems[{i}].{key} missing")
        if problem["type"] not in PROBLEM_TYPES:
            raise ValueError(f"problems[{i}].type invalid")
        if not isinstance(problem["quote"], str) or not problem["quote"].strip():
            raise ValueError(f"problems[{i}].quote must be a non-empty string")
        if not isinstance(problem["note"], str):
            raise ValueError(f"problems[{i}].note must be a string")
        clean_problems.append({
            "type": problem["type"],
            "quote": problem["quote"],
            "start": _num(problem["start"], f"problems[{i}].start"),
            "end": _num(problem["end"], f"problems[{i}].end"),
            "note": problem["note"],
        })
    if obj["verdict"] not in VERDICTS:
        raise ValueError("verdict invalid")
    if obj["use"] not in USES:
        raise ValueError("use invalid")
    if not isinstance(obj["reason"], str) or not obj["reason"].strip():
        raise ValueError("reason must be a non-empty string")
    out = {
        "hook": {
            "quote": hook["quote"],
            "start": _num(hook["start"], "hook.start"),
            "end": _num(hook["end"], "hook.end"),
            "score": _score(hook["score"], "hook.score"),
        },
        "main_point": obj["main_point"].strip(),
        "single_idea": obj["single_idea"],
        "payoff": None if payoff is None else {
            "quote": payoff["quote"],
            "start": _num(payoff["start"], "payoff.start"),
            "end": _num(payoff["end"], "payoff.end"),
        },
        "problems": clean_problems,
        "suggested_in": _num(obj["suggested_in"], "suggested_in"),
        "suggested_out": _num(obj["suggested_out"], "suggested_out"),
        "structure_score": _score(obj["structure_score"], "structure_score"),
        "verdict": obj["verdict"],
        "use": obj["use"],
        "reason": obj["reason"].strip(),
    }
    return out


def quote_ok(quote, normalized_text):
    folded = norm_phrase(quote)
    return bool(folded) and folded in normalized_text


def nearest(value, options):
    return min(options, key=lambda item: (abs(item - value), item))


def snap_in(value, words, speech_start, speech_end):
    value = min(speech_end, max(speech_start, float(value)))
    starts = [float(w["start"]) for w in words]
    return nearest(value, starts) if starts else value


def snap_out(value, words, speech_start, speech_end):
    value = min(speech_end, max(speech_start, float(value)))
    ends = [float(w["end"]) for w in words]
    return nearest(value, ends) if ends else value


def finish_judge(reply, analysis):
    obj = validate_judge(extract_json(reply))
    words = analysis["words"]
    normalized = norm_phrase(analysis.get("text") or "")
    joined = norm_phrase("".join(str(w.get("word", "")) for w in words))
    # Keep a quote if it sits in either the top-level text or the word stream.
    blobs = [item for item in (normalized, joined) if item]
    dropped = []

    def keep(quote):
        return any(quote_ok(quote, item) for item in blobs)

    speech_start = float(words[0]["start"]) if words else 0.0
    speech_end = float(words[-1]["end"]) if words else 0.0
    if not keep(obj["hook"]["quote"]):
        dropped.append({"where": "hook.quote", "quote": obj["hook"]["quote"]})
        obj["hook"]["quote"] = None
    if obj["payoff"] is not None and not keep(obj["payoff"]["quote"]):
        dropped.append({"where": "payoff.quote", "quote": obj["payoff"]["quote"]})
        obj["payoff"] = None
    kept = []
    for i, problem in enumerate(obj["problems"]):
        if keep(problem["quote"]):
            kept.append(problem)
        else:
            dropped.append({"where": f"problems[{i}].quote", "quote": problem["quote"]})
    obj["problems"] = kept

    if words:
        obj["hook"]["start"] = r3(snap_in(obj["hook"]["start"], words, speech_start, speech_end))
        obj["hook"]["end"] = r3(snap_out(obj["hook"]["end"], words, speech_start, speech_end))
        if obj["payoff"] is not None:
            obj["payoff"]["start"] = r3(snap_in(obj["payoff"]["start"], words, speech_start, speech_end))
            obj["payoff"]["end"] = r3(snap_out(obj["payoff"]["end"], words, speech_start, speech_end))
        for problem in obj["problems"]:
            problem["start"] = r3(snap_in(problem["start"], words, speech_start, speech_end))
            problem["end"] = r3(snap_out(problem["end"], words, speech_start, speech_end))
        obj["suggested_in"] = r3(snap_in(obj["suggested_in"], words, speech_start, speech_end))
        obj["suggested_out"] = r3(snap_out(obj["suggested_out"], words, speech_start, speech_end))
        if obj["suggested_out"] + 1e-6 < obj["suggested_in"]:
            later = [float(w["end"]) for w in words if float(w["end"]) >= obj["suggested_in"] - 1e-6]
            obj["suggested_out"] = r3(later[0] if later else speech_end)
    return obj, dropped


def layer1_summary(analysis):
    m = analysis["metrics"]
    flags = analysis["flags"]
    flag_txt = "none" if not flags else "; ".join(f"{f['code']}: {f['reason']}" for f in flags)
    return (
        f"speech_start={m['speech_start']} speech_end={m['speech_end']} "
        f"speaking_span_s={m['speaking_span_s']} wpm={m['wpm']}\n"
        f"lead_silence_s={m['lead_silence_s']} tail_silence_s={m['tail_silence_s']}\n"
        f"fillers={m['fillers']['count']} per_min={m['fillers']['per_min']} "
        f"longest_pause_s={m['longest_pause_s']} restarts={len(m['restarts'])} "
        f"immediate_repeats={len(m['immediate_repeats'])}\n"
        f"clean_in={m['clean_in']} hook_s={m['time_to_first_sentence_end']} "
        f"ends_on_sentence={'yes' if m['ends_on_sentence'] else 'no'} "
        f"low_confidence_ratio={m['low_confidence_ratio']}\n"
        f"metrics_verdict={analysis['metrics_verdict']}\n"
        f"flags: {flag_txt}"
    )


def sentence_block(sentences):
    if not sentences:
        return "(no sentences)"
    lines = []
    for i, sent in enumerate(sentences, 1):
        lines.append(f"{i}. [{sent['start']}-{sent['end']}] {sent['text']}")
    return "\n".join(lines)


def build_prompt(analysis, context):
    template = PROMPT_PATH.read_text(encoding="utf-8")
    return (
        template
        .replace("{{CONTEXT}}", context.strip() if context else "(none)")
        .replace("{{LAYER1}}", layer1_summary(analysis))
        .replace("{{SENTENCES}}", sentence_block(analysis["sentences"]))
    )


def run_judge_process(cmd, prompt, timeout):
    """Run the judge. Prompt goes to stdin unless an argv element contains {prompt}.

    pi -p reads a trailing message, and with no message it reads stdin
    (checked against `pi --help` and a live piped prompt). stdin is the
    default because the spec argv has no message slot.
    """
    use_stdin = not any("{prompt}" in str(part) for part in cmd)
    argv = [str(part).replace("{prompt}", prompt) for part in cmd]
    try:
        proc = subprocess.run(
            argv,
            input=prompt if use_stdin else None,
            text=True,
            capture_output=True,
            timeout=timeout,
            stdin=None if use_stdin else subprocess.DEVNULL,
        )
    except FileNotFoundError as e:
        raise RuntimeError(f"judge command not found: {cmd[0]}") from e
    except subprocess.TimeoutExpired as e:
        raise TimeoutError(f"judge timed out after {timeout}s") from e
    return proc.stdout or "", proc.stderr or "", proc.returncode


def judge_with_retry(prompt, cfg, runner=None):
    cmd = list(cfg["judge_cmd"])
    timeout = float(cfg["judge_timeout_s"])
    runner = runner or run_judge_process
    last_error = "judge failed"
    current = prompt
    for attempt in (1, 2):
        try:
            stdout, stderr, code = runner(cmd, current, timeout)
        except (TimeoutError, OSError, RuntimeError) as e:
            last_error = str(e)
            current = prompt + "\n\nReply with JSON only.\n"
            continue
        try:
            obj = validate_judge(extract_json(stdout))
            return obj, None, stdout
        except ValueError as e:
            last_error = str(e)
            if code not in (0, None) and not (stdout or "").strip():
                last_error = f"judge exited {code}: {last_error}"
            current = prompt + "\n\nReply with JSON only.\n"
            _ = stderr
            continue
    return None, last_error, None


def metrics_use(analysis):
    if analysis["silent"] or analysis["metrics_verdict"] == "red":
        return "none"
    if analysis["metrics_verdict"] == "yellow":
        return "trim"
    return "cut"


def worse(a, b):
    return a if VERDICT_RANK[a] >= VERDICT_RANK[b] else b


def combine(record):
    analysis = record["_analysis"]
    judge = record.get("judge")
    if judge and not record.get("judge_error"):
        record["verdict"] = worse(analysis["metrics_verdict"], judge["verdict"])
        record["use"] = judge["use"]
        record["suggested_in"] = judge["suggested_in"]
        record["suggested_out"] = judge["suggested_out"]
        record["structure_score"] = judge["structure_score"]
    else:
        record["verdict"] = analysis["metrics_verdict"]
        record["use"] = metrics_use(analysis)
        if analysis["silent"]:
            record["suggested_in"] = None
            record["suggested_out"] = None
        else:
            record["suggested_in"] = analysis["metrics"]["clean_in"]
            record["suggested_out"] = analysis["metrics"]["speech_end"]
        record["structure_score"] = None
    record["metrics_verdict"] = analysis["metrics_verdict"]


def sibling_video(json_path):
    stem = json_path.stem
    video_dir = json_path.parent.parent / "Video"
    for ext in _VIDEO_EXTS:
        candidate = video_dir / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    return None


def probe_duration(path):
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    token = (proc.stdout or "").strip().splitlines()
    if not token:
        return None
    try:
        return float(token[0].strip())
    except ValueError:
        return None


def collect_inputs(paths, prefixes, all_json):
    files = []
    roots = []
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            raise InputError(f"not found: {raw}")
        if path.is_file():
            if path.suffix.lower() != ".json":
                raise InputError(f"not a json file: {raw}")
            files.append(path)
            roots.append(path.parent)
        elif path.is_dir():
            roots.append(path)
            found = sorted(path.glob("**/Audio/*.json"))
            for item in found:
                if all_json or any(item.stem.startswith(prefix) for prefix in prefixes):
                    files.append(item)
        else:
            raise InputError(f"not a file or folder: {raw}")
    seen = set()
    unique = []
    for item in files:
        key = str(item.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(item)
    if not unique:
        raise InputError("no takes found")
    return unique, roots


def inside(child, parent):
    child = child.resolve()
    parent = parent.resolve()
    return child == parent or parent in child.parents


def guard_outputs(out_dir, report, roots):
    for root in roots:
        if inside(out_dir, root):
            raise InputError(f"refusing to write --out-dir inside an input folder: {out_dir}")
        if inside(report, root):
            raise InputError(f"refusing to write --report inside an input folder: {report}")


def cell(text, limit=None):
    text = "" if text is None else str(text)
    text = text.replace("|", "/").replace("\n", " ").strip()
    if limit and len(text) > limit:
        text = text[: limit - 3].rstrip() + "..."
    return text or "-"


def length_of(record):
    video = record.get("video") or {}
    if video.get("duration_s") is not None:
        return fmt_ts(video["duration_s"])
    end = (record.get("metrics") or {}).get("speech_end")
    if end is not None:
        return fmt_ts(end)
    return "-"


def hook_quote(record):
    judge = record.get("judge") or {}
    hook = (judge.get("hook") or {}).get("quote")
    if hook:
        return hook
    clean = (record.get("metrics") or {}).get("clean_in")
    for sent in record.get("sentences") or []:
        if clean is None or float(sent["end"]) > float(clean) + 1e-6:
            return sent["text"]
    return None


def top_reasons(record):
    reasons = [f["reason"] for f in record.get("flags") or []]
    judge = record.get("judge") or {}
    if judge.get("reason") and record.get("verdict") != "green":
        reasons.append(judge["reason"])
    if record.get("judge_error"):
        reasons.append(record["judge_error"])
    return "; ".join(reasons[:3])


def sort_key(record):
    score = structure_of(record)
    return (
        VERDICT_RANK.get(record.get("verdict"), 9),
        -(score if score is not None else -999),
        record.get("stem", ""),
    )


def render_report(records):
    ordered = sorted(records, key=sort_key)
    counts = {name: sum(1 for r in records if r["verdict"] == name) for name in ("red", "yellow", "green")}
    lines = [
        "# Take check",
        "",
        f"Scored {len(records)} takes. Red {counts['red']}, yellow {counts['yellow']}, green {counts['green']}.",
        "",
        "| take | length | verdict | use | in-out | hook | top reasons |",
        "|---|---|---|---|---|---|---|",
    ]
    for record in ordered:
        inn = fmt_ts(record.get("suggested_in"))
        out = fmt_ts(record.get("suggested_out"))
        span = "-" if record.get("suggested_in") is None else f"{inn}-{out}"
        lines.append(
            "| `{take}` | {length} | {verdict} | {use} | {span} | {hook} | {reasons} |".format(
                take=cell(record["stem"]),
                length=length_of(record),
                verdict=record.get("verdict") or "-",
                use=record.get("use") or "-",
                span=span,
                hook=cell(hook_quote(record), 60),
                reasons=cell(top_reasons(record), 140),
            )
        )
    lines.extend(["", "## Needs a look", ""])
    details = [r for r in ordered if r.get("verdict") in ("yellow", "red")]
    if not details:
        lines.append("None.")
    for record in details:
        lines.append(f"### `{record['stem']}` — {record['verdict']}, {record['use']}")
        lines.append("")
        if record.get("flags"):
            lines.append("Flags:")
            lines.append("")
            for flag in record["flags"]:
                lines.append(f"- **{flag['code']}** — {flag['reason']}")
            lines.append("")
        problems = (record.get("judge") or {}).get("problems") or []
        if problems:
            lines.append("Problems:")
            lines.append("")
            for problem in problems:
                lines.append(
                    f"- **{problem['type']}** {fmt_ts(problem['start'])}-{fmt_ts(problem['end'])} "
                    f"\"{problem['quote']}\" — {problem['note']}"
                )
            lines.append("")
        if record.get("judge_error"):
            lines.append(f"Judge error: {record['judge_error']}")
            lines.append("")
    lines.extend(["## Takes of the same piece", ""])
    groups = group_results(records)
    if not groups:
        lines.append("No stems differed only by a take or camera suffix.")
    for key in sorted(groups):
        rows = groups[key]
        winner = best_row(rows)
        score = structure_of(winner)
        score_txt = "n/a" if score is None else str(score)
        lines.append(f"### `{key}`")
        lines.append("")
        lines.append(
            f"Best: `{winner['stem']}` ({winner['verdict']}, structure {score_txt}, "
            f"{filler_count_of(winner)} fillers)"
        )
        lines.append("")
        lines.append("| take | verdict | structure | fillers |")
        lines.append("|---|---|---|---|")
        for row in sorted(rows, key=sort_key):
            score = structure_of(row)
            lines.append(
                f"| `{row['stem']}` | {row['verdict']} | "
                f"{'n/a' if score is None else score} | {filler_count_of(row)} |"
            )
        lines.append("")
    lines.append(f"Tool take-check {VERSION}.")
    lines.append("")
    return "\n".join(lines)


def output_stem(stem, path, seen):
    if stem not in seen:
        seen[stem] = str(path)
        return stem
    digest = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:8]
    return f"{stem}-{digest}"


def public_record(record, path, video, cfg, context):
    analysis = record["_analysis"]
    return {
        "tool": "take-check",
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input": str(path.resolve()),
        "stem": record["stem"],
        "video": video,
        "metrics": analysis["metrics"],
        "flags": analysis["flags"],
        "sentences": analysis["sentences"],
        "judge": record.get("judge"),
        "judge_skipped": record.get("judge_skipped"),
        "judge_error": record.get("judge_error"),
        "judge_dropped": record.get("judge_dropped") or [],
        "metrics_verdict": record.get("metrics_verdict"),
        "verdict": record.get("verdict"),
        "use": record.get("use"),
        "suggested_in": record.get("suggested_in"),
        "suggested_out": record.get("suggested_out"),
        "structure_score": record.get("structure_score"),
        "config_hash": config_hash(cfg),
        "context": context or None,
    }


def judge_job(item, cfg, context, runner):
    prompt = build_prompt(item["_analysis"], context)
    raw, error, reply = judge_with_retry(prompt, cfg, runner=runner)
    if error or raw is None:
        return {"judge_error": error or "judge failed", "judge": None, "judge_dropped": []}
    try:
        judge, dropped = finish_judge(reply if reply is not None else json.dumps(raw), item["_analysis"])
    except ValueError as e:
        return {"judge_error": str(e), "judge": None, "judge_dropped": []}
    return {"judge": judge, "judge_error": None, "judge_dropped": dropped}


def load_whisper(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise InputError(f"{path}: invalid JSON ({e})") from e
    if not isinstance(data, dict) or not isinstance(data.get("segments"), list):
        raise InputError(f"{path}: expected whisper JSON with a segments list")
    return data


def score_paths(files, cfg, context, judge_mode, jobs, runner=None):
    if runner is None:
        runner = JUDGE_RUNNER
    loaded = [(path, load_whisper(path)) for path in files]
    records = []
    for path, data in loaded:
        video_path = sibling_video(path)
        video = None
        duration = None
        if video_path is not None:
            duration = probe_duration(video_path)
            video = {"path": str(video_path.resolve()), "duration_s": r3(duration) if duration is not None else None}
        analysis = analyze(data, cfg, video_duration=duration)
        record = {
            "stem": path.stem,
            "input_path": path,
            "video": video,
            "_analysis": analysis,
            "metrics": analysis["metrics"],
            "flags": analysis["flags"],
            "sentences": analysis["sentences"],
            "judge": None,
            "judge_skipped": "silent" if analysis["silent"] else ("disabled" if judge_mode == "none" else None),
            "judge_error": None,
            "judge_dropped": [],
        }
        records.append(record)

    pending = [r for r in records if r["judge_skipped"] is None]
    if pending:
        workers = max(1, min(int(jobs), len(pending)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(judge_job, item, cfg, context, runner): item for item in pending
            }
            for future in as_completed(futures):
                item = futures[future]
                try:
                    item.update(future.result())
                except Exception as e:  # a judge bug should not hide the metrics
                    item["judge_error"] = f"judge crashed: {e}"
                    item["judge"] = None
    for record in records:
        combine(record)
        if record.get("judge_error"):
            print(f"{record['stem']}: {record['judge_error']}", file=sys.stderr)
    return records


def write_outputs(records, out_dir, report_path, cfg, context):
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    seen = {}
    written = []
    for record in records:
        stem = output_stem(record["stem"], record["input_path"], seen)
        record["stem"] = stem
        payload = public_record(record, record["input_path"], record.get("video"), cfg, context)
        dest = out_dir / f"{stem}.take.json"
        dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(dest)
    report_path.write_text(render_report(records), encoding="utf-8")
    return written


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("paths", nargs="+", help="whisper JSON file or shoot folder")
    parser.add_argument("--out-dir", required=True, help="where <stem>.take.json files are written")
    parser.add_argument("--report", default=None, help="markdown report (default: <out-dir>/take-report.md)")
    parser.add_argument("--all", action="store_true", help="folder scan: keep every Audio JSON")
    parser.add_argument("--prefix", action="append", default=None,
                        help="folder-scan stem prefix, comma-separated; replaces the default list")
    parser.add_argument("--context", default=None, help="what the take was meant to be")
    parser.add_argument("--judge", default=None, choices=["none"], help="none skips the model judge")
    parser.add_argument("--judge-cmd", default=None, help="shell-split argv overriding judge_cmd")
    parser.add_argument("--jobs", type=int, default=None, help="parallel judge calls (default 3)")
    parser.add_argument("--fail-on", choices=["red", "yellow"], default=None,
                        help="exit 3 if a take hits this level (yellow includes red)")
    parser.add_argument("--config", default=None, help="threshold JSON, or an object with a take_check key")
    return parser.parse_args(argv)


def main(argv=None):
    try:
        return _main(argv)
    except InputError as e:
        print(f"take-check: {e}", file=sys.stderr)
        return 2


def _main(argv):
    args = parse_args(argv)
    cfg = load_config(args.config)
    if cfg.get("_unknown"):
        print("take-check: ignoring unknown config keys: " + ", ".join(cfg["_unknown"]), file=sys.stderr)
    if args.judge_cmd:
        cfg["judge_cmd"] = shlex.split(args.judge_cmd)
    if args.jobs is not None:
        if args.jobs < 1:
            raise InputError("--jobs must be >= 1")
        cfg["jobs"] = args.jobs
    prefixes = list(cfg["prefixes"])
    if args.prefix:
        prefixes = []
        for item in args.prefix:
            prefixes.extend([part for part in item.split(",") if part])
        if not prefixes:
            raise InputError("--prefix did not contain a prefix")
    files, roots = collect_inputs(args.paths, prefixes, args.all)
    out_dir = Path(args.out_dir)
    report = Path(args.report) if args.report else out_dir / "take-report.md"
    guard_outputs(out_dir, report, roots)
    judge_mode = "none" if args.judge == "none" else "auto"
    records = score_paths(files, cfg, args.context, judge_mode, cfg["jobs"], runner=None)
    written = write_outputs(records, out_dir, report, cfg, args.context)
    for record in sorted(records, key=sort_key):
        print(f"{record['stem']}  {record['verdict']}  {record['use']}")
    print(f"wrote {len(written)} take file(s), report {report}")
    if args.fail_on:
        limit = VERDICT_RANK[args.fail_on]
        if any(VERDICT_RANK.get(r["verdict"], 0) >= limit for r in records):
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
