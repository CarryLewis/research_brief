# Design system

Visual source of truth for the public knowledge environment in [`frontend/`](../frontend/).

This file is an implementation spec, not a product constitution. It governs `frontend/` only.

The Quartz garden in [`site/`](../site/) and the Library article-feed described in [`PRODUCT_v1.md`](PRODUCT_v1.md) §8 are later, separate surfaces. Do not mix them into this homepage.

The browser extension settings UI is a different surface. Do not restyle it from this document.

---

## Product idea

Technology should become more powerful while the interface becomes quieter.

The site is not a dashboard and not an AI spectacle. It is a quiet intellectual environment: an editorial canvas where a person decides what is worth noticing, remembering, connecting, thinking about, and building.

---

## Visual rules

The impression should be **paper + graphite + ink**, with one restrained signal color.

- Warm off-white background. Near-black text. Muted gray for secondary information.
- Thin 1px borders. Shadows are rare. No gradients, glass, glow, or neon.
- Cards feel like documents on a desk, not floating SaaS tiles.
- Whitespace is structural. Hierarchy comes from position, type, scale, and weight — not color, icons, or badges.
- Animation only when it explains state or space. Typical duration 150–250ms. Honor `prefers-reduced-motion`.
- AI is infrastructure. It must not become the visual protagonist.

If a component has no cognitive purpose, can be said more simply, adds noise, or fails this language — do not add it.

---

## Tokens

Defined in [`frontend/styles/tokens.css`](../frontend/styles/tokens.css). Do not scatter equivalent magic values.

| Token | Role | Value |
|---|---|---|
| `--color-bg` | Warm paper | `#f6f3ee` |
| `--color-surface` | Slightly lighter sheet | `#faf8f4` |
| `--color-text` | Near-black ink | `#1c1b19` |
| `--color-muted` | Secondary text | `#5c5852` |
| `--color-border` | Hairline | `#e6e1d8` |
| `--color-border-hover` | Hover hairline | `#cfc8bc` |
| `--color-accent` | Single signal (umber) | `#8c4a32` |
| `--font-ui` | Interface sans | `-apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif` |
| `--font-editorial` | Selective serif | `"Iowan Old Style", Palatino, "Palatino Linotype", Georgia, serif` |
| `--space-xs` | Tight | `0.25rem` (4px) |
| `--space-sm` | Compact | `0.5rem` (8px) |
| `--space-md` | Default | `1rem` (16px) |
| `--space-lg` | Block | `2rem` (32px) |
| `--space-xl` | Section | `4rem` (64px) |
| `--space-2xl` | Breath | `6rem` (96px) |
| `--radius-sm` | Document corner | `2px` |
| `--measure` | Reading width | `38rem` |
| `--system-label` | Sequence name column | `7rem` |
| `--transition-fast` | Hover | `150ms` |
| `--transition-normal` | Reveal | `250ms` |

---

## Type

| Role | Size | Family | Weight | Notes |
|---|---|---|---|---|
| Kicker / layer number | 0.75rem | UI sans | 500 | Small caps, tracked |
| Section title | 0.8125rem | UI sans | 500 | Small caps, tracked |
| Editorial statement | 1.625–2rem | Editorial serif | 400 | Line-height ~1.4 |
| Body | 1rem | UI sans | 400 | Line-height 1.55 |
| Object type label | 0.6875rem | UI sans | 500 | Small caps, muted |
| Object title | 1.125rem | UI sans | 500 | |
| Metadata | 0.8125rem | UI sans | 400 | Muted |
| Index nav | 0.8125rem | UI sans | 400 | |

Do not load webfonts. Do not use display or decorative faces. Editorial serif is for statements only.

---

## Grid

12-column desktop grid. The grid itself is not drawn.

- Desktop: content in columns 2–11 of a wide canvas; statements may span 8–10 columns; object pairs sit side by side.
- Tablet: same hierarchy, fewer simultaneous columns.
- Mobile: single column, stronger vertical rhythm. Recompose; do not shrink the desktop layout.

Asymmetry is allowed. Randomness is not.

---

## Components

Each component must have a cognitive purpose.

| Component | Class | Cognitive purpose |
|---|---|---|
| Index nav | `.index-nav` | Book index: where am I, where can I go. Must not dominate. |
| Section header | `.section-header` | Layer label + one conceptual sentence |
| Knowledge object | `.object--knowledge` | A stored record (source, note, observation) |
| Concept object | `.object--concept` | A named idea, short definition, related count |
| Question object | `.object--question` | An unfinished thought currently alive |
| Project object | `.object--project` | Knowledge becoming work |
| Metadata row | `.meta` | Date, source, status — secondary layer |
| Relation line | `.relations` | Text links (`A · B · C`), not a graph |

Object anatomy:

```text
TYPE
Title
Short description
metadata
related: A · B · C   (collapsed until asked)
```

Borders over shadows. Small radius. Generous internal padding. Related lists use `<details>` first.

---

## Homepage narrative

Single scrolling page. Index jumps to section ids. Do not open on a dashboard.

| Layer | Id | Role |
|---|---|---|
| 01 Problem | `#problem` | Information is abundant; interfaces got noisier |
| 02 Response | `#response` | Therefore the interface should get quieter |
| 03 Philosophy | `#philosophy` | AI-era MUJI — less spectacle, more agency |
| 04 System | `#system` | Capture → Organize → Connect → Think → Distill → Publish |
| 05 Knowledge | `#knowledge` | What is currently being observed |
| 06 Thinking | `#thinking` | What questions are currently alive |
| 07 Projects | `#projects` | What is being built |
| 08 Observatory | `#observatory` | What signals are entering the system |
| 09 Person | `#person` | Who is behind this system |

Philosophical prose lives in HTML so the essay remains readable without JavaScript. Knowledge objects, questions, projects, and signals are rendered from [`frontend/content/homepage.json`](../frontend/content/homepage.json). If the JSON changes, the visible objects must change.

Copy tone: observe, connect, distill, question, understand, build, reflect. Never marketing language (revolutionary, powerful AI, next-generation).

Use real vault-derived records. Do not invent busy filler, fake metrics, or example projects that do not exist (no “ECG Stimulator”).

---

## Anti-patterns

Do not add:

- KPI tiles, charts, or fake statistics
- AI chat windows, avatars, or glowing assistants
- Gradients, glassmorphism, particle backgrounds, animated networks
- Heavy shadows, large rounded cards, badge clutter, decorative icon sets
- A giant knowledge graph
- Secondary pages, API wiring, or Quartz restyling in this milestone

---

## Preview

```bash
cd frontend && python -m http.server 4173
```

Open `http://localhost:4173`. `file://` cannot fetch `homepage.json`.
