---
version: alpha
name: "[CLIENT NAME]"
description: "Visual identity. Hex and type from the live site or brand guide, not from memory."
# Required: every value comes from the live site's CSS, a brand guide, or the owner.
# Leave a value blank rather than guess. Run: python3 <toolkit>/scripts/design_md.py check knowledge/DESIGN.md
colors:
  primary: "#000000"
  on-primary: "#FFFFFF"
  tertiary: "#000000"
  neutral: "#FFFFFF"
  on-surface: "#000000"
  outline: "#CCCCCC"
# Optional (toolkit extension): the same color names, redefined for dark mode.
# themes:
#   dark:
#     neutral: "#000000"
#     on-surface: "#FFFFFF"
typography:
  display:
    fontFamily: ""
  body:
    fontFamily: ""
  label:
    fontFamily: ""
# Optional: rounded, spacing, components. Components point at tokens:
# components:
#   button-primary:
#     backgroundColor: "{colors.primary}"
#     textColor: "{colors.on-primary}"
#   button-primary-hover:
#     backgroundColor: "{colors.primary}"
# Claude sessions add this after they build the claude.ai Design System page (private):
# design_system_url: https://claude.ai/artifact/...
---

# DESIGN.md — [CLIENT NAME]

The brand source for every surface. Google DESIGN.md format: tokens above, rules below. Fill from live CSS or a brand guide. Leave a field blank rather than guessing.

Views are built from this file and are never the source: the HTML view committed in this repo (`design_md.py render`) and, in Claude sessions, the claude.ai Design System page (`design_md.py ds`). If a view and this file disagree, this file wins. Standard: toolkit `references/design-md.md`.

## Overview

[One paragraph: what the surfaces should feel like. Materials, not slogans.]

## Colors

One bullet per token, bold label first, so the Design System page can use it as the token's note:

- **Primary ([hex]):** [where it goes, and where it never goes].

## Typography

[Which face does which job.]

## Layout

## Shapes

## Components

## Do's and Don'ts

- Do pull hex and type from this file.
- Don't invent a third palette.
