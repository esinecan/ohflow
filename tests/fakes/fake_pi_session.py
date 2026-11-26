"""A fake `pi -p --mode json` that keeps a conversation by --session-id.

The message decides the reply: `remember X` stores X, `recall` returns it,
`sleep N` sleeps N seconds first, and anything else is echoed.
"""

import json
import sys
import time
from pathlib import Path

from _common import arg, emit


def main(args):
    session = Path(arg(args, "--session-dir")) / (arg(args, "--session-id") + ".json")
    message = Path(args[args.index("--") + 1].lstrip("@")).read_text(encoding="utf-8").strip()
    state = json.loads(session.read_text(encoding="utf-8")) if session.exists() else {}
    words = message.split()
    if words[:1] == ["remember"]:
        state["token"] = words[1]
        reply = "OK"
    elif words[:1] == ["recall"]:
        reply = state.get("token", "")
    elif words[:1] == ["sleep"]:
        time.sleep(float(words[1]))
        reply = f"slept {words[1]}"
    else:
        reply = f"echo: {message}"
    session.write_text(json.dumps(state), encoding="utf-8")
    emit({"type": "message_end", "message": {
        "role": "assistant", "stopReason": "stop",
        "content": [{"type": "text", "text": reply}],
        "usage": {"input": 10, "output": 2, "cost": {"total": 0.001}}}})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
