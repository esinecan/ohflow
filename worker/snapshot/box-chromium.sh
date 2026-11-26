#!/bin/bash
set -euo pipefail
out=${1:-/tmp/box-chromium.png}
NODE_PATH=/usr/local/lib/node_modules/@playwright/mcp/node_modules node - "$out" <<'JS'
const { chromium } = require("playwright");
(async () => {
	const out = process.argv[2];
	const browser = await chromium.launch({ headless: true });
	const page = await browser.newPage({ viewport: { width: 320, height: 120 } });
	await page.goto("data:text/html,<h1 style='font-family:sans-serif'>box chromium</h1>");
	await page.screenshot({ path: out });
	console.log(`${browser.version()} ${await page.textContent("h1")}`);
	await browser.close();
})().catch((error) => {
	console.error(error);
	process.exit(1);
});
JS
file "$out"
