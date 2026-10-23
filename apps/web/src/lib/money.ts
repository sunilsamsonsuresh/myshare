// Money on the client: integers (minor units) everywhere, formatted only for display.

const EXPONENT: Record<string, number> = { JPY: 0 }

export const exponent = (currency: string) => EXPONENT[currency.toUpperCase()] ?? 2

const formatters = new Map<string, Intl.NumberFormat>()

function formatter(currency: string): Intl.NumberFormat {
  const key = currency.toUpperCase()
  let f = formatters.get(key)
  if (!f) {
    f = new Intl.NumberFormat(key === 'INR' ? 'en-IN' : undefined, {
      style: 'currency',
      currency: key,
      minimumFractionDigits: exponent(key),
      maximumFractionDigits: exponent(key),
    })
    formatters.set(key, f)
  }
  return f
}

/** 120050 INR -> "₹1,200.50". `abs` drops the sign (color carries meaning instead). */
export function formatMoney(minor: number, currency = 'INR', { abs = false } = {}): string {
  const value = (abs ? Math.abs(minor) : minor) / 10 ** exponent(currency)
  return formatter(currency).format(value)
}

/** "1,200.50" -> 120050. Returns null when the text isn't a valid positive amount. */
export function toMinor(text: string, currency = 'INR'): number | null {
  const cleaned = text.replace(/[^\d.]/g, '')
  if (!cleaned || !/^\d*\.?\d*$/.test(cleaned)) return null
  const [whole, frac = ''] = cleaned.split('.')
  const exp = exponent(currency)
  if (frac.length > exp) return null
  const minor = Number(whole || '0') * 10 ** exp + Number(frac.padEnd(exp, '0') || '0')
  return Number.isFinite(minor) && minor > 0 ? minor : null
}

/** 120050 -> "1200.50" (for pre-filling inputs). */
export const toDecimalString = (minor: number, currency = 'INR') =>
  (minor / 10 ** exponent(currency)).toFixed(exponent(currency))

export type Tone = 'positive' | 'negative' | 'neutral'
export const toneOf = (minor: number): Tone => (minor > 0 ? 'positive' : minor < 0 ? 'negative' : 'neutral')
