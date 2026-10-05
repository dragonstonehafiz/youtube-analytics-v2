/** Returns [start, end] ISO dates for the rolling window ending today, starting `days` × 24h earlier. */
export function lastNDates(days: number): [string, string] {
  const today = new Date()
  const end = today.toISOString().slice(0, 10)
  const start = new Date(today.getTime() - days * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
  return [start, end]
}
