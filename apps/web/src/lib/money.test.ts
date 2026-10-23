import { formatMoney, toMinor } from './money'
import { previewSplit } from './split'

describe('money', () => {
  it('formats minor units with Indian grouping for INR', () => {
    expect(formatMoney(12345678, 'INR')).toBe('₹1,23,456.78')
    expect(formatMoney(-500, 'INR', { abs: true })).toBe('₹5.00')
  })
  it('parses human input to minor units', () => {
    expect(toMinor('1,200.5')).toBe(120050)
    expect(toMinor('₹99')).toBe(9900)
    expect(toMinor('10.005')).toBeNull()
    expect(toMinor('')).toBeNull()
  })
})

describe('previewSplit (mirrors the API rounding rule)', () => {
  it('gives leftover units to the first participants', () => {
    expect(previewSplit(1000, [1, 1, 1])).toEqual([334, 333, 333])
  })
  it('never gives a leftover unit to a zero weight', () => {
    expect(previewSplit(101, [0, 1, 1])).toEqual([0, 51, 50])
  })
  it('always sums to the total', () => {
    for (let t = 1; t < 500; t += 7) expect(previewSplit(t, [2, 1, 1, 3]).reduce((a, b) => a + b)).toBe(t)
  })
})
