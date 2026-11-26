import { watchEvents } from "@earendil-works/pi-durable";
import { PiEventWriter } from "./pi-events.mjs";

export { PiEventWriter };

export async function streamPiEvents(harness, conversation, context, writer) {
	const stream = await watchEvents(harness, conversation.id, context);
	writer.replay(stream.snapshot.entries);
	stream.start(async (events) => {
		for (const event of events) writer.event(event);
	});
	return {
		async finish() {
			await stream.stop().catch(() => {});
			const view = await conversation.context(context);
			writer.replay(view.entries, { late: true });
		},
	};
}
