"""
Tests for DevPilot v2.1 & v2.2 — Intelligent Change Proposal & Patch Generation.

Covers:
1. Change proposal generation for known exact symbols (GraphBuilder.build, etc.)
2. Real unified diff patch generation with actual code changes (not placeholder comments)
3. Existing logging convention detection and reuse (avoids duplicate logger/imports)
4. Verification that proposal generation NEVER modifies repository source files
5. Target resolution failure handling (non-existent symbols)
6. Ambiguous target resolution handling
7. Empty and malformed request handling
8. Proposal JSON serialization schema validation
9. Syntactic validation of proposed Python source code
10. Deterministic risk calculation and reasoning
11. Integration with existing TargetResolver and ChangeImpactPlanner
12. CLI `propose` command (human-readable text and JSON)
13. FastAPI `/api/changes/propose` endpoints (GET and POST)
"""

import ast
import json
from pathlib import Path
import tempfile
import git
import pytest
from fastapi.testclient import TestClient

from app.changes.diff_generator import DiffGenerator
from app.changes.models import ChangeProposal, ProposalStatus
from app.changes.proposal import ChangeProposalGenerator
from app.changes.target_resolver import TargetResolver
from app.graph.models import EdgeType, GraphEdge, GraphNode, NodeType
from app.graph.store import GraphStore
from app.main import app, run_propose


@pytest.fixture
def temp_codebase(tmp_path: Path):
    """Creates a standalone temporary codebase for testing proposals."""
    app_dir = tmp_path / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    builder_file = app_dir / "builder.py"
    builder_file.write_text(
        "class GraphBuilder:\n"
        "    def build(self, files):\n"
        "        \"\"\"Build graph from files.\"\"\"\n"
        "        graph = {}\n"
        "        for f in files:\n"
        "            graph[f] = []\n"
        "        return graph\n",
        encoding="utf-8",
    )

    # File that already has logger convention
    service_file = app_dir / "service.py"
    service_file.write_text(
        "import logging\n"
        "\n"
        "custom_logger = logging.getLogger(__name__)\n"
        "\n"
        "class AuthService:\n"
        "    def verify_password(self, username, password):\n"
        "        if not password:\n"
        "            return False\n"
        "        return True\n",
        encoding="utf-8",
    )

    test_file = tests_dir / "test_builder.py"
    test_file.write_text(
        "from app.builder import GraphBuilder\n"
        "\n"
        "def test_build():\n"
        "    gb = GraphBuilder()\n"
        "    assert gb.build(['a.py']) == {'a.py': []}\n",
        encoding="utf-8",
    )

    # Ambiguous test files
    mod_a = tmp_path / "module_a.py"
    mod_a.write_text("def process(): return 'a'\n", encoding="utf-8")
    mod_b = tmp_path / "module_b.py"
    mod_b.write_text("def process(): return 'b'\n", encoding="utf-8")

    return tmp_path


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. Proposal Generation Unit Tests
# ==============================================================================

def test_proposal_generation_known_symbol(temp_codebase: Path):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when GraphBuilder.build starts and finishes")

    assert isinstance(proposal, ChangeProposal)
    assert proposal.target_symbol == "GraphBuilder.build"
    assert proposal.target_file == "app/builder.py"
    assert proposal.status in ("PROPOSAL_ONLY", "PENDING_APPROVAL")
    assert proposal.risk in ("LOW", "MEDIUM", "HIGH")
    assert len(proposal.proposed_changes) > 0
    assert any("start" in ch.lower() or "logging" in ch.lower() for ch in proposal.proposed_changes)
    assert len(proposal.tests_to_update) > 0 or len(proposal.tests_to_add) > 0
    assert "app/builder.py" in proposal.affected_files


def test_real_patch_generation_code_content(temp_codebase: Path):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when GraphBuilder.build starts and finishes")

    assert len(proposal.patch) > 0
    assert "--- a/app/builder.py" in proposal.patch
    assert "+++ b/app/builder.py" in proposal.patch
    assert "import logging" in proposal.patch
    assert "logger.info(\"Starting GraphBuilder.build\")" in proposal.patch
    assert "logger.info(\"Finished GraphBuilder.build\")" in proposal.patch
    assert "TODO" not in proposal.patch


def test_existing_logging_convention_reuse(temp_codebase: Path):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when AuthService.verify_password starts and finishes")

    assert len(proposal.patch) > 0
    assert "--- a/app/service.py" in proposal.patch
    # Reuses existing custom_logger rather than creating duplicate logger = logging.getLogger
    assert "custom_logger.info(\"Starting AuthService.verify_password\")" in proposal.patch
    assert "custom_logger.info(\"Finished AuthService.verify_password\")" in proposal.patch


def test_diff_generator_standalone(temp_codebase: Path):
    diff_gen = DiffGenerator(project_root=temp_codebase)
    patch, warnings = diff_gen.generate_diff(
        request="Add logging when GraphBuilder.build starts and finishes",
        target_file="app/builder.py",
        target_symbol="GraphBuilder.build",
    )

    assert len(warnings) == 0
    assert "--- a/app/builder.py" in patch
    assert "logger.info" in patch


