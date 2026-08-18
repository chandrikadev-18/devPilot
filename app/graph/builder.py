"""
DevPilot Graph Builder.

Constructs an in-memory Code Dependency & Relationship Graph from a codebase
by extracting AST elements, establishing structural and import edges, and
performing deterministic name resolution for call sites.
"""

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from app.graph.extractor import ASTExtractor, CallSite, ImportRecord, ParsedFileRelationships
from app.graph.models import (
    EdgeType,
    GraphEdge,
    GraphNode,
    NodeType,
    make_class_node_id,
    make_file_node_id,
    make_function_node_id,
    make_method_node_id,
    make_module_node_id,
    normalize_graph_path,
)
from app.graph.store import GraphStore
from app.scanner.scanner import ProjectScanner


class GraphBuilder:
    """
    Scans, parses, and links codebase elements into a directed relationship graph.
    """

    def __init__(self):
        self.extractor = ASTExtractor()
        self.scanner = ProjectScanner()

    def build(self, project_path: str | Path) -> GraphStore:
        """
        Builds and returns a complete GraphStore for the specified project directory.
        """
        root = Path(project_path).resolve()
        if not root.exists():
            raise FileNotFoundError(f"Project directory not found: {root}")

        store = GraphStore()

        # Step 1: Discover python files
        if root.is_file() and root.suffix == ".py":
            py_files = [root]
            project_root = root.parent
        else:
            project_root = root
            # Scan using ProjectScanner to honor exclusion rules (.git, venv, node_modules, etc.)
            files, _ = self.scanner.scan(str(project_root))
            py_files = [Path(f.absolute_path) for f in files if f.extension == ".py"]

        # Step 2: Extract AST elements from all files
        parsed_files: Dict[str, ParsedFileRelationships] = {}
        failed_files: List[str] = []
        for file_p in py_files:
            try:
                rel_path = file_p.relative_to(project_root).as_posix()
            except ValueError:
                rel_path = file_p.name

            try:
                parsed = self.extractor.extract_file(file_p)
                parsed.file_path = rel_path
                parsed_files[rel_path] = parsed
            except Exception:
                failed_files.append(rel_path)
                continue

        store.metadata = {
            "files_processed": len(parsed_files),
            "files_failed": len(failed_files),
            "failed_files": failed_files,
        }

        # Step 3: Create nodes for files, classes, functions, methods, and modules
        # Also build lookup dictionaries for deterministic name resolution
        file_functions: Dict[str, Dict[str, str]] = {}  # rel_path -> {func_name: node_id}
        file_classes: Dict[str, Dict[str, str]] = {}    # rel_path -> {class_name: node_id}
        class_methods: Dict[Tuple[str, str], Dict[str, str]] = {}  # (rel_path, class_name) -> {method_name: node_id}
        all_symbols_by_name: Dict[str, List[str]] = {}  # symbol_name -> list of node_ids

        # Track module name to file mapping for imports
        # e.g. "auth" -> "auth.py", "backend.auth" -> "backend/auth.py"
        module_to_file: Dict[str, str] = {}
        for rel_p in parsed_files.keys():
            mod_stem = Path(rel_p).with_suffix("").as_posix().replace("/", ".")
            module_to_file[mod_stem] = rel_p
            # Also register simple filename without extension
            simple_stem = Path(rel_p).stem
            if simple_stem not in module_to_file:
                module_to_file[simple_stem] = rel_p

        for rel_p, data in parsed_files.items():
            file_functions[rel_p] = {}
            file_classes[rel_p] = {}

            # FILE Node
            file_node_id = make_file_node_id(rel_p)
            file_node = GraphNode(
                id=file_node_id,
                node_type=NodeType.FILE,
                name=Path(rel_p).name,
                file_path=rel_p,
                start_line=1,
                end_line=max((c["end_line"] for c in data.classes + data.functions), default=1),
                metadata={"extension": Path(rel_p).suffix},
            )
            store.add_node(file_node)

            # CLASS Nodes & CONTAINS Edges
            for cls in data.classes:
                cls_name = cls["name"]
                cls_id = make_class_node_id(rel_p, cls_name)
                cls_node = GraphNode(
                    id=cls_id,
                    node_type=NodeType.CLASS,
                    name=cls_name,
                    file_path=rel_p,
                    start_line=cls["start_line"],
                    end_line=cls["end_line"],
                    parent_id=file_node_id,
                )
                store.add_node(cls_node)
                file_classes[rel_p][cls_name] = cls_id
                all_symbols_by_name.setdefault(cls_name, []).append(cls_id)

                # Edge: FILE -(CONTAINS)-> CLASS
                store.add_edge(GraphEdge(
                    source_id=file_node_id,
                    target_id=cls_id,
                    edge_type=EdgeType.CONTAINS,
                    file_path=rel_p,
                    line_number=cls["start_line"],
                ))

            # FUNCTION Nodes & DEFINES Edges
            for fn in data.functions:
                fn_name = fn["name"]
                fn_id = make_function_node_id(rel_p, fn_name)
                fn_node = GraphNode(
                    id=fn_id,
                    node_type=NodeType.FUNCTION,
                    name=fn_name,
                    file_path=rel_p,
                    start_line=fn["start_line"],
                    end_line=fn["end_line"],
                    parent_id=file_node_id,
                )
                store.add_node(fn_node)
                file_functions[rel_p][fn_name] = fn_id
                all_symbols_by_name.setdefault(fn_name, []).append(fn_id)

                # Edge: FILE -(DEFINES)-> FUNCTION
                store.add_edge(GraphEdge(
                    source_id=file_node_id,
                    target_id=fn_id,
                    edge_type=EdgeType.DEFINES,
                    file_path=rel_p,
                    line_number=fn["start_line"],
                ))

            # METHOD Nodes, CONTAINS & BELONGS_TO Edges
            for m in data.methods:
                m_name = m["name"]
                p_cls = m["parent_class"]
                m_id = make_method_node_id(rel_p, p_cls, m_name)
                cls_id = make_class_node_id(rel_p, p_cls)

                m_node = GraphNode(
                    id=m_id,
                    node_type=NodeType.METHOD,
                    name=m_name,
                    file_path=rel_p,
                    start_line=m["start_line"],
                    end_line=m["end_line"],
                    parent_id=cls_id,
                    metadata={"parent_class": p_cls},
                )
                store.add_node(m_node)
                class_methods.setdefault((rel_p, p_cls), {})[m_name] = m_id
                all_symbols_by_name.setdefault(m_name, []).append(m_id)

                # Edge: CLASS -(CONTAINS)-> METHOD
                store.add_edge(GraphEdge(
                    source_id=cls_id,
                    target_id=m_id,
                    edge_type=EdgeType.CONTAINS,
                    file_path=rel_p,
                    line_number=m["start_line"],
                ))

                # Edge: METHOD -(BELONGS_TO)-> CLASS
                store.add_edge(GraphEdge(
                    source_id=m_id,
                    target_id=cls_id,
                    edge_type=EdgeType.BELONGS_TO,
                    file_path=rel_p,
                    line_number=m["start_line"],
                ))

        # Step 4: Create IMPORTS edges
        # Support module imports and symbol imports
        for rel_p, data in parsed_files.items():
            file_node_id = make_file_node_id(rel_p)
            current_dir = Path(rel_p).parent

            for imp in data.imports:
                mod_str = imp.module_name.lstrip(".")
                # Resolve relative imports if needed
                target_file_rel = None
                if imp.module_name.startswith("."):
                    # relative import from current dir
                    cand = (current_dir / mod_str).as_posix()
                    if cand in module_to_file:
                        target_file_rel = module_to_file[cand]
                    elif (current_dir / f"{mod_str}.py").as_posix() in parsed_files:
                        target_file_rel = (current_dir / f"{mod_str}.py").as_posix()
                elif imp.module_name in module_to_file:
                    target_file_rel = module_to_file[imp.module_name]

                if target_file_rel and target_file_rel in parsed_files:
                    target_file_id = make_file_node_id(target_file_rel)
                    store.add_edge(GraphEdge(
                        source_id=file_node_id,
                        target_id=target_file_id,
                        edge_type=EdgeType.IMPORTS,
                        file_path=rel_p,
                        line_number=imp.line_number,
                        metadata={"import_type": imp.import_type, "imported_names": imp.imported_names},
                    ))
                else:
                    # External / standard module node
                    m_id = make_module_node_id(imp.module_name or "unknown")
                    if not store.get_node(m_id):
                        store.add_node(GraphNode(
                            id=m_id,
                            node_type=NodeType.MODULE,
                            name=imp.module_name or "unknown",
                            file_path="",
                        ))
                    store.add_edge(GraphEdge(
                        source_id=file_node_id,
                        target_id=m_id,
                        edge_type=EdgeType.IMPORTS,
                        file_path=rel_p,
                        line_number=imp.line_number,
                        metadata={"import_type": imp.import_type, "imported_names": imp.imported_names},
                    ))

        # Step 5: Deterministic Name Resolution for CALLS edges
        for rel_p, data in parsed_files.items():
            # Build import map for this file: imported_symbol_name -> target_node_id
            imported_symbols_map: Dict[str, str] = {}
            current_dir = Path(rel_p).parent

            for imp in data.imports:
                mod_str = imp.module_name.lstrip(".")
                target_f = None
                if imp.module_name.startswith("."):
                    cand = (current_dir / mod_str).as_posix()
                    if cand in module_to_file:
                        target_f = module_to_file[cand]
                    elif (current_dir / f"{mod_str}.py").as_posix() in parsed_files:
                        target_f = (current_dir / f"{mod_str}.py").as_posix()
                elif imp.module_name in module_to_file:
                    target_f = module_to_file[imp.module_name]

                if target_f and target_f in parsed_files:
                    for sym in imp.imported_names:
                        # Check function in target file
                        if sym in file_functions.get(target_f, {}):
                            imported_symbols_map[sym] = file_functions[target_f][sym]
                        # Check class in target file
                        elif sym in file_classes.get(target_f, {}):
                            imported_symbols_map[sym] = file_classes[target_f][sym]

            # Resolve each call site
            for call in data.calls:
                # 1. Determine caller node ID
                if call.caller_type == "method" and call.parent_class:
                    caller_id = make_method_node_id(rel_p, call.parent_class, call.caller_name)
                else:
                    caller_id = make_function_node_id(rel_p, call.caller_name)

                callee_name = call.callee_name
                resolved_callee_id: Optional[str] = None

                # Resolution priority:
                # 1. Same class method (if caller is in a class and call is self.method() or method())
                if call.parent_class and (rel_p, call.parent_class) in class_methods:
                    methods_in_cls = class_methods[(rel_p, call.parent_class)]
                    if callee_name in methods_in_cls and (call.receiver == "self" or call.receiver is None):
                        resolved_callee_id = methods_in_cls[callee_name]

                # 2. Same file function
                if not resolved_callee_id and rel_p in file_functions:
                    if callee_name in file_functions[rel_p]:
                        resolved_callee_id = file_functions[rel_p][callee_name]

                # 3. Imported symbol in this file
                if not resolved_callee_id:
                    if callee_name in imported_symbols_map:
                        resolved_callee_id = imported_symbols_map[callee_name]

                # 4. Known unique project symbol (only if single match across the project to avoid ambiguity)
                if not resolved_callee_id and callee_name in all_symbols_by_name:
                    candidates = all_symbols_by_name[callee_name]
                    if len(candidates) == 1:
                        resolved_callee_id = candidates[0]

                # 5. Add CALLS edge if successfully resolved (do NOT create fake nodes for unresolved calls)
                if resolved_callee_id and store.get_node(resolved_callee_id):
                    store.add_edge(GraphEdge(
                        source_id=caller_id,
                        target_id=resolved_callee_id,
                        edge_type=EdgeType.CALLS,
                        file_path=rel_p,
                        line_number=call.line_number,
                        metadata={"receiver": call.receiver, "call_type": call.call_type},
                    ))

        return store
