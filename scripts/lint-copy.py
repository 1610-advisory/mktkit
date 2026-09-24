#!/usr/bin/env python3
"""lint-copy.py — Deterministic anti-AI slop and copy quality linter for marketing copy.

Scans marketing copy files (.md, .html) for banned AI tropes, em dashes,
script dialogue tags, template transitional formulas, and high-frequency AI words
codified in references/ai-writing-detection.md and the humanizer skill.

Only audits client-facing deliverable copy:
- In content notes: audits ## Caption, ## Script, and copy codeblocks
- In newsletters: audits ## Variant sections
- In blogs / articles: audits the article body
- Skips frontmatter, ## Source answer, ## Revision History, ## Editor Deliverable,
  ## Production Notes, ## Strategic Context, and technical director notes.

Exit code: 0 if clean, 1 if slop patterns found.
"""

import sys, os, re, argparse

# A line made only of hashtags ("#remodel #kitchen") is not copy.
HASHTAG_LINE = re.compile(r"^#[A-Za-z0-9_]+(?:\s+#[A-Za-z0-9_]+)*\s*$")

BANNED_WORDS = [
    (r"\bdelve\b|\bdelving\b", "Overused AI verb 'delve'"),
    (r"\btestament\b", "Puffed significance 'testament'"),
    (r"\bpivotal\b", "Overused AI adjective 'pivotal'"),
    (r"\bcrucial\b", "Overused AI adjective 'crucial'"),
    (r"\bvital\b", "Overused AI adjective 'vital'"),
    (r"\brobust\b", "Overused AI adjective 'robust'"),
    (r"\bseamless\b|\bseamlessly\b", "Overused AI adjective/adverb 'seamless'"),
    (r"\blandscape\b(?!\s+(?:lighting|design|architect|contractor))\b", "Abstract AI noun 'landscape' (allowed for physical landscape lighting/design)"),
    (r"\btapestry\b", "Abstract AI noun 'tapestry'"),
    (r"\bholistic\b", "Corporate buzzword 'holistic'"),
    (r"\bfoster\b|\bfostering\b", "Overused AI verb 'foster'"),
    (r"\bbolster\b|\bbolstering\b", "Overused AI verb 'bolster'"),
    (r"\bunderscore\b|\bunderscores\b|\bunderscoring\b", "Overused AI verb 'underscore'"),
    (r"\bmoreover\b|\bfurthermore\b", "Stiff academic transition 'furthermore/moreover'"),
    (r"\bplethora\b|\bmyriad\b", "Academic filler 'plethora/myriad'"),
    (r"\bparamount\b", "Academic filler 'paramount'"),
    (r"\btransformative\b|\bgroundbreaking\b|\bcutting-edge\b", "Promotional hyperbole"),
    (r"\bcomprehensive\b", "Overused AI adjective 'comprehensive'"),
    (r"\bnavigating\b", "Overused AI metaphor 'navigating'"),
]

TROPES = [
    (r"—", "Em dash detected (strict ban in client copy; use commas, colons, or periods)"),
    (r'^\s*(?:\*\*)?[A-Z][a-z]+(?:\*\*)?:\s*"', "Script dialogue tag (e.g. 'Owner: \"...\"'); weave quotes naturally"),
    (r"\bIn his words:\s*\"", "Essayistic quote introduction 'In his words:\"'"),
    (r"\bhere is where things stand\b", "Formulaic transitional cliché 'here is where things stand'"),
    (r"\bhere is how they actually run\b", "Formulaic transitional cliché 'here is how they actually run'"),
    (r"\bhere is a thing about\b", "Conversational AI opener 'here is a thing about'"),
    (r"\bthat's the whole (?:story|email)\b", "AI conversational summarizer 'that's the whole story/email'"),
    (r"\bthis month:\s*[a-z]", "Formulaic newsletter header 'this month: ...'"),
    (r"\bwhether\b.*?\bor\b", "Symmetrical 'whether X or Y' template"),
    (r"\bwhether (?:it's|you're|a|the)\b", "Formulaic 'whether ...' template"),
    (r"\bnot only\b.*?\bbut also\b", "Negative parallelism 'not only... but also'"),
    (r",\s*(?:underscoring|highlighting|ensuring|reflecting|symbolizing|fostering)\b", "Superficial -ing participle clause"),
    (r"\b(?:How much\?|Planning a project\?)\b", "Artificial rhetorical question setup"),
]

