import { useQuery } from '@tanstack/react-query'
import { HOST_URL, request } from '../lib/api'

/** An MCP prompt as listed by the host's GET /mcp/prompts (straight from prompts/list). */
export interface McpPrompt {
  name: string
  title?: string
  description?: string
  arguments?: { name: string; description?: string; required?: boolean }[]
}

export const usePrompts = () =>
  useQuery({ queryKey: ['mcp', 'prompts'], queryFn: () => request<McpPrompt[]>(HOST_URL, '/mcp/prompts'), staleTime: 5 * 60_000 })
