// Shared spring presets (Apple-like: quick, lightly damped, no bounce overshoot to speak of).
export const spring = { type: 'spring', stiffness: 420, damping: 36, mass: 0.9 } as const
export const softSpring = { type: 'spring', stiffness: 260, damping: 30 } as const
