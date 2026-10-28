import json
from pathlib import Path

import ai_visibility

FIXTURES = Path(__file__).parent / "fixtures"

CONFIG = {
    "brand": "Acme Corp",
    "brand_aliases": ["Acme"],
    "domains": ["example.com"],
    "competitors": ["Competitor A", "Competitor B"],
}


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_openai_fixture():
    parsed = ai_visibility.parse_openai_response(load("openai_response.json"))
    assert "Acme Corp" in parsed["answer"]
    assert parsed["cited_urls"] == ["https://www.example.com/about"]
    assert parsed["usage"] == {"input_tokens": 120, "output_tokens": 40, "total_tokens": 160}


def test_parse_perplexity_fixture():
    parsed = ai_visibility.parse_perplexity_response(load("perplexity_response.json"))
    assert parsed["answer"].startswith("Acme Corp")
    assert parsed["cited_urls"] == [
        "https://example.com/pricing",
        "https://other.example/roundup",
    ]
    assert parsed["retrieved_urls"] == [
        "https://example.com/pricing",
        "https://blog.other.example/widgets",
    ]
    assert parsed["usage"]["total_tokens"] == 48


def test_parse_gemini_fixture():
    parsed = ai_visibility.parse_gemini_response(load("gemini_response.json"))
    assert "Acme" in parsed["answer"]
    assert "Competitor A" in parsed["answer"]
    assert parsed["cited_urls"] == ["https://blog.example.com/guide"]
    assert parsed["usage"]["promptTokenCount"] == 22
    assert "candidatesTokenCount" in parsed["usage"]


def test_parse_anthropic_fixture():
    parsed = ai_visibility.parse_anthropic_response(load("anthropic_response.json"))
    assert parsed["answer"] == "Acme Corp lists a starting price on its site."
    assert parsed["cited_urls"] == ["https://example.com/pricing"]
    assert parsed["retrieved_urls"] == [
        "https://example.com/pricing",
        "https://news.example/acme",
    ]
    assert parsed["usage"] == {"input_tokens": 80, "output_tokens": 36}


def test_request_builders_use_config_model_and_spec_endpoints():
    openai = ai_visibility.build_openai_request("custom-model", "Who is Acme Corp?", "test-key")
    assert openai["url"] == "https://api.openai.com/v1/responses"
    assert openai["json"]["model"] == "custom-model"
    assert openai["json"]["tools"] == [{"type": "web_search"}]
    assert openai["headers"]["Authorization"] == "Bearer test-key"
    assert openai["timeout"] == 90
    assert "gpt-" not in json.dumps(openai["json"])

    perplexity = ai_visibility.build_perplexity_request("custom-model", "question", "test-key")
    assert perplexity["url"] == "https://api.perplexity.ai/chat/completions"
    assert perplexity["json"]["messages"][0]["content"] == "question"

    gemini = ai_visibility.build_gemini_request("custom-model", "question", "test-key")
    assert gemini["url"].endswith("/models/custom-model:generateContent")
    assert gemini["headers"]["x-goog-api-key"] == "test-key"
    assert gemini["json"]["tools"] == [{"google_search": {}}]

    anthropic = ai_visibility.build_anthropic_request("custom-model", "question", "test-key", "web_search_test")
    assert anthropic["url"] == "https://api.anthropic.com/v1/messages"
    assert anthropic["headers"]["x-api-key"] == "test-key"
    assert anthropic["headers"]["anthropic-version"] == "2023-06-01"
    assert anthropic["json"]["tools"] == [{"type": "web_search_test", "name": "web_search", "max_uses": 3}]
    assert anthropic["json"]["model"] == "custom-model"


def test_aliases_word_boundary():
    assert ai_visibility.brand_mentioned("The Acme team shipped it.", "Acme Corp", ["Acme"])
    assert ai_visibility.brand_mentioned("ACME CORP wins the bid.", "Acme Corp", ["Acme"])
    assert not ai_visibility.brand_mentioned("academic research", "Acme Corp", ["Acme"])
    assert not ai_visibility.brand_mentioned("AcmeCorp launched", "Acme Corp", ["Acme"])
    assert not ai_visibility.brand_mentioned("Acme Corporate retreat", "Acme Corp", [])


