export function iterationLimit(value) {
	if (value == null) return { limit: null };
	if (!Number.isSafeInteger(value) || value < 1) return { error: `max_iterations must be an integer 1 or more, got ${JSON.stringify(value)}` };
	return { limit: value };
}
