"""
Skill Learner for Asirive Copartner
======================================
When Copartner successfully completes a complex multi-step task,
SkillLearner distills the thought trace into a reusable SKILL.md file.

Next time a similar task arrives, MemoryManager recalls the skill and
ThoughtController can execute it directly — no need to rediscover the approach.
"""

import re
import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("Copartner.SkillLearner")

PROJECT_ROOT = Path(__file__).parent.parent
SKILLS_DIR   = PROJECT_ROOT / "skills"


def _slugify(text: str) -> str:
    """Convert a task description to a safe filename slug."""
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_]+", "_", slug).strip("_")
    return slug[:60]


class SkillLearner:
    """
    Records successful task traces and generates SKILL.md files.

    These skill files are also stored in the 'skills' memory tier in ChromaDB
    so they can be recalled semantically when a similar task appears.

    Usage:
        learner = SkillLearner(memory_manager=memory)
        path = learner.save_skill(
            task_description="Deploy a React app to Vercel",
            trace=[
                {"tag": "think",        "content": "..."},
                {"tag": "code_sandbox", "content": "npm run build", "result": "Build successful"},
                {"tag": "deploy",       "content": "Vercel — output/dist/", "result": "URL: https://..."},
            ]
        )
    """

    def __init__(self, memory_manager=None):
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        self.memory = memory_manager
        logger.info(f"SkillLearner ready. Skills dir: {SKILLS_DIR}")

    def save_skill(self, task_description: str, trace: list[dict]) -> str:
        """
        Distil a successful task trace into a SKILL.md file.

        Args:
            task_description: Human-readable description of the task.
            trace:            List of step dicts: {tag, content, result?}

        Returns:
            Absolute path to the generated SKILL.md file.
        """
        timestamp  = time.strftime("%Y-%m-%d")
        slug       = _slugify(task_description)
        skill_path = SKILLS_DIR / f"{slug}.md"

        # Build SKILL.md content
        lines = [
            f"# Skill: {task_description}",
            f"Generated: {timestamp}",
            "",
            "## Summary",
            f"Auto-generated skill from a successful Copartner task trace.",
            "",
            "## Steps",
        ]

        step_num = 1
        for step in trace:
            tag     = step.get("tag", "?")
            content = step.get("content", "").strip()[:300]
            result  = step.get("result", "").strip()[:200]

            if tag == "think":
                lines.append(f"{step_num}. **Think**: {content}")
            elif tag == "code_sandbox":
                lines.append(f"{step_num}. **Execute Code**:")
                lines.append(f"   ```python\n   {content}\n   ```")
                if result:
                    lines.append(f"   *Result*: {result}")
            elif tag == "research":
                lines.append(f"{step_num}. **Research**: {content}")
                if result:
                    lines.append(f"   *Findings*: {result[:100]}")
            elif tag == "scaffold":
                lines.append(f"{step_num}. **Scaffold**: {content}")
            elif tag == "deploy":
                lines.append(f"{step_num}. **Deploy**: {content}")
                if result:
                    lines.append(f"   *Result*: {result}")
            elif tag == "memory_store":
                lines.append(f"{step_num}. **Stored to memory**: {content[:80]}")
            elif tag == "final_answer":
                lines.append(f"{step_num}. **Final Answer delivered**.")
            else:
                lines.append(f"{step_num}. **{tag}**: {content[:80]}")

            step_num += 1
            lines.append("")

        lines += [
            "## Notes",
            "- This skill was auto-generated. Review and edit as needed.",
            f"- Original task: {task_description}",
            "",
        ]

        skill_content = "\n".join(lines)
        skill_path.write_text(skill_content, encoding="utf-8")
        logger.info(f"SkillLearner: saved skill to {skill_path}")

        # Also store in ChromaDB skills memory for semantic recall
        if self.memory is not None:
            self.memory.store_skill(
                description=task_description,
                example=f"See {skill_path.name}",
                domain="auto-learned",
            )

        return str(skill_path)

    def find_skill(self, task_description: str) -> Optional[str]:
        """
        Search for an existing skill file relevant to the given task.

        Args:
            task_description: The current task being attempted.

        Returns:
            Contents of the best-matching SKILL.md, or None if none found.
        """
        # First check ChromaDB semantic recall
        if self.memory is not None:
            results = self.memory.recall(task_description, memory_type="skills", n_results=1)
            if results and results[0]["relevance"] > 0.70:
                # Extract the skill filename from the result
                content = results[0]["content"]
                match = re.search(r"See ([\w\-]+\.md)", content)
                if match:
                    skill_path = SKILLS_DIR / match.group(1)
                    if skill_path.exists():
                        logger.info(f"SkillLearner: recalled skill {skill_path.name}")
                        return skill_path.read_text(encoding="utf-8")

        # Fallback: filename fuzzy match
        slug = _slugify(task_description)
        for skill_file in SKILLS_DIR.glob("*.md"):
            if slug[:20] in skill_file.stem or skill_file.stem[:20] in slug:
                logger.info(f"SkillLearner: matched skill file {skill_file.name}")
                return skill_file.read_text(encoding="utf-8")

        return None

    def list_skills(self) -> list[str]:
        """Return a list of all skill file names."""
        return [f.name for f in sorted(SKILLS_DIR.glob("*.md"))]
