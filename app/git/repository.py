"""
DevPilot Safe Git Repository Abstraction.

Provides read-only Git repository detection, path validation, and security boundaries.
"""

from pathlib import Path
from typing import Optional
import git


class GitError(Exception):
    """Base exception for all Git intelligence operations."""
    pass


class NotAGitRepositoryError(GitError):
    """Raised when the specified directory is not a valid Git repository."""
    pass


class GitSecurityError(GitError):
    """Raised when a file path violates repository boundaries or security rules."""
    pass


class GitCommitNotFoundError(GitError):
    """Raised when a requested commit hash is not found in the repository."""
    pass


class GitFileNotFoundError(GitError):
    """Raised when a file cannot be found in repository history or working tree."""
    pass


class GitBlameError(GitError):
    """Raised when git blame fails or encounters invalid line bounds."""
    pass


def is_git_repository(project_root: Optional[Path] = None) -> bool:
    """
    Checks whether the target project directory is a Git repository.
    Verifies that .git directory exists directly in project_root.
    """
    root = (project_root or Path.cwd()).resolve()
    git_dir = root / ".git"
    if not git_dir.exists():
        return False
    try:
        repo = git.Repo(root)
        # Ensure we don't accidentally match parent repositories outside project root
        return Path(repo.working_tree_dir).resolve() == root
    except (git.InvalidGitRepositoryError, git.NoSuchPathError):
        return False
    except Exception:
        return False


class GitRepository:
    """
    Read-only wrapper around GitPython Repo object.
    Enforces strict project boundaries, path sanitization, and read-only access.
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.root = (project_root or Path.cwd()).resolve()
        if not (self.root / ".git").exists():
            raise NotAGitRepositoryError("This project is not a Git repository.")

        try:
            self._repo = git.Repo(self.root)
        except (git.InvalidGitRepositoryError, git.NoSuchPathError) as e:
            raise NotAGitRepositoryError("This project is not a Git repository.") from e

        # Ensure repository root strictly matches project root (no parent traversal)
        repo_root = Path(self._repo.working_tree_dir).resolve()
        if repo_root != self.root:
            raise NotAGitRepositoryError("This project is not a Git repository.")

    @property
    def raw_repo(self) -> git.Repo:
        """Returns the underlying GitPython Repo instance."""
        return self._repo

    def resolve_safe_relpath(self, file_path: str) -> str:
        """
        Validates and resolves a file path relative to the repository root.
        Rejects directory traversal, paths outside repo, .env, and .git files.
        Returns a normalized POSIX relative path.
        """
        if not file_path or not file_path.strip():
            raise GitSecurityError("File path cannot be empty.")

        raw_str = file_path.strip().replace("\\", "/")
        if raw_str.startswith("../") or "/../" in raw_str or raw_str == "..":
            raise GitSecurityError(f"Directory traversal is forbidden: '{file_path}'")

        # Reject .env access
        parts = [p.lower() for p in Path(raw_str).parts]
        normalized_lower = Path(raw_str).as_posix().lower()
        if any(p.startswith(".env") for p in parts) or normalized_lower.endswith(".env"):
            raise GitSecurityError(f"Access to environment files is forbidden: '{file_path}'")

        # Reject .git access
        if any(p == ".git" for p in parts):
            raise GitSecurityError(f"Access to internal .git directory is forbidden: '{file_path}'")

        # Resolve target
        if Path(raw_str).is_absolute():
            target = Path(raw_str).resolve()
        else:
            target = (self.root / raw_str).resolve()

        # Ensure target is within repo root
        try:
            rel = target.relative_to(self.root)
            return rel.as_posix()
        except ValueError:
            raise GitSecurityError(f"Access denied: '{file_path}' resolves outside repository root '{self.root}'")


def get_repository(project_root: Optional[Path] = None) -> GitRepository:
    """Factory helper to obtain a validated GitRepository instance."""
    return GitRepository(project_root=project_root)
