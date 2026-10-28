import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import site_crawl as sc

SITE = "https://example.com"

SITEMAP_URLSET = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/</loc></url>
  <url><loc>https://example.com/about/</loc></url>
</urlset>
"""

SITEMAP_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-pages.xml</loc></sitemap>
</sitemapindex>
"""

HTML = """<!doctype html>
<html><head>
<title>Hello &amp; Co</title>
<meta name="description" content="A short description that is definitely long enough to pass the seventy character minimum for the check.">
<meta name="robots" content="index,follow">
<meta property="og:title" content="OG Hello">
<meta property="og:image" content="https://example.com/og.png">
<link rel="canonical" href="/hello">
</head>
<body>
<h1>Hello <em>there</em></h1>
<h2>One</h2>
<h2>Two</h2>
<p>Visible words here.</p>
<script type="application/ld+json">{"@type":"Organization","@id":"https://example.com/#org"}</script>
<script type="application/ld+json">{not json}</script>
<script>var hidden = "not visible";</script>
<a href="/about">About</a>
<a href="https://other.example/x">Out</a>
<a href="mailto:a@example.com">Mail</a>
<img src="a.png">
<img src="b.png" alt="ok">
<img src="c.png" alt="">
</body></html>
"""


def test_user_agent():
    assert sc.USER_AGENT == "seo-kit-crawler/0.1 (+https://github.com/1610-advisory/mktkit)"


def test_same_site_treats_www_as_same_host():
    assert sc.same_site("https://www.example.com/about", SITE)
    assert sc.same_site("http://example.com/about", SITE)
    assert not sc.same_site("https://other.example/about", SITE)


def test_normalize_ignores_www_and_trailing_slash():
    assert sc.normalize_url("https://www.example.com/about/") == "https://example.com/about"
    assert sc.normalize_url("https://example.com") == "https://example.com/"
    assert sc.slash_key("https://www.example.com/about/") == "https://www.example.com/about"
    assert sc.slash_key("https://example.com/about/") == "https://example.com/about"


def test_parse_sitemap_urlset_and_index():
    kind, locs = sc.parse_sitemap(SITEMAP_URLSET)
    assert kind == "urlset"
    assert locs == ["https://example.com/", "https://example.com/about/"]
    kind, locs = sc.parse_sitemap(SITEMAP_INDEX)
    assert kind == "index"
    assert locs == ["https://example.com/sitemap-pages.xml"]


def test_parse_robots_specific_group_beats_wildcard():
    text = """
User-agent: *
Disallow: /

User-agent: Googlebot
Allow: /

User-agent: GPTBot
Disallow: /

Sitemap: https://example.com/sitemap.xml
"""
    parsed = sc.parse_robots(text)
    assert parsed["lists_sitemap"] is True
    assert parsed["blocks"]["GPTBot"] is True
    assert parsed["blocks"]["Googlebot"] is False
    assert parsed["blocks"]["Bingbot"] is True  # falls back to * which disallows /
    assert parsed["blocks"]["ClaudeBot"] is True


def test_parse_robots_partial_disallow_does_not_block_root():
    text = """
User-agent: *
Allow: /
Disallow: /cdn-cgi/

User-agent: GPTBot
Allow: /
"""
    parsed = sc.parse_robots(text)
    assert parsed["lists_sitemap"] is False
    assert all(flag is False for flag in parsed["blocks"].values())


def test_parse_html_fields():
    parsed = sc.parse_html(HTML, "https://example.com/hello", SITE)
    assert parsed["title"] == "Hello & Co"
    assert parsed["meta_description"].startswith("A short description")
    assert parsed["meta_robots"] == "index,follow"
    assert parsed["canonical"] == "https://example.com/hello"
    assert parsed["og_title"] == "OG Hello"
    assert parsed["og_image"] == "https://example.com/og.png"
    assert parsed["h1"] == ["Hello there"]
    assert parsed["h2_count"] == 2
    assert parsed["json_ld"] == [{"type": "Organization", "id": "https://example.com/#org", "org_props": []}]
    assert parsed["json_ld_errors"]
    assert parsed["internal_links"] == ["https://example.com/about"]
    assert parsed["external_link_count"] == 1
    assert parsed["images_missing_alt"] == 1
    assert parsed["word_count"] == 10
    assert "hidden" not in " ".join(str(parsed["h1"]))


