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
    AUTONOMOUS_FIX = "AUTONOMOUS_FIX"
    REVIEW_CHANGES = "REVIEW_CHANGES"
    CODE_CHANGE_ANALYSIS = "CODE_CHANGE_ANALYSIS"
    GIT_CHANGE_AND_IMPACT = "GIT_CHANGE_AND_IMPACT"
    GIT_LAST_CHANGE = "GIT_LAST_CHANGE"
    GIT_HISTORY = "GIT_HISTORY"
    GIT_BLAME = "GIT_BLAME"
    GIT_SHOW_COMMIT = "GIT_SHOW_COMMIT"
    CALLERS_AND_CALLEES = "CALLERS_AND_CALLEES"
    CALLEES = "CALLEES"
    CALLERS = "CALLERS"
    DEPENDENCIES = "DEPENDENCIES"
    DEPENDENTS = "DEPENDENTS"
    FILE_DEPENDENCIES = "FILE_DEPENDENCIES"
    DEFINITION = "DEFINITION"
    EXPLANATION = "EXPLANATION"
    REPOSITORY_CONTEXT = "REPOSITORY_CONTEXT"
    CHANGE_PLAN = "CHANGE_PLAN"
    SEMANTIC_SEARCH = "SEMANTIC_SEARCH"
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
    prefixes = (
        "the ", "a ", "an ", "function ", "method ", "class ", "module ",
        "modifying ", "refactoring ", "improving ", "changing ", "updating ",
        "fixing ", "what would be affected if ", "what could be affected if ",
        "what breaks if ", "what changes if ", "if ",
    )
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                changed = True
    # Strip common trailing suffixes
    suffixes = (
        " function", " method", " class", " module", " to improve graph construction",
        " to improve performance", " performance", " speed", " logic", " implementation",
        " changes", " breaks", " is modified", " is updated", " is changed",
    )
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if cleaned.lower().endswith(suffix):
                cleaned = cleaned[:-len(suffix)].strip()
                changed = True
    return cleaned.strip().strip("'\"`?,.:;()[]{}")


