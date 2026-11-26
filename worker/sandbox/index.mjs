export { CodemodeSandboxDurableObject as CodemodeSandbox } from "@earendil-works/pi-codemode/cloudflare";

export default {
	fetch: () => new Response("not found", { status: 404 }),
};
