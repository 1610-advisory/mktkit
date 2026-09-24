#!/usr/bin/env python3
"""scaffold-pipeline.py — Automated marketing pipeline provisioner for client marketing repos.

Checks if a client marketing repository has the required pipeline directories,
templates, configuration files, and git pre-commit hooks for:
  - newsletter (segmented, tape-grounded email issues)
  - blog (search cluster blogs with YouTube embeds, original stills, bracket citations)
  - captions (hook + expand social content notes)

If not present, automatically scaffolds them from this toolkit's templates.

Usage:
  python3 scaffold-pipeline.py [newsletter|blog|captions|all] [--cwd /path/to/client/marketing]
"""

import sys, os, shutil, argparse, subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MKT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
TEMPLATES_DIR = os.path.join(MKT_ROOT, "templates")
LINTER_PATH = os.path.join(SCRIPT_DIR, "lint-copy.py")

PRE_COMMIT_SCRIPT = f"""#!/usr/bin/env bash
# Pre-commit hook: runs lint-copy.py against staged client copy (.md files in outputs/newsletter, outputs/blog, outputs/content)
set -euo pipefail

STAGED_COPY=()
while IFS= read -r f; do
  [ -z "$f" ] && continue
  base="$(basename "$f")"
  case "$base" in README*|_template*|TEMPLATE*) continue ;; esac
  case "$f" in
    outputs/newsletter/*.md|outputs/blog/*.md|outputs/content/*.md)
      STAGED_COPY+=("$f")
      ;;
  esac
done < <(git diff --cached --name-only --diff-filter=ACM)

if [ ${{#STAGED_COPY[@]}} -gt 0 ]; then
  LINTER="{LINTER_PATH}"
  if [ -x "$LINTER" ] || [ -f "$LINTER" ]; then
    echo "Running anti-slop copy linter on staged files..."
    python3 "$LINTER" "${{STAGED_COPY[@]}}"
  fi
fi
exit 0
"""

def ensure_githook(cwd):
  git_dir = os.path.join(cwd, ".git")
  if not os.path.isdir(git_dir):
    return

  githooks_dir = os.path.join(cwd, ".githooks")
  os.makedirs(githooks_dir, exist_ok=True)
  hook_file = os.path.join(githooks_dir, "pre-commit")

  with open(hook_file, "w", encoding="utf-8") as f:
    f.write(PRE_COMMIT_SCRIPT)
  os.chmod(hook_file, 0o755)

  subprocess.run(
      ["git", "config", "core.hooksPath", ".githooks"],
      cwd=cwd,
      capture_output=True,
  )
  print(f"  [git] Configured .githooks/pre-commit with lint-copy.py")


def scaffold_newsletter(cwd):
  print(f"\nChecking Newsletter Pipeline in {cwd}...")
  nl_dir = os.path.join(cwd, "outputs", "newsletter")
  os.makedirs(nl_dir, exist_ok=True)

  template_src = os.path.join(TEMPLATES_DIR, "newsletter-note.md")
  template_dst = os.path.join(nl_dir, "_template.md")
  if not os.path.isfile(template_dst):
    shutil.copyfile(template_src, template_dst)
    print(f"  [created] {os.path.relpath(template_dst, cwd)}")
  else:
    print(f"  [ok] {os.path.relpath(template_dst, cwd)} exists")

  readme_dst = os.path.join(nl_dir, "README.md")
  if not os.path.isfile(readme_dst):
    with open(readme_dst, "w", encoding="utf-8") as f:
      f.write("""# Newsletter Pipeline

Protocol: `{MKT_ROOT}/references/newsletter-pipeline.md`
Client Configuration: `knowledge/newsletter-pipeline.md`

Every issue lives as a markdown file here: `outputs/newsletter/YYYY-MM-NL-NN-<slug>.md`.
One note holds all audience segment variants.

## Rules
- Strictly grounded in committed tape under `transcripts/` (no invented diagnostics or fake color).
- Pass 2-step Humanizer audit loop before committing.
- Zero em dashes (`—`), no script tags (`Name: "..."`), no AI conversational clichés.
- Must pass `lint-copy.py` with 0 issues.
- Client send is sign-off gated.
""".replace("{MKT_ROOT}", MKT_ROOT))
    print(f"  [created] {os.path.relpath(readme_dst, cwd)}")
  else:
    print(f"  [ok] {os.path.relpath(readme_dst, cwd)} exists")

  config_dst = os.path.join(cwd, "knowledge", "newsletter-pipeline.md")
  if not os.path.isfile(config_dst):
    os.makedirs(os.path.dirname(config_dst), exist_ok=True)
    with open(config_dst, "w", encoding="utf-8") as f:
      f.write("""---
title: Newsletter Pipeline Configuration
category: strategy
status: active
reference: "{MKT_ROOT}/references/newsletter-pipeline.md"
---

# Newsletter Pipeline Configuration

System reference: `{MKT_ROOT}/references/newsletter-pipeline.md`

## Audience Segments
- **segment-1** (Name): [Audience description, core pain point, value wedge]
- **segment-2** (Name): [Audience description, core pain point, value wedge]

## Senders & Roles
- **[Sender 1]** (<email@domain.com>): [Role, tone, audience segment]
- **[Sender 2]** (<email@domain.com>): [Role, tone, audience segment]

## Review & Sign-Off
- Review Gate: [Link to review surface]
- Send Gate: Sign-off required from owner before send.
""".replace("{MKT_ROOT}", MKT_ROOT))
    print(f"  [created] {os.path.relpath(config_dst, cwd)}")
  else:
    print(f"  [ok] {os.path.relpath(config_dst, cwd)} exists")

  ensure_githook(cwd)
  print("Newsletter pipeline ready.")


