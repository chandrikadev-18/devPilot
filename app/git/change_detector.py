
"""
DevPilot Git Change Detector.

Provides a clean, read-only abstraction for inspecting Git working tree changes,
status, branch, staged/unstaged diffs, and file-level metrics.
"""

from pathlib import Path
import re
from typing import Dict, List, Optional, Set, Tuple
import git

from app.git.models import ChangeType, GitChange
from app.git.repository import (
    GitError,
    GitRepository,
    NotAGitRepositoryError,
    get_repository,
    is_git_repository,
)


class GitChangeDetector:
    """
    Read-only service for detecting and inspecting Git working tree changes.
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = (project_root or Path.cwd()).resolve()

    def _get_repo(self) -> GitRepository:
        """Obtains validated GitRepository instance."""
        if not is_git_repository(self.project_root):
            raise NotAGitRepositoryError(f"Directory '{self.project_root}' is not a Git repository.")
        return get_repository(self.project_root)

    def get_current_branch(self) -> str:
        """
        Determines the current active branch name or detached HEAD reference.
        """
        repo = self._get_repo()
        raw = repo.raw_repo
        try:
            return raw.active_branch.name
        except TypeError:
            # Detached HEAD
            if raw.head.is_valid():
                return f"HEAD ({raw.head.commit.hexsha[:7]})"
            return "HEAD"
        except Exception:
            return "HEAD"

    def get_changes(self) -> List[GitChange]:
        """
        Inspects the Git working tree (staged, unstaged, untracked) using git status and diff,
        returning a structured list of GitChange objects with diff metrics.
        """
        repo = self._get_repo()
        raw = repo.raw_repo

        file_changes_map: Dict[str, Dict[str, Any]] = {}

        # 1. Parse git status --porcelain=v1 -u
        try:
            status_output = raw.git.status("--porcelain=v1", "-u")
            for line in status_output.splitlines():
                if not line or len(line) < 3:
                    continue
                code = line[:2]
                path_part = line[3:].strip()
                
                # Handle renamed files (e.g. "R  old -> new")
                if " -> " in path_part:
                    old_path, new_path = path_part.split(" -> ", 1)
                    rel_path = new_path.replace("\\", "/").strip('"\'')
                else:
                    rel_path = path_part.replace("\\", "/").strip('"\'')

                staged = code[0] not in (" ", "?")
                unstaged = code[1] not in (" ", "?")

                change_type = ChangeType.MODIFIED.value
                if "A" in code or code == "??":
                    change_type = ChangeType.ADDED.value
                    if code == "??":
                        staged = False
                        unstaged = True
                elif "D" in code:
                    change_type = ChangeType.DELETED.value
                elif "R" in code:
                    change_type = ChangeType.RENAMED.value

                file_changes_map[rel_path] = {
                    "change_type": change_type,
                    "staged": staged,
                    "unstaged": unstaged,
                }
        except Exception:
            # Fallback to index diffs if porcelain call fails
            try:
                for d in raw.index.diff(None):
                    p = (d.b_path or d.a_path or "").replace("\\", "/")
                    if p:
                        ct = ChangeType.ADDED.value if d.new_file else (ChangeType.DELETED.value if d.deleted_file else ChangeType.MODIFIED.value)
                        file_changes_map[p] = {"change_type": ct, "staged": False, "unstaged": True}
                if raw.head.is_valid():
                    for d in raw.index.diff("HEAD"):
                        p = (d.b_path or d.a_path or "").replace("\\", "/")
                        if p:
                            ct = ChangeType.DELETED.value if d.new_file else (ChangeType.ADDED.value if d.deleted_file else ChangeType.MODIFIED.value)
                            if p in file_changes_map:
                                file_changes_map[p]["staged"] = True
                            else:
                                file_changes_map[p] = {"change_type": ct, "staged": True, "unstaged": False}
                for u in raw.untracked_files:
                    p = u.replace("\\", "/")
                    file_changes_map[p] = {"change_type": ChangeType.ADDED.value, "staged": False, "unstaged": True}
            except Exception:
                pass

        # 2. Compute per-file diff and line additions/deletions
        result_changes: List[GitChange] = []

        for fpath, info in sorted(file_changes_map.items(), key=lambda x: x[0]):
            file_diff = ""
            additions = 0
            deletions = 0
            target_full_path = self.project_root / fpath

            # Untracked file: count file lines
            is_untracked = not info["staged"] and info["change_type"] == ChangeType.ADDED.value and not raw.head.is_valid()
            try:
                if fpath in raw.untracked_files and target_full_path.exists() and target_full_path.is_file():
                    with open(target_full_path, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                    additions = len(lines)
                    file_diff = "".join(f"+{l}" for l in lines)
                else:
                    # Get diff for this specific file
                    staged_f_diff = raw.git.diff("HEAD", "--", fpath) if (raw.head.is_valid() and info["staged"]) else ""
                    unstaged_f_diff = raw.git.diff("--", fpath) if info["unstaged"] else ""

                    combined_diff = staged_f_diff
                    if unstaged_f_diff:
                        combined_diff = (combined_diff + "\n" + unstaged_f_diff) if combined_diff else unstaged_f_diff
                    file_diff = combined_diff

                    for dline in file_diff.splitlines():
                        if dline.startswith("+") and not dline.startswith("+++"):
                            additions += 1
                        elif dline.startswith("-") and not dline.startswith("---"):
                            deletions += 1
            except Exception:
                if target_full_path.exists() and target_full_path.is_file():
                    try:
                        with open(target_full_path, "r", encoding="utf-8", errors="replace") as f:
                            additions = len(f.readlines())
                    except Exception:
                        pass

            result_changes.append(
                GitChange(
                    file_path=fpath,
                    change_type=info["change_type"],
                    staged=info.get("staged", False),
                    unstaged=info.get("unstaged", True),
                    additions=additions,
                    deletions=deletions,
                    diff=file_diff,
                )
            )

        return result_changes
