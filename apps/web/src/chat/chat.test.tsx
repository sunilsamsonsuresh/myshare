import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ApprovalCard } from './ApprovalCard'
import { ChatMessages } from './ChatMessages'
import { applyEvent, emptyChat, type ApprovalAction, type ChatState } from './model'
import { parseSSE } from './sse'

const action: ApprovalAction = {
  tool_call_id: 'c1',
  tool: 'add_expense',
  title: 'Add an expense',
  args: { description: 'Dinner', amount: '3000', group_id: 1 },
  preview: 'Add "Dinner" ₹3,000.00 in "Goa Trip", paid by Sunil; split equal: Sunil ₹1,000.00, Priya ₹1,000.00, Rahul ₹1,000.00.',
  details: {
    expense: {
      split: [
        { name: 'Sunil', owes: { display: '₹1,000.00' } },
        { name: 'Priya', owes: { display: '₹1,000.00' } },
        { name: 'Rahul', owes: { display: '₹1,000.00' } },
      ],
    },
  },
  destructive: false,
}

describe('parseSSE', () => {
  it('parses complete events and keeps a partial remainder', () => {
    const { events, rest } = parseSSE('event: token\ndata: {"text":"Hi"}\n\nevent: done\ndata: {"thread_id"')
    expect(events).toEqual([{ event: 'token', data: { text: 'Hi' } }])
    expect(rest).toBe('event: done\ndata: {"thread_id"')
  })
})

describe('applyEvent (chat stream reducer)', () => {
  it('accumulates tokens, merges tool results, and tracks approval', () => {
    const events = [
      { event: 'resource_read', data: { uri: 'myshare://me/summary' } },
      { event: 'tool_call_started', data: { id: 't1', tool: 'get_balances', phase: 'call', args: {} } },
      { event: 'tool_call_result', data: { id: 't1', tool: 'get_balances', phase: 'call', status: 'ok', summary: 'You are owed ₹100.00' } },
      { event: 'token', data: { text: 'You are ' } },
      { event: 'token', data: { text: 'owed ₹100.' } },
      { event: 'approval_required', data: { actions: [action] } },
      { event: 'done', data: { awaiting_approval: true } },
    ]
    const s = events.reduce<ChatState>(applyEvent, { ...emptyChat, streaming: true })
    expect(s.items.map((i) => i.kind)).toEqual(['resource', 'tool', 'assistant', 'approval'])
    expect(s.items[1]).toMatchObject({ status: 'ok', summary: 'You are owed ₹100.00' })
    expect(s.items[2]).toMatchObject({ text: 'You are owed ₹100.', streaming: false })
    expect(s).toMatchObject({ streaming: false, awaitingApproval: true })
  })
})

describe('ChatMessages', () => {
  it('renders streamed text and a tool chip that expands to the raw MCP JSON', async () => {
    const s = [
      { event: 'tool_call_started', data: { id: 't1', tool: 'get_balances', phase: 'call', args: {} } },
      {
        event: 'tool_call_result',
        data: {
          id: 't1',
          tool: 'get_balances',
          phase: 'call',
          status: 'ok',
          request: { jsonrpc: '2.0', id: 3, method: 'tools/call', params: { name: 'get_balances', arguments: {} } },
          response: { jsonrpc: '2.0', id: 3, result: { isError: false } },
        },
      },
      { event: 'token', data: { text: '**Priya** owes you ₹800.' } },
    ].reduce<ChatState>(applyEvent, emptyChat)

    render(<ChatMessages items={s.items} streaming={false} onDecide={() => {}} />)
    expect(screen.getByText('Priya').tagName).toBe('STRONG') // markdown rendered
    const chip = screen.getByRole('button', { name: /Checked balances/ })
    expect(chip).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(chip)
    expect(chip).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(/Request \(host → server\)/)).toBeInTheDocument()
    expect(screen.getByText(/"method": "tools\/call"/)).toBeInTheDocument()
  })
})

describe('ApprovalCard', () => {
  it('shows the dry-run preview and split, and approves', async () => {
    const onDecide = vi.fn()
    render(<ApprovalCard actions={[action]} onDecide={onDecide} />)
    expect(screen.getByText(/Add "Dinner" ₹3,000.00/)).toBeInTheDocument()
    expect(screen.getAllByText('₹1,000.00')).toHaveLength(3)
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))
    expect(onDecide).toHaveBeenCalledWith({ c1: { action: 'approve' } })
  })

  it('sends feedback when the user asks for changes', async () => {
    const onDecide = vi.fn()
    render(<ApprovalCard actions={[action]} onDecide={onDecide} />)
    await userEvent.click(screen.getByRole('button', { name: 'Edit' }))
    await userEvent.type(screen.getByLabelText('What should change?'), 'make it 2500')
    await userEvent.click(screen.getByRole('button', { name: 'Send changes' }))
    expect(onDecide).toHaveBeenCalledWith({ c1: { action: 'edit', feedback: 'make it 2500' } })
  })

  it('labels destructive actions and shows the final decision', () => {
    const del = { ...action, tool: 'delete_expense', title: 'Delete an expense', destructive: true, details: null }
    const { rerender } = render(<ApprovalCard actions={[del]} onDecide={() => {}} />)
    expect(screen.getByText('Destructive')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument()
    rerender(<ApprovalCard actions={[del]} decisions={{ c1: { action: 'reject' } }} onDecide={() => {}} />)
    expect(screen.getByText('Rejected')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
  })
})
