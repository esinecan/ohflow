export const LAST_LOOK_LIMIT = 8000;
export const LAST_LOOK_TIMEOUT_MS = 10_000;

export const LAST_LOOK = String.raw`s1=$(head -1 /proc/stat)
c1=$(cat /sys/fs/cgroup/cpu.stat 2>/dev/null)
sleep 1
s2=$(head -1 /proc/stat)
c2=$(cat /sys/fs/cgroup/cpu.stat 2>/dev/null)
echo "box: up $(cut -d' ' -f1 /proc/uptime) s, load $(cut -d' ' -f1-3 /proc/loadavg), cores $(nproc), first process: $(tr '\0' ' ' < /proc/1/cmdline | cut -c1-80)"
host=$(hostname 2>/dev/null)
timeout 2 getent ahosts "$host" > /dev/null 2>&1
case $? in 0) lookup="answered" ;; 124) lookup="gave no answer in 2 s" ;; *) lookup="found no such name" ;; esac
named=$(grep -c -w -- "$host" /etc/hosts 2>/dev/null)
[ -n "$named" ] || named=0
echo "name lookup of the box's own hostname $lookup; the hosts file names it on $named line(s)"
printf '%s\n%s\n' "$s1" "$s2" | awk '
function shares(label, u, s, i, w, st, t) { if (t < 1) t = 1; printf "machine cpu, %s: user %d%% system %d%% idle %d%% iowait %d%% steal %d%%\n", label, 100 * u / t, 100 * s / t, 100 * i / t, 100 * w / t, 100 * st / t }
NR == 1 { for (k = 2; k <= 9; k++) a[k] = $k }
NR == 2 { for (k = 2; k <= 9; k++) { b[k] = $k; d[k] = $k - a[k]; tb += b[k]; td += d[k] }
  shares("since boot", b[2] + b[3], b[4], b[5], b[6], b[9], tb)
  shares("last 1 s", d[2] + d[3], d[4], d[5], d[6], d[9], td) }'
if [ -n "$c2" ]; then
printf '%s\n--\n%s\n' "$c1" "$c2" | awk '
BEGIN { n = 0 }
$1 == "--" { n = 1; next }
{ v[n, $1] = $2 }
END { printf "container cpu (cgroup), since boot: used %.1f s, throttled %.1f s in %d of %d periods; last 1 s: used %d ms, throttled %d ms\n", v[1, "usage_usec"] / 1e6, v[1, "throttled_usec"] / 1e6, v[1, "nr_throttled"], v[1, "nr_periods"], (v[1, "usage_usec"] - v[0, "usage_usec"]) / 1000, (v[1, "throttled_usec"] - v[0, "throttled_usec"]) / 1000 }'
else
echo "container cpu (cgroup): cpu.stat is unreadable"
fi
echo "container cpu limit (cpu.max, quota and period in usec): $(cat /sys/fs/cgroup/cpu.max 2>/dev/null || echo unreadable)"
echo "container memory: $(cat /sys/fs/cgroup/memory.current 2>/dev/null || echo unreadable) of $(cat /sys/fs/cgroup/memory.max 2>/dev/null || echo unreadable) bytes"
ps -eo pid,ppid,pgid,stat,etime,time,args -ww 2>/dev/null | cut -c1-170 | awk '
NR == 1 { head = $0; next }
$1 == 2 || $2 == 2 { kernel++; next }
$4 ~ /^Z/ { zombies++; parent[$2]++; if (zombies <= 8) dead[zombies] = $0; next }
{ live[++n] = $0; if ($4 ~ /^R/) running++; if ($4 ~ /^D/) blocked++ }
END {
  printf "processes: %d live (%d running, %d blocked in the kernel), %d zombies, %d kernel threads left out\n", n, running, blocked, zombies, kernel
  if (zombies) {
    printf "zombies (dead, and not yet collected by their parent):"
    for (p in parent) printf " %d under parent %s;", parent[p], p
    printf " the first %d:\n", zombies < 8 ? zombies : 8
    print head
    for (i = 1; i <= 8 && i <= zombies; i++) print dead[i]
  }
  print "live processes, oldest first (STAT R runs, S sleeps, D is blocked in the kernel, T is stopped):"
  print head
  for (i = 1; i <= n; i++) {
    if (n > 40 && i == 16) { printf "... %d more ...\n", n - 40; i = n - 24 }
    print live[i]
  }
}'`;

export async function lastLook(run, now = () => Date.now(), timeoutMs = LAST_LOOK_TIMEOUT_MS) {
	const at = now();
	const stop = { late: false, kill: null };
	let timer;
	const deadline = new Promise((resolve) => {
		timer = setTimeout(() => resolve(null), timeoutMs);
	});
	const looked = Promise.resolve()
		.then(() => run(["sh", "-c", LAST_LOOK], stop))
		.then((done) => ({ done }), (error) => ({ error }));
	try {
		const first = await Promise.race([looked, deadline]);
		if (first === null) {
			stop.late = true;
			endQuietly(stop.kill);
			return { at, took_ms: now() - at, error: `the last look did not answer in ${timeoutMs} ms` };
		}
		if (first.error) return { at, took_ms: now() - at, error: String(first.error?.message ?? first.error).slice(0, 400) };
		const whole = String(first.done?.text ?? "");
		return { at, took_ms: now() - at, exit: first.done?.exitCode ?? null, text: whole.slice(0, LAST_LOOK_LIMIT), truncated: whole.length > LAST_LOOK_LIMIT };
	} finally {
		clearTimeout(timer);
	}
}

function endQuietly(kill) {
	if (!kill) return;
	try {
		Promise.resolve(kill()).catch(() => {});
	} catch {}
}

export async function boxLastLook(container, env, timeoutMs = LAST_LOOK_TIMEOUT_MS) {
	try {
		if (!container?.running) return null;
	} catch (error) {
		return { at: Date.now(), took_ms: 0, error: String(error?.message ?? error).slice(0, 400) };
	}
	return lastLook(
		async (command, stop) => {
			const process = await container.exec(command, { env, stderr: "combined" });
			stop.kill = () => process.kill(9);
			if (stop.late) {
				endQuietly(stop.kill);
				return { exitCode: null, text: "" };
			}
			const output = await process.output();
			return { exitCode: output.exitCode, text: new TextDecoder().decode(output.stdout).trim() };
		},
		() => Date.now(),
		timeoutMs,
	);
}
