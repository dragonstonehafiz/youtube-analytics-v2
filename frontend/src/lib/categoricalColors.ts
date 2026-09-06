// The app's validated 8-hue categorical theme (see TRAFFIC_SOURCE_COLORS), used here by
// rank rather than identity: search terms and videos have no fixed identity across
// renders, so slot 1 always goes to whichever item ranks first, not a specific name.
export const CATEGORICAL_COLORS = [
  '#2a78d6', // blue
  '#eb6834', // orange
  '#1baf7a', // aqua
  '#eda100', // yellow
  '#e87ba4', // magenta
  '#008300', // green
]

export const CATEGORICAL_OTHER_COLOR = '#898781'
