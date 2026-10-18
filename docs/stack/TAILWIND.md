---
name: Tailwind CSS
layer: Styling
detect: package.json ~ tailwindcss, */package.json ~ tailwindcss
---

# Tailwind CSS

How the office works with frontends styled with [Tailwind CSS](https://tailwindcss.com/) v4: what the repo needs, and the rules agents follow on it.

## Setting up a repo

- **Tokens live in the design system.** The repo's `DESIGN.md` (or `docs/design-system.md`) defines the color, spacing and type tokens, and Tailwind's theme (the `@theme` block in v4) is the only place their values appear.
- **A token check in verify.** A small script that fails on raw palette classes (`bg-blue-500`), hex or `rgb()` values and arbitrary values outside the token system keeps every page on the same system, whichever agent built it.
- **Shared components** (buttons, badges, cards, form fields) live in one package or folder, so pages compose them instead of restyling from scratch.

## Agent guidance

- Use the design system's tokens and shared components. Never add raw palette classes, hex values or arbitrary values (`text-[#1a73e8]`); add a token to the design system first if one is missing.
- Check which Tailwind version the repo uses before writing config. Version 4 configures the theme in CSS (`@theme`), not in `tailwind.config.js`.
- Don't let a component force text casing (`uppercase`, `capitalize`) unless the design system says so; copy rules such as sentence case belong to the content.

---
[← Back to the stack guides](README.md)
