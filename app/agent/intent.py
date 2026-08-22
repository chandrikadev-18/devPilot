"""
DevPilot Question Intent Classification and Smart Tool Selection.

Analyzes user questions to determine intent, target symbols, and preferred tool sequences
to minimize tool execution and eliminate redundant steps.
"""

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import List, Optional


class QuestionIntent(str, Enum):
    IMPACT = "IMPACT"
    CALLEES = "CALLEES"
    CALLERS = "CALLERS"
    DEPENDENCIES = "DEPENDENCIES"
    DEPENDENTS = "DEPENDENTS"
    FILE_DEPENDENCIES = "FILE_DEPENDENCIES"
    DEFINITION = "DEFINITION"
    EXPLANATION = "EXPLANATION"
    SEARCH = "SEARCH"


@dataclass
class IntentClassification:
    intent: QuestionIntent
    target_symbol: Optional[str] = None
    target_file: Optional[str] = None
    preferred_tools: List[str] = field(default_factory=list)


def _clean_symbol_candidate(raw: str) -> str:
    """Cleans a raw extracted symbol string."""
    cleaned = raw.strip().strip("'\"`?,.:;()[]{}")
    # Strip common leading prefixes
    for prefix in ("the ", "a ", "function ", "method ", "class ", "module "):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    return cleaned.strip().strip("'\"`")