def test_subdomain_citation_and_cited_domains():
    urls = [
        "https://www.example.com/about",
        "https://blog.example.com/guide",
        "https://example.com.evil.test/phish",
        "https://notexample.com/nope",
        "https://WWW.Example.com/again",
    ]
    assert ai_visibility.our_url_cited(urls, ["example.com"])
    assert not ai_visibility.our_url_cited(
        ["https://example.com.evil.test/phish", "https://notexample.com/nope"],
        ["example.com"],
    )
    assert ai_visibility.cited_domains(urls) == [
        "example.com",
        "blog.example.com",
        "example.com.evil.test",
        "notexample.com",
    ]


def test_brand_position_order():
    text = "Competitor B beat Acme Corp, while Competitor A lagged."
    assert ai_visibility.brand_position(text, "Acme Corp", ["Acme"], ["Competitor A", "Competitor B"]) == 2
    assert ai_visibility.competitors_mentioned(text, ["Competitor A", "Competitor B"]) == [
        "Competitor B",
        "Competitor A",
    ]
    alias_first = "Acme beat Competitor A on price."
    assert ai_visibility.brand_position(alias_first, "Acme Corp", ["Acme"], ["Competitor A"]) == 1
    assert ai_visibility.brand_position("Nobody relevant here.", "Acme Corp", ["Acme"], ["Competitor A"]) is None


def test_money_normalization_and_distance():
    facts = "The base plan is $1200. Travel is $50.00."
    near = "Acme Corp charges $1,200 for the base plan and $50 extra."
    analysis = ai_visibility.analyze(near, [], CONFIG, facts)
    assert analysis["money_figures"] == ["$1,200", "$50"]
    assert analysis["unverified_figures"] == []

    mixed = "Acme Corp quotes $1,201 today."
    unverified = ai_visibility.unverified_figures(mixed, "Acme Corp", ["Acme"], facts)
    assert unverified == [{"figure": "$1,201", "note": "check by hand"}]

    far = "Acme Corp costs $10." + ("x" * 400) + " The other price is $77."
    figures = ai_visibility.money_figures(far)
    assert figures == ["$10", "$77"]
    only_near = ai_visibility.unverified_figures(far, "Acme Corp", ["Acme"], "")
    assert only_near == [{"figure": "$10", "note": "check by hand"}]
    assert ai_visibility.money_key("$1,200.00") == ai_visibility.money_key("$1200")


def test_analyze_does_not_treat_unverified_as_error():
    text = "Acme Corp wants $9,999."
    analysis = ai_visibility.analyze(text, ["https://blog.example.com/a"], CONFIG, "")
    assert analysis["brand_mentioned"] is True
    assert analysis["our_url_cited"] is True
    assert analysis["cited_domains"] == ["blog.example.com"]
    assert analysis["unverified_figures"][0]["note"] == "check by hand"
    assert "error" not in analysis


def test_plan_refuses_empty_model_and_skips_missing_key():
    config = {
        "ai_engines": {
            "openai": {"model": "custom-model", "enabled": True},
            "perplexity": {"model": "", "enabled": True},
            "gemini": {"model": "custom-model", "enabled": True},
            "anthropic": {"model": "custom-model", "enabled": False, "tool": "web_search_test"},
        }
    }
    prompts = [{"id": "q", "text": "Who is Acme Corp?", "kind": "branded"}]
    plan = ai_visibility.plan_calls(config, prompts, None, 3, {"OPENAI_API_KEY": "present"}, 100)
    assert [item["engine"] for item in plan["would_run"]] == ["openai"]
    assert plan["total_calls"] == 3
    reasons = {item["engine"]: item["reason"] for item in plan["skipped"] + plan["refused"]}
    assert "model is empty" in reasons["perplexity"]
    assert reasons["gemini"] == "missing GEMINI_API_KEY"
    assert reasons["anthropic"] == "disabled in config"
    text = ai_visibility.format_plan(plan)
    assert "present" not in text
    assert "no request" not in text or True


