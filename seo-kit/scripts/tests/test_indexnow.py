import json

import indexnow


def test_key_and_host_and_payload():
    assert indexnow.key_from_key_file_url("https://example.com/abc123.txt") == "abc123"
    assert indexnow.key_from_key_file_url("https://www.example.com/path/my-key.txt") == "my-key"
    assert indexnow.url_on_site("https://www.example.com/widgets", "https://example.com")
    assert indexnow.url_on_site("https://example.com/widgets", "https://www.example.com")
    assert not indexnow.url_on_site("https://blog.example.com/widgets", "https://example.com")
    assert not indexnow.url_on_site("https://other.example/widgets", "https://example.com")
    payload = indexnow.build_payload(
        "https://example.com",
        "abc123",
        "https://example.com/abc123.txt",
        ["https://example.com/widgets"],
    )
    assert payload == {
        "host": "example.com",
        "key": "abc123",
        "keyLocation": "https://example.com/abc123.txt",
        "urlList": ["https://example.com/widgets"],
    }


def test_validate_off_site_and_cap():
    errors = indexnow.validate_submission(
        "https://example.com",
        "https://example.com/abc123.txt",
        ["https://other.example/nope", "https://example.com/ok"],
    )
    assert any("not on the config site host" in error for error in errors)
    too_many = indexnow.validate_submission(
        "https://example.com",
        "https://example.com/abc123.txt",
        [f"https://example.com/{i}" for i in range(10001)],
    )
    assert any("10000" in error for error in too_many)
    assert indexnow.validate_submission(
        "https://example.com",
        "https://example.com/abc123.txt",
        ["https://example.com/ok"],
    ) == []
    assert indexnow.key_matches("abc123\n", "abc123")
    assert not indexnow.key_matches("other", "abc123")


def test_status_messages():
    ok, message = indexnow.interpret_status(200)
    assert ok and "submitted successfully" in message
    ok, message = indexnow.interpret_status(202)
    assert ok and "pending" in message
    for status in (400, 403, 422, 429):
        ok, message = indexnow.interpret_status(status)
        assert not ok
        assert message
    ok, message = indexnow.interpret_status(500)
    assert not ok and "500" in message


def test_dry_run_prints_payload_and_does_not_send(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(indexnow, "load_client", lambda _path: {"site": "https://example.com"})

    def boom(*_args, **_kwargs):
        raise AssertionError("network was called")

    monkeypatch.setattr(indexnow, "fetch_text", boom)
    monkeypatch.setattr(indexnow, "post_payload", boom)
    code = indexnow.main([
        "--config", "cfg.yaml",
        "--key-file-url", "https://example.com/abc123.txt",
        "--urls", "https://example.com/widgets", "https://www.example.com/about",
    ])
    assert code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["host"] == "example.com"
    assert payload["key"] == "abc123"
    assert payload["urlList"] == [
        "https://example.com/widgets",
        "https://www.example.com/about",
    ]
    assert "not sent" in captured.err
    assert "api.indexnow.org" not in captured.out


def test_off_site_exits_1_without_send(monkeypatch, capsys):
    monkeypatch.setattr(indexnow, "load_client", lambda _path: {"site": "https://example.com"})
    monkeypatch.setattr(indexnow, "post_payload", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("sent")))
    code = indexnow.main([
        "--config", "cfg.yaml",
        "--key-file-url", "https://example.com/abc123.txt",
        "--urls", "https://other.example/nope",
    ])
    assert code == 1
    assert "not on the config site host" in capsys.readouterr().err


def test_send_checks_key_before_post(monkeypatch, capsys):
    monkeypatch.setattr(indexnow, "load_client", lambda _path: {"site": "https://example.com"})
    monkeypatch.setattr(indexnow, "fetch_text", lambda _url: (200, "wrong-key\n"))
    posts = []
    monkeypatch.setattr(indexnow, "post_payload", lambda payload: posts.append(payload) or (200, "ok"))
    code = indexnow.main([
        "--config", "cfg.yaml",
        "--key-file-url", "https://example.com/abc123.txt",
        "--urls", "https://example.com/widgets",
        "--send",
    ])
    assert code == 1
    assert posts == []
    assert "does not equal the key" in capsys.readouterr().err


def test_urls_file_skips_comments(tmp_path):
    path = tmp_path / "urls.txt"
    path.write_text("# note\nhttps://example.com/a\n\nhttps://example.com/b\n", encoding="utf-8")
    assert indexnow.load_urls(["https://example.com/c"], str(path)) == [
        "https://example.com/c",
        "https://example.com/a",
        "https://example.com/b",
    ]
