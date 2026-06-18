# Security Policy

## What this repo is

`1610-advisory/mktkit` is the **public parent** of the 1610 Marketing Toolkit, a multi-client system that acts as an AI CMO. The bot runtime that consumes it (the SaaS UI, deploy automation, multi-tenant infrastructure) is intentionally NOT in this repo. Per-client data (real client names, briefs, performance numbers, transcripts, memory) lives in separate **private** repos — `clients/*/` is gitignored here and never committed.

This means: **everything in this repo is intended to be public.** Anyone may fork and run their own marketing operation on top of it.

## What MUST NOT be committed

- Real client names, emails, domains, or any identifier tied to a specific operator's clients
- Operator infrastructure values: server IPs, SSH hostnames, internal hostnames, zone IDs, account IDs, Google Sheet IDs, Slack channel/user/workspace IDs, n8n credential IDs, Typefully social-set IDs
- API keys, OAuth tokens, OAuth client secrets, private keys, passwords, database connection strings — even partial, even "for testing"
- Real values from credential stores (e.g., `~/.credentials/`, `~/.zshrc.local`) — paths can be referenced; literal values cannot
- Anything that wouldn't appear in a fresh fork by a different operator

Generic placeholders are always welcome: `example.com`, `[client-name]`, `<slug>`, `your-api-key-here`, `Acme Corp`.

## Mechanical enforcement: pre-commit hook

A pre-commit hook at `.githooks/pre-commit` blocks commits that match known leak patterns. **Install per-clone:**

```bash
git config core.hooksPath .githooks
```

The hook checks generic high-signal patterns (API key shapes, tracking IDs, private-key blocks) by default. For operator-specific values, maintain a private local blocklist:

```
~/.config/ai-cmo-sanitize/blocklist.txt
```

One ERE pattern per line, `#` for comments. **Never commit this file** — putting real client names in the public repo to detect leaks of them would itself be the leak. Each operator (including forkers) maintains their own.

Override path (use sparingly, manual review required):

```bash
SKIP_AI_CMO_SANITIZE=1 git commit ...
```

See `CLAUDE.md` → "Public-Repo Safety" for the full release checklist.

## Reporting a leak in this repo

If you find committed data that looks like it belongs in a private repo — client names, real emails, infrastructure values, secrets:

1. **Open a GitHub issue** titled `security: <one-line description>`. Reference the file/line; do **not** quote the offending content in the issue body.
2. The maintainer treats these as **P0**. Expected response: history rewrite (for non-secret leaks) or rotate-and-revoke (for live secrets), depending on severity.
3. If the leak is a **live secret** (API key, token, password), also notify the maintainer via any private channel you have available before opening the public issue, so rotation can start immediately.

## Reporting a hook gap

If you find a leak pattern the pre-commit hook should catch but doesn't, open a PR adding the pattern to `.githooks/pre-commit`. Use a **generic pattern shape** (regex), not a literal value.

## Maintainer

`@dawsonschrader` — see commit history.