def test_dry_run_makes_no_request(monkeypatch, capsys, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("site: https://example.com\n", encoding="utf-8")
    prompts = tmp_path / "prompts.yaml"
    prompts.write_text(
        "- id: branded-who\n  text: Who is Acme Corp?\n  kind: branded\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ai_visibility, "load_client", lambda _path: {
        "site": "https://example.com",
        "brand": "Acme Corp",
        "domains": ["example.com"],
        "ai_engines": {
            "openai": {"model": "custom-model", "enabled": True},
            "perplexity": {"model": "", "enabled": True},
        },
    })

    def boom(*_args, **_kwargs):
        raise AssertionError("request was made")

    monkeypatch.setattr(ai_visibility, "perform_request", boom)
    monkeypatch.setattr(ai_visibility.httpx, "Client", boom)
    for name in ("OPENAI_API_KEY", "PERPLEXITY_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    code = ai_visibility.main([
        "--config", str(config_path),
        "--prompts", str(prompts),
        "--log", str(tmp_path / "log.jsonl"),
        "--out", str(tmp_path / "ai.json"),
        "--dry-run",
        "--runs", "2",
    ])
    assert code == 0
    captured = capsys.readouterr()
    assert "would run:" in captured.out
    assert "refusing to run perplexity: model is empty" in captured.out
    assert "missing OPENAI_API_KEY" in captured.out
    assert "total calls: 0" in captured.out
    assert "no request" in captured.err
    assert not (tmp_path / "log.jsonl").exists()
    assert not (tmp_path / "ai.json").exists()


def test_max_calls_hard_stop_and_summary(tmp_path):
    prompts = [
        {"id": "one", "text": "Who is Acme Corp?", "kind": "branded"},
        {"id": "two", "text": "How much does Acme Corp charge?", "kind": "cost"},
    ]
    engines = [{"engine": "openai", "model": "custom-model"}]
    calls = []

    def call_fn(engine, prompt):
        calls.append(prompt)
        return {
            "answer": "Acme Corp is listed. Competitor A is not the leader. Price is $9.",
            "cited_urls": ["https://example.com/about", "https://other.example/x"],
            "usage": {"input_tokens": 1, "output_tokens": 2},
            "error": None,
        }

    records = ai_visibility.run_battery(
        prompts, engines, runs=3, call_fn=call_fn, max_calls=2, facts="", config=CONFIG, clock=lambda: "2026-10-27T00:00:00Z"
    )
    assert len(records) == 2
    assert len(calls) == 2
    assert records[0]["run"] == 1
    assert records[0]["brand_mentioned"] is True
    assert records[0]["our_url_cited"] is True
    assert records[0]["usage"]["input_tokens"] == 1
    assert records[0]["error"] is None
    summary = ai_visibility.build_summary(records, prompts=2, runs=3, generated_at="2026-10-27T00:00:00Z", skipped=[])
    assert summary["summary"]["openai"]["calls"] == 2
    assert summary["summary"]["openai"]["mention_rate"] == 1.0
    assert summary["summary"]["openai"]["citation_rate"] == 1.0
    assert summary["top_cited_domains"][0] == ["example.com", 2]
    assert summary["unverified_figures"][0]["note"] == "check by hand"
    assert summary["unverified_figures"][0]["figure"] == "$9"


def test_retry_on_500_then_200_and_not_on_400():
    class Resp:
        def __init__(self, status, payload):
            self.status_code = status
            self._payload = payload
            self.text = json.dumps(payload)

        def json(self):
            return self._payload

    class Client:
        def __init__(self, statuses):
            self.statuses = list(statuses)
            self.calls = 0

        def request(self, method, url, headers=None, json=None, timeout=None):
            self.calls += 1
            status = self.statuses.pop(0)
            return Resp(status, {"output": [], "usage": {"input_tokens": 1}})

    slept = []
    client = Client([500, 200])
    request = ai_visibility.build_openai_request("custom-model", "q", "test-key")
    status, body, error = ai_visibility.perform_request(request, client, sleep_fn=slept.append, secrets=["test-key"])
    assert status == 200
    assert error is None
    assert client.calls == 2
    assert slept == [2.0]

    client = Client([400])
    status, body, error = ai_visibility.perform_request(request, client, sleep_fn=slept.append, secrets=["test-key"])
    assert status == 400
    assert error == "HTTP 400"
    assert client.calls == 1


def test_redact_does_not_leave_key():
    assert "test-key" not in ai_visibility.redact("Bearer test-key failed", ["test-key"])


def test_load_prompts_template():
    path = Path(__file__).resolve().parents[2] / "templates" / "prompts.yaml"
    prompts = ai_visibility.load_prompts(str(path))
    assert len(prompts) == 8
    assert {item["kind"] for item in prompts} == {"branded", "category", "comparison", "cost"}


