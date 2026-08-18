"""
Unit tests for Git repository detection, safe initialization, and security boundaries.
"""

from pathlib import Path
import pytest
import git

from app.git.repository import (
    GitError,
    GitSecurityError,
    NotAGitRepositoryError,
    GitRepository,
    get_repository,
    is_git_repository,
)


@pytest.fixture
def empty_temp_dir(tmp_path: Path) -> Path:
    """Fixture providing a temporary non-git directory."""
    non_git = tmp_path / "non_git_dir"
    non_git.mkdir()
    return non_git


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Fixture providing an initialized temporary git repository."""
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    repo = git.Repo.init(repo_dir)

    # Configure author info for reproducible test commits
    with repo.config_writer() as config:
        config.set_value("user", "name", "Test Author")
        config.set_value("user", "email", "test@example.com")

    # Create initial commit
    f1 = repo_dir / "app.py"
    f1.write_text("print('hello')\n", encoding="utf-8")
    repo.index.add(["app.py"])
    repo.index.commit("Initial commit")

    return repo_dir


def test_is_git_repository_positive(temp_git_repo: Path):
    assert is_git_repository(temp_git_repo) is True


def test_is_git_repository_negative(empty_temp_dir: Path):
    assert is_git_repository(empty_temp_dir) is False


def test_git_repository_init_success(temp_git_repo: Path):
    repo = GitRepository(temp_git_repo)
    assert repo.root == temp_git_repo.resolve()
    assert repo.raw_repo is not None


def test_git_repository_init_failure(empty_temp_dir: Path):
    with pytest.raises(NotAGitRepositoryError) as exc_info:
        GitRepository(empty_temp_dir)
    assert "not a Git repository" in str(exc_info.value)


def test_get_repository_helper(temp_git_repo: Path):
    repo = get_repository(temp_git_repo)
    assert isinstance(repo, GitRepository)


def test_path_traversal_protection(temp_git_repo: Path):
    repo = GitRepository(temp_git_repo)

    with pytest.raises(GitSecurityError) as exc:
        repo.resolve_safe_relpath("../secret.txt")
    assert "Directory traversal is forbidden" in str(exc.value)

    with pytest.raises(GitSecurityError) as exc:
        repo.resolve_safe_relpath("foo/../../bar.txt")
    assert "Directory traversal is forbidden" in str(exc.value)


def test_sensitive_files_protection(temp_git_repo: Path):
    repo = GitRepository(temp_git_repo)

    with pytest.raises(GitSecurityError):
        repo.resolve_safe_relpath(".env")

    with pytest.raises(GitSecurityError):
        repo.resolve_safe_relpath(".env.production")

    with pytest.raises(GitSecurityError):
        repo.resolve_safe_relpath(".git/config")


def test_empty_path_protection(temp_git_repo: Path):
    repo = GitRepository(temp_git_repo)

    with pytest.raises(GitSecurityError):
        repo.resolve_safe_relpath("")

    with pytest.raises(GitSecurityError):
        repo.resolve_safe_relpath("   ")


def test_valid_safe_relpath(temp_git_repo: Path):
    repo = GitRepository(temp_git_repo)
    rel = repo.resolve_safe_relpath("app.py")
    assert rel == "app.py"

    sub_rel = repo.resolve_safe_relpath("subdir/nested.py")
    assert sub_rel == "subdir/nested.py"
