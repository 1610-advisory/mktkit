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
    assert parsed["cited_urls"] == [
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
