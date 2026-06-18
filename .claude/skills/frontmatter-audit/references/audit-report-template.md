# Audit Report Template

This is the layout the audit renders for the user. Stable section headers so the user can scan the same shape every time. Translate the JSON output of `scripts/audit.py` into this format.

---

## Template

```markdown
# Frontmatter Audit — [client-name]

**Audited:** YYYY-MM-DD
**Files scanned:** N (knowledge: K, content notes: C, briefs: B)
**Issues found:** TOTAL (errors: E, warnings: W, info: I)
**Auto-fixable:** AUTO_COUNT
**Manual cleanup:** MANUAL_COUNT

---

## Schema violations

If none, write: "No schema violations. Frontmatter is clean."

Otherwise, group by file type:

### Knowledge files

```
[file-path]
  ✗ [severity] field=[field-name]  expected=[expected]  actual=[actual]  fix=[auto|user|manual]
```

### Content notes

```
[file-path]
  ✗ [severity] field=[field-name]  expected=[expected]  actual=[actual]  fix=[auto|user|manual]
```

### Briefs

```
[file-path]
  ✗ [severity] field=[field-name]  expected=[expected]  actual=[actual]  fix=[auto|user|manual]
```

---

## Structural issues

If none, write: "No structural issues."

Otherwise:

### Orphan files at outputs/ root

```
[file-path]  ← move to a subfolder or archive
```

### Broken brief references

Content notes whose `brief:` field points to a file that doesn't exist:

```
[content-note-path]
  brief: [[non-existent-brief-name]]  ← brief not found under outputs/*-briefs/
```

### Broken wiki-links from briefs

Briefs whose body references content notes that don't exist:

```
[brief-path]
  → [[non-existent-content-note]]  ← content note not found under outputs/content/
```

### Duplicate content IDs

```
content_id: [ID-VALUE]  appears in:
  - [file-1]
  - [file-2]
```

---

## Stale knowledge

Knowledge files with `status: needs-update` and `last_updated` older than 60 days:

```
[file-path]
  last_updated: YYYY-MM-DD  (N days ago)  status: needs-update
```

If none, write: "No stale knowledge files."

---

## Auto-fixable summary

If `AUTO_COUNT > 0`, list each fix:

```
[file-path]
  + key: old-value → new-value
```

Then ask:

> Want me to apply these N auto-fixes? I'll run the script with `--apply-auto-fixes` and report what changed.

If `AUTO_COUNT == 0`:

> No auto-fixes available. The remaining issues need user decisions or manual cleanup.

---

## Manual cleanup checklist

For each manual issue, give the user a concrete next step:

```
- [ ] Move [orphan-file] into the right subfolder (or archive it)
- [ ] Resolve duplicate content_id [ID]: rename one of [file-1] or [file-2]
- [ ] Relink or null the broken brief reference in [content-note-path]
- [ ] Decide what to do with stale knowledge file [file]: update content or downgrade status to `reference`
```

If `MANUAL_COUNT == 0`:

> No manual cleanup needed.
```

---

## Rendering rules

1. **Clean audit:** If everything passes, render only the headline counts and a single line: "No issues. Schema and structure are clean." Don't pad with empty sections.
2. **Long lists:** If a section has more than ~10 entries, wrap the list in a fenced code block. Long bullet lists are harder to scan than fixed-width text.
3. **Group by file:** Within each section, sort by file path so the user can read the same files together.
4. **Severity ordering:** Within a file, list `error` before `warning` before `info`.
5. **Don't editorialize:** Show the data. Save commentary for the closing question ("want me to fix these?").

---

## After applying auto-fixes

When the user approves the fix step, the script returns a JSON object with the changes made. Render it as:

```markdown
# Auto-fixes applied

**Files updated:** N
**Keys changed:** K

[file-path]
  + key1: old → new
  + key2: old → new

[file-path]
  + key3: old → new
```

Then suggest re-running the audit to confirm the report is clean (the user might want to verify before moving on to the manual cleanup).
