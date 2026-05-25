"""
Tool Executor for Asirive Copartner
=====================================
Intercepts and executes XML tool tags emitted by Gemini during the
System 2 reasoning loop.

Tag protocol (extended from Eidos ToolParser):
    <think>reasoning text</think>           → logged, not executed
    <research>search query</research>        → web search (stub for now)
    <code_sandbox>\ncode\n</code_sandbox>   → sandboxed Python execution
    <scaffold>project brief</scaffold>       → project scaffolding trigger
    <deploy>deployment target</deploy>       → deployment trigger
    <observe_screen>what to look for</observe_screen>  → screen capture + Vision
    <memory_store>tier::content</memory_store>          → write to MemoryManager
    <memory_recall>query string</memory_recall>         → read from MemoryManager
    <final_answer>response text</final_answer>          → signals loop completion

Key differences from Eidos ToolParser:
  - Tags are Copartner-specific, not math/arithmetic-focused
  - memory_store/recall routes to the ChromaDB MemoryManager
  - observe_screen routes to the perception layer (mss + Gemini Vision)
  - scaffold/deploy are stubs now, will connect to action/ layer in Phase 3
"""

import re
import ast
import operator
import io
import sys
import traceback
import logging
from typing import Optional, Any

logger = logging.getLogger("Copartner.ToolExecutor")

# ── Safe math evaluator (ported directly from Eidos ToolParser) ───────────────
_SAFE_OPS = {
    ast.Add: operator.add,  ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow,  ast.USub: operator.neg,
    ast.UAdd: operator.pos, ast.Mod: operator.mod,
}

