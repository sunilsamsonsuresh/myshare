import clsx from 'clsx'
import { motion } from 'framer-motion'
import {
  forwardRef,
  useId,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from 'react'
import { useCountUp } from '../../lib/hooks'
import { formatMoney, toneOf } from '../../lib/money'
import { spring } from '../../lib/motion'
import { ChevronRight } from './icons'


// ---------------------------------------------------------------- Button
type ButtonVariant = 'primary' | 'secondary' | 'plain' | 'destructive' | 'tinted'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  icon?: ReactNode
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', size = 'md', loading, icon, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={clsx(
        'inline-flex select-none items-center justify-center gap-2 font-semibold transition-[transform,background-color,opacity] duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-45 disabled:active:scale-100',
        size === 'sm' && 'h-8 rounded-full px-3.5 text-[15px]',
        size === 'md' && 'h-11 rounded-[14px] px-5 text-[17px]',
        size === 'lg' && 'h-[52px] rounded-2xl px-6 text-[17px]',
        variant === 'primary' && 'bg-accent text-white hover:brightness-110',
        variant === 'secondary' && 'bg-fill text-label hover:bg-fill-strong',
        variant === 'tinted' && 'bg-accent-soft text-accent hover:brightness-105',
        variant === 'plain' && 'bg-transparent text-accent hover:bg-fill',
        variant === 'destructive' && 'bg-negative-soft text-negative hover:brightness-105',
        className,
      )}
      {...rest}
    >
      {loading ? <Spinner small /> : icon}
      {children}
    </button>
  )
})

export function IconButton({
  label,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      aria-label={label}
      title={label}
      className={clsx(
        'inline-flex h-9 w-9 items-center justify-center rounded-full bg-fill text-label-2 transition active:scale-95 hover:bg-fill-strong hover:text-label',
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  )
}

export function Spinner({ small }: { small?: boolean }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={clsx(
        'inline-block animate-spin rounded-full border-2 border-current border-r-transparent opacity-70',
        small ? 'h-4 w-4' : 'h-6 w-6',
      )}
    />
  )
}

// ---------------------------------------------------------------- Card / grouped inset list
export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={clsx('rounded-[var(--radius-card)] bg-surface shadow-1', className)}>{children}</div>
}

/** iOS "inset grouped" section: optional header, rounded list, optional footer. */
export function Section({
  title,
  action,
  footer,
  children,
  className,
}: {
  title?: ReactNode
  action?: ReactNode
  footer?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={clsx('mb-8', className)}>
      {(title || action) && (
        <div className="mb-1.5 flex items-end justify-between px-4">
          {title && <h2 className="text-[13px] font-medium uppercase tracking-wide text-label-2">{title}</h2>}
          {action}
        </div>
      )}
      <div className="overflow-hidden rounded-[var(--radius-card)] bg-surface shadow-1">{children}</div>
      {footer && <p className="mt-1.5 px-4 text-[13px] text-label-2">{footer}</p>}
    </section>
  )
}

interface RowProps {
  leading?: ReactNode
  title: ReactNode
  subtitle?: ReactNode
  trailing?: ReactNode
  onClick?: () => void
  href?: string
  chevron?: boolean
  as?: 'div' | 'li'
}

/** One row in a grouped list, with a hairline separator inset past the leading icon. */
export function Row({ leading, title, subtitle, trailing, onClick, chevron, as = 'div' }: RowProps) {
  const Tag = onClick ? 'button' : as
  return (
    <Tag
      onClick={onClick}
      className={clsx(
        'group relative flex w-full items-center gap-3 px-4 py-3 text-left',
        onClick && 'transition-colors hover:bg-fill/60 active:bg-fill',
      )}
    >
      {leading && <div className="shrink-0">{leading}</div>}
      <div className="min-w-0 flex-1">
        <div className="truncate text-[17px]">{title}</div>
        {subtitle && <div className="truncate text-[14px] text-label-2">{subtitle}</div>}
      </div>
      {trailing && <div className="shrink-0 text-right">{trailing}</div>}
      {(chevron ?? !!onClick) && <ChevronRight className="shrink-0 text-label-3" />}
      <span
        aria-hidden
        className="pointer-events-none absolute bottom-0 right-0 h-px bg-separator group-last:hidden"
        style={{ left: leading ? 64 : 16, transform: 'scaleY(0.5)' }}
      />
    </Tag>
  )
}

// ---------------------------------------------------------------- Avatar
const AVATAR_HUES = [211, 145, 28, 280, 340, 190, 50, 255]

export function Avatar({ name, size = 40 }: { name: string; size?: number }) {
  const initials = name
    .split(/\s+/)
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
  const hue = AVATAR_HUES[[...name].reduce((a, c) => a + c.charCodeAt(0), 0) % AVATAR_HUES.length]
  return (
    <span
      aria-hidden
      className="inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.38,
        background: `linear-gradient(160deg, hsl(${hue} 70% 62%), hsl(${hue} 65% 46%))`,
      }}
    >
      {initials}
    </span>
  )
}