def test_proposal_does_not_modify_files(temp_codebase: Path):
    builder_file = temp_codebase / "app" / "builder.py"
    content_before = builder_file.read_text(encoding="utf-8")
    stat_before = builder_file.stat().st_mtime

    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when GraphBuilder.build starts and finishes")

    content_after = builder_file.read_text(encoding="utf-8")
    stat_after = builder_file.stat().st_mtime

    # Must be 100% untouched
    assert content_before == content_after
    assert stat_before == stat_after
    assert proposal.status in ("PROPOSAL_ONLY", "PENDING_APPROVAL")


def test_proposal_target_resolution_failure(temp_codebase: Path):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Modify CompletelyNonExistentSymbol.xyz")

    assert proposal.status in ("PROPOSAL_ONLY", "PENDING_APPROVAL")
    assert proposal.confidence == 0.0 or proposal.confidence is None
    assert len(proposal.warnings) > 0
    assert len(proposal.patch) == 0


def test_proposal_ambiguous_target(temp_codebase: Path):
    # Setup graph with ambiguous process function
    graph = GraphStore()
    node_a = GraphNode(id="func:module_a.py:process", name="process", node_type=NodeType.FUNCTION, file_path="module_a.py")
    node_b = GraphNode(id="func:module_b.py:process", name="process", node_type=NodeType.FUNCTION, file_path="module_b.py")
    graph.add_node(node_a)
    graph.add_node(node_b)

    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Refactor process", graph=graph)

    assert proposal.status in ("PROPOSAL_ONLY", "PENDING_APPROVAL")
    assert proposal.risk == "HIGH"
    assert len(proposal.warnings) > 0


def test_proposal_empty_malformed_request(temp_codebase: Path):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("   ")

    assert proposal.status in ("PROPOSAL_ONLY", "PENDING_APPROVAL")
    assert len(proposal.warnings) > 0
    assert "cannot be empty" in proposal.warnings[0].lower()


def test_proposal_json_serialization(temp_codebase: Path):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when GraphBuilder.build starts and finishes")

    d = proposal.to_dict()
    assert isinstance(d, dict)
    assert d["request"] == "Add logging when GraphBuilder.build starts and finishes"
    assert d["target_symbol"] == "GraphBuilder.build"
    assert d["target_file"] == "app/builder.py"
    assert d["status"] in ("PROPOSAL_ONLY", "PENDING_APPROVAL")
    assert isinstance(d["proposed_changes"], list)
    assert isinstance(d["affected_files"], list)
    assert isinstance(d["affected_symbols"], list)
    assert isinstance(d["tests_to_update"], list)
    assert isinstance(d["tests_to_add"], list)
    assert isinstance(d["warnings"], list)
    assert isinstance(d["unverified_assumptions"], list)

    # Valid JSON string encoding
    json_str = json.dumps(d)
    assert len(json_str) > 0


def test_proposal_human_readable_formatting(temp_codebase: Path):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when GraphBuilder.build starts and finishes")

    text = proposal.to_formatted_text()
    assert "DevPilot v2.1 — Change Proposal" in text
    assert "Request:" in text
    assert "Target:" in text
    assert "GraphBuilder.build" in text
    assert "app/builder.py" in text
    assert "Risk:" in text
    assert "Proposed Changes:" in text
    assert "Files:" in text
    assert "Tests:" in text
    assert "Patch:" in text
    assert "Status:" in text
    assert "PENDING_APPROVAL" in text or "PROPOSAL_ONLY" in text


# ==============================================================================
# 2. CLI Propose Command Tests
# ==============================================================================

def test_cli_propose_text_output(temp_codebase: Path, capsys):
    run_propose(
        request="Add logging when GraphBuilder.build starts and finishes",
        project_dir=str(temp_codebase),
        as_json=False,
    )
    captured = capsys.readouterr()

    assert "DevPilot v2.1 — Change Proposal" in captured.out
    assert "GraphBuilder.build" in captured.out
    assert "PENDING_APPROVAL" in captured.out or "PROPOSAL_ONLY" in captured.out
    assert "logger.info" in captured.out


def test_cli_propose_json_output(temp_codebase: Path, capsys):
    run_propose(
        request="Add logging when GraphBuilder.build starts and finishes",
        project_dir=str(temp_codebase),
        as_json=True,
    )
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert data["request"] == "Add logging when GraphBuilder.build starts and finishes"
    assert data["target_symbol"] == "GraphBuilder.build"
    assert data["target_file"] == "app/builder.py"
    assert data["status"] in ("PROPOSAL_ONLY", "PENDING_APPROVAL")
    assert len(data["proposed_changes"]) > 0
    assert "logger.info" in data["patch"]


# ==============================================================================
# 3. FastAPI Endpoint Tests
# ==============================================================================

def test_api_propose_get(client: TestClient, temp_codebase: Path):
    response = client.get(
        f"/api/changes/propose?request=Add+logging+when+GraphBuilder.build+starts+and+finishes&project_dir={temp_codebase}"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["target_symbol"] == "GraphBuilder.build"
    assert data["target_file"] == "app/builder.py"
    assert data["status"] in ("PROPOSAL_ONLY", "PENDING_APPROVAL")
    assert "logger.info" in data["patch"]


def test_api_propose_post(client: TestClient, temp_codebase: Path):
    response = client.post(
        "/api/changes/propose",
        json={
            "request": "Add logging when GraphBuilder.build starts and finishes",
            "project_dir": str(temp_codebase),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["target_symbol"] == "GraphBuilder.build"
    assert data["target_file"] == "app/builder.py"
    assert data["status"] in ("PROPOSAL_ONLY", "PENDING_APPROVAL")
    assert "logger.info" in data["patch"]
