#!/usr/bin/env python3
"""Rank B-roll candidates for a spoken line, and write verified subjects back.

Sourcing ladder (encoded in the score, not in a filename grep):
  1. Same project first. --project restricts; --prefer-project adds +3.0 so
     the job's own footage outranks a generic library still.
  2. Verified subjects. Token match against descriptions[].subject is the
     strongest text signal (+2.0 per query token, max +6). A rejects[].subject
     that matches the query removes the file entirely, so a still judged "not
     a hidden door" is never proposed for "hidden door" again.
  3. Captions and filename tokens. Okapi BM25 (k1=1.2, b=0.75) over
     caption + name_tokens, with light stemming (strip plural s, ing, ed)
     and the trade synonym table in this file. Phrase keys are matched
     bidirectionally (query "hidden door" expands to pocket/concealed/jib).
  4. CLIP. When the index has embeddings and open_clip imports, embed the
     query text and add +4.0 * cosine. Real matches sit around cosine 0.15
     to 0.35, so this term is about +0.6 to +1.4. Without embeddings the
     term is 0 and search still works.
  5. Orientation fit. Portrait +0.5 (9:16 delivery), square +0.2, landscape 0.
  6. Video preference. --prefer-video (default) adds --video-bonus (1.5) so an
     exact raw clip outranks a photo. Frame-level CLIP uses the MAX cosine
     over frames, not the mean. --no-prefer-video turns the bonus off.
  7. Recency tie-break. Newer `taken` wins ties.

Write-back:
  --confirm PATH --subject TEXT [--by vision-check|human]
      appends to descriptions and rewrites the index atomically.
  --reject PATH --subject TEXT
      appends to rejects. Next search for that subject drops the file.

--lines-from-manifest reads each broll[] row that has a line and an empty
path, searches, and emits proposals. It does not edit the manifest. A
project hint may be parsed from notes (`project: NAME`); there is no
manifest project field.

--sheet writes a labelled contact sheet of the top candidates. If
contact-sheet.py exists beside this script and its --help exposes output
and label flags, it is used; otherwise a Pillow grid is drawn here.

Exit codes:
  0  success, including --help and --dry-run
  1  usage or processing error
  2  a required input path is missing
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import struct
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


BM25_K1 = 1.2
BM25_B = 0.75
CLIP_WEIGHT = 4.0
PREFER_PROJECT = 3.0
DEFAULT_VIDEO_BONUS = 1.5
DEFAULT_PUNCH_DUR = 2.5
DEFAULT_MIN_CLIP_S = 1.5
# A subject a person (or a vision check) confirmed is the strongest evidence
# the index holds; it must outrank filename tokens plus the video bonus.
# Raised 2026-09-07 after a confirmed hidden-door still ranked below a
# pantry-wall clip that merely carried the tokens "built" and "wall".
VERIFIED_PER_TOKEN = 4.0
VERIFIED_CAP = 12.0
ORIENT_PORTRAIT = 0.5
ORIENT_SQUARE = 0.2
DEFAULT_TOP = 8
SCHEMA_READ = {
    "broll-index/1", "broll-index/1.1", "broll-index/1.2", "broll-index/1.3", None,
}
SHEET_MAX_W = 1600
SHEET_COLS = 4
SHEET_THUMB = 360

STOP = {
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "or",
    "is", "was", "with", "from", "by", "as", "vs", "via", "into", "onto",
    "over", "under", "this", "that", "we", "it", "its",
}

# Trade vocabulary that keeps recurring in this kind of content.
# Bidirectional: a query matching a key or any synonym expands to all tokens.
SYNONYMS: dict[str, list[str]] = {
    # A pocket door is not a hidden door (trade terms are literal, 2026-09-07).
    "hidden door": ["concealed door", "flush door", "secret door", "jib door"],
    "arch": ["arched", "arches", "archway", "archways", "arched opening", "arched doorway"],
    "pocket door": ["sliding door", "cavity slider", "slider door", "recessed door"],
    "framing": ["studs", "lumber", "frame"],
    "foundation": ["footing", "slab", "concrete pour"],
    "demo": ["demolition", "tear out", "tearout", "gut"],
    "kitchen": ["island", "cabinets", "range"],
    "bath": ["bathroom", "vanity", "tile", "shower"],
    "exterior": ["siding", "roof", "facade"],
    "plans": ["blueprint", "drawings", "floor plan"],
    "trim": ["casing", "baseboard", "crown"],
    "electrical": ["wiring", "panel", "outlet"],
    "plumbing": ["pipe", "drain", "rough in"],
    "floor": ["hardwood", "subfloor"],
}

TOKEN_RE = re.compile(r"[a-z0-9]+")
PROJECT_HINT_RE = re.compile(r"(?i)\bproject\s*[:=]\s*([A-Za-z0-9._-]+)")


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def die(msg: str, code: int = 1) -> None:
    eprint(msg)
    raise SystemExit(code)


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall((text or "").lower())


def stem(word: str) -> str:
    w = (word or "").lower()
    if len(w) > 5 and w.endswith("ing"):
        w = w[:-3]
    elif len(w) > 4 and w.endswith("ed"):
        w = w[:-2]
    elif len(w) > 4 and w.endswith("es") and w[-3] in "hxsz":
        # arches -> arch, finishes -> finish, boxes -> box (not "arche")
        w = w[:-2]
    elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    return w


def stem_tokens(text: str, drop_stop: bool = True) -> list[str]:
    out = []
    for t in tokenize(text):
        if drop_stop and t in STOP:
            continue
        s = stem(t)
        if s:
            out.append(s)
    return out


def expand_query(query: str) -> list[str]:
    """Query tokens plus synonym expansions. Order preserved, de-duped."""
    raw = [stem(t) for t in tokenize(query)]
    raw_set = set(raw)
    expanded: list[str] = []
    seen: set[str] = set()

    def add(tok: str) -> None:
        if tok and tok not in seen and tok not in STOP:
            seen.add(tok)
            expanded.append(tok)

    for t in stem_tokens(query, drop_stop=True):
        add(t)

    def phrase_hits(phrase: str) -> bool:
        pt = [stem(t) for t in tokenize(phrase)]
        return bool(pt) and set(pt) <= raw_set

    for key, vals in SYNONYMS.items():
        phrases = [key, *vals]
        if any(phrase_hits(p) for p in phrases):
            for p in phrases:
                for t in tokenize(p):
                    if t not in STOP:
                        add(stem(t))
    return expanded


def doc_tokens(entry: dict) -> list[str]:
    parts = list(entry.get("name_tokens") or [])
    cap = entry.get("caption") or ""
    if cap:
        parts.extend(tokenize(cap))
    return [stem(t) for t in parts if t and t not in STOP]


def bm25_scores(query_toks: list[str], docs: list[list[str]]) -> list[float]:
    """Okapi BM25 over a list of token lists. Empty query or corpus -> zeros."""
    n_docs = len(docs)
    if not query_toks or n_docs == 0:
        return [0.0] * n_docs
    df: dict[str, int] = {}
    for tok in set(query_toks):
        df[tok] = sum(1 for d in docs if tok in d)
    avgdl = sum(len(d) for d in docs) / n_docs
    scores = []
    for doc in docs:
        dl = len(doc) or 1
        tf: dict[str, int] = {}
        for t in doc:
            tf[t] = tf.get(t, 0) + 1
        s = 0.0
        for tok in query_toks:
            n_qi = df.get(tok, 0)
            # +1 keeps IDF non-negative
            idf = math.log((n_docs - n_qi + 0.5) / (n_qi + 0.5) + 1.0)
            f = tf.get(tok, 0)
            if f == 0:
                continue
            denom = f + BM25_K1 * (1.0 - BM25_B + BM25_B * dl / (avgdl or 1.0))
            s += idf * (f * (BM25_K1 + 1.0)) / denom
        scores.append(s)
    return scores


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / math.sqrt(na * nb)


def decode_clip(
    clip,
    clip_dtype: str | None = None,
    clip_dim: int | None = None,
) -> list[float] | None:
    """Read a clip field stored as a float list or an f16 base64 string."""
    if clip is None or clip == [] or clip == "":
        return None
    if isinstance(clip, list):
        return [float(x) for x in clip]
    if not isinstance(clip, str):
        return None
    dtype = (clip_dtype or "f16").lower()
    if dtype != "f16":
        return None
    try:
        raw = base64.b64decode(clip)
    except Exception:
        return None
    if len(raw) < 2 or len(raw) % 2:
        return None
    n = len(raw) // 2
    if clip_dim is not None and n != int(clip_dim):
        return None
    try:
        return list(struct.unpack(f"<{n}e", raw))
    except Exception:
        return None


def entry_clip_vector(entry: dict) -> list[float] | None:
    return decode_clip(entry.get("clip"), entry.get("clip_dtype"), entry.get("clip_dim"))


def taken_ts(entry: dict) -> float:
    t = entry.get("taken")
    if not t:
        return 0.0
    try:
        return datetime.fromisoformat(str(t).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def reject_matches(reject_subject: str, query: str) -> bool:
    """True when this file was judged not to show what the query is asking for."""
    rt = set(stem_tokens(reject_subject))
    qt = set(stem_tokens(query))
    if not rt or not qt:
        return False
    inter = rt & qt
    if len(inter) >= 2:
        return True
    if rt == qt:
        return True
    if len(rt) >= 2 and rt <= qt:
        return True
    if len(qt) >= 2 and qt <= rt:
        return True
    return False


def load_clip_text_encoder(model_name: str):
    """Return (encode_fn, notice, device). encode_fn is None on failure."""
    try:
        import torch
        import open_clip
    except ImportError:
        return None, "open_clip/torch not installed; CLIP term is 0", None
    try:
        device = "mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else "cpu"
        pretrained = "laion2b_s34b_b79k"
        # model_name stored as ViT-B-32 or ViT-B-32/laion2b_...
        arch = model_name.split("/")[0] if model_name else "ViT-B-32"
        model, _, _ = open_clip.create_model_and_transforms(arch, pretrained=pretrained, device=device)
        tokenizer = open_clip.get_tokenizer(arch)
        model.eval()

        def encode(text: str) -> list[float] | None:
            toks = tokenizer([text]).to(device)
            with torch.no_grad():
                feat = model.encode_text(toks)
                feat = feat / feat.norm(dim=-1, keepdim=True)
            return [float(x) for x in feat.detach().cpu().tolist()[0]]

        return encode, None, device
    except Exception as exc:
        return None, f"CLIP load failed ({exc}); CLIP term is 0", None


def evidence_label(has_text: bool, has_clip: bool) -> str:
    if has_text and has_clip:
        return "text+clip"
    if has_text:
        return "text"
    if has_clip:
        return "clip"
    return "none"


def punch_src(best_t: float | None, duration_s: float | None, dur: float) -> float:
    """In-point so a punch of length dur is centered on best_t, inside the clip."""
    duration_s = float(duration_s or 0.0)
    dur = float(dur)
    if dur < 0:
        dur = 0.0
    if best_t is None:
        best_t = duration_s / 2.0 if duration_s > 0 else 0.0
    src = max(0.0, float(best_t) - dur / 2.0)
    if duration_s > 0 and src + dur > duration_s:
        src = max(0.0, duration_s - dur)
    return src


def frame_clip_vector(entry: dict, frame: dict) -> list[float] | None:
    return decode_clip(
        frame.get("clip"),
        entry.get("clip_dtype"),
        entry.get("clip_dim"),
    )


def max_frame_clip(
    entry: dict, query_clip: list[float],
) -> tuple[float | None, float | None, str | None]:
    """MAX cosine over frames[].clip. Returns (cosine, best_t, best_thumb)."""
    best_c = None
    best_t = None
    best_thumb = None
    for fr in entry.get("frames") or []:
        if not isinstance(fr, dict):
            continue
        vec = frame_clip_vector(entry, fr)
        if not vec:
            continue
        c = cosine(query_clip, vec)
        if best_c is None or c > best_c:
            best_c = c
            try:
                best_t = float(fr.get("t"))
            except (TypeError, ValueError):
                best_t = None
            best_thumb = fr.get("thumb")
    return best_c, best_t, best_thumb


def score_entry(
    entry: dict,
    query: str,
    q_toks: list[str],
    bm25: float,
    prefer_project: str | None,
    query_clip: list[float] | None,
    prefer_video: bool = True,
    video_bonus: float = DEFAULT_VIDEO_BONUS,
) -> tuple[float, list[str], str, dict]:
    reasons: list[str] = []
    score = 0.0
    has_text = False
    has_clip = False
    extra = {"best_t": None, "best_thumb": None}

    if prefer_project and entry.get("project") == prefer_project:
        score += PREFER_PROJECT
        reasons.append(f"prefer-project {prefer_project} +{PREFER_PROJECT:.1f}")

    if prefer_video and entry.get("kind") == "video" and video_bonus:
        score += float(video_bonus)
        reasons.append(f"prefer-video +{float(video_bonus):.1f}")

    desc_tokens: set[str] = set()
    for d in entry.get("descriptions") or []:
        subj = d.get("subject") or ""
        desc_tokens.update(stem_tokens(subj))
    matched = [t for t in dict.fromkeys(q_toks) if t in desc_tokens]
    if matched:
        bonus = min(VERIFIED_CAP, VERIFIED_PER_TOKEN * len(matched))
        score += bonus
        has_text = True
        reasons.append(
            "verified subjects +" + f"{bonus:.1f} (" + ", ".join(matched) + ")"
        )

    if bm25 > 0:
        score += bm25
        has_text = True
        reasons.append(f"bm25 caption+name +{bm25:.3f}")

    if query_clip is not None:
        frame_c = None
        if entry.get("kind") == "video":
            frame_c, best_t, best_thumb = max_frame_clip(entry, query_clip)
            if frame_c is not None:
                contrib = CLIP_WEIGHT * frame_c
                score += contrib
                has_clip = True
                extra["best_t"] = best_t
                extra["best_thumb"] = best_thumb
                t_s = "?" if best_t is None else f"{best_t:g}"
                reasons.append(
                    f"clip cosine {frame_c:.3f} +{contrib:.3f} (max-frame t={t_s})"
                )
        if not has_clip:
            vec = entry_clip_vector(entry)
            if vec:
                c = cosine(query_clip, vec)
                contrib = CLIP_WEIGHT * c
                score += contrib
                has_clip = True
                reasons.append(f"clip cosine {c:.3f} +{contrib:.3f}")

    if extra["best_t"] is None and entry.get("kind") == "video":
        frames = [fr for fr in (entry.get("frames") or []) if isinstance(fr, dict)]
        if frames:
            mid = float(entry.get("duration_s") or 0.0) / 2.0
            chosen = min(frames, key=lambda fr: abs(float(fr.get("t") or 0.0) - mid))
            try:
                extra["best_t"] = float(chosen.get("t"))
            except (TypeError, ValueError):
                extra["best_t"] = mid if mid else 0.0
            extra["best_thumb"] = chosen.get("thumb") or extra.get("best_thumb")
        else:
            dur = float(entry.get("duration_s") or 0.0)
            extra["best_t"] = dur / 2.0 if dur > 0 else 0.0
        if not extra.get("best_thumb"):
            extra["best_thumb"] = entry.get("thumb")

    orient = entry.get("orientation")
    if orient == "portrait":
        score += ORIENT_PORTRAIT
        reasons.append(f"orientation portrait +{ORIENT_PORTRAIT:.1f}")
    elif orient == "square":
        score += ORIENT_SQUARE
        reasons.append(f"orientation square +{ORIENT_SQUARE:.1f}")

    return score, reasons, evidence_label(has_text, has_clip), extra


def load_index(path: Path) -> dict:
    if not path.exists():
        die(f"broll-search: index not found: {path}", 2)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(f"broll-search: index is not valid JSON: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        die("broll-search: index is missing entries[]")
    schema = data.get("schema")
    if schema not in SCHEMA_READ:
        eprint(f"broll-search: unrecognized index schema {schema!r}; continuing")
    return data


def load_exclude(path: Path | None) -> set[str]:
    if path is None:
        return set()
    if not path.exists():
        die(f"broll-search: --exclude-used not found: {path}", 2)
    used: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = Path(line).expanduser()
        used.add(str(p.resolve()) if p.exists() else line)
        used.add(line)
        used.add(p.name)
    return used


def entry_excluded(entry: dict, used: set[str]) -> bool:
    if not used:
        return False
    path = entry.get("path") or ""
    name = Path(path).name
    return path in used or name in used or Path(path).name in used


def find_entry(index: dict, path_str: str) -> dict:
    given = Path(path_str).expanduser()
    abs_given = str(given.resolve()) if given.exists() else str(given)
    basename_hits: list[dict] = []
    for e in index.get("entries") or []:
        ep = e.get("path") or ""
        if ep == path_str or ep == abs_given:
            return e
        try:
            if Path(ep).resolve() == given.resolve() and given.exists():
                return e
        except Exception:
            pass
        if Path(ep).name.lower() == given.name.lower():
            basename_hits.append(e)
        rel = e.get("rel") or ""
        if rel == path_str or rel == given.as_posix():
            basename_hits.append(e)
    # unique basename
    uniq = {e.get("path"): e for e in basename_hits}
    if len(uniq) == 1:
        return next(iter(uniq.values()))
    if len(uniq) > 1:
        die(f"broll-search: path is ambiguous (matches {len(uniq)} entries): {path_str}")
    die(f"broll-search: path not in index: {path_str}", 2)


def atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def print_entry_summary(entry: dict, verb: str) -> None:
    n_d = len(entry.get("descriptions") or [])
    n_r = len(entry.get("rejects") or [])
    print(
        f"[broll-search] {verb} {entry.get('path')} "
        f"(project={entry.get('project')} kind={entry.get('kind')} "
        f"descriptions={n_d} rejects={n_r})"
    )


def do_confirm(index_path: Path, path_str: str, subject: str, by: str, dry: bool) -> int:
    index = load_index(index_path)
    entry = find_entry(index, path_str)
    rec = {"subject": subject, "by": by, "date": iso_now()}
    descs = list(entry.get("descriptions") or [])
    if any(d.get("subject") == subject for d in descs):
        print("[broll-search] subject already on this entry; index unchanged")
        print_entry_summary(entry, "confirm")
        return 0
    if dry:
        print(f"[broll-search] DRY RUN: would confirm {entry.get('path')} subject={subject!r} by={by}")
        return 0
    descs.append(rec)
    entry["descriptions"] = descs
    atomic_write_json(index_path, index)
    print_entry_summary(entry, "confirmed")
    return 0


def do_reject(index_path: Path, path_str: str, subject: str, dry: bool) -> int:
    index = load_index(index_path)
    entry = find_entry(index, path_str)
    rec = {"subject": subject, "date": iso_now()}
    rejects = list(entry.get("rejects") or [])
    if any(d.get("subject") == subject for d in rejects):
        print("[broll-search] subject already rejected on this entry; index unchanged")
        print_entry_summary(entry, "reject")
        return 0
    if dry:
        print(f"[broll-search] DRY RUN: would reject {entry.get('path')} subject={subject!r}")
        return 0
    rejects.append(rec)
    entry["rejects"] = rejects
    atomic_write_json(index_path, index)
    print_entry_summary(entry, "rejected")
    return 0


def filter_entries(
    entries: list[dict],
    project: str | None,
    kind: str,
    orientation: str,
    used: set[str],
    query: str,
    min_clip_s: float = 0.0,
    confirmed_only: bool = False,
) -> list[dict]:
    out = []
    for e in entries:
        if project and e.get("project") != project:
            continue
        if kind != "any" and e.get("kind") != kind:
            continue
        # Stills earn a place on screen only when a person confirmed the
        # subject (owner rule 2026-09-07: no photo beats a near miss). Video
        # candidates pass; the sheet and the verifier still judge them.
        if confirmed_only and e.get("kind") == "image":
            if not any((d.get("by") == "human") for d in (e.get("descriptions") or []) if isinstance(d, dict)):
                continue
        if orientation != "any" and e.get("orientation") != orientation:
            continue
        if entry_excluded(e, used):
            continue
        if e.get("kind") == "video" and min_clip_s > 0:
            dur = e.get("duration_s")
            try:
                if dur is not None and float(dur) < float(min_clip_s):
                    continue
            except (TypeError, ValueError):
                pass
        skipped = False
        for r in e.get("rejects") or []:
            if reject_matches(r.get("subject") or "", query):
                skipped = True
                break
        if skipped:
            continue
        out.append(e)
    return out


def rank_query(
    entries: list[dict],
    query: str,
    prefer_project: str | None,
    query_clip: list[float] | None,
    top: int,
    min_score: float = 0.0,
    prefer_video: bool = True,
    video_bonus: float = DEFAULT_VIDEO_BONUS,
    punch_dur: float = DEFAULT_PUNCH_DUR,
) -> list[dict]:
    docs = [doc_tokens(e) for e in entries]
    q_toks = expand_query(query)
    bm25s = bm25_scores(q_toks, docs)
    scored: list[tuple[float, float, str, dict, list[str], str, dict]] = []
    for e, b in zip(entries, bm25s):
        score, reasons, evidence, extra = score_entry(
            e, query, q_toks, b, prefer_project, query_clip,
            prefer_video=prefer_video, video_bonus=video_bonus,
        )
        scored.append((score, taken_ts(e), e.get("path") or "", e, reasons, evidence, extra))
    scored.sort(key=lambda t: (-t[0], -t[1], t[2]))
    kept = [t for t in scored if t[0] >= min_score]
    results = []
    for i, (score, _ts, _path, e, reasons, evidence, extra) in enumerate(kept[:top], start=1):
        row = {
            "rank": i,
            "path": e.get("path"),
            "project": e.get("project"),
            "kind": e.get("kind"),
            "score": round(float(score), 4),
            "reasons": reasons,
            "evidence": evidence,
            "thumb": extra.get("best_thumb") or e.get("thumb"),
            "caption": e.get("caption"),
            "descriptions": e.get("descriptions") or [],
        }
        if e.get("kind") == "video":
            best_t = extra.get("best_t")
            dur = float(punch_dur)
            duration_s = e.get("duration_s")
            src = punch_src(best_t, duration_s, dur)
            row["src"] = round(float(src), 4)
            row["best_t"] = None if best_t is None else round(float(best_t), 4)
            row["duration_s"] = duration_s
            row["color_hint"] = e.get("color_hint")
            row["dur"] = dur
        results.append(row)
    return results


def tile_label(c: dict) -> str:
    """rank · project · score · first 24 chars of caption (fallback basename).

    Video tiles insert t=best_t before the caption.
    """
    cap = (c.get("caption") or "").strip()
    if cap:
        tail = cap[:24]
    else:
        tail = Path(c.get("path") or "").name
    project = c.get("project") or ""
    score = c.get("score")
    try:
        score_s = f"{float(score):.3f}"
    except (TypeError, ValueError):
        score_s = str(score)
    if c.get("kind") == "video" and c.get("best_t") is not None:
        try:
            t_s = f"t={float(c.get('best_t')):g}"
        except (TypeError, ValueError):
            t_s = f"t={c.get('best_t')}"
        return f"{c.get('rank')} · {project} · {score_s} · {t_s} · {tail}"
    return f"{c.get('rank')} · {project} · {score_s} · {tail}"


def sibling_contact_sheet(candidates: list[dict], out: Path) -> bool:
    """Feature-detect contact-sheet.py. Return True if it wrote `out`."""
    sibling = Path(__file__).resolve().parent / "contact-sheet.py"
    if not sibling.is_file():
        eprint("[broll-search] contact-sheet.py not found; using built-in grid")
        return False
    proc = subprocess.run(
        [sys.executable, str(sibling), "--help"],
        capture_output=True, text=True,
    )
    helptext = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        eprint("[broll-search] contact-sheet.py --help failed; using built-in grid")
        return False
    out_flag = "--output" if "--output" in helptext else ("--out" if "--out" in helptext else None)
    label_flag = None
    for cand in ("--labels", "--label", "--caption"):
        if cand in helptext:
            label_flag = cand
            break
    if out_flag is None or label_flag is None:
        eprint("[broll-search] contact-sheet.py missing output/label flags; using built-in grid")
        return False
    images: list[str] = []
    labels: list[str] = []
    for c in candidates:
        src = c.get("thumb") or c.get("path")
        if not src or not Path(src).is_file():
            continue
        if Path(src).suffix.lower() in {".mp4", ".mov", ".m4v"}:
            continue
        images.append(str(src))
        labels.append(tile_label(c))
    if not images:
        return False
    cmd = [sys.executable, str(sibling), out_flag, str(out)]
    if "--columns" in helptext:
        cmd += ["--columns", str(SHEET_COLS)]
    elif "--cols" in helptext:
        cmd += ["--cols", str(SHEET_COLS)]
    if label_flag == "--labels":
        cmd += ["--labels", *labels]
        cmd += images
    elif label_flag == "--label":
        for img, lab in zip(images, labels):
            cmd += ["--label", lab, img]
    else:
        cmd += images
    print("[broll-search] " + " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out.is_file():
        eprint("[broll-search] contact-sheet.py failed; using built-in grid")
        if r.stderr:
            eprint(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "")
        return False
    return True


def _sheet_font(size: int):
    from PIL import ImageFont

    for p in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _fit_rgb(path: Path, box: int):
    from PIL import Image, ImageOps

    try:
        im = Image.open(path)
        try:
            im = ImageOps.exif_transpose(im)
        except Exception:
            pass
        im = im.convert("RGB")
    except Exception:
        return None
    im.thumbnail((box, box))
    canvas = Image.new("RGB", (box, box), (20, 20, 20))
    x = (box - im.width) // 2
    y = (box - im.height) // 2
    canvas.paste(im, (x, y))
    return canvas


def build_sheet_pillow(candidates: list[dict], out: Path) -> None:
    from PIL import Image, ImageDraw

    n = max(1, len(candidates))
    cols = SHEET_COLS
    rows = math.ceil(n / cols)
    gap = 8
    label_h = 52
    thumb = SHEET_THUMB
    width = cols * thumb + (cols + 1) * gap
    if width > SHEET_MAX_W:
        thumb = max(64, (SHEET_MAX_W - (cols + 1) * gap) // cols)
        width = cols * thumb + (cols + 1) * gap
    height = rows * (thumb + label_h) + (rows + 1) * gap
    img = Image.new("RGB", (width, height), (18, 18, 18))
    draw = ImageDraw.Draw(img)
    font = _sheet_font(14)
    for i, c in enumerate(candidates):
        r, col = divmod(i, cols)
        x = gap + col * (thumb + gap)
        y = gap + r * (thumb + label_h + gap)
        src = None
        for cand_path in (c.get("thumb"), c.get("path")):
            if cand_path and Path(cand_path).is_file():
                if Path(cand_path).suffix.lower() in {".mp4", ".mov", ".m4v"}:
                    continue
                src = Path(cand_path)
                break
        cell = _fit_rgb(src, thumb) if src is not None else None
        if cell is None:
            cell = Image.new("RGB", (thumb, thumb), (40, 40, 40))
        img.paste(cell, (x, y))
        label = tile_label(c)
        draw.text((x + 4, y + thumb + 6), label, fill=(230, 230, 230), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=85)


def write_sheet(candidates: list[dict], out: Path, dry: bool) -> None:
    if dry:
        print(f"[broll-search] DRY RUN: would write contact sheet {out}")
        return
    if sibling_contact_sheet(candidates, out):
        print(f"[broll-search] sheet {out.resolve()}")
        return
    build_sheet_pillow(candidates, out)
    print(f"[broll-search] sheet {out.resolve()}")


def project_hint_from_notes(notes: str | None) -> str | None:
    if not notes:
        return None
    m = PROJECT_HINT_RE.search(notes)
    return m.group(1) if m else None


def print_human(query: str, candidates: list[dict], explain: bool) -> None:
    print(f"query: {query}")
    if not candidates:
        print("  (no candidates)")
        return
    for c in candidates:
        print(
            f"  {c['rank']}. {c['score']:.3f}  {c.get('kind')}  "
            f"{c.get('project')}  {c.get('path')}"
        )
        if explain:
            for r in c.get("reasons") or []:
                print(f"      {r}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--index", type=Path, required=True)
    p.add_argument("--query", action="append", default=[], help="Spoken line to match. Repeatable.")
    p.add_argument(
        "--lines-from-manifest", type=Path, default=None,
        help="Search each broll[] row that has a line and an empty path. Does not edit the manifest.",
    )
    p.add_argument("--project", default=None, help="Restrict to this project.")
    p.add_argument("--prefer-project", default=None, help="Add +3.0 to entries of this project.")
    p.add_argument("--kind", choices=["image", "video", "any"], default="any")
    p.add_argument(
        "--confirmed-only",
        action="store_true",
        help="Drop photos that no person has confirmed (descriptions[].by == human). Video candidates still pass. The rule for stills.",
    )
    p.add_argument(
        "--prefer-video", dest="prefer_video", action="store_true", default=True,
        help="Add --video-bonus to video entries so an exact clip outranks a photo "
             "(default on).",
    )
    p.add_argument(
        "--no-prefer-video", dest="prefer_video", action="store_false",
        help="Disable the video score bonus.",
    )
    p.add_argument(
        "--video-bonus", type=float, default=DEFAULT_VIDEO_BONUS, metavar="X",
        help="Score added to video entries when --prefer-video is on (default 1.5).",
    )
    p.add_argument(
        "--punch-dur", type=float, default=DEFAULT_PUNCH_DUR, metavar="SEC",
        help="Punch duration used to compute video src in-point (default 2.5).",
    )
    p.add_argument(
        "--min-clip-s", type=float, default=DEFAULT_MIN_CLIP_S, metavar="SEC",
        help="Drop video entries shorter than this many seconds (default 1.5).",
    )
    p.add_argument("--orientation", choices=["portrait", "landscape", "any"], default="any")
    p.add_argument("--top", type=int, default=DEFAULT_TOP)
    p.add_argument(
        "--min-score", type=float, default=0.0, metavar="X",
        help="Drop candidates whose total score is below X. Default 0.",
    )
    p.add_argument("--json", dest="json_out", type=Path, default=None)
    p.add_argument("--sheet", type=Path, default=None)
    p.add_argument("--exclude-used", type=Path, default=None)
    p.add_argument("--explain", action="store_true", help="Print per-candidate score reasons.")
    p.add_argument("--confirm", default=None, metavar="PATH")
    p.add_argument("--reject", default=None, metavar="PATH")
    p.add_argument("--subject", default=None)
    p.add_argument("--by", choices=["vision-check", "human"], default="vision-check")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.confirm and args.reject:
        die("broll-search: use --confirm or --reject, not both")
    if args.confirm or args.reject:
        if not args.subject:
            die("broll-search: --confirm/--reject requires --subject")
        if args.confirm:
            return do_confirm(args.index, args.confirm, args.subject, args.by, args.dry_run)
        return do_reject(args.index, args.reject, args.subject, args.dry_run)

    queries: list[str] = list(args.query)
    prefer = args.prefer_project
    if args.lines_from_manifest is not None:
        man_path = args.lines_from_manifest
        if not man_path.exists():
            die(f"broll-search: manifest not found: {man_path}", 2)
        try:
            manifest = json.loads(man_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            die(f"broll-search: manifest is not valid JSON: {exc}")
        if not prefer:
            prefer = project_hint_from_notes(manifest.get("notes") if isinstance(manifest, dict) else None)
        broll = manifest.get("broll") if isinstance(manifest, dict) else None
        if not isinstance(broll, list):
            die("broll-search: manifest has no broll[] array")
        for row in broll:
            if not isinstance(row, dict):
                continue
            line = (row.get("line") or "").strip()
            path = row.get("path")
            if path is None:
                path = ""
            if line and not str(path).strip():
                queries.append(line)
        if not queries:
            die("broll-search: manifest has no broll[] rows with a line and empty path")

    if not queries:
        die("broll-search: pass --query or --lines-from-manifest")

    index = load_index(args.index)
    used = load_exclude(args.exclude_used)
    all_entries = list(index.get("entries") or [])

    encode_text = None
    index_has_clip = any(e.get("clip") for e in all_entries)
    if index_has_clip:
        encode_text, notice, clip_device = load_clip_text_encoder(
            index.get("clip_model") or "ViT-B-32"
        )
        if notice:
            eprint(f"[broll-search] {notice}")
        elif clip_device:
            print(f"[broll-search] CLIP device: {clip_device}")

    payload_queries = []
    sheet_candidates: list[dict] = []
    honesty = (
        "no caption, filename, or embedding evidence for this query; "
        "index with --clip or add captions (--captions-from-alt)"
    )
    for q in queries:
        pool = filter_entries(
            all_entries, args.project, args.kind, args.orientation, used, q,
            min_clip_s=float(args.min_clip_s),
            confirmed_only=bool(getattr(args, "confirmed_only", False)),
        )
        q_clip = encode_text(q) if encode_text is not None else None
        cands = rank_query(
            pool, q, prefer, q_clip, args.top, min_score=args.min_score,
            prefer_video=bool(args.prefer_video),
            video_bonus=float(args.video_bonus),
            punch_dur=float(args.punch_dur),
        )
        if cands and (not index_has_clip) and all(c.get("evidence") == "none" for c in cands):
            print(honesty)
            for c in cands:
                c["reasons"] = ["no evidence"]
        payload_queries.append({"query": q, "line": q, "candidates": cands})
        print_human(q, cands, args.explain)
        for c in cands:
            sheet_candidates.append(c)

    sheet_path = None
    if args.sheet is not None:
        # One sheet: first query's top hits, then any later unique paths.
        seen: set[str] = set()
        unique: list[dict] = []
        for c in sheet_candidates:
            p = c.get("path")
            if not p or p in seen:
                continue
            seen.add(p)
            unique.append(c)
        write_sheet(unique[: max(args.top, 1)], args.sheet, args.dry_run)
        if not args.dry_run and args.sheet.exists():
            sheet_path = str(args.sheet.resolve())

    out_obj = {"queries": payload_queries, "sheet": sheet_path}
    if args.json_out is not None:
        if args.dry_run:
            print(f"[broll-search] DRY RUN: would write JSON {args.json_out}")
        else:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(json.dumps(out_obj, indent=2) + "\n", encoding="utf-8")
            print(f"[broll-search] json {args.json_out.resolve()}")
    elif args.lines_from_manifest is not None:
        print(json.dumps(out_obj, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
