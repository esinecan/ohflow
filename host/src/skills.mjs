import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { defineExtension, section } from "@earendil-works/pi-durable";

export const SKILLS_DIR = join(homedir(), ".agents", "skills");

export function frontMatter(raw) {
	const body = raw.replace(/\r\n/g, "\n");
	if (!body.startsWith("---")) return undefined;
	const end = body.indexOf("\n---", 3);
	if (end === -1) return undefined;
	const fields = {};
	for (const line of body.slice(3, end).split("\n")) {
		const match = /^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$/.exec(line);
		if (!match) continue;
		let value = match[2].trim();
		if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) value = value.slice(1, -1);
		fields[match[1]] = value;
	}
	return fields;
}

export function namedSkills(names, dir = SKILLS_DIR) {
	return names.map((name) => {
		if (!/^[A-Za-z0-9._-]+$/.test(name ?? "") || /^\.+$/.test(name)) throw new Error(`skill names must match [A-Za-z0-9._-]+ and hold a character other than a dot, got ${JSON.stringify(name)}`);
		const file = join(dir, name, "SKILL.md");
		if (!existsSync(file)) throw new Error(`skill ${name} has no ${file.replaceAll("\\", "/")} on this box`);
		const fields = frontMatter(readFileSync(file, "utf8")) ?? {};
		return { name: fields.name || name, description: (fields.description ?? "").replace(/\s+/g, " "), path: file.replaceAll("\\", "/") };
	});
}

export function skillsExtension(names, dir = SKILLS_DIR) {
	const list = [
		"Each skill is a markdown file. When a task matches a skill, open its path with read and follow it. Read the file before you rely on what it says.",
		...namedSkills(names, dir).map((skill) => `- ${skill.name}: ${skill.description}\n  read: ${skill.path}`),
	].join("\n");
	return defineExtension({ name: "skills", sections: [section("skills", () => list)] });
}
