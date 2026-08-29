"""
DevPilot Project Management Service (v2.5).

Orchestrates project registration, safe path validation, Git repository detection,
and project-scoped operation executions (scan, graph, review, agent).
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.agent import create_codebase_agent
from app.changes.reviewer import GitChangeReviewer
from app.embeddings.embedder import CodeEmbedder
from app.git.repository import is_git_repository
from app.graph.builder import GraphBuilder
from app.graph.models import NodeType
from app.llm import create_llm_provider, strip_thinking_and_tool_tags
from app.projects.models import (
    Operation,
    OperationStatus,
    OperationType,
    Project,
    ProjectStatus,
    generate_operation_id,
    generate_project_id,
)
from app.projects.store import OperationStore, ProjectStore
from app.scanner.scanner import ProjectScanner
from app.search.semantic_search import SemanticSearcher
from app.vector_store.qdrant_store import (
    DEFAULT_COLLECTION_NAME,
    DEFAULT_STORAGE_PATH,
    QdrantVectorStore,
)


class ProjectError(Exception):
    """Base exception for project operations."""
    pass


class ProjectNotFoundError(ProjectError):
    """Raised when a requested project ID is not found."""
    pass


class DuplicateProjectError(ProjectError):
    """Raised when registering a project path that already exists."""
    pass


class InvalidProjectPathError(ProjectError):
    """Raised when a project path is invalid, inaccessible, or violates boundaries."""
    pass


class OperationNotFoundError(ProjectError):
    """Raised when an operation ID is not found."""
    pass


class ProjectService:
    """
    Core backend service managing registered projects and coordinating project-scoped operations.
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        project_store: Optional[ProjectStore] = None,
        operation_store: Optional[OperationStore] = None,
    ):
        self.project_root = (project_root or Path.cwd()).resolve()
        self.project_store = project_store or ProjectStore(project_root=self.project_root)
        self.operation_store = operation_store or OperationStore(project_root=self.project_root)

    def validate_path(self, raw_path: str) -> Path:
        """
        Validates that a path is non-empty, exists on disk, is a directory,
        and does not perform illegal traversal or contain forbidden characters.
        """
        if not raw_path or not raw_path.strip():
            raise InvalidProjectPathError("Project path cannot be empty.")

        clean_str = raw_path.strip()
        if "\0" in clean_str:
            raise InvalidProjectPathError("Project path contains invalid null characters.")

        try:
            path_obj = Path(clean_str)
            # Resolve relative to project_root if not absolute
            if not path_obj.is_absolute():
                resolved = (self.project_root / path_obj).resolve()
            else:
                resolved = path_obj.resolve()
        except Exception as e:
            raise InvalidProjectPathError(f"Invalid path format: {e}")

        if not resolved.exists():
            raise InvalidProjectPathError(f"Project path does not exist: '{raw_path}'")

        if not resolved.is_dir():
            raise InvalidProjectPathError(f"Project path is not a directory: '{raw_path}'")

        return resolved

    def register_project(
        self,
        path: str,
        name: Optional[str] = None,
        repository: Optional[str] = None,
        default_branch: str = "main",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Project:
        """
        Registers a new codebase or repository project.
        """
        resolved_path = self.validate_path(path)
        posix_path = str(resolved_path).replace("\\", "/")

        # Check for duplicates
        existing = self.project_store.get_by_path(posix_path)
        if existing:
            raise DuplicateProjectError(
                f"Project at path '{posix_path}' is already registered as '{existing.name}' ({existing.project_id})."
            )

        proj_name = name.strip() if name and name.strip() else resolved_path.name
        if not proj_name:
            proj_name = "project"

        detected_repo = repository
        detected_branch = default_branch

        # Auto-detect Git repository metadata if available
        if is_git_repository(resolved_path):
            try:
                import git
                repo_obj = git.Repo(resolved_path)
                if not detected_repo and repo_obj.remotes:
                    try:
                        detected_repo = repo_obj.remotes.origin.url
                    except Exception:
                        pass
                if default_branch == "main" and not repo_obj.head.is_detached:
                    try:
                        detected_branch = repo_obj.active_branch.name
                    except Exception:
                        pass
            except Exception:
                pass

        proj_id = generate_project_id(proj_name)
        now_utc = datetime.now(timezone.utc).isoformat()

        project = Project(
            project_id=proj_id,
            name=proj_name,
            path=posix_path,
            repository=detected_repo,
            default_branch=detected_branch,
            status=ProjectStatus.ACTIVE.value,
            created_at=now_utc,
            updated_at=now_utc,
            metadata=metadata or {},
        )

        return self.project_store.save(project)

    def get_project(self, project_id: str) -> Project:
        """Retrieves a project by ID."""
        proj = self.project_store.get(project_id)
        if not proj:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found.")
        return proj

    def list_projects(self, status: Optional[str] = None) -> List[Project]:
        """Lists all registered projects, optionally filtered by status."""
        return self.project_store.list(status=status)

    def delete_project(self, project_id: str, hard_delete: bool = False) -> bool:
        """Deletes or archives a project."""
        proj = self.get_project(project_id)
        if hard_delete:
            return self.project_store.delete(project_id)
        else:
            proj.status = ProjectStatus.ARCHIVED.value
            proj.updated_at = datetime.now(timezone.utc).isoformat()
            self.project_store.save(proj)
            return True

    def scan_project(self, project_id: str) -> Tuple[Operation, Dict[str, Any]]:
        """Scans project directory files and extensions."""
        proj = self.get_project(project_id)
        root = Path(proj.path).resolve()
        if not root.exists():
            raise InvalidProjectPathError(f"Project path '{proj.path}' no longer exists on disk.")

        op = Operation(
            operation_id=generate_operation_id(OperationType.SCAN.value),
            project_id=project_id,
            operation_type=OperationType.SCAN.value,
            status=OperationStatus.RUNNING.value,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self.operation_store.save(op)

        try:
            scanner = ProjectScanner()
            files, stats = scanner.scan(root)
            result = {
                "project_name": proj.name,
                "project_path": proj.path,
                "total_files": stats.total_files,
                "total_dirs": stats.total_dirs,
                "extensions": stats.extensions,
                "files_count": len(files),
            }
            op.status = OperationStatus.COMPLETED.value
            op.completed_at = datetime.now(timezone.utc).isoformat()
            op.result = result
            self.operation_store.save(op)
            return op, result
        except Exception as e:
            op.status = OperationStatus.FAILED.value
            op.completed_at = datetime.now(timezone.utc).isoformat()
            op.error = str(e)
            self.operation_store.save(op)
            raise

    def build_graph(self, project_id: str) -> Tuple[Operation, Dict[str, Any]]:
        """Constructs codebase dependency graph for the project."""
        proj = self.get_project(project_id)
        root = Path(proj.path).resolve()
        if not root.exists():
            raise InvalidProjectPathError(f"Project path '{proj.path}' no longer exists on disk.")

        op = Operation(
            operation_id=generate_operation_id(OperationType.GRAPH_BUILD.value),
            project_id=project_id,
            operation_type=OperationType.GRAPH_BUILD.value,
            status=OperationStatus.RUNNING.value,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self.operation_store.save(op)

        try:
            builder = GraphBuilder()
            store = builder.build(root)
            nodes = store.get_nodes()
            edges = store.get_edges()

            result = {
                "project_id": project_id,
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "files": len([n for n in nodes if n.node_type == NodeType.FILE]),
                "classes": len([n for n in nodes if n.node_type == NodeType.CLASS]),
                "functions": len([n for n in nodes if n.node_type == NodeType.FUNCTION]),
            }
            op.status = OperationStatus.COMPLETED.value
            op.completed_at = datetime.now(timezone.utc).isoformat()
            op.result = result
            self.operation_store.save(op)
            return op, result
        except Exception as e:
            op.status = OperationStatus.FAILED.value
            op.completed_at = datetime.now(timezone.utc).isoformat()
            op.error = str(e)
            self.operation_store.save(op)
            raise

    def review_project(self, project_id: str) -> Tuple[Operation, Dict[str, Any]]:
        """Executes read-only code review on project's working tree."""
        proj = self.get_project(project_id)
        root = Path(proj.path).resolve()
        if not root.exists():
            raise InvalidProjectPathError(f"Project path '{proj.path}' no longer exists on disk.")

        op = Operation(
            operation_id=generate_operation_id(OperationType.REVIEW.value),
            project_id=project_id,
            operation_type=OperationType.REVIEW.value,
            status=OperationStatus.RUNNING.value,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self.operation_store.save(op)

        try:
            reviewer = GitChangeReviewer(project_root=root)
            review = reviewer.review_working_tree()
            result = review.to_dict()

            op.status = OperationStatus.COMPLETED.value
            op.completed_at = datetime.now(timezone.utc).isoformat()
            op.result = result
            self.operation_store.save(op)
            return op, result
        except Exception as e:
            op.status = OperationStatus.FAILED.value
            op.completed_at = datetime.now(timezone.utc).isoformat()
            op.error = str(e)
            self.operation_store.save(op)
            raise

    def ask_agent(
        self,
        project_id: str,
        question: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Tuple[Operation, Dict[str, Any]]:
        """Queries the codebase AI agent scoped to the project."""
        proj = self.get_project(project_id)
        root = Path(proj.path).resolve()
        if not root.exists():
            raise InvalidProjectPathError(f"Project path '{proj.path}' no longer exists on disk.")

        if not question or not question.strip():
            raise ProjectError("Agent question cannot be empty.")

        op = Operation(
            operation_id=generate_operation_id(OperationType.AGENT.value),
            project_id=project_id,
            operation_type=OperationType.AGENT.value,
            status=OperationStatus.RUNNING.value,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self.operation_store.save(op)

        try:
            embedder = CodeEmbedder()
            try:
                store = QdrantVectorStore(storage_path=DEFAULT_STORAGE_PATH)
            except Exception:
                store = QdrantVectorStore(location=":memory:", storage_path=None)

            searcher = SemanticSearcher(
                embedder=embedder,
                vector_store=store,
                collection_name=DEFAULT_COLLECTION_NAME,
            )

            llm = create_llm_provider(
                provider_name=provider,
                model=model,
            )

            agent = create_codebase_agent(
                llm=llm,
                searcher=searcher,
                project_root=root,
                vector_store=store,
                collection_name=DEFAULT_COLLECTION_NAME,
            )

            agent_result = agent.run(question=question.strip())
            clean_answer = strip_thinking_and_tool_tags(agent_result.answer)

            result = {
                "project_id": project_id,
                "question": question.strip(),
                "answer": clean_answer,
                "tool_calls": [tc.to_dict() if hasattr(tc, "to_dict") else str(tc) for tc in agent_result.tool_calls],
                "iterations": agent_result.iterations,
            }

            op.status = OperationStatus.COMPLETED.value
            op.completed_at = datetime.now(timezone.utc).isoformat()
            op.result = result
            self.operation_store.save(op)
            return op, result
        except Exception as e:
            op.status = OperationStatus.FAILED.value
            op.completed_at = datetime.now(timezone.utc).isoformat()
            op.error = str(e)
            self.operation_store.save(op)
            raise

    def get_operation(self, operation_id: str) -> Operation:
        """Retrieves an operation record by ID."""
        op = self.operation_store.get(operation_id)
        if not op:
            raise OperationNotFoundError(f"Operation with ID '{operation_id}' not found.")
        return op

    def list_operations(self, project_id: Optional[str] = None) -> List[Operation]:
        """Lists operation records, optionally filtered by project ID."""
        return self.operation_store.list(project_id=project_id)
