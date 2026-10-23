/**
 * Client-side preview of a split, using the same rounding rule as the API
 * (floor each share, hand leftover units to the first participants with weight > 0).
 * The API recomputes and is the source of truth; this is only for live feedback.
 */
export function previewSplit(total: number, weights: number[]): number[] {
  const sum = weights.reduce((a, b) => a + b, 0)
  if (total <= 0 || sum <= 0) return weights.map(() => 0)
  const floors = weights.map((w) => Math.floor((total * w) / sum))
  const eligible = weights.map((w, i) => (w > 0 ? i : -1)).filter((i) => i >= 0)
  for (let k = 0; k < total - floors.reduce((a, b) => a + b, 0); k++) floors[eligible[k % eligible.length]] += 1
  return floors
}
