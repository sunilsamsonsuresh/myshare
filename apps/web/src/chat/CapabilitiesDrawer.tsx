import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import type { ReactNode } from 'react'
import { ErrorNote, Skeleton } from '../components/ui/primitives'
import { Sheet } from '../components/ui/Sheet'
import { HOST_URL, request } from '../lib/api'
import { JsonBlock } from './ToolChip'

interface Inspect {
  transport: string
  server_info: { name: string; version?: string; title?: string }
  protocol_version: string
  capabilities: Record<string, unknown>
  instructions: string | null
  tools: {
    name: string
    title?: string
    description?: string
    inputSchema: unknown
    outputSchema?: unknown
    annotations?: { readOnlyHint?: boolean; destructiveHint?: boolean; idempotentHint?: boolean }
    requiresApproval: boolean
  }[]
  resources: { uri: string; name: string; title?: string; description?: string; mimeType?: string }[]
  resource_templates: { uriTemplate: string; name: string; title?: string; description?: string }[]
  prompts: { name: string; title?: string; description?: string; arguments?: { name: string; required?: boolean }[] }[]
  wire: { dir: 'send' | 'recv'; msg: Record<string, unknown> }[]
}

function Badge({ tone, children }: { tone: 'green' | 'blue' | 'red' | 'gray'; children: ReactNode }) {
  return (
    <span
      className={clsx(
        'rounded-full px-1.5 py-px text-[10.5px] font-semibold uppercase tracking-wide',
        tone === 'green' && 'bg-positive-soft text-positive',
        tone === 'blue' && 'bg-accent-soft text-accent',
        tone === 'red' && 'bg-negative-soft text-negative',
        tone === 'gray' && 'bg-fill text-label-2',
      )}
    >
      {children}
    </span>
  )
}

function Group({ title, who, children }: { title: string; who: string; children: ReactNode }) {
  return (
    <section className="mb-6">
      <div className="mb-1.5 flex items-baseline justify-between px-1">
        <h3 className="text-[13px] font-semibold uppercase tracking-wide text-label-2">{title}</h3>
        <span className="text-[12px] text-label-3">{who}</span>
      </div>
      <ul className="divide-y divide-separator overflow-hidden rounded-[16px] bg-surface shadow-1">{children}</ul>
    </section>
  )
}

/**
 * A teaching view: everything the host discovered about the MCP server, straight from
 * tools/list, resources/list, resources/templates/list and prompts/list, plus the raw
 * JSON-RPC messages (including the initialize handshake) used to fetch it.
 */
export function CapabilitiesDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const q = useQuery({
    queryKey: ['mcp', 'inspect'],
    queryFn: () => request<Inspect>(HOST_URL, '/mcp/inspect'),
    enabled: open,
    staleTime: 60_000,
  })
  const d = q.data
  return (
    <Sheet open={open} onClose={onClose} title="Connected capabilities" side="right" widthClass="w-[min(560px,calc(100vw-24px))]" initialFocus="none">
      <div className="p-4">
        {q.isLoading && <Skeleton className="h-64 rounded-[16px]" />}
        <ErrorNote error={q.error} />
        {d && (
          <>
            <div className="mb-6 rounded-[16px] bg-surface p-4 shadow-1">
              <p className="text-[17px] font-semibold">
                {d.server_info.title ?? d.server_info.name} <span className="font-normal text-label-2">v{d.server_info.version}</span>
              </p>
              <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[13px]">
                <dt className="text-label-2">Transport</dt>
                <dd className="font-mono">{d.transport === 'http' ? 'Streamable HTTP' : d.transport}</dd>
                <dt className="text-label-2">Protocol</dt>
                <dd className="font-mono">{d.protocol_version}</dd>
                <dt className="text-label-2">Capabilities</dt>
                <dd className="font-mono">{Object.keys(d.capabilities).join(', ')}</dd>
              </dl>
              {d.instructions && (
                <details className="mt-2 text-[13px]">
                  <summary className="cursor-pointer text-label-2">Server instructions</summary>
                  <p className="mt-1 whitespace-pre-wrap text-label">{d.instructions}</p>
                </details>
              )}
            </div>

            <Group title={`Tools · ${d.tools.length}`} who="model-controlled">
              {d.tools.map((t) => (
                <li key={t.name} className="px-3.5 py-2.5">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <code className="font-mono text-[14px] font-semibold">{t.name}</code>
                    {t.annotations?.readOnlyHint ? <Badge tone="green">read-only</Badge> : <Badge tone="blue">needs approval</Badge>}
                    {t.annotations?.destructiveHint && <Badge tone="red">destructive</Badge>}
                    {t.annotations?.idempotentHint && !t.annotations.readOnlyHint && <Badge tone="gray">idempotent</Badge>}
                  </div>
                  <p className="mt-0.5 line-clamp-3 text-[13px] text-label-2">{t.description}</p>
                  <details className="mt-1 text-[12px]">
                    <summary className="cursor-pointer text-accent">Schemas</summary>
                    <JsonBlock label="inputSchema" value={t.inputSchema} />
                    {t.outputSchema != null && <JsonBlock label="outputSchema" value={t.outputSchema} />}
                  </details>
                </li>
              ))}
            </Group>

            <Group title={`Resources · ${d.resources.length + d.resource_templates.length}`} who="application-controlled">
              {d.resources.map((r) => (
                <li key={r.uri} className="px-3.5 py-2.5">
                  <code className="font-mono text-[13px] font-semibold">{r.uri}</code>
                  <p className="text-[13px] text-label-2">{r.description}</p>
                </li>
              ))}
              {d.resource_templates.map((r) => (
                <li key={r.uriTemplate} className="px-3.5 py-2.5">
                  <code className="font-mono text-[13px] font-semibold">{r.uriTemplate}</code> <Badge tone="gray">template</Badge>
                  <p className="text-[13px] text-label-2">{r.description}</p>
                </li>
              ))}
            </Group>

            <Group title={`Prompts · ${d.prompts.length}`} who="user-controlled">
              {d.prompts.map((p) => (
                <li key={p.name} className="px-3.5 py-2.5">
                  <code className="font-mono text-[14px] font-semibold text-accent">/{p.name}</code>
                  {p.arguments?.length ? <span className="ml-1.5 font-mono text-[12px] text-label-2">({p.arguments.map((a) => a.name).join(', ')})</span> : null}
                  <p className="text-[13px] text-label-2">{p.description}</p>
                </li>
              ))}
            </Group>

            <Group title={`Wire · ${d.wire.length} messages`} who="raw JSON-RPC for this view">
              {d.wire.map((w, i) => (
                <li key={i} className="px-3.5 py-2">
                  <details className="text-[12px]">
                    <summary className="cursor-pointer">
                      <span className={w.dir === 'send' ? 'text-accent' : 'text-positive'}>{w.dir === 'send' ? 'host → server' : 'server → host'}</span>{' '}
                      <code className="font-mono">{String(w.msg.method ?? `result #${w.msg.id}`)}</code>
                    </summary>
                    <JsonBlock value={w.msg} />
                  </details>
                </li>
              ))}
            </Group>
          </>
        )}
      </div>
    </Sheet>
  )
}
