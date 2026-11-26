import { readFileSync } from "node:fs";
import { join } from "node:path";
import { boxFiles, recipe } from "../snapshot/recipe.mjs";
import { operatorDefine, WORKER_DIR } from "./settings.mjs";

const snapshotDir = join(WORKER_DIR, "snapshot");

export function recipeFiles(settings) {
	const read = (name) => readFileSync(join(snapshotDir, name), "utf8").replace(/\r\n/g, "\n");
	const files = {
		agents: read("AGENTS.md"),
		versions: read("box-versions.sh"),
		chromium: read("box-chromium.sh"),
		gateway: read("box/mcp-gateway.mjs"),
		servers: read("box/mcp-servers.json"),
		boot: read("box/harness-boot.mjs"),
		skills: read("box/box-skills.mjs"),
	};
	return boxFiles(files, operatorDefine(settings));
}

export function recipeSteps(settings) {
	return recipe(recipeFiles(settings), settings.snapshot, settings.git_identity);
}
