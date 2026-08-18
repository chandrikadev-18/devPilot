"""
Unit tests for Git history, blame, commit details, and diff handling.
"""

from pathlib import Path
import json
import pytest
import git

from app.git.history import (
    get_commit_detail,
    get_file_blame,
    get_file_history,
    get_last_commit_for_file,
    get_recent_commits,
)
from app.git.models import (
    BlameLine,
    BlameResult,
    CommitDetail,
    CommitInfo,
    FileHistoryResult,
)
from app.git.repository import (
    GitBlameError,
    GitCommitNotFoundError,
    GitFileNotFoundError,
    GitRepository,
)


@pytest.fixture
def repo_with_commits(tmp_path: Path) -> GitRepository:
    """Fixture creating a repository with multi-commit history and files."""
    repo_dir = tmp_path / "history_repo"
    repo_dir.mkdir()
    r = git.Repo.init(repo_dir)

    with r.config_writer() as config:
        config.set_value("user", "name", "Dev Tester")
        config.set_value("user", "email", "dev@example.com")

    # Commit 1: Add auth.py
    auth_file = repo_dir / "auth.py"
    auth_file.write_text("def authenticate_user():\n    return True\n", encoding="utf-8")
    r.index.add(["auth.py"])
    c1 = r.index.commit("Add auth module")

    # Commit 2: Modify auth.py and add utils.py
    auth_file.write_text("def authenticate_user(token):\n    # Validate token\n    return token is not None\n", encoding="utf-8")
    utils_file = repo_dir / "utils.py"
    utils_file.write_text("def helper():\n    return 42\n", encoding="utf-8")
    r.index.add(["auth.py", "utils.py"])
    c2 = r.index.commit("Enhance token validation and add utils")

    # Commit 3: Modify utils.py
    utils_file.write_text("def helper():\n    # Returns answer\n    return 42\n", encoding="utf-8")
    r.index.add(["utils.py"])
    c3 = r.index.commit("Update helper comments")

    return GitRepository(repo_dir)


def test_get_recent_commits(repo_with_commits: GitRepository):
    commits = get_recent_commits(repo_with_commits, limit=10)
    assert len(commits) == 3
    assert commits[0].message == "Update helper comments"
    assert commits[1].message == "Enhance token validation and add utils"
    assert commits[2].message == "Add auth module"

    # Test limit parameter
    limited = get_recent_commits(repo_with_commits, limit=2)
    assert len(limited) == 2


def test_get_file_history(repo_with_commits: GitRepository):
    # auth.py should have 2 commits
    history = get_file_history(repo_with_commits, file_path="auth.py", limit=10)
    assert isinstance(history, FileHistoryResult)
    assert history.file_path == "auth.py"
    assert len(history.commits) == 2
    assert history.commits[0].message == "Enhance token validation and add utils"
    assert history.commits[1].message == "Add auth module"

    # utils.py should have 2 commits
    u_history = get_file_history(repo_with_commits, file_path="utils.py", limit=10)
    assert len(u_history.commits) == 2
    assert u_history.commits[0].message == "Update helper comments"


def test_get_last_commit_for_file(repo_with_commits: GitRepository):
    last_auth = get_last_commit_for_file(repo_with_commits, "auth.py")
    assert last_auth is not None
    assert isinstance(last_auth, CommitInfo)
    assert last_auth.message == "Enhance token validation and add utils"
    assert last_auth.author_name == "Dev Tester"

    last_utils = get_last_commit_for_file(repo_with_commits, "utils.py")
    assert last_utils is not None
    assert last_utils.message == "Update helper comments"


def test_get_commit_detail(repo_with_commits: GitRepository):
    commits = get_recent_commits(repo_with_commits, limit=1)
    top_hash = commits[0].commit_hash

    detail = get_commit_detail(repo_with_commits, top_hash)
    assert isinstance(detail, CommitDetail)
    assert detail.commit_hash == top_hash
    assert detail.message == "Update helper comments"
    assert detail.additions >= 1
    assert "utils.py" in detail.files_changed
    assert "diff" in detail.diff_summary.lower() or "---" in detail.diff_summary or "helper" in detail.diff_summary
    assert detail.truncated is False


def test_get_commit_invalid_hash(repo_with_commits: GitRepository):
    with pytest.raises(GitCommitNotFoundError):
        get_commit_detail(repo_with_commits, "nonexistenthash123456")

    with pytest.raises(GitCommitNotFoundError):
        get_commit_detail(repo_with_commits, "")


def test_get_file_history_invalid_file(repo_with_commits: GitRepository):
    with pytest.raises(GitFileNotFoundError):
        get_file_history(repo_with_commits, "does_not_exist.py")


def test_get_file_blame(repo_with_commits: GitRepository):
    blame = get_file_blame(repo_with_commits, file_path="auth.py")
    assert isinstance(blame, BlameResult)
    assert blame.file_path == "auth.py"
    assert len(blame.lines) == 3

    assert blame.lines[0].line_number == 1
    assert "def authenticate_user" in blame.lines[0].content
    assert blame.lines[0].author == "Dev Tester"


def test_get_file_blame_line_range(repo_with_commits: GitRepository):
    blame = get_file_blame(repo_with_commits, file_path="auth.py", start_line=2, end_line=3)
    assert len(blame.lines) == 2
    assert blame.lines[0].line_number == 2
    assert blame.lines[1].line_number == 3


def test_get_file_blame_invalid_range(repo_with_commits: GitRepository):
    with pytest.raises(GitBlameError):
        get_file_blame(repo_with_commits, file_path="auth.py", start_line=0)

    with pytest.raises(GitBlameError):
        get_file_blame(repo_with_commits, file_path="auth.py", start_line=5, end_line=2)

    with pytest.raises(GitBlameError):
        get_file_blame(repo_with_commits, file_path="auth.py", start_line=100)


def test_diff_truncation(tmp_path: Path):
    repo_dir = tmp_path / "large_diff_repo"
    repo_dir.mkdir()
    r = git.Repo.init(repo_dir)

    with r.config_writer() as config:
        config.set_value("user", "name", "Big Diff")
        config.set_value("user", "email", "big@example.com")

    # Generate a large file to exceed diff limit
    large_f = repo_dir / "large.txt"
    large_f.write_text("line\n" * 1000, encoding="utf-8")
    r.index.add(["large.txt"])
    c = r.index.commit("Initial large file")

    repo = GitRepository(repo_dir)
    detail = get_commit_detail(repo, c.hexsha, max_diff_chars=200)
    assert detail.truncated is True
    assert "[diff truncated]" in detail.diff_summary
    assert len(detail.diff_summary) <= 250


def test_json_serialization(repo_with_commits: GitRepository):
    history = get_file_history(repo_with_commits, "auth.py")
    h_dict = history.to_dict()
    assert json.dumps(h_dict)

    blame = get_file_blame(repo_with_commits, "auth.py")
    b_dict = blame.to_dict()
    assert json.dumps(b_dict)

    commits = get_recent_commits(repo_with_commits, limit=2)
    c_list = [c.to_dict() for c in commits]
    assert json.dumps(c_list)
