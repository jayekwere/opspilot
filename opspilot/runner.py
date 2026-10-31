"""Fixed command registry with bounded asynchronous pipe draining."""

import asyncio
import os
import shutil
import signal
from dataclasses import dataclass

COMMANDS: dict[str, tuple[str, ...]] = {
    "service": ("systemctl", "show", "sshd.service", "--property=ActiveState", "--property=SubState"),
    "kubernetes": (
        "kubectl",
        "get",
        "pods,nodes,deployments",
        "--all-namespaces",
        "-o",
        "json",
        "--request-timeout=5s",
    ),
    "pipeline": ("gh", "run", "list", "--limit", "10", "--json", "conclusion,status,name,headSha,databaseId"),
    "cloud": (
        "aws",
        "ec2",
        "describe-instance-status",
        "--include-all-instances",
        "--max-items",
        "20",
        "--cli-connect-timeout",
        "3",
        "--cli-read-timeout",
        "3",
    ),
    "logs": ("journalctl", "-p", "err", "-n", "100", "--no-pager", "-o", "cat"),
}
COMMANDS["cloud_volumes"] = (
    "aws",
    "ec2",
    "describe-volumes",
    "--max-items",
    "20",
    "--cli-connect-timeout",
    "3",
    "--cli-read-timeout",
    "3",
)
COMMANDS["cloud_groups"] = (
    "aws",
    "ec2",
    "describe-security-groups",
    "--max-items",
    "20",
    "--cli-connect-timeout",
    "3",
    "--cli-read-timeout",
    "3",
)
SAFE_PATH = "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin"


@dataclass(frozen=True)
class Output:
    code: int
    text: str
    truncated: bool


async def _execute(argv: tuple[str, ...], timeout: float = 8, limit: int = 32768) -> Output:
    """Private primitive; public callers can only select registered command keys."""
    executable = shutil.which(argv[0], path=SAFE_PATH)
    if executable is None:
        raise OSError("required executable unavailable")
    process = await asyncio.create_subprocess_exec(
        executable,
        *argv[1:],
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
        env={
            "PATH": SAFE_PATH,
            "HOME": "/nonexistent",
            "AWS_EC2_METADATA_DISABLED": "true",
            "AWS_PAGER": "",
            "LC_ALL": "C",
            **{
                key: os.environ[key]
                for key in {
                    "gh": ("GH_TOKEN", "GH_REPO"),
                    "aws": (
                        "AWS_ACCESS_KEY_ID",
                        "AWS_SECRET_ACCESS_KEY",
                        "AWS_SESSION_TOKEN",
                        "AWS_DEFAULT_REGION",
                        "AWS_REGION",
                    ),
                    "kubectl": ("KUBECONFIG",),
                }.get(argv[0], ())
                if key in os.environ
            },
        },
    )
    collected = bytearray()
    truncated = False

    async def drain() -> None:
        nonlocal truncated
        assert process.stdout is not None
        while chunk := await process.stdout.read(4096):
            room = limit - len(collected)
            collected.extend(chunk[:room])
            truncated |= len(chunk) > room

    try:
        async with asyncio.timeout(timeout):
            await asyncio.gather(drain(), process.wait())
    finally:
        # Kill descendants too, including those keeping a pipe open after exit.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()
    return Output(process.returncode or 0, collected.decode(errors="replace"), truncated)


async def command(key: str) -> Output:
    return await _execute(COMMANDS[key], limit=262144 if key == "kubernetes" else 32768)


async def job_steps(run_id: int) -> Output:
    if type(run_id) is not int or not 0 < run_id < 10**15:
        raise ValueError("invalid provider run identifier")
    return await _execute(("gh", "run", "view", str(run_id), "--json", "jobs"))