def classify_question_intent(question: str) -> IntentClassification:
    """
    Classifies a natural language question into an actionable intent and extracts target symbols.
    """
    if not question or not question.strip():
        return IntentClassification(intent=QuestionIntent.SEARCH, preferred_tools=["search_code"])

    q = question.strip()
    q_lower = q.lower()

    # 1. IMPACT Intent
    # "What could be affected if X changes?", "What is the impact of changing X?", "What breaks if X changes?"
    impact_patterns = [
        r"what\s+(?:could|would|might|can)?\s*be\s+affected\s+if\s+(?:the\s+)?([a-zA-Z0-9_.]+?)(?:\s+function|\s+method|\s+class)?\s+changes",
        r"what\s+(?:could|would|might|can)?\s*break\s+if\s+(?:the\s+)?([a-zA-Z0-9_.]+?)(?:\s+function|\s+method|\s+class)?\s+changes",
        r"what\s+is\s+the\s+impact\s+of\s+(?:changing|modifying|updating)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"impact\s+(?:analysis\s+)?(?:of|for|on)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"what\s+(?:is|are)\s+the\s+impacts?\s+of\s+([a-zA-Z0-9_.]+)",
        r"how\s+(?:does|would)\s+changing\s+([a-zA-Z0-9_.]+)\s+affect",
    ]
    for pat in impact_patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            sym = _clean_symbol_candidate(m.group(1))
            return IntentClassification(
                intent=QuestionIntent.IMPACT,
                target_symbol=sym,
                preferred_tools=["find_symbol", "get_impact"],
            )

    # 2. CALLEES Intent (What functions does X call?)
    callees_patterns = [
        r"what\s+functions?\s+(?:does|do)\s+(?:the\s+)?([a-zA-Z0-9_.]+?)\s+(?:call|invoke)",
        r"what\s+(?:does|do)\s+(?:the\s+)?([a-zA-Z0-9_.]+?)\s+call",
        r"what\s+functions?\s+(?:are|is)\s+called\s+by\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"outgoing\s+calls?\s+(?:from|for|of)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"callees\s+of\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
    ]
    for pat in callees_patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            sym = _clean_symbol_candidate(m.group(1))
            return IntentClassification(
                intent=QuestionIntent.CALLEES,
                target_symbol=sym,
                preferred_tools=["find_symbol", "get_callees"],
            )

    # 3. CALLERS Intent (Who calls X? Where is X used?)
    callers_patterns = [
        r"who\s+calls\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"where\s+is\s+(?:the\s+)?([a-zA-Z0-9_.]+?)\s+used",
        r"what\s+functions?\s+call\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"what\s+calls\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"incoming\s+calls?\s+(?:to|for)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"callers\s+of\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
    ]
    for pat in callers_patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            sym = _clean_symbol_candidate(m.group(1))
            return IntentClassification(
                intent=QuestionIntent.CALLERS,
                target_symbol=sym,
                preferred_tools=["find_symbol", "get_callers"],
            )

    # 4. DEPENDENCIES Intent (What does X depend on?)
    dep_patterns = [
        r"what\s+(?:does|do)\s+(?:the\s+)?([a-zA-Z0-9_.]+?)\s+depend\s+on",
        r"what\s+are\s+the\s+dependencies\s+of\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"dependencies\s+of\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
    ]
    for pat in dep_patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            sym = _clean_symbol_candidate(m.group(1))
            return IntentClassification(
                intent=QuestionIntent.DEPENDENCIES,
                target_symbol=sym,
                preferred_tools=["find_symbol", "get_dependencies"],
            )

    # 5. DEPENDENTS Intent (What depends on X?)
    dependents_patterns = [
        r"what\s+depends\s+on\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"who\s+depends\s+on\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"dependents\s+of\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
    ]
    for pat in dependents_patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            sym = _clean_symbol_candidate(m.group(1))
            return IntentClassification(
                intent=QuestionIntent.DEPENDENTS,
                target_symbol=sym,
                preferred_tools=["find_symbol", "get_dependents"],
            )

    # 6. FILE_DEPENDENCIES Intent
    file_dep_patterns = [
        r"what\s+files?\s+(?:does|do)\s+([a-zA-Z0-9_/\\.]+\.py)\s+depend\s+on",
        r"what\s+does\s+([a-zA-Z0-9_/\\.]+\.py)\s+import",
        r"file\s+dependencies\s+(?:of|for)\s+([a-zA-Z0-9_/\\.]+\.py)",
    ]
    for pat in file_dep_patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            f_path = m.group(1).strip()
            return IntentClassification(
                intent=QuestionIntent.FILE_DEPENDENCIES,
                target_file=f_path,
                preferred_tools=["get_file_dependencies"],
            )

    # 7. DEFINITION Intent (Where is X defined?)
    def_patterns = [
        r"where\s+is\s+(?:the\s+)?([a-zA-Z0-9_.]+?)\s+(?:defined|declared|located)",
        r"where\s+is\s+the\s+definition\s+of\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"find\s+(?:the\s+)?(?:symbol|function|class|method)\s+([a-zA-Z0-9_.]+)",
    ]
    for pat in def_patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            sym = _clean_symbol_candidate(m.group(1))
            return IntentClassification(
                intent=QuestionIntent.DEFINITION,
                target_symbol=sym,
                preferred_tools=["find_symbol"],
            )

    # 8. EXPLANATION Intent (Explain X, What does X do?)
    explain_patterns = [
        r"^explain\s+(?:the\s+)?([a-zA-Z0-9_.]+?)(?:\s+function|\s+method|\s+class)?$",
        r"explain\s+(?:the\s+)?([a-zA-Z0-9_.]+?)(?:\s+function|\s+method|\s+class|\s+module)",
        r"what\s+does\s+(?:the\s+)?([a-zA-Z0-9_.]+?)\s+(?:do|perform)",
        r"how\s+does\s+(?:the\s+)?([a-zA-Z0-9_.]+?)\s+work",
    ]
    for pat in explain_patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            sym = _clean_symbol_candidate(m.group(1))
            return IntentClassification(
                intent=QuestionIntent.EXPLANATION,
                target_symbol=sym,
                preferred_tools=["find_symbol", "read_file"],
            )

    # Fallback to general SEARCH
    return IntentClassification(
        intent=QuestionIntent.SEARCH,
        preferred_tools=["search_code", "read_file"],
    )
