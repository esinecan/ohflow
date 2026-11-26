#!/bin/bash
status=0
show() {
	local name=$1
	shift
	local out
	if out=$("$@" 2>&1 | head -n 1) && [ -n "$out" ]; then
		printf '%-30s %s\n' "$name" "$out"
	else
		printf '%-30s MISSING %s\n' "$name" "$out"
		status=1
	fi
}
repo() {
	local dir=$1
	local version
	version=$(node -p "require('$dir/package.json').version" 2>/dev/null || echo "-")
	echo "$version $(git -C "$dir" rev-parse --short=12 HEAD)"
}
npm_version() {
	node -p "require('/usr/local/lib/node_modules/$1/package.json').version"
}
show git git --version
show gh gh --version
show ripgrep rg --version
show jq jq --version
show uv uv --version
show python3 python3 --version
show node node --version
show pnpm pnpm --version
show pandoc pandoc --version
show ffmpeg ffmpeg -version
show sqlite3 sqlite3 --version
show curl curl --version
show pip pip --version
show pdftotext bash -c 'pdftotext -v 2>&1 | head -n 1'
show tesseract bash -c 'echo "$(tesseract --version 2>&1 | head -n 1) langs: $(tesseract --list-langs 2>/dev/null | tail -n +2 | tr "\n" " ")"'
show antiword bash -c 'command -v antiword'
show python-doc-libs python3 -c 'import pymupdf, pdfplumber, pypdf, docx, openpyxl, pptx, bs4, PIL; print("pymupdf", pymupdf.__version__, "pdfplumber", pdfplumber.__version__, "pypdf", pypdf.__version__, "openpyxl", openpyxl.__version__, "Pillow", PIL.__version__)'
show yt-dlp yt-dlp --version
show computerd bash -c 'test -x /usr/local/bin/computerd && sha256sum /usr/local/bin/computerd | cut -c1-12'
show pi pi --version
show codex codex --version
show claude claude --version
if [ -d /opt/agent-skills/.git ]; then show skills git -C /opt/agent-skills rev-parse --short=12 HEAD; fi
for dir in /opt/mcp/*/; do
	[ -d "$dir" ] && show "$(basename "$dir")" repo "${dir%/}"
done
show sequential-thinking npm_version @modelcontextprotocol/server-sequential-thinking
show brave-search npm_version @brave/brave-search-mcp-server
show playwright-mcp npm_version @playwright/mcp
show chromium bash -c 'ls -d /opt/ms-playwright/chromium-* | head -n 1 | xargs -n 1 basename'
show harness-daemon bash -c 'test -f /opt/harness/ready && sha256sum /opt/harness/daemon.mjs | cut -c1-16'
exit $status
