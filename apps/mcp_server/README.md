# MyShare MCP server

A thin MCP adapter over the MyShare REST API. It exposes **14 tools, 3 resources and 3 prompts**,
knows nothing about LLMs, and calls the API with the **end user's own JWT**.

```
python -m myshare_mcp --transport http --port 8001   # Streamable HTTP: http://localhost:8001/mcp
python -m myshare_mcp --transport stdio              # stdio: needs MYSHARE_USER_TOKEN in the env
```

| Env var | Meaning |
|---|---|
| `MYSHARE_API_URL` | Where the REST API lives (default `http://localhost:8000`) |
| `MYSHARE_USER_TOKEN` | **stdio only**: the user's JWT (HTTP mode reads the `Authorization` header instead, and ignores this) |
| `MCP_TRANSPORT` | Default for `--transport` (`http` or `stdio`) |

Logs always go to **stderr**. In stdio mode stdout carries the JSON-RPC stream, so writing anything else there breaks the protocol.

## Try it with the MCP Inspector (no host, no LLM)

Start the API and the MCP server (`make api` and `make mcp` in two terminals, or `make dev`), then:

1. Get a token for the demo user: `make token`
2. Launch the Inspector: `make inspector` (it runs `npx @modelcontextprotocol/inspector` and opens a browser tab)
3. In the left panel:
   - **Transport Type**: `Streamable HTTP`
   - **URL**: `http://localhost:8001/mcp`
   - **Authentication → Custom headers**: add `Authorization` = `Bearer <token from step 1>`
   - Click **Connect**
4. Explore:
   - **Tools → List Tools**: all 14 tools with their input schemas, output schemas and annotations
     (`readOnlyHint`, `destructiveHint`...). Run `get_simplified_debts` with `group_id = 1`.
   - **Resources**: read `myshare://me/summary`; under *Resource Templates*, fill
     `myshare://groups/{group_id}` with `1`.
   - **Prompts**: get `monthly_summary` with `month = 2026-09` and see the messages it produces.
   - Try `add_expense` with `dry_run = true` to see a preview, then without it to save.
   - Remove the Authorization header and reconnect. Every tool now returns *Not authenticated*.

### Scriptable: Inspector CLI mode

```bash
TOKEN=$(make -s token)
# Streamable HTTP
npx @modelcontextprotocol/inspector --cli http://localhost:8001/mcp --transport http \
  --header "Authorization: Bearer $TOKEN" --method tools/list
npx @modelcontextprotocol/inspector --cli http://localhost:8001/mcp --transport http \
  --header "Authorization: Bearer $TOKEN" --method tools/call --tool-name get_simplified_debts --tool-arg group_id=1
# stdio (the Inspector launches the server as a subprocess; MCP_TRANSPORT picks stdio)
npx @modelcontextprotocol/inspector --cli -e MCP_TRANSPORT=stdio -e MYSHARE_USER_TOKEN=$TOKEN \
  uv run python -m myshare_mcp --method tools/call --tool-name list_friends
```

## Register it in Claude Desktop

Claude Desktop launches local MCP servers over **stdio**. Edit
`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) and add the following,
using absolute paths and your own token from `make token`:

```json
{
  "mcpServers": {
    "myshare": {
      "command": "uv",
      "args": ["--directory", "/ABSOLUTE/PATH/TO/myshare", "run", "python", "-m", "myshare_mcp", "--transport", "stdio"],
      "env": {
        "MYSHARE_USER_TOKEN": "<paste token>",
        "MYSHARE_API_URL": "http://localhost:8000"
      }
    }
  }
}
```

Restart Claude Desktop with the API running. Then ask "Who owes me money in MyShare?" in Claude Desktop.
Claude will call the same tools our own host uses, which shows the server is host-agnostic. (The token
expires after `JWT_EXPIRE_MINUTES`; refresh it with `make token`.)

## Files

| File | What it shows |
|---|---|
| `myshare_mcp/server.py` | Tool/resource/prompt definitions, annotations, structured results |
| `myshare_mcp/auth.py` | Per-user token: HTTP header vs stdio env var, plus the middleware that captures headers |
| `myshare_mcp/api_client.py` | Calls the REST API as the user; turns API errors into `ToolError`s the LLM can read |
| `myshare_mcp/views.py` | Output models: money as decimal strings, compact LLM-friendly shapes |
| `myshare_mcp/__main__.py` | CLI, transport selection, stderr logging |
