"""
Tests for DevPilot v1.7 Code Change Intelligence & Smart Impact Analysis.

Covers:
- Symbol-level change detection (added, modified, deleted, renamed)
- Static dependency impact calculation
- Deterministic change risk scoring (LOW, MEDIUM, HIGH, CRITICAL)
- CodeChangeAnalyzer orchestration
- Agent analyze_code_change tool
- Question intent classification for change questions
- API endpoints (POST /api/changes/analyze, GET /api/changes/analyze)
- CLI command execution
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.agent.intent import QuestionIntent, classify_question_intent
from app.agent.tools import create_analyze_code_change_tool
from app.changes.analyzer import CodeChangeAnalyzer
from app.changes.detector import detect_changed_symbols
from app.changes.models import (
    ChangeImpact,
    ChangeRisk,
    ChangedSymbol,
    CodeChangeAnalysis,
    RiskLevel,
    SymbolChangeType,
)
from app.changes.risk import calculate_change_risk
from app.git.repository import GitCommitNotFoundError, get_repository
from app.main import app, run_change_analyze


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).parent.parent.resolve()


@pytest.fixture
def repo(project_root: Path):
    return get_repository(project_root)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ==============================================================================
# 1. Change Models & Data Structure Tests
# ==============================================================================

def test_changed_symbol_model():
    sym = ChangedSymbol(
        name="GraphBuilder.build",
        file="app/graph/builder.py",
        change_type="modified",
        symbol_type="method",
        line_start=38,
        line_end=399,
    )
    data = sym.to_dict()
    assert data["name"] == "GraphBuilder.build"
    assert data["change_type"] == "modified"
    assert data["line_start"] == 38


def test_code_change_analysis_formatting():
    analysis = CodeChangeAnalysis(
        commit="a0635cd1234567890abcdef1234567890abcdef1",
        short_hash="a0635cd",
        author="DevPilot Tester",
        date="2026-08-28 12:00:00 UTC",
        message="feat: improve graph resolution",
        changed_files=["app/graph/builder.py"],
        changed_symbols=[
            ChangedSymbol(
                name="GraphBuilder.build",
                file="app/graph/builder.py",
                change_type="modified",
                symbol_type="method",
                line_start=38,
            )
        ],
        impact=ChangeImpact(
            direct_dependents=["_resolve_graph", "run_graph_build"],
            indirect_dependents=["find_symbol"],
            impacted_files=["app/agent/tools.py", "app/main.py"],
        ),
        risk=ChangeRisk(
            score=65,
            level="HIGH",
            reasons=["Core graph functionality changed", "High dependency count"],
        ),
    )
    text = analysis.to_formatted_text()
    assert "Commit:  a0635cd" in text
    assert "GraphBuilder.build" in text
    assert "Direct Dependents:   2" in text
    assert "Risk Level: HIGH (65/100)" in text


# ==============================================================================
# 2. Risk Scoring Formula Tests
# ==============================================================================

def test_risk_scoring_empty_change():
    risk = calculate_change_risk(
        changed_files=[],
        changed_symbols=[],
        impact=ChangeImpact(),
    )
    assert risk.score == 0
    assert risk.level == RiskLevel.LOW.value


def test_risk_scoring_test_only():
    risk = calculate_change_risk(
        changed_files=["tests/test_changes.py"],
        changed_symbols=[ChangedSymbol(name="test_foo", file="tests/test_changes.py")],
        impact=ChangeImpact(),
    )
    assert risk.score <= 15
    assert risk.level == RiskLevel.LOW.value
    assert "Only test suite files modified" in risk.reasons[0]


def test_risk_scoring_low_risk():
    risk = calculate_change_risk(
        changed_files=["app/utils/format.py"],
        changed_symbols=[ChangedSymbol(name="format_date", file="app/utils/format.py")],
        impact=ChangeImpact(
            direct_dependents=["get_date_string"],
            indirect_dependents=[],
            impacted_files=["app/utils/format.py"],
        ),
    )
    assert risk.score <= 25
    assert risk.level == RiskLevel.LOW.value


def test_risk_scoring_medium_risk():
    risk = calculate_change_risk(
        changed_files=["app/git/history.py"],
        changed_symbols=[
            ChangedSymbol(name="get_file_history", file="app/git/history.py"),
            ChangedSymbol(name="get_file_blame", file="app/git/history.py"),
        ],
        impact=ChangeImpact(
            direct_dependents=["git_history", "git_blame_symbol", "run_git_history"],
            indirect_dependents=["agent_run"],
            impacted_files=["app/agent/tools.py", "app/main.py"],
        ),
    )
    assert 26 <= risk.score <= 55
    assert risk.level == RiskLevel.MEDIUM.value


def test_risk_scoring_high_risk():
    risk = calculate_change_risk(
        changed_files=["app/graph/builder.py", "app/graph/store.py", "app/graph/models.py"],
        changed_symbols=[
            ChangedSymbol(name="GraphBuilder.build", file="app/graph/builder.py"),
            ChangedSymbol(name="GraphStore.add_edge", file="app/graph/store.py"),
            ChangedSymbol(name="GraphStore.get_node", file="app/graph/store.py"),
            ChangedSymbol(name="old_method", file="app/graph/store.py", change_type=SymbolChangeType.DELETED.value),
        ],
        impact=ChangeImpact(
            direct_dependents=[f"caller_{i}" for i in range(12)],
            indirect_dependents=[f"indirect_{i}" for i in range(15)],
            impacted_files=[f"file_{i}.py" for i in range(8)],
        ),
    )
    assert risk.score >= 56
    assert risk.level in (RiskLevel.HIGH.value, RiskLevel.CRITICAL.value)
    assert any("deletion" in r.lower() for r in risk.reasons)


# ==============================================================================
# 3. Change Detector Tests
# ==============================================================================

def test_detect_changed_symbols_head(repo):
    changed_files, changed_symbols = detect_changed_symbols(repo=repo, commit_hash="HEAD")
    assert isinstance(changed_files, list)
    assert isinstance(changed_symbols, list)


def test_detect_changed_symbols_invalid_commit(repo):
    with pytest.raises(GitCommitNotFoundError):
        detect_changed_symbols(repo=repo, commit_hash="invalid_commit_sha_12345")


# ==============================================================================
# 4. Code Change Analyzer Tests
# ==============================================================================

def test_code_change_analyzer_head(project_root: Path):
    analyzer = CodeChangeAnalyzer(project_root=project_root)
    analysis = analyzer.analyze_commit("HEAD")
    assert analysis.commit is not None
    assert len(analysis.short_hash) == 7
    assert analysis.author != ""
    assert isinstance(analysis.changed_files, list)
    assert isinstance(analysis.changed_symbols, list)
    assert analysis.impact is not None
    assert 0 <= analysis.risk.score <= 100
    assert analysis.risk.level in ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def test_code_change_analyzer_invalid_commit(project_root: Path):
    analyzer = CodeChangeAnalyzer(project_root=project_root)
    with pytest.raises(GitCommitNotFoundError):
        analyzer.analyze_commit("nonexistent_sha_0000000")


# ==============================================================================
# 5. Agent Tool Tests
# ==============================================================================

def test_analyze_code_change_tool(project_root: Path):
    tool_spec = create_analyze_code_change_tool(project_root=project_root)
    assert tool_spec["name"] == "analyze_code_change"
    res = tool_spec["func"](commit="HEAD")
    assert "data" in res
    assert "formatted_text" in res
    assert "sources" in res
    data = res["data"]
    assert "commit" in data
    assert "impact" in data
    assert "risk" in data


# ==============================================================================
# 6. Intent Classification Tests
# ==============================================================================

def test_classify_intent_code_change_analysis():
    queries = [
        "What changed in the last commit?",
        "What changed in the latest commit?",
        "What changed in commit a0635cd?",
        "What could this commit break?",
        "What could be affected by the changes in the latest commit?",
        "What functions are affected by this change?",
        "Is the latest commit risky?",
        "Show me the impact of the latest change.",
        "Which parts of the project are impacted by the latest commit?",
        "Why is this commit important?",
        "Who changed the code and what did their change affect?",
    ]
    for q in queries:
        c = classify_question_intent(q)
        assert c.intent == QuestionIntent.CODE_CHANGE_ANALYSIS, f"Failed for query: {q}"
        assert "analyze_code_change" in c.preferred_tools


# ==============================================================================
# 7. API Endpoints Tests
# ==============================================================================

def test_api_changes_analyze_post(client: TestClient):
    response = client.post("/api/changes/analyze", json={"commit": "HEAD"})
    assert response.status_code == 200
    data = response.json()
    assert "commit" in data
    assert "short_hash" in data
    assert "changed_files" in data
    assert "changed_symbols" in data
    assert "impact" in data
    assert "risk" in data
    assert data["risk"]["score"] >= 0


def test_api_changes_analyze_get(client: TestClient):
    response = client.get("/api/changes/analyze", params={"commit": "HEAD"})
    assert response.status_code == 200
    data = response.json()
    assert "commit" in data
    assert "impact" in data
    assert "risk" in data


def test_api_changes_analyze_invalid_commit(client: TestClient):
    response = client.post("/api/changes/analyze", json={"commit": "0000000000000000000000000000000000000000"})
    assert response.status_code == 404


# ==============================================================================
# 8. CLI Command Tests
# ==============================================================================

def test_cli_run_change_analyze(capsys):
    run_change_analyze(commit="HEAD", as_json=True)
    captured = capsys.readouterr()
    assert "commit" in captured.out
    assert "impact" in captured.out
    assert "risk" in captured.out
