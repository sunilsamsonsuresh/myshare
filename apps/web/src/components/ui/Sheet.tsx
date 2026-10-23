import clsx from 'clsx'
import { AnimatePresence, motion, useDragControls, useReducedMotion, type PanInfo } from 'framer-motion'
import { useEffect, useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { CloseIcon } from './icons'
import { useIsMobile } from '../../lib/hooks'
import { softSpring, spring } from '../../lib/motion'
import { IconButton } from './primitives'

// Open sheets, innermost last: Esc closes only the topmost one.
const openStack: symbol[] = []

const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select,textarea,[tabindex]:not([tabindex="-1"])'

interface SheetProps {
  open: boolean
  onClose: () => void
  title: ReactNode
  children: ReactNode
  /** desktop placement: centered dialog or a panel docked to the right */
  side?: 'center' | 'right'
  /** modal sheets dim and block the page; non-modal ones (the chat) leave it usable */
  modal?: boolean
  headerExtra?: ReactNode
  footer?: ReactNode
  widthClass?: string
  initialFocus?: 'first' | 'none'
}

/**
 * Apple-style sheet. Mobile: bottom sheet you can drag down to dismiss (from the grabber/header).
 * Desktop: a centered dialog or a side panel. Esc closes; focus moves in and is restored on close.
 */
export function Sheet({
  open,
  onClose,
  title,
  children,
  side = 'center',
  modal = true,
  headerExtra,
  footer,
  widthClass,
  initialFocus = 'first',
}: SheetProps) {
  const mobile = useIsMobile()
  const reduce = useReducedMotion()
  const drag = useDragControls()
  const panel = useRef<HTMLDivElement>(null)
  const titleId = useId()

  useEffect(() => {
    if (!open) return
    const me = Symbol('sheet')
    openStack.push(me)
    const previous = document.activeElement as HTMLElement | null
    const t = setTimeout(() => {
      if (initialFocus === 'first') panel.current?.querySelector<HTMLElement>(`main ${FOCUSABLE}`)?.focus()
      else panel.current?.focus()
    }, 50)
    const onKey = (e: KeyboardEvent) => {
      if (openStack[openStack.length - 1] !== me) return
      if (e.key === 'Escape') onClose()
      if (e.key === 'Tab' && modal && panel.current) {
        // Keep keyboard focus inside a modal sheet.
        const items = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)]
        if (!items.length) return
        const first = items[0]
        const last = items[items.length - 1]
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
    document.addEventListener('keydown', onKey)
    if (modal) document.body.style.overflow = 'hidden'
    return () => {
      openStack.splice(openStack.indexOf(me), 1)
      clearTimeout(t)
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
      previous?.focus?.()
    }
  }, [open, onClose, modal, initialFocus])

  const onDragEnd = (_: unknown, info: PanInfo) => {
    if (info.offset.y > 120 || info.velocity.y > 600) onClose()
  }

  const variants = mobile
    ? { hidden: { y: '100%' }, shown: { y: 0 } }
    : side === 'right'
      ? { hidden: { x: '105%' }, shown: { x: 0 } }
      : { hidden: { opacity: 0, scale: 0.95, y: 12 }, shown: { opacity: 1, scale: 1, y: 0 } }

  return createPortal(
    <AnimatePresence>
      {open && (
        <div className={clsx('fixed inset-0 z-50', !modal && 'pointer-events-none')}>
          {(modal || mobile) && (
            <motion.div
              className="pointer-events-auto absolute inset-0 bg-black/35 dark:bg-black/55"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: reduce ? 0 : 0.2 }}
              onClick={onClose}
              aria-hidden
            />
          )}
          <motion.div
            ref={panel}
            role="dialog"
            aria-modal={modal || mobile}
            aria-labelledby={titleId}
            tabIndex={-1}
            variants={variants}
            initial="hidden"
            animate="shown"
            exit="hidden"
            transition={reduce ? { duration: 0 } : mobile || side === 'right' ? softSpring : spring}
            drag={mobile ? 'y' : false}
            dragControls={drag}
            dragListener={false}
            dragConstraints={{ top: 0, bottom: 0 }}
            dragElastic={{ top: 0, bottom: 0.7 }}
            onDragEnd={onDragEnd}
            className={clsx(
              'pointer-events-auto absolute flex flex-col overflow-hidden bg-bg shadow-3 outline-none',
              mobile
                ? 'inset-x-0 bottom-0 max-h-[92dvh] rounded-t-[var(--radius-sheet)]'
                : side === 'right'
                  ? clsx('bottom-3 right-3 top-3 rounded-[var(--radius-sheet)] border border-[var(--material-border)]', widthClass ?? 'w-[420px]')
                  : clsx('left-1/2 top-1/2 max-h-[86vh] -translate-x-1/2 -translate-y-1/2 rounded-[var(--radius-sheet)]', widthClass ?? 'w-[min(560px,calc(100vw-32px))]'),
            )}
          >
            <header
              className="material hairline-b relative z-10 shrink-0 touch-none px-4 pb-3 pt-2"
              onPointerDown={(e) => mobile && drag.start(e)}
            >
              {mobile && <div aria-hidden className="mx-auto mb-2 h-[5px] w-9 rounded-full bg-label-3/60" />}
              <div className="flex items-center gap-2">
                <h2 id={titleId} className="min-w-0 flex-1 truncate text-[17px] font-semibold">
                  {title}
                </h2>
                {headerExtra}
                <IconButton label="Close" onClick={onClose} className="h-8 w-8">
                  <CloseIcon size={16} />
                </IconButton>
              </div>
            </header>
            <main className="min-h-0 flex-1 overflow-y-auto overscroll-contain">{children}</main>
            {footer && <footer className="material hairline-t shrink-0 p-3 pb-[max(12px,env(safe-area-inset-bottom))]">{footer}</footer>}
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  )
}
