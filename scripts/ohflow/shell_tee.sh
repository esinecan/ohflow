#!/bin/sh
# ohflow: the CLAUDE_CODE_SHELL_PREFIX wrapper of the claude harness executor.
#
# Claude runs `bash -c "<this file> '<whole shell line>'"`, so the line arrives
# as one argument and must run under bash (it uses shopt). Claude puts more than
# the Bash tool through the prefix: every stdio MCP server and every hook
# command too (measured 2026-10-10, claude 2.1.295). Those keep their own
# stdout and stderr, so only a Bash tool line is copied. A Bash tool line is
# Claude's wrapped form `... && eval '<cmd>' < /dev/null && pwd -P >| <file>`.
#
# For a Bash tool line the wrapper copies the output, stderr merged as Claude
# itself merges it, into $OHFLOW_TOOL_OUTPUT_DIR while it runs, and passes the
# output and the exit code through unchanged. It prints nothing of its own:
# Claude would see it. Details: docs/history/silent-command-liveness.md.
d="$OHFLOW_TOOL_OUTPUT_DIR"
case "$1" in
  *"eval "*"< /dev/null"*"pwd -P >|"*) ;;
  *) exec bash -c "$1" ;;
esac
if [ -z "$d" ] || ! mkdir -p "$d" 2>/dev/null; then
  exec bash -c "$1"
fi
id="sh-$(date +%s%N 2>/dev/null)-$$"
printf '%s' "$1" > "$d/$id.cmd" 2>/dev/null
printf '{"event":"start","id":"%s","tool":"Bash","at":%s,"file":"%s.log"}\n' \
  "$id" "$(date +%s.%N)" "$id" >> "$d/shell-index.jsonl" 2>/dev/null
rcf="$d/$id.rc"
{ bash -c "$1" 2>&1; echo $? > "$rcf"; } | tee -a "$d/$id.log"
rc=$(cat "$rcf" 2>/dev/null)
rm -f "$rcf" 2>/dev/null
[ -n "$rc" ] || rc=1
printf '{"event":"end","id":"%s","at":%s,"exit":%s}\n' \
  "$id" "$(date +%s.%N)" "$rc" >> "$d/shell-index.jsonl" 2>/dev/null
exit "$rc"
