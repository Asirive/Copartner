"""
Safe File Operations for Asirive Copartner
============================================
CRUD operations on the local filesystem with safety guards:
  - Path traversal prevention (no ../../etc/passwd)
  - User confirmation for destructive ops (overwrite, delete)
  - Automatic backup before overwrite
  - Size limits (no reading 10GB files)
  - Blocked directories (no touching system files)

This is how Copartner safely reads, writes, and manages files
on behalf of the user.
"""

import shutil
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("Copartner.FileOps")

# Directories that are off-limits
BLOCKED_PATHS = {
    "/", "/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64",
    "C:/Windows", "C:/Program Files", "C:/ProgramData",
    "/System", "/Volumes",
}

MAX_READ_SIZE = 10 * 1024 * 1024   # 10 MB max read
MAX_WRITE_SIZE = 5 * 1024 * 1024   # 5 MB max write
BACKUP_SUFFIX = ".copartner_backup"


def _resolve_path(path: str, base_dir: Optional[Path] = None) -> Path:
    """Resolve a path, optionally relative to a base directory."""
    p = Path(path)
    if base_dir and not p.is_absolute():
        p = base_dir / p
    return p.resolve()


def _is_safe(path: Path) -> tuple[bool, str]:
    """Check if a path is safe to operate on."""
    try:
        resolved = path.resolve()
    except (OSError, ValueError) as e:
        return False, f"Invalid path: {e}"

    # Check against blocked directories
    str_path = str(resolved).replace("\\", "/")
    for blocked in BLOCKED_PATHS:
        if str_path.startswith(blocked.replace("\\", "/")):
            return False, f"Path is in a blocked directory: {blocked}"

    return True, ""


def file_read(path: str, base_dir: Optional[Path] = None, offset: int = 0, limit: Optional[int] = None) -> dict:
    """
    Read a file safely.

    Returns:
        {"content": str, "size": int, "truncated": bool} or {"error": str}
    """
    try:
        p = _resolve_path(path, base_dir)
        safe, reason = _is_safe(p)
        if not safe:
            return {"error": reason}

        if not p.exists():
            return {"error": f"File not found: {p}"}

        if p.is_dir():
            return {"error": f"Path is a directory: {p}"}

        size = p.stat().st_size
        if size > MAX_READ_SIZE:
            return {"error": f"File too large to read ({size:,} bytes > {MAX_READ_SIZE:,} limit)"}

        content = p.read_text(encoding="utf-8", errors="replace")
        if offset or limit:
            lines = content.splitlines()
            content = "\n".join(lines[offset:offset + limit] if limit else lines[offset:])

        truncated = size > MAX_READ_SIZE
        return {
            "path": str(p),
            "content": content,
            "size": size,
            "truncated": truncated,
        }
    except Exception as e:
        logger.error(f"file_read error: {e}")
        return {"error": str(e)}


def file_write(path: str, content: str, base_dir: Optional[Path] = None, confirm_overwrite: bool = True) -> dict:
    """
    Write a file safely. Creates parent directories if needed.

    If confirm_overwrite is True and file exists, returns a confirmation request
    instead of overwriting. The caller (ToolExecutor) should handle confirmation.

    Returns:
        {"path": str, "bytes_written": int, "backed_up": str|None} or {"error": str, "needs_confirmation": bool}
    """
    try:
        p = _resolve_path(path, base_dir)
        safe, reason = _is_safe(p)
        if not safe:
            return {"error": reason}

        if len(content.encode("utf-8")) > MAX_WRITE_SIZE:
            return {"error": f"Content too large ({len(content):,} bytes > {MAX_WRITE_SIZE:,} limit)"}

        # Check for overwrite
        if p.exists() and confirm_overwrite:
            return {
                "error": f"File already exists: {p}",
                "needs_confirmation": True,
                "path": str(p),
            }

        # Backup if overwriting
        backup_path = None
        if p.exists():
            backup_path = Path(str(p) + BACKUP_SUFFIX)
            shutil.copy2(p, backup_path)
            logger.info(f"Backed up {p} → {backup_path}")

        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

        return {
            "path": str(p),
            "bytes_written": len(content.encode("utf-8")),
            "backed_up": str(backup_path) if backup_path else None,
        }
    except Exception as e:
        logger.error(f"file_write error: {e}")
        return {"error": str(e)}


def file_list(path: str, base_dir: Optional[Path] = None, recursive: bool = False) -> dict:
    """
    List files in a directory.

    Returns:
        {"path": str, "entries": [{"name": str, "type": str, "size": int}]} or {"error": str}
    """
    try:
        p = _resolve_path(path, base_dir)
        safe, reason = _is_safe(p)
        if not safe:
            return {"error": reason}

        if not p.exists():
            return {"error": f"Directory not found: {p}"}

        if not p.is_dir():
            return {"error": f"Path is not a directory: {p}"}

        entries = []
        iterator = p.rglob("*") if recursive else p.iterdir()
        for item in iterator:
            try:
                entries.append({
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else 0,
                })
            except (OSError, PermissionError):
                continue

        return {
            "path": str(p),
            "entries": entries,
        }
    except Exception as e:
        logger.error(f"file_list error: {e}")
        return {"error": str(e)}


def file_delete(path: str, base_dir: Optional[Path] = None, confirm: bool = True) -> dict:
    """
    Delete a file or empty directory.

    Returns:
        {"deleted": str, "backed_up": str|None} or {"error": str, "needs_confirmation": bool}
    """
    try:
        p = _resolve_path(path, base_dir)
        safe, reason = _is_safe(p)
        if not safe:
            return {"error": reason}

        if not p.exists():
            return {"error": f"File not found: {p}"}

        if confirm:
            return {
                "error": f"About to delete: {p}",
                "needs_confirmation": True,
                "path": str(p),
            }

        backup_path = None
        if p.is_file():
            backup_path = Path(str(p) + BACKUP_SUFFIX)
            shutil.copy2(p, backup_path)
            p.unlink()
        elif p.is_dir():
            p.rmdir()  # Only empty dirs

        return {
            "deleted": str(p),
            "backed_up": str(backup_path) if backup_path else None,
        }
    except Exception as e:
        logger.error(f"file_delete error: {e}")
        return {"error": str(e)}
