#!/usr/bin/env python3
"""Synthetic tests for ingest-footage.py. No client names or live footage."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
INGEST = SCRIPTS / "ingest-footage.py"
PY = sys.executable


def run(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run([PY, str(INGEST), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError(
            f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
    return r


def write(path: Path, text: str = "hello") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def jpeg(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"
    )


def mp4(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"ftypisom" + b"\x00" * 32)


def fixture(root: Path) -> None:
    shoot = root / "2026_Acme_Kitchen" / "2026-08-17"
    mp4(shoot / "Video" / "ARoll-Walkthrough-PRIMARY.MP4")
    mp4(shoot / "Video" / "BRoll-Brick-Detail.MP4")
    mp4(shoot / "Video" / "Scrap-False-Start.MP4")
    write(shoot / "Audio" / "ARoll-Walkthrough-PRIMARY.txt", "the wall is gone")
    write(shoot / "Audio" / "ARoll-Walkthrough-PRIMARY.json", '{"words":[]}')
    jpeg(shoot / "Photos" / "_edited" / "hero.jpg")
    jpeg(shoot / "Photos" / "raw-skip.jpg")
    jpeg(shoot / "Art" / "keeper.jpg")
    mapping = shoot / "file-mapping.csv"
    mapping.write_text(
        "original_name,new_name,type,duration_s\n"
        "064A0001.MP4,ARoll-Walkthrough-PRIMARY.MP4,a-roll,12.5\n"
        "064A0002.MP4,BRoll-Brick-Detail.MP4,b-roll,4.0\n"
        "064A0003.MP4,Scrap-False-Start.MP4,scrap,1.0\n",
        encoding="utf-8",
    )
    notes = root / "notes"
    notes.mkdir()
    (notes / "piece.md").write_text(
        "---\ncontent_id: AC-01\nsource_footage: \"Jobs / 2026_Acme_Kitchen / "
        "2026-08-17 / Video/ARoll-Walkthrough-PRIMARY.MP4\"\n---\n",
        encoding="utf-8",
    )


def test_missing_root_exits_2() -> None:
    r = run(
        [
            "--root", "t7=/no/such/footage-root",
            "--catalog", "/tmp/no-catalog.jsonl",
            "--transcripts-out", "/tmp/no-txt",
            "--content-index-out", "/tmp/no-index.md",
        ],
        check=False,
    )
    assert r.returncode == 2, r.stderr


def test_ingest_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        footage = tmp_path / "jobs"
        fixture(footage)
        social = tmp_path / "social.json"
        social.write_text(json.dumps({"2026_Acme_Kitchen": "1900 Kitchen"}), encoding="utf-8")
        catalog = tmp_path / "catalog.jsonl"
        transcripts = tmp_path / "audio"
        index_md = tmp_path / "content-index.md"
        notes = footage.parent / "notes" if False else footage / "notes"
        # notes written inside fixture at footage/notes — move: fixture put notes at root/notes
        notes = tmp_path / "notes"
        # rewrite notes next to jobs
        notes.mkdir(exist_ok=True)
        (notes / "piece.md").write_text(
            "---\ncontent_id: AC-01\nsource_footage: \"ARoll-Walkthrough-PRIMARY.MP4\"\n---\n",
            encoding="utf-8",
        )
        r = run([
            "--root", f"t7={footage}",
            "--catalog", str(catalog),
            "--transcripts-out", str(transcripts),
            "--content-index-out", str(index_md),
            "--social-map", str(social),
            "--notes-dir", str(notes),
            "--skip-broll",
        ])
        assert r.returncode == 0, r.stderr
        rows = [json.loads(line) for line in catalog.read_text().splitlines() if line]
        kinds = {row["kind"]: row for row in rows}
        rels = {row["rel"] for row in rows}
        assert "2026_Acme_Kitchen/2026-08-17/Video/ARoll-Walkthrough-PRIMARY.MP4" in rels
        assert "2026_Acme_Kitchen/2026-08-17/Video/BRoll-Brick-Detail.MP4" in rels
        assert "2026_Acme_Kitchen/2026-08-17/Photos/_edited/hero.jpg" in rels
        assert "2026_Acme_Kitchen/2026-08-17/Art/keeper.jpg" in rels
        assert not any("Scrap" in rel for rel in rels)
        assert not any("raw-skip" in rel for rel in rels)
        aroll = kinds["aroll"]
        assert aroll["social_name"] == "1900 Kitchen"
        assert aroll["shoot_date"] == "2026-08-17"
        assert aroll["duration_s"] == 12.5
        assert aroll["content_id"] == "AC-01"
        assert aroll["transcript_repo"] == "footage/audio/2026_Acme_Kitchen/2026-08-17/ARoll-Walkthrough-PRIMARY.txt"
        assert aroll["word_json_rel"] == "2026_Acme_Kitchen/2026-08-17/Audio/ARoll-Walkthrough-PRIMARY.json"
        assert not str(aroll["rel"]).startswith("/")
        copied = transcripts / "2026_Acme_Kitchen" / "2026-08-17" / "ARoll-Walkthrough-PRIMARY.txt"
        assert copied.exists()
        assert copied.read_text() == "the wall is gone"
        assert not (transcripts / "2026_Acme_Kitchen" / "2026-08-17" / "ARoll-Walkthrough-PRIMARY.json").exists()
        md = index_md.read_text()
        assert "generated: true" in md
        assert "2026_Acme_Kitchen" in md
        assert "Do not edit by hand" in md


def test_dry_run_writes_nothing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        footage = tmp_path / "jobs"
        fixture(footage)
        catalog = tmp_path / "catalog.jsonl"
        transcripts = tmp_path / "audio"
        index_md = tmp_path / "content-index.md"
        r = run([
            "--root", f"t7={footage}",
            "--catalog", str(catalog),
            "--transcripts-out", str(transcripts),
            "--content-index-out", str(index_md),
            "--skip-broll",
            "--dry-run",
        ])
        assert r.returncode == 0, r.stderr
        assert not catalog.exists()
        assert not index_md.exists()
        assert not transcripts.exists() or not any(transcripts.rglob("*.txt"))


def test_upsert_replaces_same_rel() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        footage = tmp_path / "jobs"
        fixture(footage)
        catalog = tmp_path / "catalog.jsonl"
        transcripts = tmp_path / "audio"
        index_md = tmp_path / "content-index.md"
        args = [
            "--root", f"t7={footage}",
            "--catalog", str(catalog),
            "--transcripts-out", str(transcripts),
            "--content-index-out", str(index_md),
            "--skip-broll",
        ]
        run(args)
        run(args)
        rows = [json.loads(line) for line in catalog.read_text().splitlines() if line]
        rels = [row["rel"] for row in rows]
        assert len(rels) == len(set(rels))


if __name__ == "__main__":
    tests = [
        test_missing_root_exits_2,
        test_ingest_fixture,
        test_dry_run_writes_nothing,
        test_upsert_replaces_same_rel,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"ok  {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    raise SystemExit(1 if failed else 0)
