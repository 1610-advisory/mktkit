#!/usr/bin/env python3
"""Synthetic takes only. No network. The judge is a fake."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
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
        "windows": [{
            "in": 1.62, "out": 5.05, "idea": "Price the job before starting.",
            "hook_quote": "Most owners guess wrong.",
            "payoff_quote": "We price the job before we start.", "score": 4,
        }],
        "main_point": "Price the job before starting.",
        "problems": [
            {"type": "other", "quote": "we invented fusion", "start": 1.0, "end": 2.0, "note": "not said"},
            {"type": "filler", "quote": "guess wrong", "start": 2.22, "end": 2.99, "note": "soft"},
        ],
        "verdict": "yellow",
        "use": "cut",
        "reason": "Hook lands and the payoff is a full sentence.",
    }


def timeline(blocks, word_s=0.3, gap=0.1):
    """blocks: [(start_s, text)] -> whisper words, word_s long, gap apart."""
    out = []
    for start, text in blocks:
        t = start
        for part in text.split():
            out.append(word(" " + part, round(t, 3), round(t + word_s, 3)))
            t += word_s + gap
    return out


def span_of(words, first, last):
    """in/out of the words whose text starts with first and ends with last."""
    starts = [w for w in words if w["word"].strip() == first]
    ends = [w for w in words if w["word"].strip() == last]
    return starts[0]["start"], ends[-1]["end"]


EPISODE_A = ("This is the kitchen at the Acme house. Last time the walls were still open. "
             "Now the cabinets are in and the island is set. The stone goes on next week. "
             "We picked a warm white so the room stays bright all day. The hood is the last big piece.")
EPISODE_RAMBLE = "um so uh where was I um the the plumber came and uh we we moved some stuff around and um yeah"
EPISODE_B = ("Here is the part people ask about most. The pantry door is hidden in the cabinet run. "
             "You push the panel and the whole wall opens. It keeps the snacks out of sight and the room calm. "
             "That is my favorite detail in the whole house.")


def episode_words():
    return timeline([(1.0, EPISODE_A), (22.0, EPISODE_RAMBLE), (40.0, EPISODE_B)])


def tip_words():
    return timeline([(0.5, "Most owners guess the price wrong. We price the whole job before we start. "
                           "That way nobody gets a surprise bill at the end.")])


def window_reply(windows, verdict="green", use="cut", problems=None):
    return json.dumps({
        "windows": windows, "main_point": "x", "problems": problems or [],
        "verdict": verdict, "use": use, "reason": "test reply",
    })


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
        best = payload["judge"]["windows"][payload["judge"]["best_window"]]
        self.assertEqual(best["hook_quote"], "Most owners guess wrong.")
        self.assertEqual(best["in"], 1.5)
        self.assertEqual(best["out"], 5.2)
        self.assertEqual(payload["kind"], "line")
        self.assertEqual(payload["suggested_in"], 1.5)
        self.assertEqual(payload["suggested_out"], 5.2)
        self.assertEqual(payload["structure_score"], 4)
        self.assertEqual(payload["verdict"], "yellow")
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

    def test_07_folder_scan_keeps_prefixes_skips_stray_audio_and_does_not_write_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "shoot"
            audio = root / "Audio"
            audio.mkdir(parents=True)
            (root / "Video").mkdir()
            (root / "Day" / "Audio").mkdir(parents=True)
            (root / "Day" / "Video").mkdir()
            (root / "Video" / "Audio").mkdir()
            (root / "Loose" / "Audio").mkdir(parents=True)
            samples = {
                audio / "ARoll-One.json": whisper(clean_words()),
                audio / "CB-Two.json": whisper(clean_words()),
                audio / "BRoll-Nope.json": whisper(clean_words()),
                audio / "notes.json": whisper(clean_words()),
                root / "Day" / "Audio" / "ARoll-Nested.json": whisper(clean_words()),
                root / "Day" / "Audio" / "wild.json": whisper(clean_words()),
                root / "Video" / "Audio" / "ARoll-Stray.json": whisper(clean_words()),
                root / "Loose" / "Audio" / "ARoll-Loose.json": whisper(clean_words()),
                root / "ARoll-Outside.json": whisper(clean_words()),
            }
            for path, data in samples.items():
                path.write_text(json.dumps(data), encoding="utf-8")
            (root / "Video" / "ARoll-One.MP4").write_bytes(b"")
            before = self._tree(root)
            out = Path(tmp) / "out"
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                code = tc.main([str(root), "--out-dir", str(out), "--judge", "none"])
            self.assertEqual(code, 0)
            self.assertEqual(self._tree(root), before)
            written = sorted(p.name for p in out.glob("*.take.json"))
            self.assertEqual(written, ["ARoll-Nested.take.json", "ARoll-One.take.json", "CB-Two.take.json"])
            skipped = [line for line in err.getvalue().splitlines() if "skipped" in line]
            self.assertEqual(len(skipped), 1)
            self.assertIn("skipped 2 Audio folder(s)", skipped[0])
            self.assertIn(str(Path("Video") / "Audio"), skipped[0])
            self.assertIn(str(Path("Loose") / "Audio"), skipped[0])
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
                "--config", str(cfg_path), "--fail-on", "yellow", "--kind", "tip",
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
            shoot = Path(tmp) / "shoot"
            (shoot / "Audio").mkdir(parents=True)
            (shoot / "Video").mkdir()
            (shoot / "Audio" / "ARoll-Bad.json").write_text("{not json", encoding="utf-8")
            self.assertEqual(tc.main([str(shoot), "--out-dir", str(out), "--judge", "none"]), 2)
            self.assertFalse(any(shoot.rglob("*.take.json")))

    # ---- v1.1: best window, kinds, restarts, calibration, cache, judge argv ----

    def _run_one(self, stem, data, reply, extra=None):
        prompts = []

        def runner(cmd, prompt, timeout):
            prompts.append(prompt)
            return reply, "", 0

        path = self._write_take(stem, data)
        out = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(out, ignore_errors=True))
        tc.JUDGE_RUNNER = runner
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = tc.main([str(path), "--out-dir", out, "--jobs", "1"] + (extra or []))
        self.assertEqual(code, 0)
        payload = json.loads((Path(out) / f"{stem}.take.json").read_text())
        return payload, prompts, Path(out)

    def test_episode_two_windows_and_ramble_is_not_red(self):
        words = episode_words()
        self.assertGreater(words[-1]["end"], 55)
        a_in, a_out = span_of(words, "This", "piece.")
        b_in, b_out = span_of(words, "Here", "house.")
        reply = window_reply(
            [
                {"in": a_in, "out": a_out, "idea": "kitchen progress", "hook_quote": "This is the kitchen",
                 "payoff_quote": "The hood is the last big piece.", "score": 4},
                {"in": b_in + 0.05, "out": b_out - 0.05, "idea": "hidden pantry",
                 "hook_quote": "Here is the part people ask about most.",
                 "payoff_quote": "That is my favorite detail in the whole house.", "score": 5},
            ],
            verdict="green", use="cut",
            problems=[{"type": "ramble", "quote": "where was I", "start": 23.0, "end": 24.0, "note": "lost"}],
        )
        payload, prompts, _ = self._run_one("ARoll-Kitchen-Walkthrough", whisper(episode_words()), reply)
        self.assertEqual(payload["kind"], "episode")
        self.assertIn("Take kind: episode", prompts[0])
        self.assertIn(payload["verdict"], ("green", "yellow"))
        self.assertEqual(payload["verdict"], "green")
        self.assertEqual(payload["metrics_verdict"], "yellow")  # the ramble's fillers, whole take
        self.assertEqual(payload["window_flags"], [])
        self.assertEqual(payload["suggested_in"], b_in)
        self.assertEqual(payload["suggested_out"], b_out)
        self.assertEqual(payload["structure_score"], 5)
        self.assertEqual(len(payload["judge"]["windows"]), 2)
        self.assertFalse(payload["judge"]["problems"][0]["in_best_window"])

    def test_judge_red_with_valid_window_becomes_yellow(self):
        words = tip_words()
        w_in, w_out = span_of(words, "Most", "end.")
        reply = window_reply(
            [{"in": w_in, "out": w_out, "idea": "price first", "hook_quote": "Most owners guess the price wrong.",
              "payoff_quote": None, "score": 3}],
            verdict="red", use="reshoot",
        )
        payload, _, _ = self._run_one("ARoll-Price", whisper(words), reply)
        self.assertEqual(payload["kind"], "tip")
        self.assertEqual(payload["judge"]["claimed_verdict"], "red")
        self.assertEqual(payload["verdict"], "yellow")
        self.assertEqual(payload["use"], "trim")
        self.assertTrue(payload["judge"]["corrections"])

    def test_judge_no_windows_is_red(self):
        words = tip_words()
        reply = window_reply([], verdict="green", use="cut")
        payload, _, _ = self._run_one("ARoll-Price", whisper(words), reply)
        self.assertEqual(payload["verdict"], "red")
        self.assertIn(payload["use"], ("reshoot", "blooper", "voiceover"))
        self.assertIsNone(payload["suggested_in"])
        self.assertEqual(payload["structure_score"], 1)

    def test_window_shorter_than_minimum_is_dropped(self):
        words = tip_words()  # about 11 s of speech, so the minimum is 8 s
        w_in, w_out = span_of(words, "Most", "wrong.")
        reply = window_reply([{"in": w_in, "out": w_out, "idea": "short", "hook_quote": None,
                               "payoff_quote": None, "score": 5}])
        payload, _, _ = self._run_one("ARoll-Price", whisper(words), reply)
        self.assertEqual(payload["window_min_s"], 8.0)
        self.assertEqual(payload["verdict"], "red")
        self.assertTrue(any("shorter" in d.get("reason", "") for d in payload["judge_dropped"]))

    def test_line_kind_short_opener_is_not_red(self):
        words = timeline([(0.5, "Welcome back to the Acme house, today we finish the kitchen.")])
        span = words[-1]["end"] - words[0]["start"]
        self.assertLess(span, 8)
        self.assertGreater(span, 4)
        analysis = tc.analyze(whisper(words), self.cfg, stem="ARoll-Opener")
        self.assertEqual(analysis["kind"], "line")
        self.assertAlmostEqual(analysis["window_min_s"], round(span, 3))
        self.assertNotEqual(analysis["metrics_verdict"], "red")
        reply = window_reply([{"in": words[0]["start"], "out": words[-1]["end"], "idea": "opener",
                               "hook_quote": "Welcome back to the Acme house", "payoff_quote": None, "score": 5}])
        payload, prompts, _ = self._run_one("ARoll-Opener", whisper(words), reply)
        self.assertIn("Take kind: line", prompts[0])
        self.assertEqual(payload["kind"], "line")
        self.assertEqual(payload["verdict"], "green")
        # a silent take is never line
        silent = tc.analyze(whisper([word(" Thank", 0.5, 0.8), word(" you.", 0.8, 1.1)]), self.cfg)
        self.assertNotEqual(silent["kind"], "line")

    def test_restart_ignores_going_to_be_and_catches_the_reason_we(self):
        fluent = timeline([(0.5, "It is going to be a long week, and it is going to be worth it. "
                                 "We are going to be done by Friday.")])
        result = tc.analyze(whisper(fluent), self.cfg)
        self.assertEqual(result["metrics"]["restarts"], [])
        self.assertNotIn("restart", [f["code"] for f in result["flags"]])
        stutter = timeline([(0.5, "So the reason we the reason we do this is the price.")])
        result = tc.analyze(whisper(stutter), self.cfg)
        self.assertTrue(any(r["ngram"] == "the reason we" for r in result["metrics"]["restarts"]))
        self.assertIn("restart", [f["code"] for f in result["flags"]])
        self.assertIsNotNone(result["metrics"]["restarts_per_min"])
        # a 4-word repeat inside the window counts even when not back to back
        repeat = timeline([(0.5, "Cabinet doors close soft now. Cabinet doors close soft and quiet.")])
        result = tc.analyze(whisper(repeat), self.cfg)
        self.assertTrue(any(r["n"] >= 4 for r in result["metrics"]["restarts"]))

    def test_restart_rate_threshold(self):
        # one restart over about 28 s is about 2.1/min, under the default 3/min
        filler = ("Cabinets arrive Monday morning. Plumbers set fixtures after drywall. Painters prime every wall twice. "
                  "Electricians hang lights near windows. Flooring crews start upstairs first. Tile setters finish showers early. "
                  "Inspectors walk framing before insulation. Trim carpenters fit doors carefully. Homeowners pick hardware late. "
                  "Countertops need templates measured onsite. Appliances ship separately from cabinets. ")
        long_take = timeline([(0.5, "So the reason we the reason we do this is the price. " + filler)])
        result = tc.analyze(whisper(long_take), self.cfg)
        self.assertEqual(len(result["metrics"]["restarts"]), 1)
        self.assertNotIn("restart", [f["code"] for f in result["flags"]])

    def test_kind_inference_from_stem(self):
        cfg = self.cfg
        self.assertEqual(tc.infer_kind("ARoll-Kitchen-Walkthrough", 60, False, cfg), "episode")
        self.assertEqual(tc.infer_kind("CB_monthly_update", 60, False, cfg), "episode")
        self.assertEqual(tc.infer_kind("ARoll-Basement-PROGRESS-Take2", 60, False, cfg), "episode")
        self.assertEqual(tc.infer_kind("ARoll-Walkway-Tip", 60, False, cfg), "tip")
        self.assertEqual(tc.infer_kind("ARoll-PricingTip", 60, False, cfg), "tip")
        self.assertEqual(tc.infer_kind("ARoll-Kitchen-Walkthrough", 5, False, cfg), "line")
        self.assertEqual(tc.infer_kind("ARoll-Kitchen-Walkthrough", 5, True, cfg), "episode")
        result = tc.analyze(whisper(tip_words()), cfg, stem="ARoll-Price", kind="episode")
        self.assertEqual(result["kind"], "episode")
        self.assertEqual(result["kind_source"], "flag")

    def test_default_kind_and_tip_keywords(self):
        cfg = dict(self.cfg, default_kind="episode")
        self.assertEqual(tc.infer_kind("ARoll-Kitchen-Cabinets", 60, False, cfg), "episode")
        self.assertEqual(tc.infer_kind("ARoll-Kitchen-Trim-Tip-PRIMARY", 60, False, cfg), "tip")
        self.assertEqual(tc.infer_kind("ARoll-Kitchen-Walkthrough-Tip", 60, False, cfg), "tip")
        self.assertEqual(tc.infer_kind("ARoll-Kitchen-Cabinets", 60, False, dict(cfg, default_kind="bogus")), "tip")

    def test_line_take_uses_line_floor(self):
        opener = timeline([(0.5, "Every great kitchen starts with one good plan.")])
        result = tc.analyze(whisper(opener), self.cfg, stem="ARoll-Opener")
        self.assertEqual(result["kind"], "line")
        self.assertNotIn("short_speech", [f["code"] for f in result["flags"]])
        stub = timeline([(0.5, "Okay go.")])
        self.assertIn("short_speech", [f["code"] for f in tc.analyze(whisper(stub), self.cfg, stem="ARoll-Stub")["flags"]])

    def test_hook_flag_only_for_tip(self):
        slow = timeline([(0.5, "When we started on this house the first thing we noticed was how the light "
                               "came in from the south side of the lot. Then we planned around it.")])
        tip = tc.analyze(whisper(slow), self.cfg, stem="ARoll-Light")
        episode = tc.analyze(whisper(slow), self.cfg, stem="ARoll-Light-Tour")
        self.assertIn("long_hook", [f["code"] for f in tip["flags"]])
        self.assertNotIn("long_hook", [f["code"] for f in episode["flags"]])

    def test_calibration_counts_and_false_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            takes = {
                "ARoll-Good": whisper(clean_words()),
                "ARoll-Silent": whisper([word(" Thank", 0.5, 0.8), word(" you.", 0.8, 1.1)], text="Thank you."),
                "CB-Yellow": whisper(filler_words()),
            }
            paths = []
            (tmp / "in").mkdir()
            for stem, data in takes.items():
                path = tmp / "in" / f"{stem}.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                paths.append(str(path))
            labels = tmp / "labels.json"
            labels.write_text(json.dumps({
                "ARoll-Good": "bad", "ARoll-Silent": "ok", "CB-Yellow": "ok", "ARoll-Gone": "ok",
            }), encoding="utf-8")
            out = tmp / "out"
            stdout = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                code = tc.main(paths + ["--out-dir", str(out), "--judge", "none", "--calibrate", str(labels),
                                        "--fail-on", "red"])
            self.assertEqual(code, 3)  # exit code follows --fail-on only
            report = (out / "take-report.md").read_text()
        self.assertIn("## Calibration", stdout.getvalue())
        self.assertIn("## Calibration", report)
        self.assertIn("| ok | 0 | 1 | 1 |", report)
        self.assertIn("| bad | 1 | 0 | 0 |", report)
        self.assertIn("False red (ok came out red): 1", report)
        self.assertIn("`ARoll-Silent`", report.split("False red")[1])
        self.assertIn("False green (bad came out green): 1", report)
        self.assertIn("`ARoll-Good`", report.split("False green")[1])
        self.assertIn("`ARoll-Gone`", report.split("Missing from this run")[1])

        cal = tc.calibrate(
            [{"stem": "A", "verdict": "red", "flags": [{"level": "red", "reason": "too short"}]}],
            {"A": "ok", "B": "bad"},
        )
        self.assertEqual(cal["counts"]["ok"]["red"], 1)
        self.assertEqual(cal["false_red"][0]["stem"], "A")
        self.assertIn("too short", cal["false_red"][0]["reason"])
        self.assertEqual(cal["missing"], ["B"])

    def test_bad_calibration_file_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ARoll-X.json"
            path.write_text(json.dumps(whisper(clean_words())), encoding="utf-8")
            labels = Path(tmp) / "labels.json"
            labels.write_text(json.dumps({"ARoll-X": "maybe"}), encoding="utf-8")
            with redirect_stderr(io.StringIO()):
                code = tc.main([str(path), "--out-dir", str(Path(tmp) / "out"), "--judge", "none",
                                "--calibrate", str(labels)])
            self.assertEqual(code, 2)

    def test_judge_cache_hit_skips_second_call(self):
        calls = []
        reply = "```json\n" + json.dumps(judge_payload()) + "\n```"

        def runner(cmd, prompt, timeout):
            calls.append(prompt)
            return reply, "", 0

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "in").mkdir()
            path = Path(tmp) / "in" / "ARoll-Clean.json"
            path.write_text(json.dumps(whisper(clean_words())), encoding="utf-8")
            out = Path(tmp) / "out"
            tc.JUDGE_RUNNER = runner
            args = [str(path), "--out-dir", str(out), "--jobs", "1"]
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(tc.main(args), 0)
                first = json.loads((out / "ARoll-Clean.take.json").read_text())
                self.assertEqual(len(calls), 1)
                self.assertEqual(len(list((out / ".judge-cache").glob("*.json"))), 1)
                self.assertEqual(tc.main(args), 0)
                second = json.loads((out / "ARoll-Clean.take.json").read_text())
                self.assertEqual(len(calls), 1)
                self.assertFalse(first["judge_cached"])
                self.assertTrue(second["judge_cached"])
                self.assertEqual(first["verdict"], second["verdict"])
                # a changed kind changes the prompt, so it misses
                self.assertEqual(tc.main(args + ["--kind", "episode"]), 0)
                self.assertEqual(len(calls), 2)
                self.assertEqual(tc.main(args + ["--no-judge-cache"]), 0)
                self.assertEqual(len(calls), 3)

    def test_default_judge_is_claude_no_tools_no_mcp(self):
        cmd = tc.DEFAULTS["judge_cmd"]
        self.assertEqual(cmd[:2], ["claude", "-p"])
        self.assertEqual(cmd[cmd.index("--model") + 1], "claude-sonnet-5-5")
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")
        self.assertIn("--strict-mcp-config", cmd)
        self.assertEqual(json.loads(cmd[cmd.index("--mcp-config") + 1]), {"mcpServers": {}})
        self.assertEqual(cmd[cmd.index("--setting-sources") + 1], "")
        self.assertIn("--no-session-persistence", cmd)
        self.assertFalse(any("{prompt}" in part for part in cmd))  # prompt goes to stdin
        example = json.loads(tc.EXAMPLE_CONFIG.read_text(encoding="utf-8"))
        self.assertIn("xai/grok-4.7", example["_doc"])
        skill = (tc.HERE.parent / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("xai/grok-4.7", skill)
        self.assertIn("claude-sonnet-5-5", skill)

    def test_judge_runs_in_empty_temp_dir_with_prompt_on_stdin(self):
        script = ("import os, sys, json; data = sys.stdin.read(); "
                  "print(json.dumps({'cwd': os.getcwd(), 'ls': os.listdir('.'), 'stdin': data}))")
        stdout, _, code = tc.run_judge_process([sys.executable, "-c", script], "hello judge", 30)
        self.assertEqual(code, 0)
        seen = json.loads(stdout)
        self.assertEqual(seen["stdin"], "hello judge")
        self.assertEqual(seen["ls"], [])
        self.assertTrue(os.path.basename(seen["cwd"]).startswith("take-check-judge-"))
        self.assertNotEqual(os.path.realpath(seen["cwd"]), os.path.realpath(os.getcwd()))
        self.assertFalse(os.path.exists(seen["cwd"]))

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
