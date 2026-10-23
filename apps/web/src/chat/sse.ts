// Minimal Server-Sent Events client over fetch().
// (The browser's EventSource only supports GET and can't send an Authorization
// header; our /chat endpoint is a POST with a JSON body and a Bearer token.)

export interface SSEEvent {
  event: string
  data: Record<string, unknown>
}

/** Parse SSE text incrementally. Returns complete events and the unconsumed remainder. */
export function parseSSE(buffer: string): { events: SSEEvent[]; rest: string } {
  const events: SSEEvent[] = []
  const blocks = buffer.replace(/\r\n/g, '\n').split('\n\n')
  const rest = blocks.pop() ?? '' // last block may be incomplete
  for (const block of blocks) {
    let event = 'message'
    const data: string[] = []
    for (const line of block.split('\n')) {
      if (line.startsWith(':')) continue // comment / keep-alive
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
    }
    if (!data.length) continue
    try {
      events.push({ event, data: JSON.parse(data.join('\n')) })
    } catch {
      events.push({ event, data: { raw: data.join('\n') } })
    }
  }
  return { events, rest }
}

export async function streamSSE(
  url: string,
  init: RequestInit,
  onEvent: (e: SSEEvent) => void,
): Promise<void> {
  const res = await fetch(url, init)
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as { detail?: string }).detail ?? `Chat request failed (${res.status})`)
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    const { events, rest } = parseSSE(buffer)
    buffer = rest
    events.forEach(onEvent)
  }
  if (buffer.trim()) parseSSE(buffer + '\n\n').events.forEach(onEvent)
}
