"""
Tests for DevPilot v1.6 Agent Answer Verification & Evidence Grounding.

Covers:
1. Fully supported answer (High confidence, verified evidence, 0 unverified claims)
2. Partially supported answer (Medium confidence, unverified claim recorded)
3. Unsupported / speculative claims (e.g. invented cryptographic algorithms, unverified token generation)
4. Duplicate / similar semantic search results (unproven duplicate file identity claims)
5. Missing source evidence (Low confidence, unverified flag)
6. Graph-based evidence grounding (Callers, callees, dependencies)
7. Semantic-search evidence grounding (Ranked semantic code results)
8. Mixed graph + semantic search evidence integration
"""

import pytest

from app.agent.state import AgentState
from app.agent.verifier import (
    AgentAnswerVerifier,
    EvidenceItem,
    VerificationConfidence,
    VerificationResult,
    verify_agent_answer,
)


@pytest.fixture
def verifier() -> AgentAnswerVerifier:
    return AgentAnswerVerifier()


# ==============================================================================
# 1. Fully Supported Answer Tests
# ==============================================================================

def test_fully_supported_answer(verifier: AgentAnswerVerifier):
    state = AgentState(
        user_question="Where is AuthService implemented?",
        sources=[
            {
                "file_path": "auth.py",
                "symbol_name": "AuthService",
                "start_line": 4,
                "end_line": 12,
                "source_type": "code",
                "score": 0.88,
            }
        ],
        tool_results=[
            {
                "success": True,
                "data": [
                    {
                        "file_path": "auth.py",
                        "symbol_name": "AuthService",
                        "start_line": 4,
                        "end_line": 12,
                        "code": "class AuthService:\n    def hash_password(self): pass",
                    }
                ],
            }
        ],
    )

    answer = "AuthService is defined in auth.py at lines 4-12 and contains password hashing utilities."
    res = verifier.verify(answer, state)

    assert res.confidence == VerificationConfidence.HIGH
    assert res.is_grounded is True
    assert len(res.unverified_claims) == 0
    assert len(res.evidence) >= 1
    assert res.evidence[0].file == "auth.py"
    assert res.evidence[0].symbol == "AuthService"
    assert res.evidence[0].lines == "4-12"

    formatted = res.to_formatted_string()
    assert "Answer:" in formatted
    assert "Evidence:" in formatted
    assert "Confidence:\nHigh" in formatted
    assert "Unverified:" not in formatted


# ==============================================================================
# 2. Partially Supported Answer Tests
# ==============================================================================

def test_partially_supported_answer_with_usage_assumption(verifier: AgentAnswerVerifier):
    state = AgentState(
        user_question="Where is AuthService implemented?",
        sources=[
            {
                "file_path": "auth.py",
                "symbol_name": "AuthService",
                "start_line": 4,
                "end_line": 12,
                "source_type": "code",
            }
        ],
        tool_results=[
            {
                "success": True,
                "data": [{"file_path": "auth.py", "symbol_name": "AuthService", "start_line": 4, "end_line": 12}],
            }
        ],
    )

    answer = (
        "AuthService is in auth.py (lines 4-12).\n"
        "This function is used across the sample project and called during login flows by other modules."
    )
    res = verifier.verify(answer, state)

    assert res.confidence == VerificationConfidence.MEDIUM
    assert len(res.unverified_claims) > 0
    assert any("caller evidence" in c.lower() for c in res.unverified_claims)
    formatted = res.to_formatted_string()
    assert "Unverified:" in formatted
    assert "caller evidence" in formatted


# ==============================================================================
# 3. Unsupported Speculative Claims Tests
# ==============================================================================

def test_unsupported_cryptographic_algorithm_claim(verifier: AgentAnswerVerifier):
    state = AgentState(
        user_question="How does password hashing work?",
        sources=[
            {
                "file_path": "auth.py",
                "symbol_name": "AuthService.hash_password",
                "start_line": 8,
                "end_line": 9,
                "source_type": "code",
            }
        ],
        tool_results=[
            {
                "success": True,
                "data": [
                    {
                        "file_path": "auth.py",
                        "symbol_name": "AuthService.hash_password",
                        "start_line": 8,
                        "end_line": 9,
                        "code": "def hash_password(self, pwd):\n    return str(pwd)",
                    }
                ],
            }
        ],
    )

    answer = "AuthService.hash_password uses a cryptographic hash (e.g., bcrypt or PBKDF2) for secure token generation."
    res = verifier.verify(answer, state)

    assert len(res.unverified_claims) > 0
    assert any("cryptographic" in c.lower() or "token" in c.lower() for c in res.unverified_claims)
    assert "bcrypt" not in res.verified_answer
    assert "PBKDF2" not in res.verified_answer


# ==============================================================================
# 4. Duplicate / Similar Semantic Search Results Tests
# ==============================================================================

