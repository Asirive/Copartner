"""
Behavioral Engine for Asirive Copartner
=========================================
Observes user actions (file creates, edits, terminal commands) and builds
a persistent Style Profile that Copartner injects into prompts to generate
code matching the user's exact conventions.

Inspired by Eidos Neuromodulator's σ (serotonin) concept — "what does the
user already know vs what do they need to compute?" — but implemented as a
simple action graph + heuristic style analyser, not a neural module.
"""

import json
import re
import logging
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger("Copartner.BehavioralEngine")

PROJECT_ROOT   = Path(__file__).parent.parent
ACTIONS_LOG    = PROJECT_ROOT / "data" / "logs" / "actions.jsonl"
PROFILE_FILE   = PROJECT_ROOT / "data" / "style_profile.json"


@dataclass
class StyleProfile:
    """
    The user's inferred engineering style profile.
    Updated automatically as Copartner observes file system changes.
    """
    naming_convention: str    = "unknown"   # camelCase | snake_case | PascalCase
    indent_size: int          = 4           # 2 or 4
    indent_type: str          = "spaces"    # spaces | tabs
    preferred_language: str   = "unknown"   # python | typescript | javascript | ...
    preferred_framework: str  = "unknown"   # react | next | fastapi | express | ...
    comment_style: str        = "inline"    # inline | docstring | none
    test_convention: str      = "unknown"   # pytest | jest | vitest | ...
    package_manager: str      = "unknown"   # npm | pnpm | yarn | pip | uv | ...
    observations: int         = 0           # how many file events have been analyzed

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "StyleProfile":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class BehavioralEngine:
    """
    Passively observes the user's file system changes and builds a style profile.

    Usage:
        engine = BehavioralEngine()
        engine.update_from_file("src/components/Header.tsx", content)
        prompt_addition = engine.get_profile_prompt()
    """

    def __init__(self):
        ACTIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
        self.profile = self._load_profile()
        logger.info(f"BehavioralEngine loaded. Observations: {self.profile.observations}")

    # ── Profile persistence ───────────────────────────────────────────────────

    def _load_profile(self) -> StyleProfile:
        if PROFILE_FILE.exists():
            try:
                return StyleProfile.from_dict(json.loads(PROFILE_FILE.read_text()))
            except Exception as e:
                logger.warning(f"Could not load style profile: {e}")
        return StyleProfile()

    def _save_profile(self):
        try:
            PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
            PROFILE_FILE.write_text(json.dumps(self.profile.to_dict(), indent=2))
        except Exception as e:
            logger.warning(f"Could not save style profile: {e}")

    # ── Action logging ────────────────────────────────────────────────────────

    def log_action(self, action_type: str, path: str, extra: dict | None = None):
        """
        Log a user file system action to the action log.

        action_type: "create" | "modify" | "delete" | "command"
        """
        entry = {
            "ts":   time.time(),
            "type": action_type,
            "path": path,
        }
        if extra:
            entry.update(extra)

        try:
            with open(ACTIONS_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.debug(f"Action log write failed: {e}")

    # ── Style inference ───────────────────────────────────────────────────────

    def update_from_file(self, path: str, content: str):
        """
        Analyse a file's content to infer style conventions.
        Called whenever a file is created or significantly modified.
        """
        path = path.replace("\\", "/")
        ext  = path.rsplit(".", 1)[-1].lower() if "." in path else ""

        self._infer_language(ext, path)
        self._infer_framework(path, content)
        self._infer_indent(content)
        self._infer_naming(content, ext)
        self._infer_comments(content, ext)
        self._infer_test_convention(path, content)
        self._infer_package_manager(path, content)

        self.profile.observations += 1
        self._save_profile()
        logger.debug(f"BehavioralEngine: profile updated (obs={self.profile.observations})")

    def _infer_language(self, ext: str, path: str):
        EXT_MAP = {
            "py": "python", "ts": "typescript", "tsx": "typescript",
            "js": "javascript", "jsx": "javascript", "rs": "rust",
            "go": "go", "rb": "ruby", "java": "java", "cs": "csharp",
            "cpp": "cpp", "c": "c", "swift": "swift", "kt": "kotlin",
        }
        lang = EXT_MAP.get(ext)
        if lang and self.profile.preferred_language == "unknown":
            self.profile.preferred_language = lang

    def _infer_framework(self, path: str, content: str):
        signals = {
            "react":    ["import React", "from 'react'", "jsx", "tsx"],
            "next":     ["from 'next'", "next/router", "next/image", "pages/", "app/"],
            "fastapi":  ["from fastapi", "FastAPI()", "@app.get", "@app.post"],
            "express":  ["require('express')", "from 'express'", "app.get(", "app.listen("],
            "svelte":   [".svelte", "from 'svelte'"],
            "vue":      [".vue", "from 'vue'"],
            "django":   ["from django", "django.contrib", "urlpatterns"],
            "flask":    ["from flask", "Flask(__name__)", "@app.route"],
        }
        if self.profile.preferred_framework != "unknown":
            return
        for fw, markers in signals.items():
            if any(m in content or m in path for m in markers):
                self.profile.preferred_framework = fw
                return

    def _infer_indent(self, content: str):
        lines = content.splitlines()[:100]
        tab_lines   = sum(1 for l in lines if l.startswith("\t"))
        two_lines   = sum(1 for l in lines if l.startswith("  ") and not l.startswith("   "))
        four_lines  = sum(1 for l in lines if l.startswith("    "))

        if tab_lines > max(two_lines, four_lines):
            self.profile.indent_type = "tabs"
            self.profile.indent_size = 1
        elif two_lines > four_lines:
            self.profile.indent_type = "spaces"
            self.profile.indent_size = 2
        elif four_lines > 0:
            self.profile.indent_type = "spaces"
            self.profile.indent_size = 4

    def _infer_naming(self, content: str, ext: str):
        # Heuristic: look at function/variable names
        if ext in ("ts", "tsx", "js", "jsx"):
            camel_count = len(re.findall(r'\bconst [a-z][a-zA-Z]+\b', content))
            pascal_count = len(re.findall(r'\bconst [A-Z][a-zA-Z]+\b', content))
            if camel_count > pascal_count:
                self.profile.naming_convention = "camelCase"
            elif pascal_count > camel_count:
                self.profile.naming_convention = "PascalCase"
        elif ext == "py":
            snake_count = len(re.findall(r'\bdef [a-z][a-z_]+\b', content))
            if snake_count > 2:
                self.profile.naming_convention = "snake_case"

    def _infer_comments(self, content: str, ext: str):
        if '"""' in content or "'''" in content:
            self.profile.comment_style = "docstring"
        elif "/**" in content or "/*" in content:
            self.profile.comment_style = "jsdoc"
        elif content.count("#") > 5 or content.count("//") > 5:
            self.profile.comment_style = "inline"

    def _infer_test_convention(self, path: str, content: str):
        if self.profile.test_convention != "unknown":
            return
        if "pytest" in content or "test_" in path:
            self.profile.test_convention = "pytest"
        elif "describe(" in content and "it(" in content:
            self.profile.test_convention = "jest"
        elif "vitest" in content:
            self.profile.test_convention = "vitest"

    def _infer_package_manager(self, path: str, content: str):
        if self.profile.package_manager != "unknown":
            return
        if "pnpm-lock.yaml" in path or "pnpm" in content:
            self.profile.package_manager = "pnpm"
        elif "yarn.lock" in path or "yarn add" in content:
            self.profile.package_manager = "yarn"
        elif "package-lock.json" in path or "npm install" in content:
            self.profile.package_manager = "npm"
        elif "pyproject.toml" in path or "uv pip" in content:
            self.profile.package_manager = "uv"
        elif "requirements.txt" in path or "pip install" in content:
            self.profile.package_manager = "pip"

    # ── Prompt injection ──────────────────────────────────────────────────────

    def get_profile_prompt(self) -> str:
        """
        Returns a short paragraph describing the user's style to inject
        into Copartner's system prompt. Only includes fields with known values.
        """
        p = self.profile
        if p.observations < 3:
            return ""  # Not enough data yet

        parts = []
        if p.preferred_language != "unknown":
            parts.append(f"preferred language: {p.preferred_language}")
        if p.preferred_framework != "unknown":
            parts.append(f"preferred framework: {p.preferred_framework}")
        if p.naming_convention != "unknown":
            parts.append(f"naming convention: {p.naming_convention}")
        if p.indent_type != "unknown":
            parts.append(f"indentation: {p.indent_size} {p.indent_type}")
        if p.comment_style != "inline":
            parts.append(f"comment style: {p.comment_style}")
        if p.test_convention != "unknown":
            parts.append(f"test framework: {p.test_convention}")
        if p.package_manager != "unknown":
            parts.append(f"package manager: {p.package_manager}")

        if not parts:
            return ""

        return (
            f"[User's coding style profile — follow these conventions in all generated code:]\n"
            + "\n".join(f"  • {part}" for part in parts)
        )
