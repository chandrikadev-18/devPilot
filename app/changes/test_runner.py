"""
DevPilot Test Runner & Validation Subsystem (v1.7).

Executes repository tests post-patch application and extracts execution metrics.
"""

from pathlib import Path
import re
import subprocess
import sys
import time
from typing import List, Optional

from app.changes.models import TestValidationResult


class TestRunner:
    """
    Executes repository test suites safely and collects structured test results.
    """
    __test__ = False

    def __init__(self, project_root: Optional[Path] = None, timeout_seconds: int = 180):
        self.project_root = (project_root or Path.cwd()).resolve()
        self.timeout_seconds = timeout_seconds

    def run_tests(self, test_targets: Optional[List[str]] = None) -> TestValidationResult:
        """
        Executes pytest in project_root and parses passed/failed/skipped metrics.
        """
        cmd = [sys.executable, "-m", "pytest", "-q"]
        if test_targets:
            # Filter valid existing files in tests/
            valid_targets = []
            for t in test_targets:
                # Strip parenthetical location if present
                clean_t = t.split(" ")[0].strip()
                if (self.project_root / clean_t).exists() and clean_t.endswith(".py"):
                    valid_targets.append(clean_t)
            if valid_targets:
                cmd.extend(valid_targets)

        start_time = time.time()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            exec_time = round(time.time() - start_time, 2)
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            output = stdout + ("\n" + stderr if stderr else "")

            # Parse results from output
            passed = 0
            failed = 0
            skipped = 0

            pass_match = re.search(r"(\d+)\s+passed", output)
            if pass_match:
                passed = int(pass_match.group(1))

            fail_match = re.search(r"(\d+)\s+failed", output)
            if fail_match:
                failed = int(fail_match.group(1))

            skip_match = re.search(r"(\d+)\s+skipped", output)
            if skip_match:
                skipped = int(skip_match.group(1))

            is_success = proc.returncode in (0, 5) and failed == 0

            return TestValidationResult(
                passed=passed,
                failed=failed,
                skipped=skipped,
                execution_time=exec_time,
                exit_code=proc.returncode,
                is_success=is_success,
                output=output.strip(),
            )
        except subprocess.TimeoutExpired as e:
            exec_time = round(time.time() - start_time, 2)
            return TestValidationResult(
                passed=0,
                failed=1,
                skipped=0,
                execution_time=exec_time,
                exit_code=124,
                is_success=False,
                output=f"Test execution timed out after {self.timeout_seconds} seconds.",
            )
        except Exception as e:
            exec_time = round(time.time() - start_time, 2)
            return TestValidationResult(
                passed=0,
                failed=1,
                skipped=0,
                execution_time=exec_time,
                exit_code=1,
                is_success=False,
                output=f"Error executing test runner: {str(e)}",
            )