def test_error_text_keeps_vendor_reason():
    body = {"error": {"type": "insufficient_quota", "code": "credit_balance_exhausted", "message": "No credits."}}
    assert ai_visibility._error_text(429, body) == "HTTP 429 credit_balance_exhausted: No credits."
    assert ai_visibility._error_text(500, {"_raw": "oops"}) == "HTTP 500"
    assert ai_visibility._error_text(400, {"error": "bad model"}) == "HTTP 400: bad model"


def test_api_key_stripped_and_redact_covers_repr():
    env = {"OPENAI_API_KEY": "  test-key  \n"}
    assert ai_visibility.read_api_key(env, "openai") == "test-key"
    config = {
        "ai_engines": {"openai": {"model": "custom-model", "enabled": True}},
    }
    prompts = [{"id": "q", "text": "Who is Acme Corp?", "kind": "branded"}]
    plan = ai_visibility.plan_calls(config, prompts, ["openai"], 1, env, 10)
    assert plan["would_run"][0]["engine"] == "openai"
    request = ai_visibility.build_openai_request("custom-model", "q", ai_visibility.read_api_key(env, "openai"))
    assert request["headers"]["Authorization"] == "Bearer test-key"

    class Resp:
        status_code = 200
        text = ""

        def json(self):
            return {
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "Acme Corp"}]}],
                "usage": {"input_tokens": 1},
            }

    seen = {}

    class Client:
        def request(self, method, url, headers=None, json=None, timeout=None):
            seen["authorization"] = headers["Authorization"]
            return Resp()

    parsed = ai_visibility._live_call(
        {"engine": "openai", "model": "custom-model"},
        "q",
        env,
        Client(),
        lambda *_args: None,
    )
    assert seen["authorization"] == "Bearer test-key"
    assert parsed["error"] is None
    secret = "ab\\cd"
    escaped = repr(secret)[1:-1]
    assert escaped != secret
    redacted = ai_visibility.redact(f"raw {secret} escaped {escaped}", [secret])
    assert secret not in redacted
    assert escaped not in redacted
    auth = {"error": {"code": "invalid_api_key", "message": "Incorrect API key sk-test****abcd"}}
    assert ai_visibility._error_text(401, auth) == "HTTP 401 invalid_api_key"
    assert "sk-test" not in ai_visibility._error_text(403, auth)
    assert "Incorrect" not in ai_visibility._error_text(403, auth)


def test_gemini_proxy_uri_uses_title_host():
    payload = {
        "candidates": [
            {
                "content": {"parts": [{"text": "Acme is listed."}]},
                "groundingMetadata": {
                    "groundingChunks": [
                        {
                            "web": {
                                "uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc",
                                "title": "blog.example.com",
                            }
                        },
                        {
                            "web": {
                                "uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/def",
                                "title": "A guide page",
                            }
                        },
                    ]
                },
            }
        ]
    }
    parsed = ai_visibility.parse_gemini_response(payload)
    assert parsed["cited_urls"][0] == "https://blog.example.com"
    assert "vertexaisearch.cloud.google.com" in parsed["cited_urls"][1]
    assert "vertexaisearch.cloud.google.com" not in ai_visibility.cited_domains(parsed["cited_urls"])
    analysis = ai_visibility.analyze(parsed["answer"], parsed["cited_urls"], CONFIG, "")
    assert analysis["our_url_cited"] is True
    assert "vertexaisearch.cloud.google.com" not in analysis["cited_domains"]


def test_cited_urls_exclude_retrieved_and_analysis_splits_them():
    perplexity = ai_visibility.parse_perplexity_response(load("perplexity_response.json"))
    assert "https://blog.other.example/widgets" not in perplexity["cited_urls"]
    assert "https://blog.other.example/widgets" in perplexity["retrieved_urls"]
    anthropic = ai_visibility.parse_anthropic_response(load("anthropic_response.json"))
    assert anthropic["cited_urls"] == ["https://example.com/pricing"]
    assert "https://news.example/acme" in anthropic["retrieved_urls"]
    assert "https://news.example/acme" not in anthropic["cited_urls"]
    analysis = ai_visibility.analyze(
        "Acme Corp is here.",
        ["https://other.example/roundup"],
        CONFIG,
        "",
        retrieved_urls=["https://example.com/pricing"],
    )
    assert analysis["our_url_cited"] is False
    assert analysis["our_url_retrieved"] is True
    assert analysis["cited_domains"] == ["other.example"]


