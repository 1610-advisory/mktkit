# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.27",
#     "pyyaml>=6",
# ]
# ///
"""
IndexNow submitter. Dry-run unless --send is passed.

Usage:
    uv run indexnow.py --config tracking/seo/config.yaml \\
        --key-file-url https://example.com/<key>.txt \\
        --urls https://example.com/page https://example.com/other
    uv run indexnow.py --config tracking/seo/config.yaml \\
        --key-file-url https://example.com/<key>.txt \\
        --urls-file changed.txt --send

Default is a dry run: print the JSON payload and do not fetch the key file
or POST. --send fetches the key file, checks the body equals the key
(the key is the file name stem), then POSTs to
https://api.indexnow.org/indexnow.

Every URL hostname must equal the payload host exactly. www is a different
host and is rejected, including on a dry run. At most 10000 URLs. No API key
environment variable; the key is the file stem. The key-file fetch does not
follow a redirect onto another host.

Exit 0 on a dry run or a 200/202 submit. Exit 1 on usage or a key mismatch.
Exit 2 on a network failure or a 400/403/422/429 from IndexNow.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
MAX_URLS = 10000
STATUS_MESSAGES = {
    200: "OK: URL submitted successfully",
    202: "Accepted: URL received, key validation pending",
    400: "Bad request: invalid format",
    403: "Forbidden: key not valid (not found, or file does not contain the key)",
    422: "Unprocessable: URLs do not belong to the host, or the key does not match the protocol",
    429: "Too many requests",
}


def load_client(path: str) -> dict:
    try:
        from seo_config import load_config
    except ImportError:
        print(
            "Error: seo-kit/scripts/seo_config.py is missing (it is provided separately).",
            file=sys.stderr,
        )
        raise SystemExit(1)
    try:
        return load_config(path)
    except Exception as exc:
        print(f"Error: could not load config: {exc}", file=sys.stderr)
        raise SystemExit(1)


def write_json(path: str, payload: dict) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def configured_host(site: str) -> str:
    host = urlparse(site).hostname or ""
    return host.lower().rstrip(".")


def url_on_site(url: str, site: str) -> bool:
    """True when the URL hostname equals the payload host. www is not folded."""
    site_ref = site if "://" in site else f"https://{site}"
    site_host = configured_host(site_ref)
    return bool(site_host) and configured_host(url) == site_host


def key_from_key_file_url(url: str) -> str:
    name = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    if name.lower().endswith(".txt"):
        return name[:-4]
    return Path(name).stem


def load_urls(arg_urls: list[str] | None, urls_file: str | None) -> list[str]:
    items = list(arg_urls or [])
    if urls_file:
        for line in Path(urls_file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                items.append(line)
    return items


def validate_submission(site: str, key_file_url: str, urls: list[str]) -> list[str]:
    errors = []
    if not configured_host(site):
        errors.append("config site has no host")
    if not urls:
        errors.append("no URLs to submit")
    if len(urls) > MAX_URLS:
        errors.append(f"{len(urls)} URLs exceeds the {MAX_URLS} URL limit")
    key = key_from_key_file_url(key_file_url)
    if not key:
        errors.append("key file URL has no file name stem")
    if key_file_url and not url_on_site(key_file_url, site):
        errors.append("key file URL is not on the config site host")
    bad = [url for url in urls if not url_on_site(url, site)]
    if bad:
        shown = ", ".join(bad[:3])
        errors.append(f"{len(bad)} URLs are not on the config site host: {shown}")
    return errors


def build_payload(site: str, key: str, key_file_url: str, urls: list[str]) -> dict:
    return {
        "host": configured_host(site),
        "key": key,
        "keyLocation": key_file_url,
        "urlList": urls,
    }


def key_matches(body: str, key: str) -> bool:
    return body.strip() == key


def interpret_status(status: int) -> tuple[bool, str]:
    message = STATUS_MESSAGES.get(status, f"unexpected status {status}")
    return status in (200, 202), message


def fetch_key_body(url: str, get, hops: int = 5) -> tuple[int, str]:
    """Fetch a key file. get(url) -> (status, headers, text).

    Same-host redirects are followed. A redirect to another host is an error
    and is not followed.
    """
    current = url
    origin = configured_host(url)
    for _ in range(hops):
        status, headers, text = get(current)
        if status in (301, 302, 303, 307, 308):
            location = ""
            if headers is not None:
                location = headers.get("location") or headers.get("Location") or ""
            if not location:
                return status, text
            nxt = urljoin(current, location)
            if configured_host(nxt) != origin:
                raise RuntimeError("key file redirect left the host")
            current = nxt
            continue
        return status, text
    raise RuntimeError("too many key file redirects")


def fetch_text(url: str, timeout: float = 30) -> tuple[int, str]:
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:

        def get(current: str):
            resp = client.get(current)
            return resp.status_code, resp.headers, resp.text

        return fetch_key_body(url, get)


def post_payload(payload: dict, timeout: float = 60) -> tuple[int, str]:
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        resp = client.post(
            INDEXNOW_ENDPOINT,
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
    return resp.status_code, resp.text


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Submit URLs to IndexNow (dry-run unless --send)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    def _error(message: str) -> None:
        print(f"Error: {message}", file=sys.stderr)
        raise SystemExit(1)

    parser.error = _error  # type: ignore[method-assign]
    parser.add_argument("--config", required=True, help="Path to tracking/seo/config.yaml")
    parser.add_argument("--key-file-url", required=True, help="Public URL of the key file")
    parser.add_argument("--urls", nargs="*", default=[], help="URLs to submit")
    parser.add_argument("--urls-file", help="Text file of URLs, one per line")
    parser.add_argument("--send", action="store_true", help="POST to IndexNow (default is dry-run)")
    parser.add_argument("--out", help="Optional JSON path for the payload or result")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = load_client(args.config)
    site = (config.get("site") or "").strip()
    try:
        urls = load_urls(args.urls, args.urls_file)
    except OSError as exc:
        print(f"Error: could not read URLs file: {exc.strerror or 'read failed'}", file=sys.stderr)
        return 1
    errors = validate_submission(site, args.key_file_url, urls)
    if errors:
        for error in errors:
            print(f"Error: {error}", file=sys.stderr)
        return 1
    key = key_from_key_file_url(args.key_file_url)
    payload = build_payload(site, key, args.key_file_url, urls)
    if not args.send:
        text = json.dumps(payload, indent=2)
        print(text)
        if args.out:
            write_json(args.out, payload)
        print(
            f"indexnow dry-run: {len(urls)} urls for {payload['host']}, not sent",
            file=sys.stderr,
        )
        return 0

    try:
        status, body = fetch_text(args.key_file_url)
    except Exception as exc:
        print(f"Error: could not fetch key file: {type(exc).__name__}", file=sys.stderr)
        return 2
    if status != 200:
        print(f"Error: key file returned HTTP {status}", file=sys.stderr)
        return 1
    if not key_matches(body, key):
        print("Error: key file body does not equal the key (file name stem).", file=sys.stderr)
        return 1
    try:
        status, body = post_payload(payload)
    except Exception as exc:
        print(f"Error: IndexNow request failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    ok, message = interpret_status(status)
    result = {"ok": ok, "status": status, "message": message, "submitted": len(urls)}
    if args.out:
        write_json(args.out, result)
    print(f"indexnow: {message} ({len(urls)} urls)", file=sys.stderr)
    if not ok:
        preview = (body or "").strip().replace("\n", " ")[:180]
        if preview:
            print(f"Error: response: {preview}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
