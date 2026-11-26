import assert from "node:assert/strict";
import test from "node:test";
import { movedPins, pinnedRepos, rewritePins } from "../scripts/pins.mjs";

const A = "a".repeat(40);
const B = "b".repeat(40);
const C = "c".repeat(40);
const TEXT = `{
	"snapshot": {
		"skills": { "repo": "alice/skills", "sha": "${A}" },
		"repos": [
			{ "repo": "alice/tool", "sha": "${B}", "build": ["npm ci"] },
			{ "repo": "alice/other", "sha": "${C}" }
		]
	}
}
`;

test("the pins are the skills repo and every snapshot repo", () => {
	assert.deepEqual(pinnedRepos(JSON.parse(TEXT).snapshot), [
		{ where: "snapshot.skills", repo: "alice/skills", sha: A },
		{ where: "snapshot.repos[0]", repo: "alice/tool", sha: B },
		{ where: "snapshot.repos[1]", repo: "alice/other", sha: C },
	]);
	assert.deepEqual(pinnedRepos(undefined), []);
});

test("a pin moves only when the head of main differs", () => {
	const pins = pinnedRepos(JSON.parse(TEXT).snapshot);
	const head = "d".repeat(40);
	const result = movedPins(pins, { "alice/skills": A, "alice/tool": head, "alice/other": C });
	assert.deepEqual(result.map((pin) => pin.moved), [false, true, false]);
	const text = rewritePins(TEXT, result);
	assert.equal(text, TEXT.replace(B, head));
	assert.deepEqual(JSON.parse(text).snapshot.repos[0], { repo: "alice/tool", sha: head, build: ["npm ci"] });
	assert.throws(() => movedPins(pins, { "alice/skills": A }), /no head of main for alice\/tool/);
});

test("a commit id that the file names twice is not rewritten", () => {
	const pins = movedPins([{ where: "snapshot.repos[0]", repo: "alice/tool", sha: B }], { "alice/tool": A });
	assert.throws(() => rewritePins(`${TEXT}${B}`, pins), /names b+ of alice\/tool 2 times/);
});