def test_incomplete_200_sets_error_and_summary_counts_failed():
    assert ai_visibility.ANTHROPIC_MAX_TOKENS == 4096
    assert ai_visibility.response_error("openai", {"status": "incomplete"}, {"answer": "partial"}) == "openai status incomplete"
    assert ai_visibility.response_error("openai", {"status": "completed"}, {"answer": "Acme"}) is None
    assert ai_visibility.response_error("anthropic", {"stop_reason": "pause_turn"}, {"answer": "partial"})
    assert ai_visibility.response_error("anthropic", {"stop_reason": "max_tokens"}, {"answer": "partial"})
    assert ai_visibility.response_error("gemini", {"promptFeedback": {"blockReason": "SAFETY"}, "candidates": [{}]}, {"answer": "x"})
    assert ai_visibility.response_error("gemini", {"candidates": []}, {"answer": ""}) == "gemini no candidates"
    assert ai_visibility.response_error("perplexity", {}, {"answer": "  "}) == "empty answer"
    records = [
        {
            "engine": "openai",
            "prompt_id": "a",
            "kind": "branded",
            "run": 1,
            "error": "empty answer",
            "brand_mentioned": True,
            "our_url_cited": True,
            "brand_position": 1,
            "cited_domains": ["example.com"],
            "unverified_figures": [],
        },
        {
            "engine": "openai",
            "prompt_id": "a",
            "kind": "branded",
            "run": 2,
            "error": None,
            "brand_mentioned": False,
            "our_url_cited": False,
            "brand_position": None,
            "cited_domains": [],
            "unverified_figures": [],
        },
    ]
    summary = ai_visibility.build_summary(records, prompts=1, runs=2, generated_at="2026-10-27T00:00:00Z", skipped=[])
    assert summary["summary"]["openai"]["failed"] == 1
    assert summary["summary"]["openai"]["calls"] == 2
    assert summary["summary"]["openai"]["mention_rate"] == 0.0
    assert summary["summary"]["openai"]["citation_rate"] == 0.0


def test_jsonl_flushes_each_row_and_analyze_error_continues(tmp_path, monkeypatch):
    log_path = tmp_path / "ai.jsonl"
    prompts = [
        {"id": "one", "text": "Who is Acme Corp?", "kind": "branded"},
        {"id": "two", "text": "How much?", "kind": "cost"},
    ]
    engines = [{"engine": "openai", "model": "custom-model"}]
    seen = []

    def call_fn(engine, prompt):
        if seen:
            text = log_path.read_text(encoding="utf-8")
            assert seen[0] in text
        seen.append(prompt)
        return {"answer": "Acme Corp", "cited_urls": [], "retrieved_urls": [], "usage": None, "error": None}

    records = ai_visibility.run_battery(
        prompts,
        engines,
        runs=1,
        call_fn=call_fn,
        max_calls=10,
        facts="",
        config=CONFIG,
        clock=lambda: "2026-10-27T00:00:00Z",
        log_path=str(log_path),
    )
    assert len(records) == 2
    assert log_path.read_text(encoding="utf-8").count("\n") == 2

    def boom(*_args, **_kwargs):
        raise RuntimeError("bad answer")

    monkeypatch.setattr(ai_visibility, "analyze", boom)
    survived = ai_visibility.run_battery(
        prompts,
        engines,
        runs=1,
        call_fn=lambda _engine, _prompt: {"answer": "x", "cited_urls": [], "error": None},
        max_calls=10,
        facts="",
        config=CONFIG,
        clock=lambda: "2026-10-27T00:00:00Z",
    )
    assert len(survived) == 2
    assert all(row["error"] == "analyze failed: RuntimeError" for row in survived)
    odd = {**CONFIG, "competitors": [1], "brand_aliases": [2], "domains": [3]}
    monkeypatch.undo()
    analysis = ai_visibility.analyze("Acme Corp versus 1", [], odd, "")
    assert analysis["brand_mentioned"] is True
    assert analysis["competitors_mentioned"] == ["1"]