def test_unproven_duplicate_identity_claim(verifier: AgentAnswerVerifier):
    state = AgentState(
        user_question="Where is authentication handled?",
        sources=[
            {"file_path": "auth.py", "symbol_name": "AuthService", "start_line": 4, "end_line": 12},
            {"file_path": "sample_project/auth.py", "symbol_name": "AuthService", "start_line": 4, "end_line": 12},
        ],
        tool_results=[
            {
                "success": True,
                "data": {
                    "results": [
                        {"file": "auth.py", "symbol": "AuthService", "start_line": 4, "end_line": 12},
                        {"file": "sample_project/auth.py", "symbol": "AuthService", "start_line": 4, "end_line": 12},
                    ]
                },
            }
        ],
    )

    answer = (
        "AuthService is in auth.py.\n"
        "An identical class appears in sample_project/auth.py (duplicate copy) with identical symbols, indicating the same authentication implementation."
    )
    res = verifier.verify(answer, state)

    assert len(res.unverified_claims) > 0
    assert any("duplicate" in c.lower() or "comparison" in c.lower() for c in res.unverified_claims)


# ==============================================================================
# 5. Missing Source Evidence Tests
# ==============================================================================

def test_missing_source_evidence(verifier: AgentAnswerVerifier):
    state = AgentState(
        user_question="Where is database pooling handled?",
        sources=[],
        tool_results=[],
    )

    answer = "Database pooling is handled in app/db/pool.py."
    res = verifier.verify(answer, state)

    assert res.confidence == VerificationConfidence.LOW
    assert res.is_grounded is False
    assert len(res.evidence) == 0
    assert len(res.unverified_claims) > 0
    assert "No direct codebase evidence" in res.unverified_claims[0]


# ==============================================================================
# 6. Graph-Based Evidence Grounding Tests
# ==============================================================================

def test_graph_based_evidence(verifier: AgentAnswerVerifier):
    state = AgentState(
        user_question="What are the callers of GraphBuilder.build?",
        sources=[],
        tool_calls=[{"tool": "get_callers", "arguments": {"symbol": "GraphBuilder.build"}}],
        tool_results=[
            {
                "success": True,
                "data": [
                    {
                        "caller_name": "run_cli",
                        "caller_file": "app/main.py",
                        "caller_line": 45,
                        "relationship": "calls",
                    }
                ],
                "sources": [
                    {
                        "file_path": "app/main.py",
                        "symbol_name": "run_cli",
                        "start_line": 45,
                        "end_line": 45,
                        "relationship": "calls",
                        "source_type": "graph",
                    }
                ],
            }
        ],
    )

    answer = "GraphBuilder.build is called by run_cli in app/main.py at line 45."
    res = verifier.verify(answer, state)

    assert res.confidence == VerificationConfidence.HIGH
    assert len(res.evidence) >= 1
    assert res.evidence[0].file == "app/main.py"
    assert res.evidence[0].symbol == "run_cli"
    assert res.evidence[0].lines == "45-45"
    assert "calls" in res.evidence[0].reason


# ==============================================================================
# 7. Semantic Search Evidence Grounding Tests
# ==============================================================================

def test_semantic_search_evidence(verifier: AgentAnswerVerifier):
    state = AgentState(
        user_question="Find code related to dependency graph",
        sources=[],
        tool_results=[
            {
                "success": True,
                "data": {
                    "results": [
                        {
                            "file": "app/graph/builder.py",
                            "symbol": "GraphBuilder.build",
                            "start_line": 38,
                            "end_line": 328,
                            "score": 0.92,
                            "reason": "Primary builder for dependency graph",
                        }
                    ]
                },
            }
        ],
    )

    answer = "Dependency graph construction is handled by GraphBuilder.build in app/graph/builder.py (lines 38-328)."
    res = verifier.verify(answer, state)

    assert res.confidence == VerificationConfidence.HIGH
    assert len(res.evidence) >= 1
    assert res.evidence[0].file == "app/graph/builder.py"
    assert res.evidence[0].symbol == "GraphBuilder.build"
    assert res.evidence[0].lines == "38-328"
    assert "Primary builder" in res.evidence[0].reason


# ==============================================================================
# 8. Mixed Graph + Semantic Evidence Tests
# ==============================================================================

def test_mixed_graph_and_semantic_evidence(verifier: AgentAnswerVerifier):
    state = AgentState(
        user_question="Where is authentication handled and what calls it?",
        sources=[
            {
                "file_path": "auth.py",
                "symbol_name": "AuthService.verify_password",
                "start_line": 11,
                "end_line": 12,
                "score": 0.85,
                "source_type": "semantic",
            },
            {
                "file_path": "app/main.py",
                "symbol_name": "login_handler",
                "start_line": 120,
                "end_line": 140,
                "relationship": "calls",
                "source_type": "graph",
            },
        ],
        tool_results=[
            {
                "success": True,
                "data": {
                    "results": [
                        {
                            "file": "auth.py",
                            "symbol": "AuthService.verify_password",
                            "start_line": 11,
                            "end_line": 12,
                            "score": 0.85,
                            "reason": "Implements password verification",
                        }
                    ]
                },
            },
            {
                "success": True,
                "data": [
                    {
                        "caller_name": "login_handler",
                        "caller_file": "app/main.py",
                        "caller_line": 125,
                        "relationship": "calls",
                    }
                ],
            },
        ],
    )

    answer = "Authentication is handled by AuthService.verify_password in auth.py:11-12 and called by login_handler in app/main.py."
    res = verifier.verify(answer, state)

    assert res.confidence == VerificationConfidence.HIGH
    assert len(res.evidence) >= 2
    files = [e.file for e in res.evidence]
    assert "auth.py" in files
    assert "app/main.py" in files
