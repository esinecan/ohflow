# Rules for every agent in the box

You run in the box: a Debian Linux container in Cloudflare, with bash as its shell. The box starts
from the default snapshot, so every program below is already installed. Install nothing at step
time. A step box has no general Internet access: outbound HTTPS reaches only the hosts that the MCP
servers need, through the Worker.

## What the box holds

- Programs: git, gh, ripgrep (`rg`), jq, uv, python3, pip, node, pnpm, pandoc, ffmpeg, sqlite3,
  curl and yt-dlp. `box-versions` prints the version of each one.
- Document tools: poppler (`pdftotext`, `pdftoppm`), tesseract with German and English, antiword,
  and the Python libraries pymupdf, pdfplumber, pypdf, python-docx, openpyxl, python-pptx,
  beautifulsoup4 and Pillow in the system Python.
- Agent CLIs: `pi`, `codex` and `claude`.
- Skills: `/opt/agent-skills`, linked as `~/.agents/skills` and `~/.claude/skills`. In a Claude Code
  or Codex step that names skills, it holds those skills at the commit that
  `/etc/agent-box/skills.json` records. In any other step it holds the skills repo that the
  operator's snapshot settings name, or nothing.
- MCP server programs: sequential-thinking, brave-search and Playwright MCP (`@playwright/mcp`) as
  global npm packages, and each repo that the operator's snapshot settings clone, in
  `/opt/mcp/<name>`. Playwright MCP drives headless Chromium from `/opt/ms-playwright`, and
  `box-chromium` checks that Chromium renders.
- Your work: the step's repository is under `/workspace`.

The MCP gateway `box-mcp-gateway` (`node /usr/local/lib/box/mcp-gateway.mjs`) starts with the first
MCP call of a pi step, and with the container of a Claude Code or Codex step. It serves each server named in
`/etc/agent-box/mcp-servers.json` at `http://127.0.0.1:8800/mcp/<server>` (Streamable HTTP, JSON
replies) and keeps one child process per server for the life of the box.

The box holds no credential and no login. A server that needs a key gets a placeholder value in
its environment, and the Worker writes the real key into the request header on the way out.

## Files state what is true now

Git holds the history, so a file does not. In a doc, plan, README or skill, write no list of what
was left out and no dated "was X, now Y" corrections. Change the sentence that changed.

## Long-running work carries a heartbeat

A task that can run past twenty minutes writes a heartbeat to a file. Each unit of work writes one
line when it starts, naming the unit, and one line when it ends, naming its outcome and its cost.
A unit that failed twice is not tried again.
