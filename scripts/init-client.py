#!/usr/bin/env python3
"""
Initialize a new 1610 Marketing Toolkit client folder structure.

Usage:
    init-client.py <client-name> --path <base-path>

Example:
    init-client.py acme-corp --path clients/

Creates the full client directory structure with template files:
    clients/acme-corp/
    ├── CLAUDE.md
    ├── knowledge/
    │   ├── 00-client-overview.md
    │   ├── voice-guidelines.md
    │   ├── personas-storybrand.md
    │   ├── goals-and-benchmarks.md
    │   └── whats-working.md
    ├── tracking/
    │   ├── content-log.csv
    │   ├── performance.csv
    │   └── revenue-attribution.csv
    ├── content/our-content/
    ├── content/competitors/
    ├── research/
    ├── transcripts/
    ├── memory/
    │   ├── MEMORY.md
    │   └── logs/
    └── outputs/
        ├── monthly-briefs/
        ├── weekly-briefs/
        └── biweekly-briefs/
"""

import subprocess
import sys
import shutil
from pathlib import Path


def find_templates_dir():
    """Find the templates directory relative to this script."""
    script_dir = Path(__file__).resolve().parent
    # Templates are in templates/ at the project root
    templates_dir = script_dir.parent / "templates"
    if templates_dir.exists():
        return templates_dir
    return None


def setup_git(client_dir, templates_dir):
    """Initialize an isolated git repo in the client folder for revision tracking.

    The parent toolkit repo ignores clients/*/, so this creates a private,
    standalone repo that stays outside the published plugin. Obsidian Sync
    carries the .git folder across devices, giving multi-machine history
    without needing a remote.
    """
    # Copy gitignore template
    if templates_dir:
        gitignore_src = templates_dir / "gitignore.template"
        if gitignore_src.exists():
            gitignore_dest = client_dir / ".gitignore"
            shutil.copy2(gitignore_src, gitignore_dest)
            print("  Copied .gitignore")
        else:
            print("  Warning: gitignore.template not found — creating minimal .gitignore")
            (client_dir / ".gitignore").write_text(
                ".DS_Store\n.claude/settings.local.json\n.env\n*.token.json\n"
            )

    # Initialize git repo and make an initial commit
    try:
        subprocess.run(
            ["git", "init", "-q"],
            cwd=client_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "add", "."],
            cwd=client_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-q", "-m", "Initial client setup"],
            cwd=client_dir,
            check=True,
            capture_output=True,
        )
        print("  Initialized git repo with initial commit")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"  Warning: Could not initialize git ({e})")
        print(f"  You can run 'cd {client_dir} && git init' manually later.")
        return False


def init_client(client_name, base_path):
    """Create client folder structure and copy templates."""
    client_dir = Path(base_path).resolve() / client_name

    if client_dir.exists():
        print(f"Error: Client directory already exists: {client_dir}")
        return False

    templates_dir = find_templates_dir()

    # Create directory structure
    dirs = [
        ".claude",
        "knowledge",
        "tracking",
        "content/our-content",
        "content/competitors",
        "research",
        "transcripts",
        "memory/logs",
        "outputs/monthly-briefs",
        "outputs/weekly-briefs",
        "outputs/biweekly-briefs",
        "outputs/content",
    ]

    for d in dirs:
        (client_dir / d).mkdir(parents=True, exist_ok=True)
        print(f"  Created {d}/")

    # Map template files to destinations
    template_map = {
        # Client CLAUDE.md
        "CLIENT-CLAUDE.md": "CLAUDE.md",
        # Knowledge files
        "00-client-overview.md": "knowledge/00-client-overview.md",
        "voice-guidelines.md": "knowledge/voice-guidelines.md",
        "personas-storybrand.md": "knowledge/personas-storybrand.md",
        "goals-and-benchmarks.md": "knowledge/goals-and-benchmarks.md",
        "whats-working.md": "knowledge/whats-working.md",
        # Tracking files
        "content-log.csv": "tracking/content-log.csv",
        "performance.csv": "tracking/performance.csv",
        "revenue-attribution.csv": "tracking/revenue-attribution.csv",
        # Memory
        "MEMORY.md": "memory/MEMORY.md",
    }

    if templates_dir:
        for src_name, dest_path in template_map.items():
            src = templates_dir / src_name
            dest = client_dir / dest_path
            if src.exists():
                shutil.copy2(src, dest)
                print(f"  Copied {src_name} -> {dest_path}")
            else:
                print(f"  Warning: Template not found: {src_name}")
    else:
        print("  Warning: Templates directory not found. Creating empty files.")
        for dest_path in template_map.values():
            dest = client_dir / dest_path
            if dest_path.endswith(".csv"):
                # Create CSV headers
                if "content-log" in dest_path:
                    dest.write_text("content_id,date_published,platform,format,title_description,content_url,theme_topic,hook_used,cta_type,created_by,status,notes\n")
                elif "performance" in dest_path:
                    dest.write_text("content_id,date_measured,views,reach,likes,comments,shares,saves,link_clicks,follows,engagement_rate,performance_score,notes\n")
                elif "revenue" in dest_path:
                    dest.write_text("lead_id,lead_date,lead_name,lead_source,platform,content_id,first_touch,last_touch,lead_status,close_date,project_type,revenue,notes\n")
            else:
                dest.write_text(f"# {dest_path.split('/')[-1].replace('.md', '').replace('-', ' ').title()}\n\n[To be completed during onboarding]\n")

    # Replace placeholders in all markdown templates
    for dest_path in template_map.values():
        dest = client_dir / dest_path
        if dest.exists() and dest_path.endswith(".md"):
            content = dest.read_text()
            display_name = client_name.replace("-", " ").title()
            content = content.replace("[Client Name]", display_name)
            content = content.replace("[CLIENT NAME]", display_name.upper())
            content = content.replace("[client-name]", client_name)
            dest.write_text(content)

    # Initialize git for revision tracking (isolated repo, private to client)
    setup_git(client_dir, templates_dir)

    print(f"\nClient '{client_name}' initialized at {client_dir}")
    print("\nNext: Run through the onboarding interview to populate knowledge files.")
    return True


def main():
    if len(sys.argv) < 4 or sys.argv[2] != "--path":
        print("Usage: init-client.py <client-name> --path <base-path>")
        print("\nExample:")
        print("  init-client.py acme-corp --path clients/")
        sys.exit(1)

    client_name = sys.argv[1]
    base_path = sys.argv[3]

    print(f"Initializing client: {client_name}")
    print(f"Location: {base_path}\n")

    if init_client(client_name, base_path):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