def test_jsonld_graph():
    blob = """
    {"@context":"https://schema.org","@graph":[
      {"@type":"WebPage","@id":"https://example.com/#page"},
      {"@type":["Organization","Brand"],"@id":"https://example.com/#org"}
    ]}
    """
    nodes, errors = sc.parse_jsonld_nodes(blob)
    assert errors == []
    assert nodes[0]["type"] == "WebPage"
    assert nodes[1]["type"] == "Organization, Brand"


def _page(url, **overrides):
    record = {
        "url": url,
        "status": 200,
        "redirect_location": None,
        "redirect_chain": [url],
        "final_url": url,
        "content_type": "text/html; charset=utf-8",
        "x_robots_tag": None,
        "cache_control": None,
        "in_sitemap": True,
        "error": None,
        "title": "Unique " + url,
        "meta_description": "A unique description for this page that is long enough to clear seventy characters easily.",
        "meta_robots": "index,follow",
        "canonical": url,
        "h1": ["Heading"],
        "h2_count": 1,
        "json_ld": [],
        "json_ld_errors": [],
        "internal_links": [],
        "external_link_count": 0,
        "images_missing_alt": 0,
        "word_count": 80,
    }
    record.update(overrides)
    return record


def test_compute_issues_covers_codes():
    home = "https://example.com/"
    about = "https://example.com/about"
    missing = "https://example.com/missing"
    noindex = "https://example.com/noindex"
    dup = "https://example.com/dup"
    dup2 = "https://example.com/dup2"
    orphan = "https://example.com/orphan"
    extra = "https://example.com/extra"
    old = "https://example.com/old"
    mid = "https://example.com/mid"
    new = "https://example.com/new"
    bad = "https://example.com/badjson"
    canon = "https://example.com/canon"
    slash = "https://example.com/slash"
    secret = "https://example.com/secret"
    notitle = "https://example.com/notitle"
    shared_title = "Shared title for two pages here"
    shared_desc = "Shared description that is long enough to pass the seventy character minimum for both pages."

    pages = {
        home: _page(
            home,
            title="Home page title",
            meta_description="x" * 40,
            images_missing_alt=2,
            internal_links=[about, missing, noindex, dup, extra, new, bad, canon, slash, secret, notitle],
        ),
        about: _page(
            about,
            title="T" * 70,
            meta_description=None,
            canonical=None,
            h1=[],
            internal_links=[home],
        ),
        missing: _page(missing, status=404, content_type="text/html", title=None, in_sitemap=True),
        noindex: _page(noindex, meta_robots="noindex, nofollow", in_sitemap=False),
        dup: _page(dup, title=shared_title, meta_description=shared_desc, internal_links=[dup2]),
        dup2: _page(dup2, title=shared_title, meta_description=shared_desc, internal_links=[dup, home]),
        orphan: _page(orphan),
        extra: _page(extra, in_sitemap=False, internal_links=[home]),
        old: _page(old, status=301, content_type=None, redirect_location=mid, title=None, h1=None),
        mid: _page(mid, status=302, content_type=None, redirect_location=new, title=None, h1=None, in_sitemap=False),
        new: _page(new, internal_links=[home]),
        bad: _page(bad, json_ld_errors=["JSON-LD parse error: Expecting value"]),
        canon: _page(canon, canonical="https://example.com/other"),
        slash: _page(slash, canonical="https://example.com/slash/"),
        secret: _page(secret, meta_robots="noindex"),
        notitle: _page(notitle, title=None),
    }
    # Drop HTML-only keys that _page added on non-HTML responses so is_html_200 stays false.
    for url in (missing, old, mid):
        for key in ("title", "meta_description", "meta_robots", "canonical", "h1", "json_ld", "json_ld_errors", "internal_links", "word_count"):
            pages[url].pop(key, None)

    sitemap = [home, about, missing, orphan, old, new, bad, canon, slash, secret, notitle, dup, dup2]
    robots = {"url": "https://example.com/robots.txt", "status": 200, "blocks": {"GPTBot": True, "Googlebot": False}}
    llms = {"url": "https://example.com/llms.txt", "status": 404, "present": False}
    issues = sc.compute_issues(pages, sitemap, robots, llms, SITE)
    pairs = {(item["code"], item["url"]) for item in issues}

    expected = {
        ("description_length", home),
        ("img_missing_alt", home),
        ("title_too_long", about),
        ("missing_description", about),
        ("canonical_missing", about),
        ("h1_count", about),
        ("thin_inbound", about),
        ("broken_internal_link", missing),
        ("sitemap_non_200", missing),
        ("noindex_linked", noindex),
        ("duplicate_title", dup),
        ("duplicate_title", dup2),
        ("duplicate_description", dup),
        ("duplicate_description", dup2),
        ("orphan", orphan),
        ("not_in_sitemap", extra),
        ("thin_inbound", extra),
        ("sitemap_redirect", old),
        ("redirect_chain", old),
        ("jsonld_parse_error", bad),
        ("canonical_mismatch", canon),
        ("missing_title", notitle),
        ("sitemap_noindex", secret),
        ("noindex_linked", secret),
        ("robots_blocks_ai_bot", "https://example.com/robots.txt#GPTBot"),
        ("llms_txt_missing", "https://example.com/llms.txt"),
    }
    missing_pairs = expected - pairs
    assert not missing_pairs, missing_pairs
    assert ("canonical_mismatch", slash) not in pairs
    assert ("title_too_long", notitle) not in pairs
    by_code = {item["code"]: item for item in issues}
    assert by_code["broken_internal_link"]["severity"] == "high"
    assert by_code["llms_txt_missing"]["severity"] == "low"
    assert by_code["noindex_linked"]["severity"] == "low"
    assert by_code["thin_inbound"]["severity"] == "low"
    chain = pages[old]["redirect_chain"]
    assert chain[0] == old
    assert new in chain


