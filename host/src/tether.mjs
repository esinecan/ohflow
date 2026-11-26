export const TETHER_EXIT = 70;

export function tether({ intervalMs = 2000, onLost = () => process.exit(TETHER_EXIT) } = {}) {
	let gone = false;
	const lost = () => {
		if (gone) return;
		gone = true;
		onLost();
	};
	process.stdout.on("error", lost);
	process.stderr.on("error", lost);
	if (!intervalMs) return () => {};
	const timer = setInterval(() => {
		process.stderr.write(".", (error) => {
			if (error) lost();
		});
	}, intervalMs);
	timer.unref();
	return () => clearInterval(timer);
}
