"""
IDE & File System Watcher for Asirive Copartner — Phase 2 Perception
======================================================================
Monitors a project directory for file changes using the watchdog library.
Each event is:
  1. Logged to BehavioralEngine (for style profile updates)
  2. Logged to data/logs/actions.jsonl (for action graph)
  3. Optionally triggers proactive suggestions via ThoughtController

This is how Copartner stays aware of what you're building without
you having to tell it anything — it watches and learns silently.
"""

import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("Copartner.IDEWatcher")

try:
    from watchdog.observers import Observer
    from watchdog.events import (
        FileSystemEventHandler,
        FileCreatedEvent,
        FileModifiedEvent,
        FileDeletedEvent,
        FileMovedEvent,
    )
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    logger.warning("watchdog not installed. Run: pip install watchdog")

# File extensions we care about — ignore build artifacts, node_modules, etc.
WATCHED_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".html", ".css", ".scss",
    ".rs", ".go", ".rb", ".java", ".cs", ".swift", ".kt",
    ".json", ".yaml", ".yml", ".toml", ".md", ".env.example",
}

IGNORED_DIRS = {
    "node_modules", ".git", "__pycache__", ".next", "dist", "build",
    "target", ".venv", "venv", ".pytest_cache", "htmlcov", ".cache",
}


class _CopartnerEventHandler(FileSystemEventHandler if WATCHDOG_AVAILABLE else object):
    """Internal watchdog event handler that routes events to Copartner systems."""

    def __init__(
        self,
        behavioral_engine=None,
        on_create: Optional[Callable[[str, str], None]] = None,
        on_modify: Optional[Callable[[str, str], None]] = None,
        on_delete: Optional[Callable[[str], None]] = None,
    ):
        if WATCHDOG_AVAILABLE:
            super().__init__()
        self.behavior  = behavioral_engine
        self.on_create = on_create
        self.on_modify = on_modify
        self.on_delete = on_delete
        self._last_modified: dict[str, float] = {}   # debounce

    def _should_watch(self, path: str) -> bool:
        """Filter out irrelevant files and directories."""
        p = Path(path)
        # Ignore hidden files
        if any(part.startswith(".") for part in p.parts[:-1]):
            return False
        # Ignore specific directories
        if any(ignored in p.parts for ignored in IGNORED_DIRS):
            return False
        # Only watch relevant extensions (or no extension = scripts)
        if p.suffix and p.suffix.lower() not in WATCHED_EXTENSIONS:
            return False
        return True

    def _debounce(self, path: str, cooldown: float = 1.5) -> bool:
        """Return True if enough time has passed since last event for this path."""
        now  = time.time()
        last = self._last_modified.get(path, 0)
        if now - last < cooldown:
            return False
        self._last_modified[path] = now
        return True

    def _read_content(self, path: str) -> str:
        """Safely read file content for style analysis."""
        try:
            return Path(path).read_text(encoding="utf-8", errors="ignore")[:8000]
        except Exception:
            return ""

    def on_created(self, event):
        if event.is_directory or not self._should_watch(event.src_path):
            return
        path = event.src_path
        logger.debug(f"[IDEWatcher] Created: {path}")
        content = self._read_content(path)
        if self.behavior:
            self.behavior.log_action("create", path)
            self.behavior.update_from_file(path, content)
        if self.on_create:
            self.on_create(path, content)

    def on_modified(self, event):
        if event.is_directory or not self._should_watch(event.src_path):
            return
        path = event.src_path
        if not self._debounce(path):
            return
        logger.debug(f"[IDEWatcher] Modified: {path}")
        content = self._read_content(path)
        if self.behavior:
            self.behavior.log_action("modify", path)
            self.behavior.update_from_file(path, content)
        if self.on_modify:
            self.on_modify(path, content)

    def on_deleted(self, event):
        if event.is_directory or not self._should_watch(event.src_path):
            return
        path = event.src_path
        logger.debug(f"[IDEWatcher] Deleted: {path}")
        if self.behavior:
            self.behavior.log_action("delete", path)
        if self.on_delete:
            self.on_delete(path)

    def on_moved(self, event):
        if event.is_directory:
            return
        logger.debug(f"[IDEWatcher] Moved: {event.src_path} → {event.dest_path}")
        if self.behavior:
            self.behavior.log_action("move", event.src_path,
                                     extra={"dest": event.dest_path})


class IDEWatcher:
    """
    Watches a project directory for file system events.

    Automatically feeds BehavioralEngine so Copartner learns your coding style
    just by observing what you create and modify — no setup needed.

    Usage:
        watcher = IDEWatcher(
            watch_path="c:/projects/my-app",
            behavioral_engine=behavior,
            on_create=lambda path, content: print(f"New file: {path}"),
        )
        watcher.start()
        # ... watcher runs in background thread ...
        watcher.stop()
    """

    def __init__(
        self,
        watch_path: str | Path,
        behavioral_engine=None,
        on_create: Optional[Callable[[str, str], None]] = None,
        on_modify: Optional[Callable[[str, str], None]] = None,
        on_delete: Optional[Callable[[str], None]] = None,
    ):
        self.watch_path = Path(watch_path)
        self._observer: Optional[object] = None
        self._handler = None

        if WATCHDOG_AVAILABLE:
            self._handler = _CopartnerEventHandler(
                behavioral_engine=behavioral_engine,
                on_create=on_create,
                on_modify=on_modify,
                on_delete=on_delete,
            )
        else:
            logger.error("watchdog not available — IDEWatcher disabled")

    def start(self):
        """Start watching the directory in a background thread."""
        if not WATCHDOG_AVAILABLE:
            return
        if not self.watch_path.exists():
            logger.warning(f"Watch path does not exist: {self.watch_path}")
            return

        self._observer = Observer()
        self._observer.schedule(self._handler, str(self.watch_path), recursive=True)
        self._observer.start()
        logger.info(f"IDEWatcher started → {self.watch_path}")

    def stop(self):
        """Stop the file system watcher."""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            logger.info("IDEWatcher stopped")

    @property
    def is_running(self) -> bool:
        return bool(self._observer and self._observer.is_alive())