def classify_question_intent(question: str) -> IntentClassification:
    """
    Classifies a natural language question into an actionable intent and extracts target symbols.
    """
    if not question or not question.strip():
        return IntentClassification(intent=QuestionIntent.SEARCH, preferred_tools=["search_code"])

    q = question.strip()
    q_lower = q.lower()

    # 0a. CODE_CHANGE_ANALYSIS Intent (v1.7)
    code_change_patterns = [
        (r"(?:what|which\s+symbols?)\s+changed\s+in\s+(?:the\s+)?(?:last|latest)\s+commit", "HEAD"),
        (r"(?:what|which\s+symbols?)\s+changed\s+in\s+commit\s+([a-fA-F0-9]{4,40}|HEAD)", None),
        (r"(?:what\s+could|what\s+can|what\s+might|what\s+breaks|what\s+would)\s+(?:the\s+)?(?:latest|last|this)?\s*commit\s*(?:break|affect|impact)", "HEAD"),
        (r"what\s+could\s+be\s+affected\s+by\s+(?:the\s+changes\s+in\s+)?(?:the\s+)?(?:latest|last|this)?\s*commit", "HEAD"),
        (r"(?:what\s+functions|what\s+symbols|what\s+classes)\s+are\s+affected\s+by\s+(?:this|the\s+latest|the\s+last)?\s*(?:change|commit)", "HEAD"),
        (r"is\s+(?:the\s+)?(?:latest|last|this)?\s*commit\s+risky", "HEAD"),
        (r"(?:show\s+me\s+)?(?:the\s+)?impact\s+of\s+(?:the\s+)?(?:latest|last|this)\s+(?:change|commit)", "HEAD"),
        (r"which\s+parts\s+of\s+the\s+project\s+are\s+impacted(?:\s+by\s+(?:the\s+)?(?:latest|last|this)?\s*commit)?", "HEAD"),
        (r"why\s+is\s+(?:this|the\s+latest|the\s+last)\s+commit\s+important", "HEAD"),
        (r"who\s+changed\s+the\s+code\s+and\s+what\s+did\s+(?:their|the)\s+change\s+affect", "HEAD"),
    ]
    for pat, default_commit in code_change_patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            c_val = m.group(1).strip() if m.groups() and m.group(1) else default_commit
            return IntentClassification(
                intent=QuestionIntent.CODE_CHANGE_ANALYSIS,
                target_symbol=c_val,
                preferred_tools=["analyze_code_change"],
            )

    # 0b. REVIEW_CHANGES Intent (v1.8)
    review_change_patterns = [
        r"^(?:review|inspect|summarize|analyze)\s+(?:my\s+|the\s+|all\s+)?(?:current\s+|uncommitted\s+|working\s+tree\s+|local\s+)?(?:changes|diff|modifications|work)",
        r"^what\s+(?:is|are|will\s+be|could\s+be)\s+affected\s+by\s+(?:my\s+|the\s+)?(?:current\s+|uncommitted\s+|local\s+)?changes",
        r"^what\s+tests?\s+(?:should|do|must|can)\s+(?:i|we)\s+run\s+(?:for|on)\s+(?:my\s+|the\s+)?(?:current\s+|uncommitted\s+|local\s+)?changes",
        r"^what\s+tests?\s+cover\s+(?:my\s+|the\s+)?(?:current\s+|uncommitted\s+|local\s+)?changes",
        r"^what\s+changed\s+in\s+(?:my\s+|the\s+)?(?:working\s+tree|local\s+repository|local\s+branch|workspace)",
        r"^what\s+are\s+my\s+(?:current\s+|uncommitted\s+|local\s+)?changes",
        r"^(?:show|get|display)\s+(?:my\s+|the\s+)?(?:current\s+|uncommitted\s+)?git\s+(?:changes|diff|status)",
    ]
    for pat in review_change_patterns:
        if re.search(pat, q, re.IGNORECASE):
            return IntentClassification(
                intent=QuestionIntent.REVIEW_CHANGES,
                preferred_tools=["review_changes"],
            )

    # 0c. AUTONOMOUS_FIX Intent (v1.9)
    # "Analyze this bug but don't change anything", "Prepare a patch for this issue", "Fix this issue automatically and run the tests", "Fix the bug in GraphBuilder.build"
    fix_patterns = [
        (r"^(?:analyze|inspect)\s+(?:this\s+)?(?:bug|issue|problem|error|failure)\s+but\s+don'?t\s+change\s+anything", "plan"),
        (r"^prepare\s+(?:a\s+)?patch\s+(?:for|to)\s+(?:this\s+)?(?:issue|bug|problem|error|failure|task|request)?\s*(.*)", "patch"),
        (r"^(?:generate|create)\s+(?:a\s+)?patch\s+(?:for|to)\s+(.*)", "patch"),
        (r"^fix\s+(?:this\s+)?(?:issue|bug|problem|error|failure)\s+(?:automatically|auto)\s*(?:and\s+run\s+(?:the\s+)?tests?)?", "auto"),
        (r"^(?:automatically|auto)\s+fix\s+(.*)", "auto"),
        (r"^fix\s+(?:the\s+)?(?:bug|issue|problem|error|failure|regression)\s+in\s+([a-zA-Z0-9_.]+(?:\.[a-zA-Z0-9_]+)?)", "plan"),
    ]
    for pat, fix_mode in fix_patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            sym_raw = m.group(1).strip() if m.groups() and m.group(1) else ""
            sym = _clean_symbol_candidate(sym_raw) if sym_raw else None
            return IntentClassification(
                intent=QuestionIntent.AUTONOMOUS_FIX,
                target_symbol=sym,
                preferred_tools=["autonomous_fix"],
            )

    # 0b. CHANGE_PLAN Intent (v1.7/v1.8)
    # "Plan changes for X", "How should I refactor X?", "Improve GraphBuilder.build performance", "What is the plan to change X?"
    plan_patterns = [
        r"^(?:create|generate|build|provide|make)?\s*(?:a\s+)?change\s+plan\s+(?:for|to|on)\s+(?:modifying\s+|refactoring\s+|improving\s+|updating\s+)?(.+)",
        r"^(?:plan|how\s+to\s+plan)\s+(?:changes?\s+(?:for|to|in)|refactoring\s+(?:of|for)|modification\s+(?:of|for))\s+(.+)",
        r"^how\s+(?:should|can|do)\s+(?:i|we)\s+(?:refactor|change|modify|improve|update)\s+(.+)",
        r"^plan\s+(?:to\s+)?(?:improve|refactor|change|modify|update|optimize)\s+(.+)",
        r"^(?:improve|optimize|refactor)\s+([a-zA-Z0-9_.]+(?:\.[a-zA-Z0-9_]+)?)\s+(?:performance|speed|implementation|logic)",
        r"^(?:improve|optimize|refactor|modify|update|change)\s+([a-zA-Z0-9_.]+(?:\.[a-zA-Z0-9_]+)?)$",
        r"^what\s+(?:is|would\s+be)\s+the\s+(?:implementation\s+)?plan\s+(?:to|for)\s+(?:change|refactor|improve|modify)\s+(.+)",
        r"^i\s+want\s+to\s+(?:modify|change|refactor|improve|update)\s+(.+)",
    ]
    for pat in plan_patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            sym = _clean_symbol_candidate(m.group(1))
            return IntentClassification(
                intent=QuestionIntent.CHANGE_PLAN,
                target_symbol=sym,
                preferred_tools=["plan_code_change"],
            )

    # 1. GIT_CHANGE_AND_IMPACT Intent
    # "What changed around X and what could be affected?", "What changed in X and what could break?"
    git_impact_patterns = [
        r"what\s+changed\s+(?:around|in|to)\s+(?:the\s+)?([a-zA-Z0-9_.]+?)\s+and\s+what\s+(?:could|would|might|can)?\s*(?:be\s+affected|break)",
        r"what\s+changed\s+(?:around|in|to)\s+(?:the\s+)?([a-zA-Z0-9_.]+?)\s+and\s+its\s+impact",
        r"impact\s+of\s+changes?\s+(?:to|in|around)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
    ]
    for pat in git_impact_patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            sym = _clean_symbol_candidate(m.group(1))
            return IntentClassification(
                intent=QuestionIntent.GIT_CHANGE_AND_IMPACT,
                target_symbol=sym,
                preferred_tools=["find_symbol", "git_last_change", "get_impact"],
            )

    # 2. GIT_LAST_CHANGE Intent
    # "Who last changed X?", "When was X modified?", "Who introduced X?"
    last_change_patterns = [
        r"who\s+(?:last\s+)?(?:changed|modified|updated|edited|touched)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"who\s+(?:introduced|added|created)\s+(?:the\s+)?(?:current\s+implementation\s+of\s+)?([a-zA-Z0-9_.]+)",
        r"when\s+was\s+(?:the\s+)?([a-zA-Z0-9_.]+?)\s+(?:last\s+)?(?:changed|modified|updated|created|introduced)",
        r"what\s+commit\s+(?:introduced|added|created|modified|changed)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"last\s+change\s+(?:to|for|in|of)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
    ]
    for pat in last_change_patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            sym = _clean_symbol_candidate(m.group(1))
            return IntentClassification(
                intent=QuestionIntent.GIT_LAST_CHANGE,
                target_symbol=sym,
                preferred_tools=["find_symbol", "git_last_change"],
            )

    # 3. GIT_HISTORY Intent
    # "Show me the history of X", "Commit history of X"
    history_patterns = [
        r"(?:show|get|display|view)\s+(?:me\s+)?(?:the\s+)?history\s+(?:of\s+changes\s+for|of|for)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"(?:commit|git|change)\s+history\s+(?:of|for)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"history\s+(?:of\s+changes\s+for|of|for)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
    ]
    for pat in history_patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            sym = _clean_symbol_candidate(m.group(1))
            return IntentClassification(
                intent=QuestionIntent.GIT_HISTORY,
                target_symbol=sym,
                preferred_tools=["find_symbol", "git_history"],
            )

    # 4. GIT_BLAME Intent
    # "Who wrote X?", "Who is the likely owner/contributor of X?"
    blame_patterns = [
        r"who\s+(?:wrote|authored)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"who\s+is\s+the\s+(?:likely\s+)?(?:owner|author|contributor)\s+(?:of|for)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"who\s+owns\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"blame\s+(?:for|of|on)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
    ]
    for pat in blame_patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            sym = _clean_symbol_candidate(m.group(1))
            return IntentClassification(
                intent=QuestionIntent.GIT_BLAME,
                target_symbol=sym,
                preferred_tools=["find_symbol", "git_blame_symbol"],
            )

    # 5. GIT_SHOW_COMMIT Intent
    # "What changed in commit X?", "Show commit X"
    show_commit_patterns = [
        r"(?:what\s+changed\s+in|show|details\s+of|inspect)\s+commit\s+([a-fA-F0-9]{4,40}|HEAD|\^[\w]+)",
        r"which\s+files\s+were\s+changed\s+by\s+(?:commit\s+)?([a-fA-F0-9]{4,40})",
        r"commit\s+([a-fA-F0-9]{7,40})\s+(?:details|summary|changes)",
    ]
    for pat in show_commit_patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            c_hash = m.group(1).strip()
            return IntentClassification(
                intent=QuestionIntent.GIT_SHOW_COMMIT,
                target_symbol=c_hash,
                preferred_tools=["git_show_commit"],
            )

    # 1. IMPACT Intent
    # "What could be affected if X changes?", "What is the impact of changing X?", "What breaks if X changes?", "Explain the impact of X"
    impact_patterns = [
        r"(?:explain\s+)?what\s+(?:could|would|might|can)?\s*be\s+affected\s+if\s+(?:the\s+)?([a-zA-Z0-9_.]+?)(?:\s+function|\s+method|\s+class)?\s+changes",
        r"(?:explain\s+)?what\s+(?:could|would|might|can)?\s*break\s+if\s+(?:the\s+)?([a-zA-Z0-9_.]+?)(?:\s+function|\s+method|\s+class)?\s+changes",
        r"(?:explain\s+)?(?:what\s+is\s+)?(?:the\s+)?impact\s+(?:analysis\s+)?(?:of|for|on)\s+(?:the\s+)?(?:changing\s+|modifying\s+|updating\s+)?([a-zA-Z0-9_.]+)",
        r"what\s+is\s+the\s+impact\s+of\s+(?:changing|modifying|updating)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
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

    # 2. CALLERS_AND_CALLEES Intent (Combined callers & callees)
    combined_patterns = [
        r"what\s+(?:are\s+)?(?:the\s+)?callers\s+and\s+callees\s+(?:of|for)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"what\s+(?:are\s+)?(?:the\s+)?callees\s+and\s+callers\s+(?:of|for)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"callers\s+and\s+callees\s+(?:of|for)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"callees\s+and\s+callers\s+(?:of|for)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"who\s+calls\s+([a-zA-Z0-9_.]+?)(?:\s+function|\s+method|\s+class)?\s+and\s+what\s+does\s+(?:it|\1)\s+call",
        r"what\s+calls\s+([a-zA-Z0-9_.]+?)(?:\s+function|\s+method|\s+class)?\s+and\s+what\s+does\s+(?:it|\1)\s+call",
        r"what\s+does\s+([a-zA-Z0-9_.]+?)\s+call\s+and\s+who\s+calls\s+(?:it|\1)",
        r"incoming\s+and\s+outgoing\s+calls?\s+(?:of|for|to)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"outgoing\s+and\s+incoming\s+calls?\s+(?:of|for|to)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
    ]
    for pat in combined_patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            sym = _clean_symbol_candidate(m.group(1))
            return IntentClassification(
                intent=QuestionIntent.CALLERS_AND_CALLEES,
                target_symbol=sym,
                preferred_tools=["find_symbol", "get_callers", "get_callees"],
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

    # 8. REPOSITORY_CONTEXT Intent (tests covering X, context for X, history/repo intelligence)
    context_patterns = [
        r"(?:which|what)\s+tests?\s+(?:cover|test)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"tests?\s+(?:covering|for)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"(?:what|show|get)\s+(?:is\s+the\s+)?(?:repository\s+)?context\s+(?:for|of|on)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
        r"why\s+was\s+(?:the\s+)?([a-zA-Z0-9_.]+?)\s+(?:changed|modified|updated)",
        r"repository\s+intelligence\s+(?:for|on|about)\s+(?:the\s+)?([a-zA-Z0-9_.]+)",
    ]
    for pat in context_patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            sym = _clean_symbol_candidate(m.group(1))
            return IntentClassification(
                intent=QuestionIntent.REPOSITORY_CONTEXT,
                target_symbol=sym,
                preferred_tools=["get_repository_context"],
            )

    # 9. EXPLANATION Intent (Explain X, What does X do?)
    explain_patterns = [
        r"^explain\s+(?:the\s+)?([a-zA-Z0-9_.]+?)(?:\s+function|\s+method|\s+class)?$",
        r"explain\s+(?:the\s+)?([a-zA-Z0-9_.]+?)(?:\s+function|\s+method|\s+class|\s+module)",
        r"what\s+does\s+(?:the\s+)?([a-zA-Z0-9_.]+?)\s+(?:do|perform)",
        r"how\s+does\s+(?:the\s+)?([a-zA-Z0-9_.]+?)\s+work$",
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

    # 10. SEMANTIC_SEARCH Intent (v1.8)
    semantic_patterns = [
        r"where\s+is\s+(.+?)\s+handled",
        r"where\s+(?:do\s+we|can\s+we)\s+handle\s+(.+)",
        r"where\s+are\s+(.+?)\s+(?:validated|handled|processed|managed)",
        r"where\s+is\s+(.+?)\s+(?:implemented|located|found)",
        r"find\s+code\s+related\s+to\s+(.+)",
        r"find\s+(?:the\s+)?implementation\s+(?:related\s+to|responsible\s+for|for)\s+(.+)",
        r"which\s+code\s+is\s+responsible\s+for\s+(.+)",
        r"which\s+(?:code|part\s+of\s+the\s+code)\s+handles\s+(.+)",
        r"how\s+does\s+(?:the\s+)?(.+?)\s+(?:get\s+built|get\s+created|work)",
        r"show\s+(?:me\s+)?code\s+related\s+to\s+(.+)",
        r"show\s+(?:me\s+)?(?:the\s+)?implementation\s+(?:of|for|related\s+to)\s+(.+)",
    ]
    for pat in semantic_patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            query_topic = m.group(1).strip().strip("'\"`?,.:;")
            return IntentClassification(
                intent=QuestionIntent.SEMANTIC_SEARCH,
                target_symbol=query_topic,
                preferred_tools=["semantic_code_search"],
            )

    # Fallback to general SEARCH
    return IntentClassification(
        intent=QuestionIntent.SEARCH,
        preferred_tools=["semantic_code_search", "search_code", "read_file"],
    )