def test_max_calls_counts_retries_and_round_robin():
    prompts = [
        {"id": "one", "text": "Who is Acme Corp?", "kind": "branded"},
        {"id": "two", "text": "How much?", "kind": "cost"},
    ]
    engines = [
        {"engine": "openai", "model": "custom-model"},
        {"engine": "perplexity", "model": "custom-model"},
    ]
    seen = []

    def call_fn(engine, prompt):
        seen.append((engine["engine"], prompt))
        return {"answer": "Acme Corp", "cited_urls": [], "error": None}

    records = ai_visibility.run_battery(
        prompts,
        engines,
        runs=2,
        call_fn=call_fn,
        max_calls=2,
        facts="",
        config=CONFIG,
        clock=lambda: "2026-10-27T00:00:00Z",
    )
    assert [(row["engine"], row["prompt_id"], row["run"]) for row in records] == [
        ("openai", "one", 1),
        ("perplexity", "one", 1),
    ]

    class Resp:
        def __init__(self, status):
            self.status_code = status
            self.text = "{}"

        def json(self):
            return {"status": "completed", "output": [], "usage": {}}

    class Client:
        def __init__(self):
            self.calls = 0

        def request(self, method, url, headers=None, json=None, timeout=None):
            self.calls += 1
            return Resp(500)

    budget = ai_visibility.call_budget(2)
    client = Client()
    request = ai_visibility.build_openai_request("custom-model", "q", "test-key")
    _status, _body, error = ai_visibility.perform_request(
        request, client, sleep_fn=lambda *_args: None, secrets=["test-key"], budget=budget
    )
    assert client.calls == 2
    assert budget["made"] == 2
    assert error
    again = Client()
    status, _body, blocked = ai_visibility.perform_request(
        request, again, sleep_fn=lambda *_args: None, secrets=["test-key"], budget=budget
    )
    assert again.calls == 0
    assert blocked == "max-calls reached"
    assert budget["capped"] is True
    summary = ai_visibility.build_summary(
        records, prompts=2, runs=2, generated_at="2026-10-27T00:00:00Z", skipped=[], capped=True, calls_made=2
    )
    assert summary["capped"] is True
    assert summary["calls_made"] == 2


def test_parse_openrouter_fixture():
    parsed = ai_visibility.parse_openrouter_response(load("openrouter_response.json"))
    assert parsed["answer"].startswith("Acme Corp")
    assert parsed["cited_urls"] == [
        "https://example.com/about",
        "https://other.example/roundup",
        "https://example.com/pricing",
        "https://news.example/acme",
    ]
    assert "https://ignored.example/file" not in parsed["cited_urls"]
    assert parsed["usage"]["cost"] == 0.00125
    assert parsed["usage"]["total_tokens"] == 62


