import clsx from 'clsx'
import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { WarningIcon } from '../components/ui/icons'
import { ApprovalCard } from './ApprovalCard'
import type { ChatItem, Decision } from './model'
import { ToolChip } from './ToolChip'

const bubbleIn = { initial: { opacity: 0, y: 6 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.18 } }

export function Markdown({ text }: { text: string }) {
  return (
    <div className="prose-chat">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  )
}

export function ChatMessages({
  items,
  streaming,
  onDecide,
}: {
  items: ChatItem[]
  streaming: boolean
  onDecide: (approvalId: string, d: Record<string, Decision>) => void
}) {
  const lastAssistant = items.findLastIndex((x) => x.kind === 'assistant')
  return (
    <div className="space-y-3">
      {items.map((item, i) => {
        switch (item.kind) {
          case 'user':
            return (
              <motion.div key={item.id} {...bubbleIn} className="flex justify-end">
                <div className="max-w-[85%] whitespace-pre-wrap rounded-[20px] rounded-br-[6px] bg-accent px-3.5 py-2 text-[15px] text-white">
                  {item.text}
                </div>
              </motion.div>
            )
          case 'prompt':
            return (
              <motion.div key={item.id} {...bubbleIn} className="flex justify-end">
                <div className="max-w-[85%] rounded-[20px] rounded-br-[6px] bg-accent-soft px-3.5 py-2 text-[14px]">
                  <p className="mb-1 font-mono text-[12px] font-semibold text-accent">/{item.name}</p>
                  <p className="line-clamp-4 whitespace-pre-wrap text-label-2">{item.text}</p>
                </div>
              </motion.div>
            )
          case 'assistant':
            return (
              <motion.div key={item.id} {...bubbleIn} className="max-w-[92%] text-[15px] leading-relaxed">
                <Markdown text={item.text} />
                {item.streaming && i === lastAssistant && <span aria-hidden className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-accent align-middle" />}
              </motion.div>
            )
          case 'tool':
          case 'resource':
            return (
              <motion.div key={item.id} {...bubbleIn}>
                <ToolChip item={item} />
              </motion.div>
            )
          case 'approval':
            return (
              <ApprovalCard
                key={item.id}
                actions={item.actions}
                decisions={item.decisions}
                disabled={streaming}
                onDecide={(d) => onDecide(item.id, d)}
              />
            )
          case 'error':
            return (
              <div key={item.id} role="alert" className={clsx('flex items-start gap-2 rounded-[14px] bg-negative-soft px-3 py-2 text-[14px] text-negative')}>
                <WarningIcon size={16} className="mt-0.5 shrink-0" />
                {item.text}
              </div>
            )
        }
      })}
    </div>
  )
}
