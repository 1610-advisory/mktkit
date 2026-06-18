---
description: Scan a content folder and update the client's content asset index
argument-hint: /path/to/content-folder [location-label]
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion]
---

# Index Content Assets

Scan a content storage folder and create or update the client's `tracking/content-index.md` — a master inventory of all shot content across all storage locations.

## Arguments

User provided: $ARGUMENTS

Parse for:
- **Path** to the content folder (e.g., `/Volumes/T7 - D01/02. Client Projects`, `~/Google Drive/Client Content`)
- **Location label** — short name for this storage location (e.g., `T7-D01`, `Editor Copy`, `Google Drive`)

If no path provided, ask:
1. "Where is the content folder? (full path)"
2. "What should I call this storage location? (e.g., T7-D01, Editor Copy, Google Drive)"

If path provided but no label, ask for the label.

---

## Workflow

### Step 1: Verify the Folder Exists

```bash
ls "[path]"
```

If the path doesn't exist (e.g., drive not mounted), tell the user and stop.

### Step 2: Detect the Client

Determine the active client from the current working directory:
- If inside `clients/[client-name]/`, use that client
- Otherwise, ask: "Which client is this content for?"

### Step 3: Read Existing Index (if any)

Check if `tracking/content-index.md` exists for this client. If it does:
- Read it
- Note which locations and projects are already indexed
- This is a **merge** operation — preserve all existing data for other locations

If it doesn't exist, start fresh.

### Step 4: Scan the Folder Structure

Inventory the content folder:

```bash
# List top-level items
ls -1 "[path]"
```

Classify each item:
- **Project folders** — match pattern `YYYY_Name_*` (e.g., `2026_Mitchell_Kitchen`). These contain shoot date subfolders.
- **Special folders** — `Assets`, `Reels`, template folders, or anything not matching the project pattern. Track these in the "Other Folders" section.
- **Ignore** — hidden files (`._*`, `.DS_Store`), system files

### Step 5: Scan Each Project Folder

For each project folder, find shoot date subfolders and special subfolders:

```bash
ls -1 "[path]/[project-folder]"
```

**Shoot date subfolders** match `YYYY-MM-DD`. For each:

1. **Count files:**
```bash
# Videos
find "[shoot-path]" -maxdepth 1 -type f \( -iname "*.mp4" -o -iname "*.mov" \) | wc -l

# Photos
find "[shoot-path]" -maxdepth 1 -type f \( -iname "*.cr3" -o -iname "*.jpg" -o -iname "*.raf" \) | wc -l
```

2. **Check organized status:**
```bash
ls "[shoot-path]/file-mapping.txt" 2>/dev/null
```
If file-mapping.txt exists → `Organized: Yes`. Parse it for key content.

3. **Parse file-mapping.txt (if exists):**
Extract named content pieces:
- A-Roll lines: look for `ARoll-` or `Post[N]-` (legacy) entries. Note the description and duration.
- CB lines: `CB-` entries with descriptions
- B-Roll count: count `BRoll-` entries
- Summarize as "Key Content" (e.g., `ARoll: 113s walkthrough (demo to framing). 3 CB pieces. 9 named B-roll.`)

4. **Check for transcripts:**
```bash
ls "[shoot-path]/Audio/"*.txt 2>/dev/null | wc -l
```

**Static subfolders** (`01. Before`, `Final`, etc.):
- Note if they have content (photos/videos) or are empty containers

### Step 6: Build the Index

#### If creating fresh:

Write `tracking/content-index.md` with:

```markdown
---
title: Content Asset Index
description: Master inventory of all shot content across all storage locations
last_updated: [today's date]
status: active
priority: high
---

# Content Asset Index — [Client Name]

## Storage Locations

| Label | Path | Type | Last Indexed |
|-------|------|------|--------------|
| [label] | [path] | [type — infer from path: External SSD, Local, Cloud Sync] | [today] |

---

## Projects

### [Project Display Name]
**Folder:** `[folder-name]/`

| Location | Shoot Date | Videos | Photos | Organized | Key Content |
|----------|------------|--------|--------|-----------|-------------|
| [label] | [date] | [#] | [#] | [Yes/No] | [summary] |

---

[repeat for each project]

## Other Folders

| Location | Folder | Contents | Notes |
|----------|--------|----------|-------|
| [label] | [name] | [description] | [notes] |
```

**Project display name:** Derive from folder name. `2026_Mitchell_Kitchen` → `Mitchell Kitchen`. `2026_Hargrove_1930 Spacelift` → `Hargrove 1930 Spacelift`. Drop the year prefix — it's in the folder reference.

**Project ordering:** Alphabetical by display name.

**Type inference from path:**
- `/Volumes/` → `External SSD`
- `~/` or `/Users/` → `Local`
- Contains `Google Drive` or `Dropbox` → `Cloud Sync`
- Otherwise → ask the user

#### If merging with existing:

1. **Storage Locations table:** Add a new row for this location label (or update `Last Indexed` if the label already exists).

2. **Projects:**
   - If the project section already exists: add new rows for this location (or update existing rows for this location + shoot date)
   - If the project is new: add a new section in alphabetical order

3. **Other Folders:** Add rows for this location's special folders.

4. **Never remove data** for other locations. Only touch rows matching the current location label.

### Step 7: Report

Show the user a summary:

```
## Content Index Updated

**Location:** [label] ([path])
**Client:** [client name]

### Projects Indexed
| Project | Shoots | Total Videos | Total Photos |
|---------|--------|-------------|-------------|
| [name] | [#] | [#] | [#] |
...

**Total:** [N] projects, [N] shoots, [N] videos, [N] photos

### Changes
- [New projects added / Updated projects / New location added]
```

If this is a re-index of an existing location, highlight what changed (new shoots, updated counts, etc.).

---

## Notes

- **Drive must be mounted** for external drives. If the path doesn't exist, remind the user to connect the drive.
- **File counts are for the shoot date folder only** (maxdepth 1). Don't count files inside `Audio/` subdirectories.
- **Existing `Post[N]-` prefixed files** are legacy A-roll naming. Treat them the same as `ARoll-` when parsing file-mappings.
- **Large folders** may have many shoots. Batch `find` commands to avoid excessive tool calls.
- **Mac metadata files** (`._*`) should be excluded from counts.
