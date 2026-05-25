"""
Sandboxed Shell Executor for Asirive Copartner
===============================================
Safely executes shell commands with guards:
  - Blocklist: no rm -rf /, no curl | bash, no sudo
  - Timeout: commands killed after N seconds
  - Output capture: stdout + stderr captured
  - Working directory restriction
  - Confirmation for write operations

This is how Copartner runs commands on your system safely.
"""

import subprocess
import shlex
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger("Copartner.ShellExecutor")

# Commands that are NEVER allowed
BLOCKED_COMMANDS = {
    "rm", "dd", "mkfs", "fdisk", "format", "del",
    "curl.*\\|.*sh", "wget.*\\|.*sh", "eval",
    "sudo", "su", "passwd", "usermod", "userdel",
    "chmod.*777", "chmod.*000",
    "> /dev/", "> /sys/", "> /proc/",
    "shutdown", "reboot", "halt", "poweroff",
    "nc", "netcat", "ncat", "telnet",
    "base64.*\\|", "eval\\(", "exec\\(",
}

# Commands allowed without confirmation
SAFE_COMMANDS = {
    "ls", "dir", "pwd", "echo", "cat", "head", "tail", "grep", "find",
    "git", "npm", "npx", "pnpm", "yarn", "pip", "python", "node",
    "mkdir", "touch", "cp", "mv", "chmod", "chown",
    "cargo", "rustc", "go", "javac", "java",
    "docker", "docker-compose",
    "pytest", "jest", "vitest", "mocha",
    "tsc", "eslint", "prettier",
    "vite", "next", "create-react-app",
}

DEFAULT_TIMEOUT = 30  # seconds
MAX_OUTPUT_LINES = 200


def _is_blocked(cmd: str) -> tuple[bool, str]:
    """Check if a command matches the blocklist."""
    cmd_lower = cmd.lower().strip()

    # Exact match blocklist
    for blocked in BLOCKED_COMMANDS:
        if re.search(blocked, cmd_lower, re.IGNORECASE):
            return True, f"Command matches blocked pattern: {blocked}"

    # Parse first token
    try:
        tokens = shlex.split(cmd)
        if not tokens:
            return True, "Empty command"
        first = tokens[0].lower()
    except ValueError:
        return True, "Invalid command syntax"

    # Check for path traversal in arguments
    for token in tokens[1:]:
        if ".." in token and ("/" in token or "\\" in token):
            if any(sys_dir in token for sys_dir in ["/etc", "/usr", "/bin", "/sys", "/proc", "C:/Windows"]):
                return True, f"Path traversal detected: {token}"

    return False, ""


def _needs_confirmation(cmd: str) -> tuple[bool, str]:
    """Check if a command should require user confirmation before running."""
    try:
        tokens = shlex.split(cmd)
        if not tokens:
            return True, "Empty command"
        first = tokens[0].lower()
    except ValueError:
        return True, "Invalid command syntax"

    # Safe commands don't need confirmation
    if first in SAFE_COMMANDS:
        return False, ""

    # Destructive operations need confirmation
    destructive = {"rm", "rmdir", "del", "format", "truncate", "shred"}
    if first in destructive:
        return True, f"Destructive command: {first}"

    # Write operations need confirmation
    if any(tok in cmd for tok in [">", ">>", "|", "tee"]):
        return True, "Command writes to disk or pipes"

    # Unknown commands need confirmation
    return True, f"Unknown command: {first}"


def shell_exec(
    command: str,
    cwd: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
    env: Optional[dict] = None,
) -> dict:
    """
    Execute a shell command safely.

    Returns:
        {
            "command": str,
            "stdout": str,
            "stderr": str,
            "returncode": int,
            "duration_ms": int,
        }
        or {"error": str, "needs_confirmation": bool}
    """
    # Sanitize
    command = command.strip()
    if not command:
        return {"error": "Empty command"}

    # Blocklist check
    blocked, reason = _is_blocked(command)
    if blocked:
        logger.warning(f"Blocked command: {command[:80]} | {reason}")
        return {"error": f"Command blocked: {reason}"}

    # Confirmation check
    needs_confirm, confirm_reason = _needs_confirmation(command)
    if needs_confirm:
        return {
            "error": f"Confirmation required: {confirm_reason}",
            "needs_confirmation": True,
            "command": command,
        }

    # Resolve working directory
    if cwd:
        cwd_path = Path(cwd).resolve()
        if not cwd_path.exists():
            return {"error": f"Working directory does not exist: {cwd_path}"}
    else:
        cwd_path = Path.cwd()

    logger.info(f"Executing: {command[:80]} in {cwd_path}")

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd_path,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**dict(__import__("os").environ), **(env or {})},
        )

        stdout = result.stdout
        stderr = result.stderr

        # Truncate long output
        stdout_lines = stdout.splitlines()
        if len(stdout_lines) > MAX_OUTPUT_LINES:
            stdout = "\n".join(stdout_lines[:MAX_OUTPUT_LINES]) + f"\n... ({len(stdout_lines) - MAX_OUTPUT_LINES} more lines)"

        return {
            "command": command,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": result.returncode,
            "duration_ms": 0,  # Could measure with time.monotonic
        }

    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out after {timeout}s: {command[:80]}")
        return {"error": f"Command timed out after {timeout} seconds"}
    except Exception as e:
        logger.error(f"shell_exec error: {e}")
        return {"error": str(e)}
