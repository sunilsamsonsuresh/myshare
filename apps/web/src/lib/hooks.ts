import { animate, useReducedMotion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'

/** Animate a number from its previous value to `target`. Static when disabled or reduced motion is on. */
export function useCountUp(target: number, enabled = true): number {
  const reduce = useReducedMotion()
  const animating = enabled && !reduce
  const [value, setValue] = useState(animating ? 0 : target)
  const from = useRef(animating ? 0 : target)
  useEffect(() => {
    if (!animating) return
    const controls = animate(from.current, target, {
      duration: 0.9,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => setValue(Math.round(v)),
    })
    from.current = target
    return () => controls.stop()
  }, [target, animating])
  return animating ? value : target
}

export function useIsMobile(breakpoint = 640): boolean {
  const query = `(max-width: ${breakpoint}px)`
  const [mobile, setMobile] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const m = window.matchMedia(query)
    const on = () => setMobile(m.matches)
    m.addEventListener?.('change', on)
    return () => m.removeEventListener?.('change', on)
  }, [query])
  return mobile
}