export function EmojiTile({ emoji, size = 40 }: { emoji: string; size?: number }) {
  return (
    <span
      aria-hidden
      className="inline-flex shrink-0 items-center justify-center rounded-[12px] bg-fill"
      style={{ width: size, height: size, fontSize: size * 0.5 }}
    >
      {emoji}
    </span>
  )
}

// ---------------------------------------------------------------- Money
/** A balance, colored by meaning: green = owed to you, red = you owe. Counts up on change. */
export function Amount({
  minor,
  currency = 'INR',
  className,
  animated = false,
  signed = false,
}: {
  minor: number
  currency?: string
  className?: string
  animated?: boolean
  signed?: boolean
}) {
  const tone = toneOf(minor)
  const shown = useCountUp(minor, animated)
  return (
    <span
      className={clsx(
        'tabular',
        tone === 'positive' && 'text-positive',
        tone === 'negative' && 'text-negative',
        tone === 'neutral' && 'text-label-2',
        className,
      )}
    >
      {signed && minor > 0 ? '+' : ''}
      {formatMoney(shown, currency, { abs: !signed })}
    </span>
  )
}

export function BalanceLabel({ minor, currency = 'INR' }: { minor: number; currency?: string }) {
  if (minor === 0) return <span className="text-[14px] text-label-2">settled up</span>
  return (
    <div className="leading-tight">
      <div className={clsx('text-[12px]', minor > 0 ? 'text-positive' : 'text-negative')}>
        {minor > 0 ? 'owes you' : 'you owe'}
      </div>
      <Amount minor={minor} currency={currency} className="text-[16px] font-semibold" />
    </div>
  )
}

// ---------------------------------------------------------------- Segmented control
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  label,
  className,
}: {
  options: { value: T; label: ReactNode }[]
  value: T
  onChange: (v: T) => void
  label: string
  className?: string
}) {
  const id = useId()
  return (
    <div role="tablist" aria-label={label} className={clsx('flex rounded-[10px] bg-fill p-0.5', className)}>
      {options.map((o) => {
        const active = o.value === value
        return (
          <button
            key={o.value}
            role="tab"
            type="button"
            aria-selected={active}
            onClick={() => onChange(o.value)}
            onKeyDown={(e) => {
              const i = options.findIndex((x) => x.value === value)
              if (e.key === 'ArrowRight') onChange(options[(i + 1) % options.length].value)
              if (e.key === 'ArrowLeft') onChange(options[(i - 1 + options.length) % options.length].value)
            }}
            className="relative flex-1 rounded-[8px] px-3 py-1.5 text-[14px] font-medium"
          >
            {active && (
              <motion.span
                layoutId={`seg-${id}`}
                transition={spring}
                className="absolute inset-0 rounded-[8px] bg-raised shadow-[0_3px_8px_rgb(0_0_0/0.12),0_1px_1px_rgb(0_0_0/0.04)]"
              />
            )}
            <span className={clsx('relative', active ? 'text-label' : 'text-label-2')}>{o.label}</span>
          </button>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------- Form fields
export const TextField = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: ReactNode; error?: string | null }
>(function TextField({ label, hint, error, className, id, ...rest }, ref) {
  const autoId = useId()
  const inputId = id ?? autoId
  return (
    <div className={className}>
      <label htmlFor={inputId} className="mb-1 block px-1 text-[13px] font-medium text-label-2">
        {label}
      </label>
      <input
        ref={ref}
        id={inputId}
        aria-invalid={!!error || undefined}
        aria-describedby={error || hint ? `${inputId}-desc` : undefined}
        className={clsx(
          'h-11 w-full rounded-[12px] bg-fill px-3.5 text-[17px] text-label placeholder:text-label-3 transition focus:bg-surface focus:outline-none focus:ring-2 focus:ring-accent',
          error && 'ring-2 ring-negative',
        )}
        {...rest}
      />
      {(error || hint) && (
        <p id={`${inputId}-desc`} className={clsx('mt-1 px-1 text-[13px]', error ? 'text-negative' : 'text-label-2')}>
          {error || hint}
        </p>
      )}
    </div>
  )
})

export function SelectField({
  label,
  children,
  className,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string }) {
  const id = useId()
  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1 block px-1 text-[13px] font-medium text-label-2">
        {label}
      </label>
      <select
        id={id}
        className="h-11 w-full appearance-none rounded-[12px] bg-fill bg-[length:14px] bg-[right_14px_center] bg-no-repeat px-3.5 pr-9 text-[17px] text-label focus:outline-none focus:ring-2 focus:ring-accent"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%238e8e93' stroke-width='2.5' stroke-linecap='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")",
        }}
        {...rest}
      >
        {children}
      </select>
    </div>
  )
}

// ---------------------------------------------------------------- Feedback
export function EmptyState({ icon, title, body, action }: { icon?: ReactNode; title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-12 text-center">
      {icon && <div className="mb-3 text-[40px]">{icon}</div>}
      <p className="text-[17px] font-semibold">{title}</p>
      {body && <p className="mt-1 max-w-xs text-[15px] text-label-2">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx('animate-pulse rounded-lg bg-fill', className)} />
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null
  return (
    <p role="alert" className="rounded-[12px] bg-negative-soft px-3.5 py-2.5 text-[15px] text-negative">
      {error instanceof Error ? error.message : String(error)}
    </p>
  )
}
