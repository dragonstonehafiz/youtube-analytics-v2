# SVG Figures

## Purpose

How to draw and update the SVG figures used by the `docs/human/` pages. Follow [`documentation-maintenance.md`](documentation-maintenance.md) for when a figure needs updating; this file covers what the figure looks like.

## Contents

- [Source of truth](#source-of-truth)
- [Structure](#structure)
- [Labels](#labels)
- [Color](#color)
- [Legend](#legend)
- [Text around the figure](#text-around-the-figure)
- [SVG mechanics](#svg-mechanics)
- [Verification](#verification)

## Source of truth

- Derive every node from current source. Show what the code actually does, including requests that fire while their tab is hidden, not what it should do.
- Keep the diagram format. Do not replace a figure with a table, an interactive widget or a script-driven view.

## Structure

- Organize a figure by page content: page → tab → sub-tab → card → the request or data behind that card. Never organize by user action or event ("change the dates", "switch tab"); timing goes in each request's note.
- Draw one figure per page family, with every tab and sub-tab in it, so the whole page can be seen at once. Do not split it into one file per tab. When pages share a layout (channel, playlist and video Analytics), draw them once and mark scope with badges.
- Include only real hierarchy levels: the page, its tabs, sub-tabs and cards. Do not add grouping boxes such as "page header" or "shared by both tabs".
- One box per card actually rendered. Do not merge cards (four sidebar cards are four boxes, each with its own request).
- Show a request once, under the card it feeds. Do not add boxes for "nothing sent" or "uses data already loaded".
- Layout: the hierarchy is an indented outline on the left; requests sit in one column on the right, joined to their card. Keep figures readable at page width (about 1100 px wide at most).

## Labels

- Card boxes use the card's exact on-screen title; a button uses its label. When a card has no title, use its component name (`VideoStatsBar`, `PeriodSelect`), or its class name when it is inline markup (`sync-table`).
- Request boxes show the route the request calls, in monospace (`/analytics/playlists/{id}/top`, `POST /sync/trigger`), not a restatement of the card name. When the same request calls a different route per scope, keep one box and list each route on its own line with that line's badges. For pages with one scope, leave out the badges.
- Under each request, two short columns: `Sent:` on the left with what first sends it (`page open`, `tab shown`, `referrers arrive`), and `Reloads:` on the right with what re-sends it (`any filter`, `title, type, privacy`, `never`). A few words each, no sentences.
- Every arrow carries a label saying what it is for (`terms arrive`). A request that waits for another gets an arrow from that request.
- Mark which pages have a node with small `C`, `P`, `V` badges inside the box.

## Color

Color marks meaning, never depth in the hierarchy.

| Element | Style |
|---|---|
| Tab | orange |
| Card | blue |
| Page, sub-tab | neutral outline |
| Request sent when the tab is shown | purple |
| Request sent when the page opens | grey |
| Request sent by a button | green |
| Request sent once an earlier one returns | dashed, in the color of the request it waits for |

## Legend

- List only what the reader needs to decode: `Card`, the request kinds, and the scope badges.
- No legend entries for tab, sub-tab or page.
- Name the meaning, not the styling: `From previous request`, not "Dashed: sent once the request above comes back".
- Badge entries read `channel page`, `playlist page`, `video page`, with no prefix label.
- Include only entries the figure uses.

## Text around the figure

- No intro paragraph restating what the figure shows or how to read it.
- Below the figure, at most a few one-line bullets for facts the figure cannot show (debounce delay, a request sent twice, 404 behavior). Do not repeat anything the figure already says.

## SVG mechanics

- Plain standalone `.svg` in the page's `figures/` folder, with `<title>`, `role="img"` and `aria-label`.
- Styles inline in a `<style>` block, with a `@media (prefers-color-scheme: dark)` block redefining every color.
- System font stack; monospace only for code.

## Verification

Render each changed figure (for example with headless Chrome `--screenshot`) and inspect it before finishing. Check for overlapping text, arrows crossing labels, and boxes sized to their text. Check that it still reads in both light and dark color schemes.
