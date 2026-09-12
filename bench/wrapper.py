"""One measured run of one tool: a container, a timeout and `/usr/bin/time -v`.

`run_measured` starts a container from the benchmark image with the directories
the run needs mounted into it, runs `timeout -s KILL <seconds> /usr/bin/time -v
<argv>` inside it under a cgroup memory cap, and returns what the run cost and
how it ended. Every run is a container; there is no host mode. The container is
named rather than removed on exit, so that the memory kill and the exit code
can be read back from it, and is removed once they have been.

The classification:

- `true` ends as `finished`, exit code 0, wall under a second.
- `sleep 30` under a two second timeout ends as `timeout`, exit code 137, wall
  about two seconds. `timeout` kills `time` itself, so there is no `time`
  block to read: the wall time is the wrapper's own clock and the user time,
  system time and peak resident set size are absent.
- `tools-python -c "bytearray(3 * 10**9)"` under a 512 MB cap ends as
  `out_of_memory`: the container is reported as killed for memory, and `time`
  reports the kill by signal 9 with a peak resident set size at the cap.
- any other nonzero exit ends as `error`.
"""

import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

IMAGE = "localhost/chomp3rs-bench:latest"
TIME_BLOCK_MARKERS = ("Command being timed:", "Command terminated by signal")
WALL_MARKER = "Tool wall nanoseconds:"
CLOCK_SCRIPT = (
    "start=$(date +%s%N); "
    '"$@"; '
    "status=$?; "
    "end=$(date +%s%N); "
    f'echo "{WALL_MARKER} $((end - start))" >&2; '
    "exit $status"
)


@dataclass
class Measurement:
    status: str
    wall_seconds: float
    user_seconds: float
    system_seconds: float
    peak_rss_kilobytes: int
    exit_code: int | None
    stdout: str
    stderr: str


def run_measured(
    argv, *, timeout_seconds, memory_limit_bytes, threads, mounts, workdir
):
    """Run `argv` in a container under the cap and the timeout and measure it.

    `mounts` are `(host_path, container_path, "ro" | "rw")`.
    """
    name = f"bench-{uuid.uuid4().hex}"
    command = [
        "podman",
        "run",
        "--name",
        name,
        "--network=none",
        f"--memory={memory_limit_bytes}",
        f"--memory-swap={memory_limit_bytes}",
        f"--cpus={threads}",
        "--env",
        "OMP_NUM_THREADS=1",
        "--env",
        f"RAYON_NUM_THREADS={threads}",
    ]
    for host_path, container_path, mode in mounts:
        command += [
            "--volume",
            f"{Path(host_path).resolve()}:{container_path}:{mode}",
        ]
    command += ["--workdir", workdir, IMAGE]
    command += ["timeout", "-s", "KILL", str(timeout_seconds), "/usr/bin/time", "-v"]
    command += ["sh", "-c", CLOCK_SCRIPT, "sh"]
    command += argv

    started = time.monotonic()
    completed = subprocess.run(command, capture_output=True, text=True)
    wrapper_seconds = time.monotonic() - started
    inspected = subprocess.run(
        [
            "podman",
            "inspect",
            "--format",
            "{{.State.OOMKilled}} {{.State.ExitCode}}",
            name,
        ],
        capture_output=True,
        text=True,
    )
    subprocess.run(["podman", "rm", name], capture_output=True, text=True)

    memory_killed_text, exit_code_text = inspected.stdout.split()
    memory_killed = memory_killed_text == "true"
    exit_code = int(exit_code_text)
    tool_stderr, block = split_time_block(completed.stderr)
    peak_rss_kilobytes = block.get("peak_rss_kilobytes")
    wall_seconds = block.get("wall_seconds", wrapper_seconds)

    signalled = "Command terminated by signal 9" in completed.stderr
    at_the_cap = (
        peak_rss_kilobytes is not None
        and peak_rss_kilobytes * 1024 > 0.9 * memory_limit_bytes
    )
    if memory_killed or (signalled and at_the_cap):
        status = "out_of_memory"
    elif exit_code == 137 or wall_seconds > timeout_seconds:
        status = "timeout"
    elif exit_code != 0:
        status = "error"
    else:
        status = "finished"

    return Measurement(
        status=status,
        wall_seconds=wall_seconds,
        user_seconds=block.get("user_seconds"),
        system_seconds=block.get("system_seconds"),
        peak_rss_kilobytes=peak_rss_kilobytes,
        exit_code=exit_code,
        stdout=completed.stdout,
        stderr=tool_stderr,
    )


def split_time_block(stderr):
    """Split the tool's own stderr from the clock line the shell printed and
    from what `/usr/bin/time -v` printed after it."""
    lines = stderr.splitlines()
    start = len(lines)
    for index, line in enumerate(lines):
        if line.strip().startswith(TIME_BLOCK_MARKERS):
            start = index
            break
    block = {}
    tool_lines = []
    for line in lines[:start]:
        if line.strip().startswith(WALL_MARKER):
            block["wall_seconds"] = int(line.strip().split(":")[1]) / 1e9
        else:
            tool_lines.append(line)
    tool_stderr = "\n".join(tool_lines)
    for line in lines[start:]:
        stripped = line.strip()
        if stripped.startswith("User time (seconds):"):
            block["user_seconds"] = float(stripped.split(":")[1])
        elif stripped.startswith("System time (seconds):"):
            block["system_seconds"] = float(stripped.split(":")[1])
        elif stripped.startswith("Maximum resident set size (kbytes):"):
            block["peak_rss_kilobytes"] = int(stripped.split(":")[1])
    return tool_stderr, block
