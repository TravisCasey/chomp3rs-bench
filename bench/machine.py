"""The machine, container image, and commit that produced a result."""

import os
import socket
import subprocess
from pathlib import Path

from bench.wrapper import IMAGE


def describe():
    return {
        "hostname": socket.gethostname(),
        "cpu_model": cpu_model(),
        "kernel": os.uname().release,
        "image_id": output_of(
            ["podman", "image", "inspect", "--format", "{{.Id}}", IMAGE]
        ),
        "repository_commit": repository_commit(),
    }


def cpu_model():
    for line in Path("/proc/cpuinfo").read_text().splitlines():
        if line.startswith("model name"):
            return line.split(":", 1)[1].strip()


def repository_commit():
    commit = output_of(["git", "rev-parse", "HEAD"])
    if output_of(["git", "status", "--porcelain", "--untracked-files=no"]):
        return f"{commit}-dirty"
    return commit


def output_of(command):
    return subprocess.run(command, capture_output=True, text=True).stdout.strip()
