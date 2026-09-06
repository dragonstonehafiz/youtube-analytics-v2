import './categoricalColors.css'

// The app's validated 8-hue categorical theme (see TRAFFIC_SOURCE_COLORS), used here by
// rank rather than identity: search terms and videos have no fixed identity across
// renders, so slot 1 always goes to whichever item ranks first, not a specific name.
// Actual color values live in categoricalColors.css as design tokens.
export const CATEGORICAL_SLOT_COUNT = 6

/** CSS class for the Nth-ranked categorical slot (0-indexed). Usable as both a swatch
 * `background` and an SVG `fill` — see categoricalColors.css. */
export function categoricalColorClass(rank: number): string {
  return `categorical-color-${rank}`
}