def _safe_eval_node(node) -> Any:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Only numeric constants allowed")
    if isinstance(node, ast.BinOp):
        op = type(node.op)
        if op in _SAFE_OPS:
            return _SAFE_OPS[op](_safe_eval_node(node.left), _safe_eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        op = type(node.op)
        if op in _SAFE_OPS:
            return _SAFE_OPS[op](_safe_eval_node(node.operand))
    raise ValueError(f"Unsafe node type: {type(node).__name__}")

def safe_math_eval(expr: str) -> str:
    expr = expr.strip().replace("^", "**").replace("×", "*").replace("÷", "/")
    try:
        tree = ast.parse(expr, mode="eval")
        result = _safe_eval_node(tree.body)
        return str(result)
    except Exception as e:
        return f"[calc error: {e}]"


# ── Sandboxed Python execution (ported from Eidos ToolParser) ─────────────────
_SANDBOX_BUILTINS = {
    "print": print, "range": range, "len": len, "int": int, "float": float,
    "str": str, "list": list, "dict": dict, "set": set, "tuple": tuple,
    "sum": sum, "min": min, "max": max, "abs": abs, "sorted": sorted,
    "reversed": reversed, "enumerate": enumerate, "zip": zip, "map": map,
    "filter": filter, "any": any, "all": all, "round": round, "pow": pow,
    "True": True, "False": False, "None": None,
    "__import__": None,   # Block import
}

def sandbox_exec(code: str) -> str:
    """Execute Python code in a restricted sandbox. Returns stdout or error."""
    code = code.strip()
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        exec(code, {"__builtins__": _SANDBOX_BUILTINS}, {})
        out = buf.getvalue().strip()
        return out if out else "[executed — no output]"
    except Exception:
        return f"[exec error]\n{traceback.format_exc(limit=2)}"
    finally:
        sys.stdout = old


# ── Tag pattern ───────────────────────────────────────────────────────────────
TAG_PATTERN = re.compile(
    r"<(think|research|code_sandbox|scaffold|deploy|observe_screen"
    r"|memory_store|memory_recall|final_answer"
    r"|file_read|file_write|file_list|shell_exec)>(.*?)</\1>",
    re.DOTALL | re.IGNORECASE,
)


class ToolExecutor:
    """
    Intercepts Copartner XML tool tags and routes them to the right handler.
    Injected with MemoryManager for memory_store/memory_recall operations.
    Screen capture is a stub for Phase 2 (perception layer).
    """

    def __init__(
        self,
        memory_manager=None,
        gemini_client=None,
        code_scaffolder=None,
        vercel_connector=None,
        screen_observer=None,
    ):
        self.memory    = memory_manager
        self.gemini    = gemini_client
        self.scaffolder = code_scaffolder
        self.vercel     = vercel_connector
        self.screen_observer = screen_observer
        self.stats: dict[str, int] = {}
        logger.info("ToolExecutor initialized")

    # ── Dispatch ──────────────────────────────────────────────────────────────

    def execute(self, tag: str, content: str) -> str:
        """Execute a single tool tag. Returns the result string."""
        tag = tag.lower()
        self.stats[tag] = self.stats.get(tag, 0) + 1
        logger.debug(f"ToolExecutor: executing <{tag}> ({len(content)} chars)")

        handlers = {
            "think":          self._handle_think,
            "research":       self._handle_research,
            "code_sandbox":   self._handle_code_sandbox,
            "scaffold":       self._handle_scaffold,
            "deploy":         self._handle_deploy,
            "observe_screen": self._handle_observe_screen,
            "memory_store":   self._handle_memory_store,
            "memory_recall":  self._handle_memory_recall,
            "final_answer":   self._handle_final_answer,
            "file_read":      self._handle_file_read,
            "file_write":     self._handle_file_write,
            "file_list":      self._handle_file_list,
            "shell_exec":     self._handle_shell_exec,
        }

        handler = handlers.get(tag)
        if handler:
            return handler(content)
        return f"[unknown tag: {tag}]"

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _handle_think(self, content: str) -> str:
        """<think> blocks are internal reasoning — log but don't execute."""
        logger.debug(f"[THINK] {content[:120].strip()}")
        return ""  # No result injected back

    def _handle_research(self, content: str) -> str:
        """
        <research> triggers a web search.
        Phase 1 stub — returns placeholder. Phase 3 will wire to Brave/Google.
        """
        logger.info(f"[RESEARCH] query: {content.strip()[:100]}")
        # TODO Phase 3: integrate Brave Search API or MCP search server
        return (
            f"[Research results for: '{content.strip()[:80]}']\n"
            f"Web search integration coming in Phase 3. "
            f"For now, use your training knowledge to answer."
        )

    def _handle_code_sandbox(self, content: str) -> str:
        """<code_sandbox> runs Python in a restricted sandbox."""
        logger.info(f"[CODE_SANDBOX] executing {len(content)} chars of Python")
        result = sandbox_exec(content)
        return f"[Execution result]\n{result}"

    def _handle_scaffold(self, content: str) -> str:
        """
        <scaffold> generates a complete project from a brief.
        Uses CodeScaffolder if available, else logs as stub.
        """
        logger.info(f"[SCAFFOLD] brief: {content.strip()[:100]}")
        if self.scaffolder is not None:
            result = self.scaffolder.scaffold(brief=content.strip())
            if "error" in result:
                return f"[Scaffold error] {result['error']}"
            lines = [
                f"[Scaffold complete] {result['file_count']} files written to: {result['output_path']}",
                f"Project type: {result['project_type']}",
            ]
            if result.get("setup_commands"):
                lines.append("Setup: " + " && ".join(result["setup_commands"]))
            if result.get("notes"):
                lines.append(f"Notes: {result['notes'][:100]}")
            return "\n".join(lines)
        return f"[Scaffold queued] Brief received. Wire CodeScaffolder in ToolExecutor to enable."

    def _handle_deploy(self, content: str) -> str:
        """
        <deploy> triggers a Vercel deployment.
        Uses VercelConnector if available, else logs as stub.
        """
        logger.info(f"[DEPLOY] target: {content.strip()[:100]}")
        if self.vercel is not None:
            # Parse "project_name::path" format or just use content as project name
            parts = content.strip().split("::", 1)
            project_name = parts[0].strip().lower().replace(" ", "-")
            project_dir  = parts[1].strip() if len(parts) > 1 else f"output/{project_name}"
            result = self.vercel.deploy(project_dir=project_dir, project_name=project_name)
            if "error" in result:
                return f"[Deploy error] {result['error']}"
            return f"[Deployed] {result['url']} | Status: {result['status']}"
        return f"[Deploy queued] Target: '{content.strip()[:80]}'. Set VERCEL_TOKEN in .env to enable."

    def _handle_observe_screen(self, content: str) -> str:
        """
        <observe_screen> captures the screen and analyses it with Gemini Vision.
        Uses the injected ScreenObserver for real screen capture + analysis.
        """
        logger.info(f"[OBSERVE_SCREEN] instruction: {content.strip()[:100]}")
        if self.screen_observer is None:
            return "[Screen observation] ScreenObserver not available."
        try:
            analysis = self.screen_observer.capture_and_analyze(content.strip())
            return f"[Screen observation result]\n{analysis}"
        except Exception as e:
            logger.error(f"Screen observation failed: {e}")
            return f"[Screen observation error: {e}]"

    def _handle_memory_store(self, content: str) -> str:
        """
        <memory_store>tier::content_to_store</memory_store>
        Stores something to ChromaDB memory.
        """
        if self.memory is None:
            return "[memory_store] MemoryManager not available"

        parts = content.strip().split("::", 1)
        if len(parts) != 2:
            return "[memory_store] Format must be: tier::content (e.g. semantic::Python uses 0-indexed lists)"

        tier, text = parts[0].strip().lower(), parts[1].strip()
        valid_tiers = ("episodic", "semantic", "skills", "preferences")
        if tier not in valid_tiers:
            return f"[memory_store] Invalid tier '{tier}'. Use one of: {valid_tiers}"

        mem_id = self.memory.store(text, tier, source="copartner_action")
        return f"[Memory stored] ID: {mem_id} | Tier: {tier}"

    def _handle_memory_recall(self, content: str) -> str:
        """
        <memory_recall>query</memory_recall>
        Retrieves relevant memories from ChromaDB.
        """
        if self.memory is None:
            return "[memory_recall] MemoryManager not available"

        query = content.strip()
        results = self.memory.recall(query, n_results=4)
        if not results:
            return f"[Memory recall] No relevant memories found for: '{query[:60]}'"

        lines = [f"[Memory recall for: '{query[:60]}']"]
        for i, r in enumerate(results, 1):
            relevance = r.get("relevance", 0)
            lines.append(f"  {i}. [{relevance:.2f}] {r['content'][:200]}")

        return "\n".join(lines)

    def _handle_final_answer(self, content: str) -> str:
        """<final_answer> signals the end of the loop. Content is the answer itself."""
        return content.strip()

    # ── File operations ───────────────────────────────────────────────────────

    def _handle_file_read(self, content: str) -> str:
        """<file_read>path</file_read> — read a file safely."""
        from action.file_ops import file_read
        path = content.strip()
        result = file_read(path)
        if "error" in result:
            return f"[file_read error] {result['error']}"
        return f"[file_read: {result['path']}]\n{result['content']}"

    def _handle_file_write(self, content: str) -> str:
        """<file_write>path::content</file_write> — write a file safely."""
        from action.file_ops import file_write
        parts = content.strip().split("::", 1)
        if len(parts) != 2:
            return "[file_write error] Format: path::content"
        path, file_content = parts[0].strip(), parts[1].strip()
        result = file_write(path, file_content, confirm_overwrite=False)
        if "error" in result:
            return f"[file_write error] {result['error']}"
        return f"[file_write: {result['path']}] {result['bytes_written']} bytes written"

    def _handle_file_list(self, content: str) -> str:
        """<file_list>path</file_list> — list directory contents."""
        from action.file_ops import file_list
        path = content.strip()
        result = file_list(path)
        if "error" in result:
            return f"[file_list error] {result['error']}"
        entries = result.get("entries", [])
        lines = [f"[file_list: {result['path']}] {len(entries)} entries"]
        for e in entries[:50]:
            icon = "📁" if e["type"] == "directory" else "📄"
            lines.append(f"  {icon} {e['name']} ({e['size']:,} bytes)")
        if len(entries) > 50:
            lines.append(f"  ... ({len(entries) - 50} more)")
        return "\n".join(lines)

    # ── Shell execution ───────────────────────────────────────────────────────

    def _handle_shell_exec(self, content: str) -> str:
        """<shell_exec>command</shell_exec> — run a shell command safely."""
        from action.shell_executor import shell_exec
        command = content.strip()
        result = shell_exec(command)
        if "error" in result:
            return f"[shell_exec error] {result['error']}"
        lines = [f"[shell_exec: {result['command']}]"]
        if result.get("stdout"):
            lines.append("STDOUT:")
            lines.append(result["stdout"])
        if result.get("stderr"):
            lines.append("STDERR:")
            lines.append(result["stderr"])
        lines.append(f"Exit code: {result['returncode']}")
        return "\n".join(lines)

    # ── Batch processing ──────────────────────────────────────────────────────

    def process_text(self, text: str) -> tuple[str, list[dict]]:
        """
        Find all tool tags in a text block, execute them, and return
        the augmented text and a list of actions taken.

        Returns:
            (augmented_text, actions_taken)
        """
        actions = []

        def replacer(match: re.Match) -> str:
            tag     = match.group(1).lower()
            content = match.group(2)
            result  = self.execute(tag, content)
            actions.append({"tag": tag, "result_preview": result[:120]})

            if tag == "think":
                return f"<think>{content}</think>"   # Preserve think blocks as-is
            if tag == "final_answer":
                return f"<final_answer>{content}</final_answer>"
            if not result:
                return f"<{tag}>{content}</{tag}>"
            return f"<{tag}>{content}</{tag}>\n[result: {result}]"

        augmented = TAG_PATTERN.sub(replacer, text)
        return augmented, actions

    def has_final_answer(self, text: str) -> Optional[str]:
        """
        Check if text contains a <final_answer> tag.
        Returns the answer content if found, None otherwise.
        """
        match = re.search(
            r"<final_answer>(.*?)</final_answer>",
            text, re.DOTALL | re.IGNORECASE
        )
        return match.group(1).strip() if match else None

    def get_stats_str(self) -> str:
        if not self.stats:
            return "No tool calls this session"
        return ", ".join(f"{k}×{v}" for k, v in sorted(self.stats.items()))