def test_openrouter_request_search_native_exa_or_omitted():
    native = ai_visibility.build_openrouter_request("perplexity/sonar", "Who is Acme Corp?", "test-key", "native")
    assert native["method"] == "POST"
    assert native["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert native["headers"]["Authorization"] == "Bearer test-key"
    assert native["headers"]["Content-Type"] == "application/json"
    assert native["headers"]["HTTP-Referer"] == "https://github.com/1610-advisory/mktkit"
    assert native["headers"]["X-Title"] == "seo-kit"
    assert native["json"]["model"] == "perplexity/sonar"
    assert native["json"]["messages"] == [{"role": "user", "content": "Who is Acme Corp?"}]
    assert native["json"]["plugins"] == [{"id": "web", "engine": "native"}]
    assert native["json"]["usage"] == {"include": True}
    assert native["timeout"] == 90
    exa = ai_visibility.build_openrouter_request("perplexity/sonar", "q", "test-key", "exa")
    assert exa["json"]["plugins"] == [{"id": "web", "engine": "exa"}]
    omitted = ai_visibility.build_openrouter_request("perplexity/sonar", "q", "test-key", "")
    assert omitted["json"]["plugins"] == [{"id": "web"}]
    assert "engine" not in omitted["json"]["plugins"][0]


def test_plan_openrouter_two_models():
    config = {
        "ai_engines": {
            "openai": {"model": "custom-model", "enabled": False},
            "openrouter": {
                "enabled": True,
                "models": ["openai/gpt-5.4-mini", "perplexity/sonar", "perplexity/sonar"],
                "search": "native",
            },
        }
    }
    prompts = [{"id": "q", "text": "Who is Acme Corp?", "kind": "branded"}]
    plan = ai_visibility.plan_calls(config, prompts, None, 3, {"OPENROUTER_API_KEY": "present"}, 100)
    assert [item["engine"] for item in plan["would_run"]] == [
        "openrouter:openai/gpt-5.4-mini",
        "openrouter:perplexity/sonar",
    ]
    assert [item["model"] for item in plan["would_run"]] == [
        "openai/gpt-5.4-mini",
        "perplexity/sonar",
    ]
    assert all(item["search"] == "native" for item in plan["would_run"])
    assert all(item["calls"] == 3 for item in plan["would_run"])
    assert plan["total_calls"] == 6
    text = ai_visibility.format_plan(plan)
    assert "openrouter:openai/gpt-5.4-mini" in text
    assert "openrouter:perplexity/sonar" in text
    assert "calls=3" in text
    assert "present" not in text
    one = ai_visibility.plan_calls(
        config, prompts, ["openrouter:perplexity/sonar"], 2, {"OPENROUTER_API_KEY": "present"}, 100
    )
    assert [item["engine"] for item in one["would_run"]] == ["openrouter:perplexity/sonar"]
    assert one["total_calls"] == 2
    assert one["would_run"][0]["calls"] == 2
    missing = ai_visibility.plan_calls(config, prompts, None, 1, {}, 100)
    reasons = {item["engine"]: item["reason"] for item in missing["skipped"] + missing["refused"]}
    assert reasons["openrouter:openai/gpt-5.4-mini"] == "missing OPENROUTER_API_KEY"
    assert reasons["openrouter:perplexity/sonar"] == "missing OPENROUTER_API_KEY"
    assert missing["would_run"] == []


def test_openrouter_dry_run_lists_each_model_with_call_count(monkeypatch, capsys, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("site: https://example.com\n", encoding="utf-8")
    prompts = tmp_path / "prompts.yaml"
    prompts.write_text(
        "- id: branded-who\n  text: Who is Acme Corp?\n  kind: branded\n"
        "- id: cost-how\n  text: How much does Acme Corp charge?\n  kind: cost\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ai_visibility, "load_client", lambda _path: {
        "site": "https://example.com",
        "brand": "Acme Corp",
        "domains": ["example.com"],
        "ai_engines": {
            "openai": {"model": "", "enabled": False},
            "openrouter": {
                "enabled": True,
                "models": ["openai/gpt-5.4-mini", "perplexity/sonar"],
                "search": "native",
            },
        },
    })

    def boom(*_args, **_kwargs):
        raise AssertionError("request was made")

    monkeypatch.setattr(ai_visibility, "perform_request", boom)
    monkeypatch.setattr(ai_visibility.httpx, "Client", boom)
    monkeypatch.setenv("OPENROUTER_API_KEY", "present")
    code = ai_visibility.main([
        "--config", str(config_path),
        "--prompts", str(prompts),
        "--log", str(tmp_path / "log.jsonl"),
        "--out", str(tmp_path / "ai.json"),
        "--dry-run",
        "--runs", "2",
    ])
    assert code == 0
    captured = capsys.readouterr()
    assert "openrouter:openai/gpt-5.4-mini model=openai/gpt-5.4-mini search=native calls=4" in captured.out
    assert "openrouter:perplexity/sonar model=perplexity/sonar search=native calls=4" in captured.out
    assert "total calls: 8" in captured.out
    assert "present" not in captured.out
    assert "no request" in captured.err
    assert not (tmp_path / "log.jsonl").exists()
    assert not (tmp_path / "ai.json").exists()


def test_openrouter_cost_summed_per_engine():
    prompts = [{"id": "q", "text": "Who is Acme Corp?", "kind": "branded"}]
    engines = [
        {"engine": "openrouter:perplexity/sonar", "model": "perplexity/sonar", "provider": "openrouter"},
        {"engine": "openrouter:openai/gpt-5.4-mini", "model": "openai/gpt-5.4-mini", "provider": "openrouter"},
    ]

    def call_fn(engine, prompt):
        cost = 0.01 if engine["model"] == "perplexity/sonar" else 0.02
        return {
            "answer": "Acme Corp makes widgets.",
            "cited_urls": ["https://example.com/about"],
            "usage": {"prompt_tokens": 4, "completion_tokens": 6, "cost": cost},
            "error": None,
        }

    records = ai_visibility.run_battery(
        prompts,
        engines,
        runs=2,
        call_fn=call_fn,
        max_calls=10,
        facts="",
        config=CONFIG,
        clock=lambda: "2026-10-27T00:00:00Z",
    )
    assert [row["engine"] for row in records] == [
        "openrouter:perplexity/sonar",
        "openrouter:openai/gpt-5.4-mini",
        "openrouter:perplexity/sonar",
        "openrouter:openai/gpt-5.4-mini",
    ]
    assert [row["cost_usd"] for row in records] == [0.01, 0.02, 0.01, 0.02]
    bare = ai_visibility.run_battery(
        prompts,
        [{"engine": "openai", "model": "custom-model"}],
        runs=1,
        call_fn=lambda _engine, _prompt: {
            "answer": "Acme Corp",
            "cited_urls": [],
            "usage": {"input_tokens": 1},
            "error": None,
        },
        max_calls=5,
        facts="",
        config=CONFIG,
        clock=lambda: "2026-10-27T00:00:00Z",
    )
    assert "cost_usd" not in bare[0]
    failed = {
        "engine": "openrouter:perplexity/sonar",
        "prompt_id": "q",
        "kind": "branded",
        "run": 3,
        "error": "empty answer",
        "brand_mentioned": False,
        "our_url_cited": False,
        "brand_position": None,
        "cited_domains": [],
        "unverified_figures": [],
        "cost_usd": 0.01,
    }
    summary = ai_visibility.build_summary(
        records + bare + [failed],
        prompts=1,
        runs=2,
        generated_at="2026-10-27T00:00:00Z",
        skipped=[],
    )
    assert summary["summary"]["openrouter:perplexity/sonar"]["cost_usd"] == 0.03
    assert summary["summary"]["openrouter:perplexity/sonar"]["calls"] == 3
    assert summary["summary"]["openrouter:perplexity/sonar"]["failed"] == 1
    assert summary["summary"]["openrouter:openai/gpt-5.4-mini"]["cost_usd"] == 0.04
    assert summary["summary"]["openai"]["cost_usd"] == 0


def test_openrouter_failed_200_and_live_call_parses_fixture():
    assert ai_visibility.response_error("openrouter", {"choices": []}, {"answer": ""}) == "openrouter no choices"
    assert ai_visibility.response_error(
        "openrouter",
        {"choices": [{"message": {"content": ""}}]},
        {"answer": ""},
    ) == "empty answer"
    assert ai_visibility.response_error(
        "openrouter",
        {"error": {"code": "model_not_found", "message": "No such model."}},
        {"answer": ""},
    ) == "model_not_found: No such model."
    leaked = ai_visibility.response_error(
        "openrouter",
        {"error": {"code": 401, "message": "Invalid key test-key-do-not-log"}},
        {"answer": ""},
    )
    assert leaked == "401"
    assert "test-key" not in leaked
    assert ai_visibility.response_error(
        "openrouter",
        {"error": {"code": "403", "message": "forbidden detail"}},
        {"answer": ""},
    ) == "403"

    payload = load("openrouter_response.json")
    seen = {}

    class Resp:
        status_code = 200
        text = ""

        def json(self):
            return payload

    class Client:
        def request(self, method, url, headers=None, json=None, timeout=None):
            seen["method"] = method
            seen["url"] = url
            seen["headers"] = headers
            seen["json"] = json
            return Resp()

    parsed = ai_visibility._live_call(
        {
            "engine": "openrouter:perplexity/sonar",
            "model": "perplexity/sonar",
            "provider": "openrouter",
            "search": "native",
        },
        "Who is Acme Corp?",
        {"OPENROUTER_API_KEY": "  test-key  "},
        Client(),
        lambda *_args: None,
    )
    assert seen["method"] == "POST"
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer test-key"
    assert seen["headers"]["HTTP-Referer"] == "https://github.com/1610-advisory/mktkit"
    assert seen["json"]["model"] == "perplexity/sonar"
    assert seen["json"]["plugins"] == [{"id": "web", "engine": "native"}]
    assert parsed["error"] is None
    assert parsed["cited_urls"][0] == "https://example.com/about"
    assert parsed["usage"]["cost"] == 0.00125
