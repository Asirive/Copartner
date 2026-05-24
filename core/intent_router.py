"""
Intent Router for Asirive Copartner
=====================================
Routes incoming queries to the optimal Gemini model (Pro / Flash / Vision)
based on detected intent signals. Inspired by Eidos Neuromodulator concept —
"what kind of thinking does this require?" — but implemented purely via
heuristics + Gemini Flash classification, not local neural weights.
"""

import re
import logging
from dataclasses import dataclass

logger = logging.getLogger("Copartner.IntentRouter")


@dataclass
class RouteDecision:
    model: str          # "pro" | "flash" | "vision"
    intent: str         # detected intent label
    rationale: str      # human-readable explanation
    use_pro: bool       # convenience bool for GeminiClient


# ── Keyword/pattern rules ─────────────────────────────────────────────────────
# Each rule: (intent_label, model, pattern_list)
ROUTING_RULES: list[tuple[str, str, list[str]]] = [
    # Vision — anything about looking at the screen
    # Uses gemini-3.5-flash (natively multimodal — same model, image in contents list)
    ("screen_analysis", "flash", [
        r"what('s| is) on (my |the )?screen",
        r"look at (my |the )?screen",
        r"observe",
        r"screenshot",
        r"what do you see",
        r"read (the |this )?image",
        r"describe (the |this )?screen",
    ]),

    # Pro — deep reasoning (gemini-3.1-pro-preview)
    ("deep_code", "pro", [
        r"\barchitect\b",
        r"\bscaffold\b",
        r"\brefactor\b",
        r"\bdesign pattern\b",
        r"\bsystem design\b",
        r"\bdebug\b",
        r"\boptimize\b",
        r"\bbuild (a|an|the)\b",
        r"\bcreate (a|an|the)\b",
        r"\bwrite (a|an|the)\b.*(app|system|service|api|pipeline)",
        r"\bimplement\b",
    ]),
    ("deep_analysis", "pro", [
        r"\banalyze\b",
        r"\bexplain (how|why|what)\b",
        r"\bcompare\b",
        r"\bpros and cons\b",
        r"\btrade.?off\b",
        r"\bresearch\b",
        r"\binvestigate\b",
        r"\bplan\b",
    ]),
    ("code_generation", "pro", [
        r"\bcode\b",
        r"\bfunction\b",
        r"\bclass\b",
        r"\bscript\b",
        r"\bmodule\b",
        r"\btest(s| case| suite)\b",
        r"\bdeploy\b",
        r"\bci/cd\b",
        r"\bdockerfile\b",
    ]),

    # Flash — simple, fast tasks (gemini-3.5-flash)
    ("quick_classify", "flash", [
        r"^(yes|no|is it|does it|can you|will)",
        r"\bquick(ly)?\b",
        r"\bfast\b",
        r"\bsimple\b",
        r"\bsummariz(e|ation)\b",
        r"\bformat\b",
        r"\bconvert\b",
        r"\btransla(te|tion)\b",
        r"\brephrase\b",
        r"\bshorten\b",
        r"\bfix typo\b",
    ]),
    ("quick_question", "flash", [
        r"^what (is|are) ",
        r"^who (is|are) ",
        r"^when (is|was) ",
        r"^where (is|are) ",
        r"^how (do|does|many|much) ",
    ]),
]


class IntentRouter:
    """
    Lightweight model router. Routes queries to Gemini Pro, Flash, or Vision
    based on simple pattern matching with sane defaults.

    When in doubt, it defaults to Flash to save budget, and the ThoughtController
    can escalate to Pro if the model signals low confidence (loops >3 times).
    """

    def __init__(self, default_model: str = "flash"):
        self.default_model = default_model
        logger.info(f"IntentRouter initialized (default: {default_model})")

    def route(self, query: str) -> RouteDecision:
        """
        Analyse the query and return a RouteDecision with the best model.

        Args:
            query: The raw user query string.

        Returns:
            RouteDecision with model, intent, rationale, and use_pro flag.
        """
        q = query.lower().strip()

        for intent, model, patterns in ROUTING_RULES:
            for pattern in patterns:
                if re.search(pattern, q, re.IGNORECASE):
                    rationale = f"Matched pattern '{pattern}' → intent '{intent}'"
                    logger.debug(f"IntentRouter: {model.upper()} | {rationale}")
                    return RouteDecision(
                        model=model,
                        intent=intent,
                        rationale=rationale,
                        use_pro=(model == "pro"),
                    )

        # Default: Flash for unknown queries (saves budget)
        return RouteDecision(
            model=self.default_model,
            intent="general",
            rationale="No strong intent signal detected — using default model",
            use_pro=(self.default_model == "pro"),
        )

    def escalate(self, decision: RouteDecision, reason: str = "low confidence") -> RouteDecision:
        """
        Escalate an existing Flash decision to Pro.
        Called by ThoughtController when the model loops too many times.
        """
        if decision.model == "flash":
            logger.info(f"IntentRouter: escalating Flash → Pro ({reason})")
            return RouteDecision(
                model="pro",
                intent=decision.intent + "_escalated",
                rationale=f"Escalated from Flash: {reason}",
                use_pro=True,
            )
        return decision
