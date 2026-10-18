# daily-news-mcp

An [MCP](https://modelcontextprotocol.io) server that exposes a daily **AI/news engine** —
fetch → curate → rewrite — as tools any MCP client (Claude Desktop, Cursor, …) can call. It runs
locally and uses **your own** credentials; nothing is sent to a hosted service.

> This package is the reusable *news engine*. It's part of a larger project (a voice/phone
> briefing agent); that live-call side is **not** included here. Full project:
> https://github.com/vinaykumar2126/Daily-AI-News

## Tools

| Tool | Credentials | What it does |
|------|-------------|--------------|
| `list_topics()` | none | the topics covered ("AI & Tech", "US Headlines", "Immigration & Visas", "Markets") |
| `get_stories(topic)` | none | today's raw source stories for a topic (RSS, Hacker News, TLDR, markets) |
| `get_briefing(topic?)` | Google Cloud / Vertex | a curated, rewritten briefing — one topic, or all |

## Install & run

```bash
uvx daily-news-mcp                 # run without installing (keyless tools)
uvx "daily-news-mcp[briefing]"     # include get_briefing (adds the Gemini/Vertex stack)
# or:
pip install daily-news-mcp
pip install "daily-news-mcp[briefing]"
```

`list_topics` and `get_stories` need no credentials or extras. `get_briefing` additionally needs
the **`briefing`** extra plus Google Cloud / Vertex AI access
(`GOOGLE_CLOUD_PROJECT` + `gcloud auth application-default login`) — it calls Gemini to curate and
rewrite. Without the extra, `get_briefing` returns a clear "install the briefing extra" message and
the keyless tools keep working.

## Use it in Claude Desktop

Add to `claude_desktop_config.json` (keys stay on your machine):

```jsonc
{
  "mcpServers": {
    "daily-news": {
      "command": "uvx",
      "args": ["daily-news-mcp"],
      "env": { "GOOGLE_CLOUD_PROJECT": "your-gcp-project" }
    }
  }
}
```

Restart Claude Desktop, then ask: *"What topics can the daily-news server cover?"*

## License

MIT