def _raw(status=200, body=b"", content_type="text/html", location=None, error=None):
    headers = {"content-type": [content_type]} if content_type else {}
    if location:
        headers["location"] = [location]
    return {"status": status, "headers": headers, "body": body, "location": location, "error": error, "truncated": False}


def test_crawl_follows_internal_redirects_and_skips_links(tmp_path):
    html_home = b"""<html><head><title>Home</title><link rel="canonical" href="https://example.com/"></head>
<body><h1>Home</h1><a href="/new">New</a><a href="/cdn-cgi/l/email-protection">Mail</a></body></html>"""
    html_new = b"""<html><head><title>New</title></head><body><h1>New</h1><a href="/about">About</a></body></html>"""
    html_about = b"""<html><head></head><body><p>No title here and enough words to count.</p></body></html>"""
    sitemap = b"""<?xml version="1.0"?><urlset><url><loc>https://example.com/</loc></url><url><loc>https://example.com/old</loc></url></urlset>"""
    fetched = []

    def fake(url):
        fetched.append(url)
        path = urlparse(url).path
        if path == "/robots.txt":
            return _raw(200, b"User-agent: *\nAllow: /\nSitemap: https://example.com/sitemap.xml\n", "text/plain")
        if path == "/llms.txt":
            return _raw(404, b"", "text/plain")
        if path == "/sitemap.xml":
            return _raw(200, sitemap, "application/xml")
        if path == "/":
            return _raw(200, html_home)
        if path == "/old":
            return _raw(301, b"", "text/html", location="https://example.com/new")
        if path == "/new":
            return _raw(200, html_new)
        if path == "/about":
            return _raw(200, html_about)
        return _raw(404, b"missing", "text/html")

    config = {
        "site": SITE,
        "sitemap": "https://example.com/sitemap.xml",
        "skip_links": ["/cdn-cgi/"],
        "max_pages": 20,
    }
    report = sc.crawl(config, fetch=fake, delay=0, sleep=lambda _s: None)
    paths = {urlparse(url).path for url in fetched}
    assert "/cdn-cgi/l/email-protection" not in paths
    assert "/about" in paths
    assert report["pages"]["https://example.com/old"]["status"] == 301
    assert "https://example.com/new" in report["pages"]["https://example.com/old"]["redirect_chain"]
    codes = {item["code"] for item in report["issues"]}
    assert "sitemap_redirect" in codes
    assert "missing_title" in codes
    assert "llms_txt_missing" in codes
    assert report["robots"]["lists_sitemap"] is True
    assert report["counts"]["html_pages"] >= 2