def scaffold_blog(cwd):
  print(f"\nChecking Blog Pipeline in {cwd}...")
  blog_dir = os.path.join(cwd, "outputs", "blog")
  os.makedirs(blog_dir, exist_ok=True)

  template_src = os.path.join(TEMPLATES_DIR, "cluster-blog.md")
  template_dst = os.path.join(blog_dir, "_template.md")
  if not os.path.isfile(template_dst):
    shutil.copyfile(template_src, template_dst)
    print(f"  [created] {os.path.relpath(template_dst, cwd)}")
  else:
    print(f"  [ok] {os.path.relpath(template_dst, cwd)} exists")

  readme_dst = os.path.join(blog_dir, "README.md")
  if not os.path.isfile(readme_dst):
    with open(readme_dst, "w", encoding="utf-8") as f:
      f.write("""# Search-First Cluster Blog Pipeline

Protocol: `{MKT_ROOT}/references/search-cluster-blog-ranking.md`
Drafting Skill: `draft-cluster-blog`

Turn educational video transcripts into authoritative search-optimized blog posts that rank in Google and convert high-intent local searchers.

## Core Pillars
1. **Verbatim Transcript Spine:** Client's exact words on tape as the core quotes [1].
2. **Original Project Photography:** Real jobsite photos (WebP, descriptive local alt text) for algorithmic E-E-A-T proof.
3. **Video Embeds:** YouTube Shorts or long-form videos embedded near the top.
4. **Local Neighborhood Texture:** Authentic neighborhood names, housing eras, and regional building realities.
5. **Numbered Bracket Citations:** `[1]`, `[2]` linking claims to external studies and matching video clips.
6. **Actionable FAQ Schema:** High-conviction answers to People Also Ask queries with real numbers and timelines.
7. **Anti-Slop Standards:** Zero em dashes (`—`), no meta-staging, no copula avoidance, pass `lint-copy.py`.
""".replace("{MKT_ROOT}", MKT_ROOT))
    print(f"  [created] {os.path.relpath(readme_dst, cwd)}")
  else:
    print(f"  [ok] {os.path.relpath(readme_dst, cwd)} exists")

  ensure_githook(cwd)
  print("Blog pipeline ready.")


def scaffold_captions(cwd):
  print(f"\nChecking Social Captions Pipeline in {cwd}...")
  content_dir = os.path.join(cwd, "outputs", "content")
  os.makedirs(content_dir, exist_ok=True)

  template_src = os.path.join(TEMPLATES_DIR, "content-note.md")
  template_dst = os.path.join(content_dir, "_template.md")
  if not os.path.isfile(template_dst):
    shutil.copyfile(template_src, template_dst)
    print(f"  [created] {os.path.relpath(template_dst, cwd)}")
  else:
    print(f"  [ok] {os.path.relpath(template_dst, cwd)} exists")

  ensure_githook(cwd)
  print("Captions pipeline ready.")


def main():
  parser = argparse.ArgumentParser(
      description="Scaffold or check marketing pipelines in a client repo."
  )
  parser.add_argument(
      "pipeline",
      choices=["newsletter", "blog", "captions", "all"],
      help="Which pipeline to scaffold/check",
  )
  parser.add_argument(
      "--cwd",
      default=os.getcwd(),
      help="Target client marketing repository directory",
  )
  args = parser.parse_args()

  target_cwd = os.path.abspath(args.cwd)

  if args.pipeline in ("newsletter", "all"):
    scaffold_newsletter(target_cwd)
  if args.pipeline in ("blog", "all"):
    scaffold_blog(target_cwd)
  if args.pipeline in ("captions", "all"):
    scaffold_captions(target_cwd)


if __name__ == "__main__":
  main()