INTERNAL_SECTIONS = [
    "source answer", "source transcript", "raw transcript",
    "revision history", "editor deliverable", "production notes",
    "strategic context", "visual hook", "assets", "video tracks",
    "audio tracks", "b-roll", "edit brief", "meta-bar"
]

COPY_SECTIONS = [
    "variant", "caption", "script", "body", "issue", "newsletter", "copy"
]

def check_file(filepath):
    # Always skip documentation, templates, and guides
    base = os.path.basename(filepath)
    if base.startswith(("_template", "README", "TEMPLATE")):
        return []

    issues = []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    in_frontmatter = False
    in_code_block = False
    
    # By default, for notes with section headers, check if file uses sectioning
    has_explicit_sections = any(
        line.strip().startswith("##") and any(cs in line.strip().lower() for cs in COPY_SECTIONS)
        for line in lines
    )
    
    in_copy_section = not has_explicit_sections

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Handle frontmatter
        if i == 0 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
            continue

        # Detect headers
        if stripped.startswith("#"):
            lower_h = stripped.lower()
            if any(k in lower_h for k in INTERNAL_SECTIONS):
                in_copy_section = False
            elif any(k in lower_h for k in COPY_SECTIONS):
                in_copy_section = True
            elif has_explicit_sections:
                in_copy_section = False

        # In content notes, captions are often enclosed in triple-backtick blocks under ## Caption
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue

        if not in_copy_section:
            continue

        # Skip blockquotes (usually verbatim quotes from tape in reference sections)
        if stripped.startswith(">"):
            continue

        # Skip markdown hashtag lines
        if stripped.startswith("**Hashtags:**") or HASHTAG_LINE.match(stripped):
            continue

        # Skip URL lines
        if stripped.startswith("http://") or stripped.startswith("https://") or (stripped.startswith("[") and "](http" in stripped):
            continue

        # Check tropes and banned words
        for pattern, desc in TROPES:
            if re.search(pattern, line, re.IGNORECASE if "—" not in pattern else 0):
                issues.append((i + 1, desc, line.strip()))

        for pattern, desc in BANNED_WORDS:
            m = re.search(pattern, line, re.IGNORECASE)
            if m:
                issues.append((i + 1, f"{desc} ('{m.group(0)}')", line.strip()))

    return issues

def main():
    parser = argparse.ArgumentParser(description="Lint marketing copy for AI tropes and slop.")
    parser.add_argument("targets", nargs="+", help="Files or directories to lint")
    args = parser.parse_args()

    files = []
    for t in args.targets:
        if os.path.isfile(t):
            files.append(t)
        elif os.path.isdir(t):
            for root, _, filenames in os.walk(t):
                for fn in filenames:
                    if fn.endswith((".md", ".html")) and not fn.startswith(("_template", "README")):
                        files.append(os.path.join(root, fn))

    total_issues = 0
    clean_files = 0

    for fpath in sorted(files):
        issues = check_file(fpath)
        if issues:
            total_issues += len(issues)
            print(f"\n❌ \033[1;31m{fpath}\033[0m ({len(issues)} issues found):")
            for line_no, desc, snippet in issues:
                print(f"  Line {line_no:3d}: \033[33m{desc}\033[0m")
                print(f"           \033[90m{snippet[:100]}\033[0m")
        else:
            clean_files += 1
            print(f"✅ \033[32m{fpath}\033[0m — clean")

    print(f"\nSummary: {clean_files} clean files, {len(files) - clean_files} files with issues, {total_issues} total issues.")
    sys.exit(1 if total_issues > 0 else 0)

if __name__ == "__main__":
    main()