def test_crawl_max_pages():
    locs = "".join(f"<url><loc>https://example.com/p{i}</loc></url>" for i in range(5))
    sitemap = f"<?xml version='1.0'?><urlset>{locs}</urlset>".encode()

    def fake(url):
        path = urlparse(url).path
        if path == "/robots.txt":
            return _raw(200, b"User-agent: *\nAllow: /\n", "text/plain")
        if path == "/llms.txt":
            return _raw(200, b"hello", "text/plain")
        if path == "/sitemap.xml":
            return _raw(200, sitemap, "application/xml")
        body = f"<html><head><title>{path}</title></head><body><h1>x</h1></body></html>".encode()
        return _raw(200, body)

    config = {"site": SITE, "sitemap": "https://example.com/sitemap.xml", "max_pages": 2}
    report = sc.crawl(config, fetch=fake, delay=0)
    assert report["counts"]["pages"] == 2


def test_main_config_error(tmp_path, capsys):
    code = sc.main(["--config", str(tmp_path / "missing.yaml"), "--out", str(tmp_path / "out.json")])
    assert code == 1
    assert "Error:" in capsys.readouterr().err


QUIET_ROBOTS = {"url": "https://example.com/robots.txt", "status": 200, "blocks": {}}
QUIET_LLMS = {"url": "https://example.com/llms.txt", "status": 200, "present": True}


def _codes(issues, code):
    return [item for item in issues if item["code"] == code]


def test_link_header_recorded_raw():
    raw = _raw(200, b"# title", "text/markdown")
    raw["headers"]["link"] = [
        '<https://example.com/llms.txt>; rel="describedby"',
        '<https://example.com/post>; rel="canonical"',
    ]
    record = sc.record_from_fetch("https://example.com/post.md", raw, SITE, True)
    assert record["link_header"] == (
        '<https://example.com/llms.txt>; rel="describedby", '
        '<https://example.com/post>; rel="canonical"'
    )
    missing = sc.record_from_fetch("https://example.com/gone", _raw(404, b"", "text/plain"), SITE, False)
    assert missing["link_header"] is None


def test_has_canonical_link_is_a_rel_token():
    assert sc.has_canonical_link('<https://example.com/post>; rel="canonical"')
    assert sc.has_canonical_link('<https://example.com/post>; rel=canonical')
    assert sc.has_canonical_link(
        '<https://example.com/md>; rel="alternate", <https://example.com/post>; rel="canonical"'
    )
    # Same shape as a site that advertises llms.txt and the sitemap, not a canonical.
    described = (
        '<https://example.com/llms.txt>; rel="describedby"; type="text/plain", '
        '<https://example.com/sitemap.xml>; rel="sitemap"; type="application/xml"'
    )
    assert not sc.has_canonical_link(described)
    assert not sc.has_canonical_link('<https://example.com/?rel=canonical>; rel="alternate"')
    assert not sc.has_canonical_link(None)


