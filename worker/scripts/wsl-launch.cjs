const { spawnSync } = require("node:child_process");
const argv = JSON.parse(Buffer.from(process.argv[2], "base64").toString("utf8"));
const result = spawnSync(argv[0], argv.slice(1), { stdio: "inherit" });
process.exit(result.status ?? 1);
