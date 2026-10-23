import clsx from 'clsx'
import { motion, useMotionValueEvent, useReducedMotion, useScroll } from 'framer-motion'
import { useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router'
import { ChevronLeft } from './icons'

/**
 * A page with an iOS "large title" that collapses into the translucent nav bar on scroll.
 */
export function Page({
  title,
  subtitle,
  actions,
  back,
  children,
}: {
  title: string
  subtitle?: ReactNode
  actions?: ReactNode
  back?: { to: string; label: string }
  children: ReactNode
}) {
  const { scrollY } = useScroll()
  const reduce = useReducedMotion()
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  useMotionValueEvent(scrollY, 'change', (y) => setCollapsed(y > 44))

  return (
    <div>
      {/* Compact nav bar: material appears and the small title fades in once the large title scrolls away. */}
      <div
        className={clsx(
          'sticky top-0 z-30 transition-[background-color,box-shadow] duration-200',
          collapsed ? 'material hairline-b' : 'bg-transparent',
        )}
      >
        <div className="mx-auto flex h-12 max-w-3xl items-center gap-2 px-4">
          <div className="flex min-w-0 flex-1 items-center">
            {back && (
              <button
                onClick={() => navigate(back.to)}
                className="-ml-2 flex items-center gap-0.5 rounded-lg px-1 py-1 text-[17px] text-accent hover:opacity-80"
              >
                <ChevronLeft size={22} />
                <span className="truncate">{back.label}</span>
              </button>
            )}
          </div>
          <motion.div
            aria-hidden={!collapsed}
            animate={{ opacity: collapsed ? 1 : 0, y: collapsed || reduce ? 0 : 4 }}
            transition={{ duration: 0.18 }}
            className="pointer-events-none max-w-[50%] truncate text-[17px] font-semibold"
          >
            {title}
          </motion.div>
          <div className="flex flex-1 items-center justify-end gap-2">{actions}</div>
        </div>
      </div>

      <div className="mx-auto max-w-3xl px-4 pb-32">
        <header className="pb-5 pt-1">
          <h1 className="text-[34px] font-bold leading-tight tracking-[-0.02em]">{title}</h1>
          {subtitle && <div className="mt-0.5 text-[15px] text-label-2">{subtitle}</div>}
        </header>
        {children}
      </div>
    </div>
  )
}
