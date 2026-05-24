"""
Code Scaffolder for Asirive Copartner — Phase 3 Action
=======================================================
Generates complete, ready-to-run project scaffolds from a natural language
brief. Copartner asks Gemini to produce the full file tree, then writes
every file to disk. This is the "instant studio" capability.

The scaffolder is triggered by <scaffold> tags from the ThoughtController,
or called directly from CLI/Tauri frontend.

Supported project types (auto-detected from brief):
    - Next.js app (App Router, TypeScript)
    - React SPA (Vite + TypeScript)
    - FastAPI backend
    - Express/Node API
    - Static HTML/CSS/JS landing page
    - Python CLI tool

Output: writes all files to output/<project-slug>/
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("Copartner.CodeScaffolder")

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR   = PROJECT_ROOT / "output"


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug[:50]


SCAFFOLD_PROMPT_TEMPLATE = """You are an expert software engineer. Generate a complete, production-ready project scaffold.

PROJECT BRIEF:
{brief}

OUTPUT FORMAT (strict JSON, no markdown):
{{
  "project_type": "nextjs|react|fastapi|express|static|cli",
  "project_name": "slug-case-name",
  "description": "one sentence description",
  "files": {{
    "relative/path/to/file.ext": "full file content here",
    "another/file.ext": "full file content here"
  }},
  "setup_commands": ["npm install", "npm run dev"],
  "notes": "any important information for the developer"
}}

REQUIREMENTS:
- Generate REAL, working code — no placeholders or TODOs
- Include at minimum: entry point, README.md, package.json or requirements.txt
- Use TypeScript for JS projects
- Include basic styling if it's a frontend project
- Keep files focused and clean
- The user's style preferences: {style_context}
"""


class CodeScaffolder:
    """
    Generates complete project scaffolds from natural language briefs.

    Cost strategy:
      1. Try OpenCode Go (Kimi K2.6) first — ~10x cheaper than Gemini Pro
      2. Fall back to Gemini Pro if OpenCode is unavailable

    Usage:
        scaffolder = CodeScaffolder(gemini_client=client, opencode_client=opencode)
        result = scaffolder.scaffold("Build a landing page for a coffee shop called Beanery")
        print(result["output_path"])   # c:/...Copartner/output/beanery/
        print(result["files_created"]) # list of file paths
    """

    def __init__(self, gemini_client=None, behavioral_engine=None, opencode_client=None):
        self.gemini      = gemini_client
        self.behavior    = behavioral_engine
        self.opencode    = opencode_client
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def scaffold(
        self,
        brief: str,
        output_subdir: Optional[str] = None,
    ) -> dict:
        """
        Generate and write a complete project from a brief.

        Args:
            brief:        Natural language project description.
            output_subdir: Optional output folder name (auto-slugified from brief).

        Returns:
            dict with: output_path, files_created, project_type, setup_commands, notes
        """
        if self.gemini is None:
            return {"error": "GeminiClient not injected"}

        logger.info(f"Scaffolding: {brief[:80]}")

        # Get style context from behavioral engine
        style_ctx = ""
        if self.behavior:
            style_ctx = self.behavior.get_profile_prompt() or "No style preferences known yet."

        # Build prompt
        prompt = SCAFFOLD_PROMPT_TEMPLATE.format(
            brief=brief,
            style_context=style_ctx,
        )

        # Cost-optimised routing:
        # Try OpenCode Go (Kimi K2.6) first — cheaper for heavy generation
        # Fall back to Gemini Pro if OpenCode is unavailable
        raw = None
        if self.opencode and self.opencode.ready:
            logger.info("Scaffolding via OpenCode Go (Kimi K2.6)")
            raw = self.opencode.scaffold_with_opencode(
                brief=prompt,
                system_instruction=(
                    "You are an expert software engineer. Generate complete, "
                    "production-ready project scaffolds. Output strict JSON only."
                ),
            )
        elif self.gemini is not None:
            logger.info("Scaffolding via Gemini Pro (OpenCode not available)")
            try:
                raw = self.gemini.generate(
                    contents=[prompt],
                    use_pro=True,
                    temperature=0.3,
                    max_output_tokens=8192,
                )
            except Exception as e:
                logger.error(f"Gemini scaffold generation failed: {e}")
                return {"error": str(e)}
        else:
            return {"error": "No generation backend available (Gemini or OpenCode required)"}

        if raw is None:
            return {"error": "Generation returned no content"}

        # Parse JSON response
        scaffold_data = self._parse_scaffold_json(raw)
        if "error" in scaffold_data:
            return scaffold_data

        # Write files to disk
        slug        = output_subdir or _slugify(
            scaffold_data.get("project_name", brief)
        )
        output_path = OUTPUT_DIR / slug
        output_path.mkdir(parents=True, exist_ok=True)

        files_created = []
        files = scaffold_data.get("files", {})

        for rel_path, content in files.items():
            # Sanitize path (prevent directory traversal)
            rel_path  = rel_path.lstrip("/\\").replace("..", "")
            full_path = output_path / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                full_path.write_text(str(content), encoding="utf-8")
                files_created.append(str(full_path))
                logger.debug(f"  Written: {rel_path}")
            except Exception as e:
                logger.error(f"  Failed to write {rel_path}: {e}")

        result = {
            "output_path":    str(output_path),
            "project_type":   scaffold_data.get("project_type", "unknown"),
            "project_name":   scaffold_data.get("project_name", slug),
            "description":    scaffold_data.get("description", brief[:80]),
            "files_created":  files_created,
            "file_count":     len(files_created),
            "setup_commands": scaffold_data.get("setup_commands", []),
            "notes":          scaffold_data.get("notes", ""),
        }

        logger.info(
            f"Scaffold complete: {len(files_created)} files → {output_path}"
        )
        return result

    def _parse_scaffold_json(self, raw: str) -> dict:
        """Extract and parse JSON from Gemini's response."""
        # Strip markdown code fences if present
        raw = re.sub(r"```(?:json)?\s*", "", raw).strip()
        raw = raw.strip("`").strip()

        # Try to find JSON object in response
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return {"error": f"No JSON found in scaffold response. Raw: {raw[:200]}"}

        try:
            return json.loads(match.group())
        except json.JSONDecodeError as e:
            return {"error": f"JSON parse error: {e}. Raw: {raw[:200]}"}

    def list_output_projects(self) -> list[str]:
        """List all scaffolded projects in the output directory."""
        if not OUTPUT_DIR.exists():
            return []
        return [d.name for d in OUTPUT_DIR.iterdir() if d.is_dir()]
