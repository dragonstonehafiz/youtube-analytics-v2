# SVG Figures

## Purpose

How to draw and update the SVG figures used by the `docs/human/` pages. Follow [`documentation-maintenance.md`](documentation-maintenance.md) for when a figure needs updating; this file covers what a figure looks like.

## Contents

- [Source of truth](#source-of-truth)
- [Structure](#structure)
- [Labels](#labels)
- [Arrows](#arrows)
- [Color](#color)
- [Legend](#legend)
- [Text around the figure](#text-around-the-figure)
- [SVG mechanics](#svg-mechanics)
- [Verification](#verification)

## Source of truth

- Derive every node and arrow from current source. Show what the code actually does, including paths that only run in some states (a request that fires while its tab is hidden), not what it should do.
- Keep the diagram format. Do not replace a figure with a table, an interactive widget or a script-driven view.

## Structure

- Organize a figure by the structure of what it shows: page → tab → sub-tab → card or component; package → module; table → table. Never organize by user action or event ("change the dates", "switch tab"); when something happens goes in a note on the node it affects.
- One figure per subject, showing all of it at once. Do not split a page into one figure per tab. When several subjects share a layout (channel, playlist and video Analytics), draw it once and mark which subject has each node with small scope badges (`C`, `P`, `V`).
- Include only real levels of the structure. Do not add grouping boxes such as "page header" or "shared by both tabs"; a node used in several places appears under each.
- One box per thing that exists. Do not merge repeated items into one box or write counts like `×2`.
- Do not add boxes for absences ("nothing sent", "uses data already loaded").
- Hierarchies read as an indented outline on the left; what each leaf uses or calls sits in a column on the right, joined to it. Graphs lay out so most arrows run one way.
- Keep figures readable at page width (about 1100 px wide at most).

## Labels

- Use the exact name the reader will find: the on-screen title for a card or button, the component, module, package or table name in code, the route a request calls. Code names are monospace.
- When a node has no on-screen title, use its component name, or its class name when it is inline markup.
- A node may carry one short muted line under its name: its role, its row type, or when it runs (`Sent: tab shown · Reloads: any filter`). A few words, no sentences.

## Arrows

- Every arrow carries a label saying what it is for (`terms arrive`, `404 checks, first year`, `playlist_id`). A legend entry such as "contains" or "imports" does not replace the label.
- In an outline, nesting shows containment; do not draw containment arrows.
- Do not color arrows by caller. Solid versus dashed is the only arrow styling, and the legend says what each means.
- Arrows and labels do not cross other labels or run through boxes.

## Color

- Color marks the kind of node (tab, card, component defined in the page file, backend layer, how a request is triggered), never its depth in a hierarchy.
- The same kind uses the same color in every figure on a page.
- A node that follows from another (a request sent once an earlier one returns) is dashed, in the color of the node it waits for.

## Legend

- List only what the reader cannot decode from the labels: node kinds that color distinguishes, arrow styles and scope badges.
- Name the meaning, not the styling: `From previous request`, not "Dashed: sent once the request above comes back".
- Scope badge entries name the subject (`channel page`, `playlist page`, `video page`), with no prefix label.
- Include only entries the figure uses.

## Text around the figure

- A figure may have a short caption naming its subject (page name and route).
- No intro paragraph restating what the figure shows or how to read it; the legend does that.
- Below the figure, at most a few one-line bullets for facts the figure cannot show (debounce delay, a request sent twice, 404 behavior). Do not repeat anything the figure already says.

## SVG mechanics

- A figure is either a standalone `.svg` in the page's `figures/` folder, embedded with `<img>`, or an inline `<svg>` in the page HTML.
- Standalone files have `<title>`, `role="img"` and `aria-label`, and their own `<style>` block with a `@media (prefers-color-scheme: dark)` block redefining every color.
- Inline diagrams use `role="img"`, `aria-labelledby` pointing at a `<title>` and a `<desc>` that lists every node and arrow in words, and the shared diagram classes in `docs/human/human-docs.css`, which already have dark-mode colors. Give each inline diagram's marker `id`s that are unique within the page.
- System font stack; monospace only for code.

## Verification

Render each changed figure (for example with headless Chrome `--screenshot` on the `.svg` file or on the page holding the inline diagram) and inspect it before finishing. Check for overlapping text, arrows crossing labels, and boxes sized to their text. Check that it still reads in both light and dark color schemes.
