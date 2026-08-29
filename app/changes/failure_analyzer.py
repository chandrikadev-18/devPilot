"""
DevPilot Failure Analyzer (v2.3).

Parses and diagnoses test suite failures, execution errors, AST syntax errors,
and runtime exceptions to extract root causes and actionable repair recommendations.
"""

from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.changes.models import (
    ChangeExecution,
    ChangeProposal,
    FailureAnalysis,
    TestValidationResult,
)


class FailureAnalyzer:
    """
    Analyzes execution failures, pytest outputs, stack traces, and diffs
    to extract failed tests, error types, likely root causes, and repair directions.
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = (project_root or Path.cwd()).resolve()

    def analyze(
        self,
        output_or_error: str,
        test_result: Optional[TestValidationResult] = None,
        execution: Optional[ChangeExecution] = None,
        proposal: Optional[ChangeProposal] = None,
    ) -> FailureAnalysis:
        """
        Extracts structured failure diagnosis from test runner output or execution errors.
        """
        raw_text = output_or_error or ""
        if test_result and getattr(test_result, "output", ""):
            raw_text = f"{raw_text}\n{test_result.output}"
        if execution and execution.error:
            raw_text = f"{raw_text}\n{execution.error}"

        failed_tests = self._extract_failed_tests(raw_text)
        error_type, error_message = self._extract_error_type_and_message(raw_text)
        traceback_str = self._extract_traceback(raw_text)
        affected_files = self._extract_affected_files(raw_text, proposal)
        affected_symbols = self._extract_affected_symbols(raw_text, proposal)
        root_cause, confidence, fix_direction = self._diagnose_root_cause(
            error_type=error_type,
            error_message=error_message,
            failed_tests=failed_tests,
            affected_files=affected_files,
            affected_symbols=affected_symbols,
            proposal=proposal,
            raw_text=raw_text,
        )

        return FailureAnalysis(
            failed_tests=failed_tests,
            error_type=error_type,
            error_message=error_message,
            traceback=traceback_str,
            affected_files=affected_files,
            affected_symbols=affected_symbols,
            likely_root_cause=root_cause,
            confidence=confidence,
            suggested_fix_direction=fix_direction,
        )

    def _extract_failed_tests(self, text: str) -> List[str]:
        """Extracts names of failed tests from pytest summary or failure lines."""
        failed: Set[str] = set()

        # Match FAILED tests/test_foo.py::test_bar
        for m in re.finditer(r"FAILED\s+([^\s:]+(?:::[^\s]+)?)", text):
            failed.add(m.group(1))

        # Match short summary lines: ________________ test_name ________________
        for m in re.finditer(r"_{3,}\s*(test_[a-zA-Z0-9_]+)\s*_{3,}", text):
            failed.add(m.group(1))

        # Match standard pytest fail lines
        for m in re.finditer(r"(tests/[a-zA-Z0-9_/\.\-]+::test_[a-zA-Z0-9_]+)", text):
            failed.add(m.group(1))

        return sorted(list(failed))

    def _extract_error_type_and_message(self, text: str) -> Tuple[str, str]:
        """Identifies the specific exception/error type and its description."""
        # 1. Syntax & Indentation Errors
        m = re.search(r"Syntax validation failed in '([^']+)':\s*(.*)", text)
        if m:
            return "SyntaxError", f"{m.group(2)} in {m.group(1)}"

        m = re.search(r"(IndentationError|SyntaxError):\s*(.+)", text)
        if m:
            return m.group(1), m.group(2).strip()

        # 2. Pytest Assertion Errors
        m = re.search(r"E\s+assert\s+(.+)", text)
        if m:
            return "AssertionError", f"assert {m.group(1).strip()}"

        m = re.search(r"AssertionError:\s*(.+)", text)
        if m:
            return "AssertionError", m.group(1).strip()

        # 3. Import & Module Errors
        m = re.search(r"E\s+(ModuleNotFoundError|ImportError):\s*(.+)", text)
        if m:
            return m.group(1), m.group(2).strip()

        m = re.search(r"(ModuleNotFoundError|ImportError):\s*(.+)", text)
        if m:
            return m.group(1), m.group(2).strip()

        # 4. Standard Python Exceptions (TypeError, AttributeError, KeyError, ValueError, etc.)
        for exc in ("TypeError", "AttributeError", "KeyError", "IndexError", "ValueError", "FileNotFoundError", "NameError", "RuntimeError"):
            m = re.search(rf"E\s+{exc}:\s*(.+)", text)
            if m:
                return exc, m.group(1).strip()
            m = re.search(rf"{exc}:\s*(.+)", text)
            if m:
                return exc, m.group(1).strip()

        # 5. Patch Validation or Stale Errors
        if "stale" in text.lower() or "modified on disk" in text.lower():
            return "StalePatchError", "Target files have drifted or were modified on disk."

        if "validation" in text.lower() and "fail" in text.lower():
            return "PatchValidationError", "Unified diff patch validation failed."

        if "failed" in text.lower() and "test" in text.lower():
            return "TestFailure", "One or more automated tests failed."

        return "UnknownError", text.strip()[:120] if text else "Unknown execution error."

    def _extract_traceback(self, text: str) -> str:
        """Extracts the relevant stack traceback from output."""
        # Find traceback blocks
        tb_match = re.search(r"(Traceback \(most recent call last\):[\s\S]+?)(?=\n={3,}|\Z)", text)
        if tb_match:
            return tb_match.group(1).strip()

        # Extract failure detail block from pytest (lines starting with > or E )
        lines = text.splitlines()
        tb_lines = []
        in_failure = False
        for line in lines:
            if line.startswith("____") and "test" in line:
                in_failure = True
            elif line.startswith("====") and in_failure and tb_lines:
                break
            if in_failure:
                tb_lines.append(line)

        if tb_lines:
            return "\n".join(tb_lines).strip()

        return text.strip()

    def _extract_affected_files(self, text: str, proposal: Optional[ChangeProposal] = None) -> List[str]:
        """Extracts affected files mentioned in the traceback or proposal."""
        files: Set[str] = set()
        if proposal:
            if proposal.target_file:
                files.add(proposal.target_file.replace("\\", "/"))
            for f in proposal.affected_files:
                files.add(f.replace("\\", "/"))

        # Find .py files in traceback
        for m in re.finditer(r"['\"]?([a-zA-Z0-9_\-/\\]+\.py)['\"]?", text):
            f_norm = m.group(1).replace("\\", "/")
            if not f_norm.startswith("<") and not "site-packages" in f_norm and not "Python3" in f_norm:
                files.add(f_norm)

        return sorted(list(files))

    def _extract_affected_symbols(self, text: str, proposal: Optional[ChangeProposal] = None) -> List[str]:
        """Extracts relevant affected symbols."""
        symbols: Set[str] = set()
        if proposal:
            if proposal.target_symbol:
                symbols.add(proposal.target_symbol)
            for s in proposal.affected_symbols:
                symbols.add(s)

        # Match Python symbols like Class.method or function_name in failure text
        for m in re.finditer(r"(?:in\s+)?([A-Z][a-zA-Z0-9_]+\.[a-z_][a-zA-Z0-9_]*)", text):
            symbols.add(m.group(1))

        return sorted(list(symbols))

    def _diagnose_root_cause(
        self,
        error_type: str,
        error_message: str,
        failed_tests: List[str],
        affected_files: List[str],
        affected_symbols: List[str],
        proposal: Optional[ChangeProposal],
        raw_text: str,
    ) -> Tuple[str, float, str]:
        """
        Determines likely root cause, confidence score, and suggested fix direction.
        """
        target_name = (proposal.target_symbol if proposal else None) or (affected_symbols[0] if affected_symbols else "target function")

        if error_type in ("SyntaxError", "IndentationError"):
            root_cause = f"Python syntax or indentation error in modified file: {error_message}"
            confidence = 0.95
            fix_direction = f"Fix indentation and syntax formatting in {affected_files[0] if affected_files else 'target file'}."
            return root_cause, confidence, fix_direction

        if error_type in ("ModuleNotFoundError", "ImportError"):
            root_cause = f"Unresolved or missing import dependency: {error_message}"
            confidence = 0.90
            fix_direction = f"Add missing import statement or verify module availability in {affected_files[0] if affected_files else 'source'}."
            return root_cause, confidence, fix_direction

        if error_type == "AssertionError":
            root_cause = f"Test assertion mismatch in {target_name}: output did not match expected test return value or state."
            confidence = 0.85
            fix_direction = f"Adjust return value and logic in {target_name} to satisfy test assertions while preserving intended behavior."
            return root_cause, confidence, fix_direction

        if error_type in ("TypeError", "AttributeError"):
            root_cause = f"Interface or type mismatch in {target_name}: {error_message}"
            confidence = 0.80
            fix_direction = f"Ensure correct parameter types and method attributes in {target_name}."
            return root_cause, confidence, fix_direction

        if error_type == "StalePatchError":
            root_cause = "Target file was modified on disk concurrently or has drifted."
            confidence = 0.90
            fix_direction = "Regenerate change proposal based on current on-disk target file state."
            return root_cause, confidence, fix_direction

        if failed_tests:
            root_cause = f"Test validation failed on {len(failed_tests)} test(s): {', '.join(failed_tests[:2])}"
            confidence = 0.70
            fix_direction = f"Refine implementation in {target_name} to pass test assertions in {failed_tests[0]}."
            return root_cause, confidence, fix_direction

        root_cause = f"Execution failed with {error_type}: {error_message}"
        confidence = 0.50
        fix_direction = f"Investigate {error_type} and correct logic in {target_name}."
        return root_cause, confidence, fix_direction