def test_sitemap_non_html_requires_canonical_link_header():
    md = "https://example.com/post.md"
    js = "https://example.com/post.json"
    html = "https://example.com/post"
    pages = {
        md: {
            "url": md,
            "status": 200,
            "content_type": "text/markdown; charset=utf-8",
            "link_header": '<https://example.com/llms.txt>; rel="describedby"',
            "redirect_chain": [md],
            "final_url": md,
        },
        js: {
            "url": js,
            "status": 200,
            "content_type": "application/json",
            "link_header": '<https://example.com/post>; rel="canonical"',
            "redirect_chain": [js],
            "final_url": js,
        },
        html: _page(html),
    }
    issues = sc.compute_issues(pages, [md, js, html], QUIET_ROBOTS, QUIET_LLMS, SITE)
    hits = _codes(issues, "sitemap_non_html")
    assert len(hits) == 1
    assert hits[0]["url"] == md
    assert hits[0]["severity"] == "medium"
    assert hits[0]["detail"] == "text/markdown; charset=utf-8"


def test_parse_sitemap_entries_keeps_lastmod():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/a</loc><lastmod>2026-01-01</lastmod></url>
      <url><loc>https://example.com/b</loc></url>
    </urlset>
    """
    kind, entries = sc.parse_sitemap_entries(xml)
    assert kind == "urlset"
    assert entries == [
        {"loc": "https://example.com/a", "lastmod": "2026-01-01"},
        {"loc": "https://example.com/b", "lastmod": None},
    ]
    kind, locs = sc.parse_sitemap(xml)
    assert kind == "urlset"
    assert locs == ["https://example.com/a", "https://example.com/b"]


def test_collect_sitemap_ignores_index_lastmod():
    index = b"""<?xml version='1.0'?><sitemapindex>
      <sitemap><loc>https://example.com/child.xml</loc><lastmod>2020-01-01</lastmod></sitemap>
    </sitemapindex>"""
    child = b"""<?xml version='1.0'?><urlset>
      <url><loc>https://example.com/a</loc><lastmod>2024-05-01</lastmod></url>
      <url><loc>https://example.com/b</loc><lastmod>2024-06-01</lastmod></url>
    </urlset>"""

    def fetch(url):
        if url.endswith("child.xml"):
            return _raw(200, child, "application/xml")
        return _raw(200, index, "application/xml")

    entries, err = sc.collect_sitemap("https://example.com/sitemap.xml", fetch, SITE)
    assert err is None
    assert entries == [
        {"loc": "https://example.com/a", "lastmod": "2024-05-01"},
        {"loc": "https://example.com/b", "lastmod": "2024-06-01"},
    ]


def test_sitemap_lastmod_uniform_when_most_values_match():
    urls = [f"https://example.com/p{i}" for i in range(6)]
    same = ["2026-01-01T00:00:00Z"] * 6
    issues = sc.compute_issues({}, urls, QUIET_ROBOTS, QUIET_LLMS, SITE, same)
    hits = _codes(issues, "sitemap_lastmod_uniform")
    assert len(hits) == 1
    assert hits[0]["url"] == SITE
    assert hits[0]["severity"] == "low"
    assert hits[0]["detail"] == "6 of 6 URLs share lastmod 2026-01-01T00:00:00Z"

    half = same[:3] + ["2026-02-01T00:00:00Z", "2026-02-02T00:00:00Z", "2026-02-03T00:00:00Z"]
    assert _codes(sc.compute_issues({}, urls, QUIET_ROBOTS, QUIET_LLMS, SITE, half), "sitemap_lastmod_uniform") == []
    assert _codes(sc.compute_issues({}, urls[:5], QUIET_ROBOTS, QUIET_LLMS, SITE, same[:5]), "sitemap_lastmod_uniform") == []
    missing = [None] * 6
    assert _codes(sc.compute_issues({}, urls, QUIET_ROBOTS, QUIET_LLMS, SITE, missing), "sitemap_lastmod_uniform") == []


def test_jsonld_org_props_walks_nested_and_type_list():
    blob = """
    {"@context":"https://schema.org","@graph":[
      {"@type":"WebPage","@id":"https://example.com/#page",
       "publisher":{"@type":"Organization","name":"Acme","url":"https://example.com/",
                    "logo":"https://example.com/logo.png","sameAs":["https://example.com/social"],
                    "founder":{"@type":"Person","name":"Ada"}}},
      {"@type":["ProfessionalService","LocalBusiness"],"@id":"https://example.com/#office","url":"https://example.com/office"},
      {"@type":"https://schema.org/AccountingService","name":"Acme Books"},
      {"@type":"Corporation","name":"Partner","url":"https://partner.example/"}
    ]}
    """
    nodes, errors = sc.parse_jsonld_nodes(blob)
    assert errors == []
    orgs = [node for node in nodes if "org_props" in node]
    assert [node["type"] for node in orgs] == [
        "Organization",
        "ProfessionalService, LocalBusiness",
        "https://schema.org/AccountingService",
        "Corporation",
    ]
    assert orgs[0]["id"] is None
    assert orgs[0]["org_props"] == ["url", "logo", "sameAs", "founder", "name"]
    assert orgs[0]["url"] == "https://example.com/"
    assert orgs[1]["org_props"] == ["url"]
    assert orgs[2]["org_props"] == ["name"]
    assert "org_props" not in nodes[0]  # WebPage
    assert any(node["type"] == "Person" for node in nodes)


def test_jsonld_entity_no_id_is_per_page_and_skips_foreign_orgs():
    home = "https://example.com/"
    about = "https://example.com/about"
    pages = {
        home: _page(home, in_sitemap=False, json_ld=[
            {"type": "Organization", "id": None, "org_props": ["name", "url"], "url": "https://example.com/"},
            {"type": "LocalBusiness", "id": None, "org_props": ["name"]},
            {"type": "Corporation", "id": None, "org_props": ["name", "url"], "url": "https://client.example/"},
        ]),
        about: _page(about, in_sitemap=False, json_ld=[
            {"type": "Organization", "id": "https://example.com/#org", "org_props": ["url", "logo", "sameAs"], "url": "https://example.com/"},
        ]),
    }
    issues = sc.compute_issues(pages, [], QUIET_ROBOTS, QUIET_LLMS, SITE)
    hits = _codes(issues, "jsonld_entity_no_id")
    assert len(hits) == 1
    assert hits[0]["url"] == home
    assert hits[0]["severity"] == "medium"
    assert hits[0]["detail"] == "No @id on Organization, LocalBusiness"


def test_jsonld_entity_ids_differ_is_one_site_issue():
    home = "https://example.com/"
    about = "https://example.com/about"
    www = "https://www.example.com/contact"
    pages = {
        home: _page(home, in_sitemap=False, json_ld=[{
            "type": "Organization", "id": "https://example.com/#org",
            "url": "https://example.com/", "org_props": ["url", "logo", "sameAs"],
        }]),
        about: _page(about, in_sitemap=False, json_ld=[{
            "type": "LocalBusiness", "id": "https://example.com/#office",
            "url": "https://example.com/office", "org_props": ["url", "logo", "sameAs"],
        }]),
        www: _page(www, in_sitemap=False, json_ld=[{
            "type": "Organization", "id": "https://www.example.com/#org",
            "url": "https://www.example.com/", "org_props": ["url", "logo", "sameAs"],
        }]),
    }
    issues = sc.compute_issues(pages, [], QUIET_ROBOTS, QUIET_LLMS, SITE)
    hits = _codes(issues, "jsonld_entity_ids_differ")
    assert len(hits) == 1
    assert hits[0]["url"] == SITE
    assert hits[0]["severity"] == "medium"
    assert hits[0]["detail"] == (
        "Distinct @id values: https://example.com/#office, https://example.com/#org"
    )

    pages.pop(about)
    issues = sc.compute_issues(pages, [], QUIET_ROBOTS, QUIET_LLMS, SITE)
    assert _codes(issues, "jsonld_entity_ids_differ") == []


def test_jsonld_org_incomplete_uses_most_common_id():
    common = "https://example.com/#org"
    rare = "https://example.com/#other"
    full = ["url", "logo", "sameAs", "name"]
    pages = {
        "https://example.com/": _page("https://example.com/", in_sitemap=False, json_ld=[{
            "type": "Organization", "id": common, "url": "https://example.com/", "org_props": ["url", "name"],
        }]),
        "https://example.com/about": _page("https://example.com/about", in_sitemap=False, json_ld=[{
            "type": "Organization", "id": common, "url": "https://example.com/", "org_props": ["url", "name"],
        }]),
        "https://example.com/contact": _page("https://example.com/contact", in_sitemap=False, json_ld=[{
            "type": "Organization", "id": rare, "url": "https://example.com/", "org_props": full,
        }]),
    }
    issues = sc.compute_issues(pages, [], QUIET_ROBOTS, QUIET_LLMS, SITE)
    hits = _codes(issues, "jsonld_org_incomplete")
    assert len(hits) == 1
    assert hits[0]["url"] == SITE
    assert hits[0]["severity"] == "low"
    assert hits[0]["detail"] == f"{common} lacks logo, sameAs"

    # Props can be split across pages. The entity has them if any node with that @id does.
    merged = {
        "https://example.com/": _page("https://example.com/", in_sitemap=False, json_ld=[{
            "type": "Organization", "id": common, "url": "https://example.com/", "org_props": ["url", "name"],
        }]),
        "https://example.com/about": _page("https://example.com/about", in_sitemap=False, json_ld=[{
            "type": "Organization", "id": common, "url": "https://example.com/", "org_props": ["logo", "sameAs"],
        }]),
    }
    assert _codes(sc.compute_issues(merged, [], QUIET_ROBOTS, QUIET_LLMS, SITE), "jsonld_org_incomplete") == []


def test_crawl_records_link_header_lastmod_and_non_html(tmp_path):
    locs = "".join(
        f"<url><loc>https://example.com/p{i}</loc><lastmod>2026-01-01</lastmod></url>" for i in range(6)
    )
    locs += "<url><loc>https://example.com/post.md</loc><lastmod>2026-01-01</lastmod></url>"
    sitemap = f"<?xml version='1.0'?><urlset>{locs}</urlset>".encode()

    def fake(url):
        path = urlparse(url).path
        if path == "/robots.txt":
            return _raw(200, b"User-agent: *\nAllow: /\n", "text/plain")
        if path == "/llms.txt":
            return _raw(200, b"hi", "text/plain")
        if path == "/sitemap.xml":
            return _raw(200, sitemap, "application/xml")
        if path == "/post.md":
            raw = _raw(200, b"# post", "text/markdown")
            raw["headers"]["link"] = ['<https://example.com/llms.txt>; rel="describedby"']
            return raw
        body = f"<html><head><title>{path}</title><link rel='canonical' href='{url}'></head><body><h1>x</h1></body></html>".encode()
        raw = _raw(200, body)
        raw["headers"]["link"] = [f'<{url}>; rel="canonical"']
        return raw

    report = sc.crawl(
        {"site": SITE, "sitemap": "https://example.com/sitemap.xml", "max_pages": 20},
        fetch=fake,
        delay=0,
    )
    assert report["pages"]["https://example.com/post.md"]["link_header"] == (
        '<https://example.com/llms.txt>; rel="describedby"'
    )
    assert report["pages"]["https://example.com/p0"]["link_header"] == '<https://example.com/p0>; rel="canonical"'
    non_html = _codes(report["issues"], "sitemap_non_html")
    assert [item["url"] for item in non_html] == ["https://example.com/post.md"]
    assert non_html[0]["detail"] == "text/markdown"
    lastmod = _codes(report["issues"], "sitemap_lastmod_uniform")
    assert len(lastmod) == 1
    assert "7 of 7 URLs share lastmod 2026-01-01" == lastmod[0]["detail"]


def test_lastmod_flags_majority_build_stamp():
    urls = [f"https://example.com/p{i}" for i in range(8)]
    stamps = ["2026-01-01"] * 2 + ["2026-03-01T12:00:00.000Z"] * 6
    issue = sc._sitemap_lastmod_issue(urls, stamps, "https://example.com")
    assert issue and issue["code"] == "sitemap_lastmod_uniform"
    assert "6 of 8" in issue["detail"]


def test_lastmod_mixed_dates_not_flagged():
    urls = [f"https://example.com/p{i}" for i in range(8)]
    stamps = [f"2026-01-0{i + 1}" for i in range(8)]
    assert sc._sitemap_lastmod_issue(urls, stamps, "https://example.com") is None


def test_redirect_exact_url_fetches_slash_target_and_www():
    about_html = b"<html><head><title>About</title></head><body><h1>About</h1></body></html>"
    www_home = b'<html><head><title>Home</title></head><body><h1>Home</h1><a href="/pricing">Pricing</a></body></html>'
    pricing = b"<html><head><title>Pricing</title></head><body><h1>Pricing</h1></body></html>"
    sitemap_slash = b'<?xml version="1.0"?><urlset><url><loc>https://example.com/about/</loc></url></urlset>'
    sitemap_apex = b'<?xml version="1.0"?><urlset><url><loc>https://example.com/</loc></url></urlset>'

    def fake_slash(url):
        path = urlparse(url).path
        if path == "/robots.txt":
            return _raw(200, b"User-agent: *\nAllow: /\n", "text/plain")
        if path == "/llms.txt":
            return _raw(404, b"", "text/plain")
        if path == "/sitemap.xml":
            return _raw(200, sitemap_slash, "application/xml")
        if url == "https://example.com/about/":
            return _raw(308, b"", "text/html", location="https://example.com/about")
        if url == "https://example.com/about":
            return _raw(200, about_html)
        return _raw(404, b"missing", "text/html")

    config = {"site": SITE, "sitemap": "https://example.com/sitemap.xml", "max_pages": 20}
    report = sc.crawl(config, fetch=fake_slash, delay=0, sleep=lambda _s: None)
    assert "https://example.com/about" in report["pages"]
    page = sc.find_page("https://example.com/about", report["pages"])
    assert page["status"] == 200
    assert page["title"] == "About"

    def fake_www(url):
        parsed = urlparse(url)
        if parsed.path == "/robots.txt":
            return _raw(200, b"User-agent: *\nAllow: /\n", "text/plain")
        if parsed.path == "/llms.txt":
            return _raw(404, b"", "text/plain")
        if parsed.path == "/sitemap.xml":
            return _raw(200, sitemap_apex, "application/xml")
        if url == "https://example.com/":
            return _raw(308, b"", "text/html", location="https://www.example.com/")
        if parsed.hostname == "www.example.com" and parsed.path == "/":
            return _raw(200, www_home)
        if parsed.hostname == "www.example.com" and parsed.path == "/pricing":
            return _raw(200, pricing)
        return _raw(404, b"missing", "text/html")

    report = sc.crawl(config, fetch=fake_www, delay=0, sleep=lambda _s: None)
    assert report["pages"]["https://www.example.com/"]["status"] == 200
    assert report["pages"]["https://www.example.com/pricing"]["title"] == "Pricing"
    final = sc.find_page("https://www.example.com/", report["pages"])
    assert final["title"] == "Home"


def test_title_first_only_ignores_svg_and_robots_tokens():
    html = """<html><head>
    <svg><title>Icon label</title></svg>
    <title>First title</title>
    <title>Second title</title>
    <meta name="robots" content="max-image-preview:none, index">
    <meta name="googlebot" content="googlebot: noindex">
    </head><body><p>Words here.</p></body></html>"""
    parsed = sc.parse_html(html, "https://example.com/", SITE)
    assert parsed["title"] == "First title"
    assert parsed["meta_googlebot"] == "googlebot: noindex"
    assert sc.robots_value_is_noindex("max-image-preview:none") is False
    assert sc.has_noindex({"meta_robots": "max-image-preview:none", "x_robots_tag": None}) is False
    assert sc.has_noindex(parsed) is True
    assert sc.robots_value_is_noindex("none") is True
    assert sc.robots_value_is_noindex("noindex, nofollow") is True
