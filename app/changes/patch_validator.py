"""
DevPilot Patch Validator (v1.7).

Validates unified diff patches against file boundaries, security rules,
stale context, and Git working tree status.
"""

from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.agent.tools import resolve_safe_path
from app.changes.models import PatchValidationResult
from app.git.repository import is_git_repository


PROTECTED_PATTERNS = [
    r"^\.env(\..+)?$",
    r"^\.git(/.*)?$",
    r".*secret.*",
    r".*credential.*",
    r".*token.*",
    r".*id_rsa.*",
]


class PatchValidator:
    """
    Validates unified diff patches for safety, security, file bounds,
    and consistency with working tree files.
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = (project_root or Path.cwd()).resolve()

    def parse_patch_files(self, patch_str: str) -> List[Dict[str, Any]]:
        """
        Parses unified diff into file blocks with header info and hunks.
        """
        if not patch_str or not patch_str.strip():
            return []

        file_blocks: List[Dict[str, Any]] = []
        current_block: Optional[Dict[str, Any]] = None

        lines = patch_str.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith("--- "):
                from_path = line[4:].strip()
                if from_path.startswith("a/"):
                    from_path = from_path[2:]
                i += 1
                if i < len(lines) and lines[i].startswith("+++ "):
                    to_path = lines[i][4:].strip()
                    if to_path.startswith("b/"):
                        to_path = to_path[2:]

                    current_block = {
                        "from_file": from_path,
                        "to_file": to_path,
                        "file": to_path if to_path != "/dev/null" else from_path,
                        "hunks": [],
                        "raw_lines": [line, lines[i]],
                    }
                    file_blocks.append(current_block)
            elif line.startswith("@@ ") and current_block is not None:
                hunk = {
                    "header": line,
                    "lines": [],
                }
                current_block["hunks"].append(hunk)
                current_block["raw_lines"].append(line)
            elif current_block is not None and current_block["hunks"]:
                current_block["hunks"][-1]["lines"].append(line)
                current_block["raw_lines"].append(line)

            i += 1

        return file_blocks

    def is_protected_file(self, rel_path: str) -> bool:
        """Checks if a relative path matches protected files (e.g. .env, secrets)."""
        norm = rel_path.replace("\\", "/").lower()
        parts = norm.split("/")
        for part in parts:
            for pat in PROTECTED_PATTERNS:
                if re.match(pat, part, re.IGNORECASE):
                    return True
        return False

    def validate(self, patch_str: str) -> PatchValidationResult:
        """
        Validates a unified diff patch without modifying any files.
        """
        if not patch_str or not patch_str.strip():
            return PatchValidationResult(
                is_valid=False,
                status="VALIDATION FAILED",
                files_affected=[],
                additions=0,
                deletions=0,
                errors=["Patch string is empty."],
            )

        file_blocks = self.parse_patch_files(patch_str)
        if not file_blocks:
            # Check if malformed
            return PatchValidationResult(
                is_valid=False,
                status="VALIDATION FAILED",
                files_affected=[],
                additions=0,
                deletions=0,
                errors=["Malformed patch: no valid unified diff headers found."],
            )

        files_affected: List[str] = []
        additions = 0
        deletions = 0
        warnings: List[str] = []
        errors: List[str] = []
        conflicts: List[str] = []

        for block in file_blocks:
            file_rel = block["file"].replace("\\", "/")
            files_affected.append(file_rel)

            # 1. Path Safety & Traversal Checks
            if file_rel.startswith("../") or "/../" in file_rel or file_rel == "..":
                errors.append(f"Directory traversal detected: '{file_rel}'")
                continue

            if self.is_protected_file(file_rel):
                errors.append(f"Modification of protected file forbidden: '{file_rel}'")
                continue

            try:
                safe_target = resolve_safe_path(file_rel, self.project_root)
            except Exception as e:
                errors.append(f"Invalid file path '{file_rel}': {str(e)}")
                continue

            # 2. File Existence & Content Verification
            if not safe_target.exists():
                errors.append(f"Target file does not exist: '{file_rel}'")
                continue

            if not safe_target.is_file():
                errors.append(f"Target path is not a file: '{file_rel}'")
                continue

            try:
                with open(safe_target, "r", encoding="utf-8", errors="replace") as f:
                    file_content = f.read()
            except Exception as e:
                errors.append(f"Could not read target file '{file_rel}': {str(e)}")
                continue

            # 3. Check Hunks for Additions, Deletions, and Context Consistency
            for hunk in block["hunks"]:
                hunk_lines = hunk["lines"]
                removals = [l[1:] for l in hunk_lines if l.startswith("-")]
                adds = [l[1:] for l in hunk_lines if l.startswith("+")]

                additions += len(adds)
                deletions += len(removals)

                # Check if context/removed lines exist in target file
                for rem in removals:
                    rem_clean = rem.strip()
                    if rem_clean and rem_clean not in file_content:
                        warnings.append(
                            f"Stale patch context in '{file_rel}': line '{rem_clean[:40]}' not found."
                        )
                        break

            # 4. Check for Uncommitted Git Modifications on Target File
            if is_git_repository(self.project_root):
                try:
                    import git
                    repo = git.Repo(self.project_root)
                    # Check if file has unstaged or staged changes
                    diffs = repo.index.diff(None)
                    head_diffs = repo.index.diff("HEAD") if repo.head.is_valid() else []
                    modified_git_files = {d.a_path for d in diffs if d.a_path} | {d.a_path for d in head_diffs if d.a_path}
                    if file_rel in modified_git_files:
                        conflicts.append(
                            f"File '{file_rel}' contains uncommitted local Git changes."
                        )
                except Exception:
                    pass

        is_valid = len(errors) == 0
        if not is_valid:
            status = "VALIDATION FAILED"
        elif warnings:
            status = "SAFE TO APPLY (WITH WARNINGS)"
        else:
            status = "SAFE TO APPLY"

        return PatchValidationResult(
            is_valid=is_valid,
            status=status,
            files_affected=sorted(list(set(files_affected))),
            additions=additions,
            deletions=deletions,
            warnings=warnings,
            errors=errors,
            conflicts=conflicts,
        )
