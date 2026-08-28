"""
DevPilot Change Risk Scoring Engine.

Computes a transparent, deterministic risk score (0-100) and risk level
(LOW, MEDIUM, HIGH, CRITICAL) for a set of code changes based on dependency
depth, affected modules, and symbol sensitivity.
"""

from typing import List
from app.changes.models import ChangeImpact, ChangedSymbol, ChangeRisk, RiskLevel, SymbolChangeType

CORE_MODULE_PREFIXES = (
    "app/graph/",
    "app/agent/",
    "app/api/",
    "app/main.py",
    "app/git/",
    "app/context/",
    "app/changes/",
    "app/vector_store/",
)


def calculate_change_risk(
    changed_files: List[str],
    changed_symbols: List[ChangedSymbol],
    impact: ChangeImpact,
) -> ChangeRisk:
    """
    Deterministically evaluates the risk of a code change.
    """
    # Edge case: No files or symbols changed
    if not changed_files and not changed_symbols:
        return ChangeRisk(
            score=0,
            level=RiskLevel.LOW.value,
            reasons=["No changes detected."],
        )

    # Check if this is a test-only change
    is_test_only = bool(changed_files) and all(
        f.startswith("tests/") or "test_" in f or f.endswith("_test.py") for f in changed_files
    )

    if is_test_only:
        test_score = min(15, len(changed_files) * 3 + len(changed_symbols) * 2)
        return ChangeRisk(
            score=test_score,
            level=RiskLevel.LOW.value,
            reasons=["Low risk: Only test suite files modified."],
        )

    score = 0
    reasons: List[str] = []

    # 1. Changed symbols factor (up to 20 pts)
    sym_count = len(changed_symbols)
    sym_pts = min(20, sym_count * 4)
    score += sym_pts
    if sym_count > 3:
        reasons.append(f"Multiple symbols modified ({sym_count} symbols).")

    # Deletions factor
    has_deletions = any(s.change_type == SymbolChangeType.DELETED.value for s in changed_symbols)
    if has_deletions:
        score += 10
        reasons.append("Symbol deletion detected; potential breaking change.")

    # 2. Direct dependents factor (up to 25 pts)
    direct_count = len(impact.direct_dependents)
    direct_pts = min(25, direct_count * 3)
    score += direct_pts
    if direct_count >= 8:
        reasons.append(f"High number of direct dependents ({direct_count} callers).")
    elif direct_count >= 3:
        reasons.append(f"Moderate number of direct dependents ({direct_count} callers).")

    # 3. Indirect dependents factor (up to 15 pts)
    indirect_count = len(impact.indirect_dependents)
    indirect_pts = min(15, int(indirect_count * 1.5))
    score += indirect_pts
    if indirect_count >= 10:
        reasons.append(f"Broad downstream ripple effects ({indirect_count} indirect callers).")

    # 4. Impacted files factor (up to 20 pts)
    all_files = set(changed_files) | set(impact.impacted_files)
    file_count = len(all_files)
    file_pts = min(20, file_count * 4)
    score += file_pts
    if file_count >= 5:
        reasons.append(f"Multiple modules affected ({file_count} files).")

    # 5. Core module sensitivity factor (up to 15 pts)
    core_files = [
        f for f in changed_files if any(f.startswith(prefix) for prefix in CORE_MODULE_PREFIXES)
    ]
    if core_files:
        score += 15
        reasons.append(f"Core architecture component modified ({', '.join(core_files[:2])}).")

    # Clamp score between 0 and 100
    final_score = max(0, min(100, score))

    # Map to risk level
    if final_score <= 25:
        level = RiskLevel.LOW.value
        if not reasons:
            reasons.append("Low risk: Isolated changes with minimal dependents.")
    elif final_score <= 55:
        level = RiskLevel.MEDIUM.value
    elif final_score <= 80:
        level = RiskLevel.HIGH.value
    else:
        level = RiskLevel.CRITICAL.value

    return ChangeRisk(
        score=final_score,
        level=level,
        reasons=reasons,
    )
