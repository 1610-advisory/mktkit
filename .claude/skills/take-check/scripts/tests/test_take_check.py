#!/usr/bin/env python3
"""Synthetic takes only. No network. The judge is a fake."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import take_check as tc


def word(text, start, end, prob=0.95):
    return {"word": text, "start": start, "end": end, "probability": prob}


def whisper(words, text=None, no_speech=0.05):
    body = "".join(w["word"] for w in words).strip()
    return {
        "text": body if text is None else text,
        "language": "en",
        "segments": [{
            "start": words[0]["start"] if words else 0,
            "end": words[-1]["end"] if words else 0,
            "text": " " + body if body else "",
            "no_speech_prob": no_speech,
            "avg_logprob": -0.2,
            "words": words,
        }],
    }


def clean_words():
    return [
        word(" Ready?", 0.40, 0.80),
        word(" Yep.", 0.90, 1.20),
        word(" Most", 1.50, 1.80),
        word(" owners", 1.80, 2.20),
        word(" guess", 2.20, 2.60),
        word(" wrong.", 2.60, 3.00),
        word(" We", 3.20, 3.40),
        word(" price", 3.40, 3.70),
        word(" the", 3.70, 3.90),
        word(" job", 3.90, 4.20),
        word(" before", 4.20, 4.60),
        word(" we", 4.60, 4.80),
        word(" start.", 4.80, 5.20),
    ]


def restart_words():
    # "so the reason we the reason we do this." stretched past min_speech_s.
    spans = [
        (" so", 0.20, 0.50),
        (" the", 0.50, 0.90),
        (" reason", 0.90, 1.40),
        (" we", 1.40, 1.70),
        (" the", 1.80, 2.20),
        (" reason", 2.20, 2.70),
        (" we", 2.70, 3.00),
        (" do", 3.10, 3.50),
        (" this.", 3.50, 5.40),
    ]
    return [word(text, start, end) for text, start, end in spans]


def filler_words():
    spans = [
        (" Um", 0.20, 0.50),
        (" uh", 0.60, 0.90),
        (" the", 1.00, 1.30),
        (" owner", 1.30, 1.70),
        (" prices", 1.80, 2.20),
        (" jobs", 2.30, 2.60),
        (" early", 2.70, 3.10),
        (" um", 3.20, 3.50),
        (" uh", 3.60, 3.90),
        (" today", 4.00, 4.60),
    ]
    return [word(text, start, end) for text, start, end in spans]


def judge_payload():
    return {
        "hook": {"quote": "Most owners guess wrong.", "start": 1.62, "end": 2.91, "score": 4},
        "main_point": "Price the job before starting.",
        "single_idea": True,
        "payoff": {"quote": "We price the job before we start.", "start": 3.2, "end": 5.2},
        "problems": [
            {"type": "other", "quote": "we invented fusion", "start": 1.0, "end": 2.0, "note": "not said"},
            {"type": "filler", "quote": "guess wrong", "start": 2.22, "end": 2.99, "note": "soft"},
        ],
        "suggested_in": 1.62,
        "suggested_out": 5.05,
        "structure_score": 4,
        "verdict": "green",
        "use": "cut",
        "reason": "Hook lands and the payoff is a full sentence.",
    }


class TakeCheckTests(unittest.TestCase):
    def setUp(self):
        self.cfg = tc.load_config(None)
        tc.JUDGE_RUNNER = None

    def tearDown(self):
        tc.JUDGE_RUNNER = None

    def test_01_clean_setup_is_green(self):
        result = tc.analyze(whisper(clean_words()), self.cfg)
        self.assertAlmostEqual(result["metrics"]["clean_in"], 1.50)
        self.assertNotEqual(result["metrics"]["clean_in"], result["metrics"]["speech_start"])
        self.assertEqual([c["phrase"] for c in result["metrics"]["setup_cues"]], ["ready", "yep"])
        self.assertTrue(result["metrics"]["ends_on_sentence"])
        self.assertEqual(result["metrics_verdict"], "green")
        self.assertFalse(result["silent"])
        self.assertEqual(result["flags"], [])

    def test_02_restart_flagged(self):
        result = tc.analyze(whisper(restart_words()), self.cfg)
        codes = [f["code"] for f in result["flags"]]
        self.assertIn("restart", codes)
        self.assertTrue(any("the reason we" in r["ngram"] for r in result["metrics"]["restarts"]))
        self.assertEqual(result["metrics_verdict"], "yellow")

    def test_03_fillers_and_no_end_are_yellow(self):
        result = tc.analyze(whisper(filler_words()), self.cfg)
        codes = [f["code"] for f in result["flags"]]
        self.assertIn("fillers_per_min", codes)
        self.assertIn("no_sentence_end", codes)
        self.assertGreater(result["metrics"]["fillers"]["per_min"], 4)
        self.assertFalse(result["metrics"]["ends_on_sentence"])
        self.assertEqual(result["metrics_verdict"], "yellow")

    def test_04_silent_thank_you_skips_judge(self):
        called = []

        def runner(cmd, prompt, timeout):
            called.append(prompt)
            raise AssertionError("judge must not run on a silent take")

        data = whisper(
            [word(" Thank", 0.50, 0.80), word(" you.", 0.80, 1.10)],
            text="Thank you.",
        )
        path = self._write_take("ThankYou", data)
        with tempfile.TemporaryDirectory() as out:
            tc.JUDGE_RUNNER = runner
            code = tc.main([str(path), "--out-dir", out])
            self.assertEqual(code, 0)
            self.assertEqual(called, [])
            payload = json.loads((Path(out) / "ThankYou.take.json").read_text())
        self.assertTrue(payload["metrics"]["silent"])
        self.assertEqual(payload["verdict"], "red")
        self.assertEqual(payload["use"], "none")
        self.assertEqual(payload["judge_skipped"], "silent")
        self.assertIsNone(payload["judge"])
        self.assertIn("hallucination", payload["metrics"]["silent_reason"])

    def test_05_fenced_judge_drops_fabricated_quote_and_snaps(self):
        reply = "Sure, here is the score:\n```json\n" + json.dumps(judge_payload()) + "\n```\n"

        def runner(cmd, prompt, timeout):
            return reply, "", 0

        path = self._write_take("ARoll-Clean", whisper(clean_words()))
        with tempfile.TemporaryDirectory() as out:
            tc.JUDGE_RUNNER = runner
            code = tc.main([str(path), "--out-dir", out, "--jobs", "1"])
            self.assertEqual(code, 0)
            payload = json.loads((Path(out) / "ARoll-Clean.take.json").read_text())
        self.assertIsNotNone(payload["judge"])
        self.assertEqual(len(payload["judge_dropped"]), 1)
        self.assertIn("fusion", payload["judge_dropped"][0]["quote"])
        self.assertEqual(len(payload["judge"]["problems"]), 1)
        self.assertEqual(payload["judge"]["problems"][0]["quote"], "guess wrong")
        self.assertEqual(payload["judge"]["hook"]["quote"], "Most owners guess wrong.")
        self.assertEqual(payload["judge"]["hook"]["start"], 1.5)
        self.assertEqual(payload["judge"]["hook"]["end"], 3.0)
        self.assertEqual(payload["suggested_in"], 1.5)
        self.assertEqual(payload["suggested_out"], 5.2)
        self.assertEqual(payload["judge"]["problems"][0]["start"], 2.2)
        self.assertEqual(payload["judge"]["problems"][0]["end"], 3.0)

    def test_06_garbage_judge_falls_back_to_metrics(self):
        calls = []

        def runner(cmd, prompt, timeout):
            calls.append(prompt)
            return "I think this take is fine, no json here.", "", 0

        path = self._write_take("ARoll-Clean", whisper(clean_words()))
        with tempfile.TemporaryDirectory() as out:
            tc.JUDGE_RUNNER = runner
            code = tc.main([str(path), "--out-dir", out, "--jobs", "1"])
            self.assertEqual(code, 0)
            payload = json.loads((Path(out) / "ARoll-Clean.take.json").read_text())
        self.assertEqual(len(calls), 2)
        self.assertIn("JSON only", calls[1])
        self.assertIsNotNone(payload["judge_error"])
        self.assertIsNone(payload["judge"])
        self.assertEqual(payload["metrics_verdict"], "green")
        self.assertEqual(payload["verdict"], "green")
        self.assertEqual(payload["use"], "cut")

    def test_07_folder_scan_keeps_prefixes_and_does_not_write_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "shoot"
            audio = root / "Audio"
            audio.mkdir(parents=True)
            (root / "Day" / "Audio").mkdir(parents=True)
            (root / "Video").mkdir()
            samples = {
                audio / "ARoll-One.json": whisper(clean_words()),
                audio / "CB-Two.json": whisper(clean_words()),
                audio / "BRoll-Nope.json": whisper(clean_words()),
                audio / "notes.json": whisper(clean_words()),
                root / "Day" / "Audio" / "ARoll-Nested.json": whisper(clean_words()),
                root / "Day" / "Audio" / "wild.json": whisper(clean_words()),
                root / "ARoll-Outside.json": whisper(clean_words()),
            }
            for path, data in samples.items():
                path.write_text(json.dumps(data), encoding="utf-8")
            (root / "Video" / "ARoll-One.MP4").write_bytes(b"")
            before = self._tree(root)
            out = Path(tmp) / "out"
            code = tc.main([str(root), "--out-dir", str(out), "--judge", "none"])
            self.assertEqual(code, 0)
            self.assertEqual(self._tree(root), before)
            written = sorted(p.name for p in out.glob("*.take.json"))
            self.assertEqual(written, ["ARoll-Nested.take.json", "ARoll-One.take.json", "CB-Two.take.json"])
            one = json.loads((out / "ARoll-One.take.json").read_text())
            self.assertIsNotNone(one["video"])
            self.assertTrue(one["video"]["path"].endswith("ARoll-One.MP4"))
            self.assertIsNone(one["video"]["duration_s"])
            self.assertTrue((out / "take-report.md").is_file())

    def test_08_grouping_picks_best_of_take_bcam(self):
        self.assertEqual(tc.piece_key("ARoll-Widget-Take2"), "ARoll-Widget")
        self.assertEqual(tc.piece_key("ARoll-Widget-BCam"), "ARoll-Widget")
        self.assertEqual(tc.piece_key("ARoll-Widget-PRIMARY"), "ARoll-Widget")
        self.assertEqual(tc.piece_key("ARoll-Widget-Phone"), "ARoll-Widget")
        self.assertEqual(tc.piece_key("ARoll-Widget-False-Start"), "ARoll-Widget")
        self.assertEqual(tc.piece_key("ARoll-Widget-Take2-BCam"), "ARoll-Widget")
        rows = [
            {"stem": "ARoll-Widget-Take1", "verdict": "yellow", "structure_score": 5, "filler_count": 0},
            {"stem": "ARoll-Widget-Take2", "verdict": "green", "structure_score": 4, "filler_count": 2},
            {"stem": "ARoll-Widget-BCam", "verdict": "green", "structure_score": 4, "filler_count": 0},
            {"stem": "CB-Other-Take1", "verdict": "red", "structure_score": 1, "filler_count": 0},
        ]
        groups = tc.group_results(rows)
        self.assertEqual(tc.best_row(groups["ARoll-Widget"])["stem"], "ARoll-Widget-BCam")
        higher = [
            {"stem": "ARoll-Widget-Take2", "verdict": "green", "structure_score": 5, "filler_count": 9},
            {"stem": "ARoll-Widget-BCam", "verdict": "green", "structure_score": 4, "filler_count": 0},
        ]
        self.assertEqual(tc.best_row(higher)["stem"], "ARoll-Widget-Take2")
        report = tc.render_report([
            {**row, "use": "cut", "suggested_in": 0.2, "suggested_out": 4.0,
             "metrics": {"speech_end": 5, "fillers": {"count": row["filler_count"]}},
             "flags": [], "sentences": [], "judge": {"structure_score": row["structure_score"]}}
            for row in rows[:3]
        ])
        self.assertIn("Best: `ARoll-Widget-BCam`", report)

    def test_example_config_matches_defaults(self):
        example = json.loads(tc.EXAMPLE_CONFIG.read_text(encoding="utf-8"))
        self.assertTrue(example["_doc"])
        self.assertEqual(set(example) - {"_doc"}, set(tc.DEFAULTS))
        loaded = tc.load_config(tc.EXAMPLE_CONFIG)
        for key, value in tc.DEFAULTS.items():
            self.assertEqual(loaded[key], value)

    def test_config_take_check_key_and_fail_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            shoot = Path(tmp) / "shoot"
            shoot.mkdir()
            cfg_path = Path(tmp) / "reel-style.json"
            cfg_path.write_text(json.dumps({
                "fonts": {"cover": "unused"},
                "take_check": {"pause_s": 0.3},
            }), encoding="utf-8")
            words = [
                word(" The", 0.0, 0.4),
                word(" gap", 0.4, 0.8),
                word(" here", 1.4, 1.8),
                word(" is", 1.8, 2.2),
                word(" long", 2.2, 6.0),
                word(" enough.", 6.0, 6.4),
            ]
            path = shoot / "ARoll-Gap.json"
            path.write_text(json.dumps(whisper(words)), encoding="utf-8")
            out = Path(tmp) / "out"
            code = tc.main([
                str(path), "--out-dir", str(out), "--judge", "none",
                "--config", str(cfg_path), "--fail-on", "yellow",
            ])
            self.assertEqual(code, 3)
            payload = json.loads((out / "ARoll-Gap.take.json").read_text())
            self.assertTrue(payload["metrics"]["pauses"])
            self.assertEqual(payload["verdict"], "yellow")

    def test_no_takes_and_bad_json_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty"
            empty.mkdir()
            out = Path(tmp) / "out"
            self.assertEqual(tc.main([str(empty), "--out-dir", str(out), "--judge", "none"]), 2)
            self.assertFalse(out.exists())
            bad = Path(tmp) / "Audio"
            bad.mkdir()
            (bad.parent / "shoot").mkdir()
            shoot = Path(tmp) / "shoot"
            (shoot / "Audio").mkdir(parents=True)
            (shoot / "Audio" / "ARoll-Bad.json").write_text("{not json", encoding="utf-8")
            self.assertEqual(tc.main([str(shoot), "--out-dir", str(out), "--judge", "none"]), 2)
            self.assertFalse(any(shoot.rglob("*.take.json")))

    def test_timestamp_format(self):
        self.assertEqual(tc.fmt_ts(65.3), "01:05.3")
        self.assertEqual(tc.fmt_ts(None), "-")

    def _write_take(self, stem, data):
        folder = tempfile.mkdtemp()
        path = Path(folder) / f"{stem}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return path

    @staticmethod
    def _tree(root):
        return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


if __name__ == "__main__":
    unittest.main()
