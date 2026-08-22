import sys
import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.scanner.scanner import ProjectScanner
from app.parser.python_parser import PythonParser
from app.indexer.chunker import CodeChunk, CodeChunker
from app.embeddings.embedder import (
    CodeEmbedder,
    save_embedding_index,
    DEFAULT_EMBEDDING_MODEL,
)
from app.vector_store.qdrant_store import (
    QdrantVectorStore,
    DEFAULT_COLLECTION_NAME,
    DEFAULT_STORAGE_PATH,
    VectorStoreError,
    ConfigurationMismatchError,
    ValidationError,
)
from app.search.semantic_search import (
    SearchResult,
    SemanticSearcher,
)
from app.llm import (
    LLMAuthenticationError,
    LLMError,
    LLMProvider,
    create_llm_provider,
    strip_thinking_and_tool_tags,
)
from app.rag import (
    ContextBuilder,
    QAResult,
    RAGPipeline,
)
from app.agent import (
    AgentResult,
    CodebaseAgent,
    create_codebase_agent,
)
from app.git import (
    GitBlameError,
    GitCommitNotFoundError,
    GitError,
    GitFileNotFoundError,
    GitRepository,
    GitSecurityError,
    NotAGitRepositoryError,
    get_commit_detail,
    get_file_blame,
    get_file_history,
    get_last_commit_for_file,
    get_recent_commits,
    get_repository,
    is_git_repository,
)
from app.graph import (
    EdgeType,
    GraphBuilder,
    GraphStore,
    NodeType,
    get_callees,
    get_callers,
    get_dependencies,
    get_dependents,
    get_file_dependencies,
    get_impact,
    load_graph,
    save_graph,
)


def run_scan(directory: str):
    scanner = ProjectScanner()
    try:
        files, stats = scanner.scan(directory)
        
        print(f"Project: {Path(directory).name}\n")
        print(f"Files: {stats.total_files}")
        print(f"Directories: {stats.total_dirs}\n")
        
        print("Extensions:")
        sorted_exts = sorted(stats.extensions.items(), key=lambda item: item[1], reverse=True)
        for ext, count in sorted_exts:
            ext_display = ext if ext else "(none)"
            print(f"{ext_display:<8} {count}")
            
    except Exception as e:
        print(f"Error scanning directory: {e}", file=sys.stderr)
        sys.exit(1)


def run_parse(directory: str, as_json: bool = False):
    parser = PythonParser()
    try:
        results = parser.parse_directory(directory)
        
        if as_json:
            print(json.dumps(results, indent=2))
        else:
            print(f"Parsed {len(results)} Python files in {Path(directory).name}\n")
            for file_res in results:
                print(f"File: {file_res.get('file', 'Unknown')}")
                if 'error' in file_res:
                    print(f"  Error: {file_res['error']}")
                    continue
                
                print(f"  Imports: {len(file_res['imports'])}")
                print(f"  Classes: {len(file_res['classes'])}")
                print(f"  Methods: {len(file_res['methods'])}")
                print(f"  Functions: {len(file_res['functions'])}\n")
                
    except Exception as e:
        print(f"Error parsing directory: {e}", file=sys.stderr)
        sys.exit(1)


def run_index(directory: str, as_json: bool = False):
    scanner = ProjectScanner()
    parser = PythonParser()
    chunker = CodeChunker()
    
    root_path = Path(directory).resolve()
    if not root_path.exists():
        print(f"Error: Directory does not exist: {root_path}", file=sys.stderr)
        sys.exit(1)
    if not root_path.is_dir():
        print(f"Error: Path is not a directory: {root_path}", file=sys.stderr)
        sys.exit(1)

    try:
        files, stats = scanner.scan(directory)
    except Exception as e:
        print(f"Error scanning directory: {e}", file=sys.stderr)
        sys.exit(1)

    python_files = [f for f in files if f.extension == ".py"]
    
    all_chunks: List[CodeChunk] = []
    file_errors: List[dict] = []
    analyzed_files_count = 0

    function_count = 0
    class_count = 0
    method_count = 0

    for file_info in python_files:
        try:
            parsed_res = parser.parse_file(file_info.absolute_path)
            if "error" in parsed_res:
                file_errors.append({
                    "file": file_info.relative_path,
                    "error": parsed_res["error"]
                })
                continue
            
            chunks = chunker.chunk_parsed_file(
                parsed_res, file_path_override=file_info.relative_path
            )
            all_chunks.extend(chunks)
            analyzed_files_count += 1

            for chunk in chunks:
                if chunk.symbol_type == "function":
                    function_count += 1
                elif chunk.symbol_type == "class":
                    class_count += 1
                elif chunk.symbol_type == "method":
                    method_count += 1

        except Exception as e:
            file_errors.append({
                "file": file_info.relative_path,
                "error": str(e)
            })

    if as_json:
        output = {
            "project": directory,
            "total_chunks": len(all_chunks),
            "chunks": [chunk.to_dict() for chunk in all_chunks],
        }
        if file_errors:
            output["errors"] = file_errors
        print(json.dumps(output, indent=2))
    else:
        print("DevPilot v0.3 - Code Indexer\n")
        print(f"Project: {directory}\n")
        print(f"Python files analyzed: {analyzed_files_count}\n")
        print(f"Chunks created: {len(all_chunks)}\n")
        print(f"Functions: {function_count}")
        print(f"Classes: {class_count}")
        print(f"Methods: {method_count}\n")

        if file_errors:
            print("Files with errors:")
            for err in file_errors:
                print(f"  {err['file']} → parsing failed: {err['error']}")
            print()

        print("Indexing completed successfully.")


def run_embed(directory: str, output_path: str = "data/embeddings/index.json"):
    t_start = time.time()
    
    root_path = Path(directory).resolve()
    if not root_path.exists():
        print(f"Error: Directory does not exist: {root_path}", file=sys.stderr)
        sys.exit(1)
    if not root_path.is_dir():
        print(f"Error: Path is not a directory: {root_path}", file=sys.stderr)
        sys.exit(1)

    # 1. Scan and parse
    t_chunk_start = time.time()
    scanner = ProjectScanner()
    parser = PythonParser()
    chunker = CodeChunker()

    try:
        files, stats = scanner.scan(directory)
    except Exception as e:
        print(f"Error scanning directory: {e}", file=sys.stderr)
        sys.exit(1)

    python_files = [f for f in files if f.extension == ".py"]
    all_chunks: List[CodeChunk] = []
    analyzed_files_count = 0
    file_errors: List[dict] = []

    for file_info in python_files:
        try:
            parsed_res = parser.parse_file(file_info.absolute_path)
            if "error" in parsed_res:
                file_errors.append({
                    "file": file_info.relative_path,
                    "error": parsed_res["error"]
                })
                continue
            chunks = chunker.chunk_parsed_file(
                parsed_res, file_path_override=file_info.relative_path
            )
            all_chunks.extend(chunks)
            analyzed_files_count += 1
        except Exception as e:
            file_errors.append({
                "file": file_info.relative_path,
                "error": str(e)
            })

    t_chunk_end = time.time()
    chunk_prep_time = t_chunk_end - t_chunk_start

    if not all_chunks:
        print("No code chunks found.\nNothing to embed.")
        return

    # 2. Model Loading
    t_model_start = time.time()
    try:
        embedder = CodeEmbedder()
        _ = embedder.dimension  # ensures model is loaded
    except Exception as e:
        print(f"Error loading embedding model: {e}", file=sys.stderr)
        sys.exit(1)
    t_model_end = time.time()
    model_load_time = t_model_end - t_model_start

    # 3. Embedding generation
    t_embed_start = time.time()
    try:
        embeddings = embedder.embed_chunks(all_chunks)
    except Exception as e:
        print(f"Error generating embeddings: {e}", file=sys.stderr)
        sys.exit(1)
    t_embed_end = time.time()
    embed_time = t_embed_end - t_embed_start

    # 4. Save index
    t_save_start = time.time()
    try:
        saved_path = save_embedding_index(
            output_path=output_path,
            model_name=embedder.model_name,
            dimension=embedder.dimension,
            chunks=all_chunks,
            embeddings=embeddings,
        )
    except Exception as e:
        print(f"Error saving embedding index: {e}", file=sys.stderr)
        sys.exit(1)
    t_save_end = time.time()
    save_time = t_save_end - t_save_start

    total_time = time.time() - t_start

    print("DevPilot v0.4 - Code Embeddings\n")
    print(f"Project: {directory}\n")
    print(f"Python files analyzed: {analyzed_files_count}")
    print(f"Code chunks: {len(all_chunks)}\n")
    print(f"Embedding model:\n{embedder.model_name}\n")
    print(f"Embedding dimension:\n{embedder.dimension}\n")
    print(f"Embeddings generated:\n{len(embeddings)}\n")
    print(f"Index saved:\n{Path(saved_path).as_posix()}\n")
    
    print("Performance:")
    print(f"  Model loading: {model_load_time:.2f}s")
    print(f"  Chunk preparation: {chunk_prep_time:.2f}s")
    print(f"  Embedding generation: {embed_time:.2f}s")
    print(f"  Index saving: {save_time:.2f}s")
    print(f"  Total: {total_time:.2f}s\n")

    if file_errors:
        print("Files with errors:")
        for err in file_errors:
            print(f"  {err['file']} → parsing failed: {err['error']}")
        print()

    print("Embedding completed successfully.")


def run_embed_query(query: str, show_vector: bool = False):
    if not query or not query.strip():
        print("Error: Query cannot be empty.", file=sys.stderr)
        sys.exit(1)

    try:
        embedder = CodeEmbedder()
        vector = embedder.embed_text(query)
    except Exception as e:
        print(f"Error generating query embedding: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Query:\n{query}\n")
    print(f"Embedding dimension:\n{embedder.dimension}\n")
    print("Vector generated successfully.")

    if show_vector:
        print("\nVector:")
        print(f"[{', '.join(f'{x:.4f}' for x in vector[:8])}, ... ({len(vector)} dimensions total)]")


def run_store(
    directory: str,
    storage_path: str = DEFAULT_STORAGE_PATH,
    collection_name: str = DEFAULT_COLLECTION_NAME,
):
    """Executes the full v0.5 pipeline: scan -> parse -> chunk -> embed -> Qdrant store."""
    t_start = time.time()

    root_path = Path(directory).resolve()
    if not root_path.exists():
        print(f"Error: Directory does not exist: {root_path}", file=sys.stderr)
        sys.exit(1)
    if not root_path.is_dir():
        print(f"Error: Path is not a directory: {root_path}", file=sys.stderr)
        sys.exit(1)

    # 1. Scanner
    t_scan_start = time.time()
    scanner = ProjectScanner()
    try:
        files, stats = scanner.scan(directory)
    except Exception as e:
        print(f"Error scanning directory: {e}", file=sys.stderr)
        sys.exit(1)
    t_scan_end = time.time()
    scan_time = t_scan_end - t_scan_start

    # 2. Parser
    t_parse_start = time.time()
    parser = PythonParser()
    python_files = [f for f in files if f.extension == ".py"]
    parsed_results = []
    file_errors = []
    analyzed_files_count = 0

    for file_info in python_files:
        try:
            parsed_res = parser.parse_file(file_info.absolute_path)
            if "error" in parsed_res:
                file_errors.append({
                    "file": file_info.relative_path,
                    "error": parsed_res["error"]
                })
                continue
            parsed_results.append((file_info.relative_path, parsed_res))
            analyzed_files_count += 1
        except Exception as e:
            file_errors.append({
                "file": file_info.relative_path,
                "error": str(e)
            })
    t_parse_end = time.time()
    parse_time = t_parse_end - t_parse_start

    # 3. Chunking
    t_chunk_start = time.time()
    chunker = CodeChunker()
    all_chunks: List[CodeChunk] = []
    for rel_path, parsed_res in parsed_results:
        chunks = chunker.chunk_parsed_file(parsed_res, file_path_override=rel_path)
        all_chunks.extend(chunks)
    t_chunk_end = time.time()
    chunk_time = t_chunk_end - t_chunk_start

    if not all_chunks:
        print("DevPilot v0.5 - Vector Store\n")
        print(f"Project: {directory}\n")
        print("No code chunks found.\nNothing to store.")
        return

    # 4. Embeddings
    t_embed_start = time.time()
    try:
        embedder = CodeEmbedder()
        _ = embedder.dimension  # ensure model is ready
        embeddings = embedder.embed_chunks(all_chunks)
    except Exception as e:
        print(f"Error generating embeddings: {e}", file=sys.stderr)
        sys.exit(1)
    t_embed_end = time.time()
    embed_time = t_embed_end - t_embed_start

    # 5. Qdrant Store
    t_qdrant_start = time.time()
    try:
        store = QdrantVectorStore(storage_path=storage_path)
        store.create_collection(
            collection_name=collection_name,
            vector_size=embedder.dimension,
        )
    except ConfigurationMismatchError as e:
        print(f"Configuration Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error initializing Qdrant store: {e}", file=sys.stderr)
        sys.exit(1)
    t_qdrant_end = time.time()
    qdrant_init_time = t_qdrant_end - t_qdrant_start

    # 6. Upsert vectors
    t_upsert_start = time.time()
    try:
        points_stored = store.upsert_chunks(
            chunks=all_chunks,
            vectors=embeddings,
            collection_name=collection_name,
        )
    except Exception as e:
        print(f"Error storing vectors in Qdrant: {e}", file=sys.stderr)
        sys.exit(1)
    t_upsert_end = time.time()
    upsert_time = t_upsert_end - t_upsert_start

    total_time = time.time() - t_start

    # Output matching specification
    print("DevPilot v0.5 - Vector Store\n")
    print(f"Project: {directory}\n")
    print(f"Python files analyzed: {analyzed_files_count}")
    print(f"Code chunks: {len(all_chunks)}\n")
    print(f"Embedding model:\n{embedder.model_name}\n")
    print(f"Embedding dimension:\n{embedder.dimension}\n")
    print(f"Qdrant collection:\n{collection_name}\n")
    print(f"Vectors stored:\n{points_stored}\n")
    print(f"Storage:\n{Path(storage_path).as_posix()}/\n")
    print("Performance:")
    print(f"  Scanner: {scan_time:.2f}s")
    print(f"  Parser: {parse_time:.2f}s")
    print(f"  Chunking: {chunk_time:.2f}s")
    print(f"  Embedding: {embed_time:.2f}s")
    print(f"  Qdrant: {qdrant_init_time:.2f}s")
    print(f"  Upsert: {upsert_time:.2f}s")
    print(f"  Total: {total_time:.2f}s\n")

    if file_errors:
        print("Files with errors:")
        for err in file_errors:
            print(f"  {err['file']} → parsing failed: {err['error']}")
        print()

    print("Vector storage completed successfully.")


def run_store_info(
    storage_path: str = DEFAULT_STORAGE_PATH,
    collection_name: str = DEFAULT_COLLECTION_NAME,
):
    """Displays information about the Qdrant vector collection."""
    try:
        store = QdrantVectorStore(storage_path=storage_path)
        if not store.collection_exists(collection_name):
            print("DevPilot v0.5 - Vector Store Information\n")
            print(f"Collection:\n{collection_name}\n")
            print("Status:\nCollection does not exist.")
            return

        info = store.get_collection_info(collection_name)
        print("DevPilot v0.5 - Vector Store Information\n")
        print(f"Collection:\n{info['collection_name']}\n")
        print(f"Vector dimension:\n{info['vector_size']}\n")
        print(f"Distance:\n{info['distance']}\n")
        print(f"Points:\n{info['points']}\n")
        print(f"Status:\n{info['status']}")
    except Exception as e:
        print(f"Error retrieving collection info: {e}", file=sys.stderr)
        sys.exit(1)


def run_store_get(
    chunk_id: str,
    storage_path: str = DEFAULT_STORAGE_PATH,
    collection_name: str = DEFAULT_COLLECTION_NAME,
):
    """Retrieves and displays a stored CodeChunk by its ID."""
    if not chunk_id or not chunk_id.strip():
        print("Error: chunk_id cannot be empty.", file=sys.stderr)
        sys.exit(1)

    try:
        store = QdrantVectorStore(storage_path=storage_path)
        payload = store.get_by_id(chunk_id.strip(), collection_name=collection_name)
    except Exception as e:
        print(f"Error querying vector store: {e}", file=sys.stderr)
        sys.exit(1)

    if not payload:
        print(f"Chunk ID '{chunk_id}' not found in vector store.")
        return

    print("Chunk ID:")
    print(f"{payload.get('chunk_id', chunk_id)}\n")
    print("File:")
    print(f"{payload.get('file_path', '')}\n")
    print("Symbol:")
    print(f"{payload.get('symbol_name', '')}\n")
    print("Type:")
    print(f"{payload.get('symbol_type', '')}\n")
    if payload.get("parent_symbol"):
        print("Parent:")
        print(f"{payload.get('parent_symbol')}\n")
    print("Lines:")
    print(f"{payload.get('start_line', 0)}-{payload.get('end_line', 0)}")


def run_store_reset(
    storage_path: str = DEFAULT_STORAGE_PATH,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    auto_confirm: bool = False,
):
    """Deletes the Qdrant vector collection upon explicit confirmation."""
    if not auto_confirm:
        print("Are you sure you want to delete the DevPilot vector collection?")
        try:
            user_input = input("Type 'yes' to continue: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nReset cancelled.")
            return

        if user_input != "yes":
            print("Reset cancelled.")
            return

    try:
        store = QdrantVectorStore(storage_path=storage_path)
        deleted = store.delete_collection(collection_name=collection_name)
        if deleted:
            print(f"Collection '{collection_name}' deleted successfully.")
        else:
            print(f"Collection '{collection_name}' does not exist.")
    except Exception as e:
        print(f"Error resetting collection: {e}", file=sys.stderr)
        sys.exit(1)


def run_search(
    query: str,
    top_k: int = 5,
    min_score: Optional[float] = None,
    extension: Optional[str] = None,
    path_prefix: Optional[str] = None,
    symbol_type: Optional[str] = None,
    as_json: bool = False,
    storage_path: str = DEFAULT_STORAGE_PATH,
    collection_name: str = DEFAULT_COLLECTION_NAME,
):
    """Executes semantic code search across indexed code vectors."""
    if not query or not query.strip():
        print("Search query cannot be empty.", file=sys.stderr)
        sys.exit(1)

    t_start = time.time()
    try:
        t_model_start = time.time()
        embedder = CodeEmbedder()
        _ = embedder.dimension  # ensure model is loaded
        t_model_end = time.time()
        model_load_time = t_model_end - t_model_start

        store = QdrantVectorStore(storage_path=storage_path)
        searcher = SemanticSearcher(
            embedder=embedder,
            vector_store=store,
            collection_name=collection_name,
        )

        # 1. Verify compatibility
        searcher.verify_collection_compatibility()

        # 2. Embedding query
        t_embed_start = time.time()
        _ = embedder.embed_text(query)
        t_embed_end = time.time()
        embed_time = t_embed_end - t_embed_start

        # 3. Vector Search & Processing
        t_search_start = time.time()
        results = searcher.search(
            query=query,
            top_k=top_k,
            min_score=min_score,
            extension=extension,
            path_prefix=path_prefix,
            symbol_type=symbol_type,
        )
        t_search_end = time.time()
        search_time = t_search_end - t_search_start

        total_time = time.time() - t_start
        proc_time = max(0.0, total_time - model_load_time - embed_time - search_time)

    except (VectorStoreError, ConfigurationMismatchError, ValidationError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Search error: {e}", file=sys.stderr)
        sys.exit(1)

    if as_json:
        output = {
            "query": query,
            "top_k": top_k,
            "results": [r.to_dict() for r in results],
        }
        print(json.dumps(output, indent=2))
        return

    print("DevPilot v0.6 - Semantic Code Search\n")
    print(f"Query:\n{query}\n")

    if not results:
        print("No sufficiently relevant code found.")
        return

    print("Results:\n")
    for idx, r in enumerate(results, start=1):
        print(f"[{idx}] Score: {r.score:.4f}")
        print(f"File: {r.file_path}")
        print(f"Symbol: {r.symbol_name}")
        print(f"Type: {r.symbol_type}")
        if r.parent_symbol:
            print(f"Class: {r.parent_symbol}")
        print(f"Lines: {r.start_line}-{r.end_line}\n")
        print(f"{r.code.strip()}\n")

    print(f"Found {len(results)} relevant result{'s' if len(results) != 1 else ''}.\n")
    print("Performance:")
    print(f"  Query embedding: {embed_time:.2f}s")
    print(f"  Qdrant search: {search_time:.2f}s")
    print(f"  Result processing: {proc_time:.2f}s")
    print(f"  Total: {total_time:.2f}s")


def run_ask(
    question: str,
    top_k: int = 5,
    min_score: Optional[float] = None,
    extension: Optional[str] = None,
    path_prefix: Optional[str] = None,
    symbol_type: Optional[str] = None,
    as_json: bool = False,
    storage_path: str = DEFAULT_STORAGE_PATH,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    provider_name: Optional[str] = None,
    model_name: Optional[str] = None,
):
    """Executes RAG Codebase Question Answering."""
    try:
        embedder = CodeEmbedder()
        store = QdrantVectorStore(storage_path=storage_path)
        searcher = SemanticSearcher(
            embedder=embedder,
            vector_store=store,
            collection_name=collection_name,
        )

        llm = create_llm_provider(
            provider_name=provider_name,
            model=model_name,
        )

        pipeline = RAGPipeline(
            searcher=searcher,
            llm=llm,
        )

        result = pipeline.ask(
            question=question,
            top_k=top_k,
            min_score=min_score,
            extension=extension,
            path_prefix=path_prefix,
            symbol_type=symbol_type,
        )

    except LLMAuthenticationError as e:
        print(f"LLM API key is not configured.\nPlease configure the required environment variable.", file=sys.stderr)
        sys.exit(1)
    except (VectorStoreError, ConfigurationMismatchError, ValidationError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except LLMError as e:
        print(f"LLM Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
        return

    print("DevPilot v0.7 - Codebase Q&A\n")
    print(f"Question:\n{result.question}\n")
    print(f"Answer:\n\n{result.answer}\n")

    if result.sources:
        print("Sources:\n")
        for idx, src in enumerate(result.sources, start=1):
            print(f"{idx}. {src.get('file_path')}")
            sym = src.get('symbol_name')
            if sym:
                parent = src.get('parent_symbol')
                if parent:
                    print(f"   {parent}.{sym}()")
                else:
                    print(f"   {sym}()")
            print(f"   Lines: {src.get('start_line')}-{src.get('end_line')}")
            if "score" in src:
                print(f"   Score: {src.get('score'):.4f}")
            print()

    search_time = result.timings.get("search", 0.0)
    llm_time = result.timings.get("llm", 0.0)
    total_time = result.timings.get("total", 0.0)

    print(f"Search time: {search_time:.2f}s")
    print(f"LLM time: {llm_time:.2f}s")
    print(f"Total time: {total_time:.2f}s")


def run_agent(
    question: str,
    top_k: int = 5,
    min_score: Optional[float] = None,
    project_dir: Optional[str] = None,
    as_json: bool = False,
    debug: bool = False,
    storage_path: str = DEFAULT_STORAGE_PATH,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    provider_name: Optional[str] = None,
    model_name: Optional[str] = None,
):
    """Executes AI Agent Codebase Reasoning and Tool Use."""
    root_path = Path(project_dir or ".").resolve()

    try:
        embedder = CodeEmbedder()
        store = QdrantVectorStore(storage_path=storage_path)
        searcher = SemanticSearcher(
            embedder=embedder,
            vector_store=store,
            collection_name=collection_name,
        )

        llm = create_llm_provider(
            provider_name=provider_name,
            model=model_name,
        )

        agent = create_codebase_agent(
            llm=llm,
            searcher=searcher,
            project_root=root_path,
            vector_store=store,
            collection_name=collection_name,
        )

        def on_iter_start(it: int):
            if debug and not as_json:
                print(f"\n[Agent Iteration {it}]")

        def on_tool(tool_name: str, args: Dict[str, Any]):
            if as_json:
                return
            if debug:
                print(f"Tool selected: {tool_name}")
                print(f"Arguments:\n{json.dumps(args, indent=2)}")
            else:
                print(f"Tool:\n{tool_name}\n")
                if "query" in args:
                    print(f"Query:\n{args['query']}\n")
                elif "file_path" in args:
                    print(f"File:\n{args['file_path']}\n")
                    if "_cache" in args:
                        print(f"Cache:\n{args['_cache']}\n")
                elif "symbol" in args:
                    print(f"Symbol:\n{args['symbol']}\n")
                elif "symbol_name" in args:
                    print(f"Symbol:\n{args['symbol_name']}\n")

        def on_tool_res(tool_name: str, res: Dict[str, Any]):
            if as_json:
                return
            if debug:
                print(f"Result for {tool_name}:\n{json.dumps(res.get('data') if res.get('success') else res.get('error'), indent=2)}\n")
            else:
                sources = res.get("sources", [])
                if sources:
                    print("Results:")
                    for s in sources[:2]:
                        p = s.get("file_path", "")
                        sym = s.get("symbol_name", "")
                        if sym:
                            print(f"{p}\n{sym}()")
                        else:
                            print(f"{p}")
                    print()

        if not as_json and not debug:
            print("DevPilot v1.2 - Codebase & Dependency Graph Agent\n")
            print(f"Question:\n{question}\n")
            print("Agent:\n")
        elif debug and not as_json:
            print("DevPilot v1.2 - Codebase & Dependency Graph Agent (Debug Mode)\n")
            print(f"Question:\n{question}\n")

        result = agent.run(
            question=question,
            on_iteration_start=on_iter_start,
            on_tool_call=on_tool,
            on_tool_result=on_tool_res,
        )

    except LLMAuthenticationError:
        print(f"LLM API key is not configured.\nPlease configure the required environment variable.", file=sys.stderr)
        sys.exit(1)
    except (VectorStoreError, ConfigurationMismatchError, ValidationError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except LLMError as e:
        print(f"LLM Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    result.answer = strip_thinking_and_tool_tags(result.answer)

    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
        return

    print(f"Final Answer:\n\n{result.answer}\n")

    if result.sources:
        print("Sources:\n")
        for idx, src in enumerate(result.sources, start=1):
            if src.get("source_type") == "git" or "commit_hash" in src:
                c_hash = src.get("short_hash") or (src.get("commit_hash", "")[:7] if src.get("commit_hash") else "")
                print(f"{idx}. [Git Source] Commit {c_hash}")
                if "author" in src and src["author"]:
                    print(f"   Author: {src['author']}")
                if "date" in src and src["date"]:
                    print(f"   Date:   {src['date']}")
                if "file_path" in src and src["file_path"]:
                    print(f"   File:   {src['file_path']}")
                if "message" in src and src["message"]:
                    print(f"   Message: {src['message']}")
            elif src.get("source_type") == "graph":
                print(f"{idx}. [Graph Source] {src.get('symbol_name') or src.get('file_path')}")
                if "file_path" in src and src["file_path"]:
                    print(f"   File:     {src['file_path']}")
                if "start_line" in src and "end_line" in src and src["start_line"] > 0:
                    print(f"   Lines:    {src['start_line']}-{src['end_line']}")
                elif "start_line" in src and src["start_line"] > 0:
                    print(f"   Line:     {src['start_line']}")
                if "relationship" in src and src["relationship"]:
                    print(f"   Relation: {src['relationship']}")
            else:
                print(f"{idx}. [Code Source] {src.get('file_path')}")
                sym = src.get('symbol_name')
                if sym and sym != "file" and sym != src.get('file_path'):
                    parent = src.get('parent_symbol')
                    if parent:
                        print(f"   {parent}.{sym}()")
                    else:
                        print(f"   {sym}()")
                if "start_line" in src and "end_line" in src:
                    print(f"   Lines: {src.get('start_line')}-{src.get('end_line')}")
                if "score" in src:
                    print(f"   Score: {src.get('score'):.4f}")
            print()

    total_time = result.timing.get("total", 0.0)
    print(f"Agent iterations: {result.iterations}")
    print(f"Tool calls: {len(result.tool_calls)}")
    print(f"Total time: {total_time:.2f}s")


def run_git_log(limit: int = 10, project_dir: str = ".", as_json: bool = False):
    """Executes git-log command showing recent repository commits."""
    root_path = Path(project_dir).resolve()
    try:
        repo = get_repository(root_path)
        commits = get_recent_commits(repo=repo, limit=limit)
        if as_json:
            print(json.dumps([c.to_dict() for c in commits], indent=2))
            return

        print(f"Recent Commits ({len(commits)}):\n")
        if not commits:
            print("No commits found in repository.")
            return

        for c in commits:
            print(f"Commit:  {c.short_hash} ({c.commit_hash})")
            print(f"Author:  {c.author_name} <{c.author_email}>")
            print(f"Date:    {c.date}")
            if c.files_changed:
                print(f"Files:   {', '.join(c.files_changed)}")
            print(f"Message: {c.message}\n")
    except (NotAGitRepositoryError, GitSecurityError, GitError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def run_git_history(file_path: str, limit: int = 10, project_dir: str = ".", as_json: bool = False):
    """Executes git-history command showing commit history for a file."""
    root_path = Path(project_dir).resolve()
    try:
        repo = get_repository(root_path)
        history = get_file_history(repo=repo, file_path=file_path, limit=limit)
        if as_json:
            print(json.dumps(history.to_dict(), indent=2))
            return

        print(f"Commit History: {history.file_path} ({len(history.commits)} commits)\n")
        if not history.commits:
            print("No commits found affecting this file.")
            return

        for c in history.commits:
            print(f"Commit:  {c.short_hash}")
            print(f"Author:  {c.author_name}")
            print(f"Date:    {c.date}")
            print(f"Message: {c.message}\n")
    except (NotAGitRepositoryError, GitSecurityError, GitFileNotFoundError, GitError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def run_git_last_change(file_path: str, project_dir: str = ".", as_json: bool = False):
    """Executes git-last-change command showing the most recent commit affecting a file."""
    root_path = Path(project_dir).resolve()
    try:
        repo = get_repository(root_path)
        commit = get_last_commit_for_file(repo=repo, file_path=file_path)
        if as_json:
            print(json.dumps(commit.to_dict() if commit else None, indent=2))
            return

        if not commit:
            print(f"No commit history found for file: {file_path}")
            return

        print(f"Last Change: {file_path}\n")
        print(f"Commit:  {commit.short_hash} ({commit.commit_hash})")
        print(f"Author:  {commit.author_name} <{commit.author_email}>")
        print(f"Date:    {commit.date}")
        print(f"Message: {commit.message}")
        if commit.files_changed:
            print("Files Changed:")
            for f in commit.files_changed:
                print(f"  - {f}")
    except (NotAGitRepositoryError, GitSecurityError, GitFileNotFoundError, GitError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def run_git_show(commit_hash: str, project_dir: str = ".", as_json: bool = False):
    """Executes git-show command showing commit metadata and diff."""
    root_path = Path(project_dir).resolve()
    try:
        repo = get_repository(root_path)
        detail = get_commit_detail(repo=repo, commit_hash=commit_hash)
        if as_json:
            print(json.dumps(detail.to_dict(), indent=2))
            return

        print(f"Commit:  {detail.commit_hash} [{detail.short_hash}]")
        print(f"Author:  {detail.author_name} <{detail.author_email}>")
        print(f"Date:    {detail.date}")
        print(f"Message:\n  {detail.message}\n")
        print(f"Changes: Files: {len(detail.files_changed)} (+{detail.additions}, -{detail.deletions})\n")
        if detail.diff_summary:
            print("Diff:")
            print(detail.diff_summary)
    except (NotAGitRepositoryError, GitSecurityError, GitCommitNotFoundError, GitError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def run_git_blame(
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    project_dir: str = ".",
    as_json: bool = False,
):
    """Executes git-blame command showing line-by-line commit authorship."""
    root_path = Path(project_dir).resolve()
    try:
        repo = get_repository(root_path)
        blame_res = get_file_blame(
            repo=repo,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
        )
        if as_json:
            print(json.dumps(blame_res.to_dict(), indent=2))
            return

        range_str = f"Lines {blame_res.start_line or 1}-{blame_res.end_line or blame_res.lines[-1].line_number if blame_res.lines else 0}"
        print(f"Blame: {blame_res.file_path} ({range_str})\n")
        for line in blame_res.lines:
            print(f"{line.line_number:<4} | {line.short_hash} | {line.author:<15} | {line.date[:10]} | {line.content}")
    except (NotAGitRepositoryError, GitSecurityError, GitFileNotFoundError, GitBlameError, GitError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _load_or_build_graph(graph_path: Optional[str] = None, project_dir: str = ".") -> GraphStore:
    """Helper to load a stored graph or build from directory."""
    root = Path(project_dir).resolve()
    target_path = Path(graph_path).resolve() if graph_path else root / "data" / "graph.json"
    if target_path.is_file():
        try:
            return GraphStore.load(target_path)
        except Exception:
            pass
    return GraphBuilder().build(root)


def run_graph_build(directory: str = ".", output_path: str = "data/graph.json"):
    """Builds and serializes a code dependency graph for a directory."""
    root = Path(directory).resolve()
    out = Path(output_path).resolve()
    try:
        builder = GraphBuilder()
        graph = builder.build(root)
        graph.save(out)

        nodes = graph.get_nodes()
        edges = graph.get_edges()

        classes_cnt = len([n for n in nodes if n.node_type == NodeType.CLASS])
        funcs_cnt = len([n for n in nodes if n.node_type == NodeType.FUNCTION])
        methods_cnt = len([n for n in nodes if n.node_type == NodeType.METHOD])
        files_cnt = len([n for n in nodes if n.node_type == NodeType.FILE])
        modules_cnt = len([n for n in nodes if n.node_type == NodeType.MODULE])

        calls_cnt = len([e for e in edges if e.edge_type == EdgeType.CALLS])
        imports_cnt = len([e for e in edges if e.edge_type == EdgeType.IMPORTS])
        contains_cnt = len([e for e in edges if e.edge_type == EdgeType.CONTAINS])
        defines_cnt = len([e for e in edges if e.edge_type == EdgeType.DEFINES])

        meta = graph.metadata or {}
        files_proc = meta.get("files_processed", files_cnt)
        files_failed = meta.get("files_failed", 0)

        print(f"DevPilot v1.0 - Code Dependency Graph Built\n")
        print(f"Target Directory: {root.name}")
        print(f"Output File:      {out}\n")
        print(f"Files Processed:  {files_proc}")
        print(f"Files Failed:     {files_failed}\n")
        print(f"Nodes Created ({len(nodes)}):")
        print(f"  - Files:        {files_cnt}")
        print(f"  - Classes:      {classes_cnt}")
        print(f"  - Functions:    {funcs_cnt}")
        print(f"  - Methods:      {methods_cnt}")
        print(f"  - Modules:      {modules_cnt}\n")
        print(f"Edges Created ({len(edges)}):")
        print(f"  - CALLS:        {calls_cnt}")
        print(f"  - IMPORTS:      {imports_cnt}")
        print(f"  - CONTAINS:     {contains_cnt}")
        print(f"  - DEFINES:      {defines_cnt}")
    except Exception as e:
        print(f"Error building graph: {e}", file=sys.stderr)
        sys.exit(1)


def run_graph_info(graph_path: Optional[str] = None, project_dir: str = ".", as_json: bool = False):
    """Displays summary statistics of the dependency graph."""
    try:
        graph = _load_or_build_graph(graph_path=graph_path, project_dir=project_dir)
        nodes = graph.get_nodes()
        edges = graph.get_edges()

        stats = {
            "total_nodes": len(nodes),
            "files": len([n for n in nodes if n.node_type == NodeType.FILE]),
            "classes": len([n for n in nodes if n.node_type == NodeType.CLASS]),
            "functions": len([n for n in nodes if n.node_type == NodeType.FUNCTION]),
            "methods": len([n for n in nodes if n.node_type == NodeType.METHOD]),
            "modules": len([n for n in nodes if n.node_type == NodeType.MODULE]),
            "total_edges": len(edges),
            "calls": len([e for e in edges if e.edge_type == EdgeType.CALLS]),
            "imports": len([e for e in edges if e.edge_type == EdgeType.IMPORTS]),
            "contains": len([e for e in edges if e.edge_type == EdgeType.CONTAINS]),
            "defines": len([e for e in edges if e.edge_type == EdgeType.DEFINES]),
            "belongs_to": len([e for e in edges if e.edge_type == EdgeType.BELONGS_TO]),
        }

        if as_json:
            print(json.dumps(stats, indent=2))
            return

        print("DevPilot v1.0 - Code Dependency Graph Info\n")
        print(f"Nodes: {stats['total_nodes']}")
        print(f"  - Files:     {stats['files']}")
        print(f"  - Classes:   {stats['classes']}")
        print(f"  - Functions: {stats['functions']}")
        print(f"  - Methods:   {stats['methods']}")
        print(f"  - Modules:   {stats['modules']}\n")
        print(f"Edges: {stats['total_edges']}")
        print(f"  - CALLS:      {stats['calls']}")
        print(f"  - IMPORTS:    {stats['imports']}")
        print(f"  - CONTAINS:   {stats['contains']}")
        print(f"  - DEFINES:    {stats['defines']}")
        print(f"  - BELONGS_TO: {stats['belongs_to']}")
    except Exception as e:
        print(f"Error inspecting graph: {e}", file=sys.stderr)
        sys.exit(1)


def run_graph_callers(symbol: str, graph_path: Optional[str] = None, project_dir: str = ".", as_json: bool = False):
    """Finds functions/methods calling a symbol."""
    try:
        graph = _load_or_build_graph(graph_path=graph_path, project_dir=project_dir)
        callers = get_callers(graph, symbol=symbol)

        if as_json:
            print(json.dumps({"symbol": symbol, "callers": callers}, indent=2))
            return

        print("DevPilot v1.0 - Code Dependency Graph\n")
        print(f"Symbol:\n{symbol}\n")
        if not callers:
            print(f"No direct callers found for '{symbol}'.")
            return

        print("Callers:\n")
        for idx, c in enumerate(callers, start=1):
            line_str = f":{c['start_line']}" if c.get("start_line") else ""
            call_l = f" (call at line {c['call_line']})" if c.get("call_line") else ""
            print(f"{idx}. {c['name']}")
            print(f"   {c['file_path']}{line_str}{call_l}\n")
    except Exception as e:
        print(f"Error querying callers: {e}", file=sys.stderr)
        sys.exit(1)


def run_graph_callees(symbol: str, graph_path: Optional[str] = None, project_dir: str = ".", as_json: bool = False):
    """Finds functions/methods called by a symbol."""
    try:
        graph = _load_or_build_graph(graph_path=graph_path, project_dir=project_dir)
        callees = get_callees(graph, symbol=symbol)

        if as_json:
            print(json.dumps({"symbol": symbol, "callees": callees}, indent=2))
            return

        print("DevPilot v1.0 - Code Dependency Graph\n")
        print(f"Symbol:\n{symbol}\n")
        if not callees:
            print(f"No outgoing calls found from '{symbol}'.")
            return

        print("Calls:\n")
        for idx, c in enumerate(callees, start=1):
            line_str = f":{c['start_line']}" if c.get("start_line") else ""
            call_l = f" (call at line {c['call_line']})" if c.get("call_line") else ""
            print(f"{idx}. {c['name']}")
            print(f"   {c['file_path']}{line_str}{call_l}\n")
    except Exception as e:
        print(f"Error querying callees: {e}", file=sys.stderr)
        sys.exit(1)


def run_graph_dependencies(symbol: str, depth: int = 1, graph_path: Optional[str] = None, project_dir: str = ".", as_json: bool = False):
    """Traverses downstream call dependencies for a symbol."""
    try:
        graph = _load_or_build_graph(graph_path=graph_path, project_dir=project_dir)
        bounded_depth = max(1, min(depth, 10))
        dep_result = get_dependencies(graph, symbol=symbol, depth=bounded_depth)

        if as_json:
            print(json.dumps(dep_result, indent=2))
            return

        print("DevPilot v1.0 - Code Dependency Graph (Dependencies)\n")
        print(f"Symbol: {dep_result['symbol']} (Depth: {dep_result['depth']})")
        print(f"Total Dependencies: {dep_result['total_dependencies']}\n")

        if not dep_result["dependencies"]:
            print(f"No downstream call dependencies found for '{symbol}'.")
            return

        for idx, d in enumerate(dep_result["dependencies"], start=1):
            line_str = f":{d['start_line']}" if d.get("start_line") else ""
            print(f"{idx}. {d['name']} (Depth {d['depth']})")
            print(f"   {d['file_path']}{line_str}")
            print(f"   Path: {d['call_path']}\n")
    except Exception as e:
        print(f"Error querying dependencies: {e}", file=sys.stderr)
        sys.exit(1)


def run_graph_dependents(symbol: str, depth: int = 1, graph_path: Optional[str] = None, project_dir: str = ".", as_json: bool = False):
    """Traverses upstream reverse call dependencies (who calls this) for a symbol."""
    try:
        graph = _load_or_build_graph(graph_path=graph_path, project_dir=project_dir)
        bounded_depth = max(1, min(depth, 10))
        dep_result = get_dependents(graph, symbol=symbol, depth=bounded_depth)

        if as_json:
            print(json.dumps(dep_result, indent=2))
            return

        print("DevPilot v1.0 - Code Dependency Graph (Dependents)\n")
        print(f"Symbol: {dep_result['symbol']} (Depth: {dep_result['depth']})")
        print(f"Total Dependents: {dep_result['total_dependents']}\n")

        if not dep_result["dependents"]:
            print(f"No upstream callers found for '{symbol}'.")
            return

        for idx, d in enumerate(dep_result["dependents"], start=1):
            line_str = f":{d['start_line']}" if d.get("start_line") else ""
            print(f"{idx}. {d['name']} (Depth {d['depth']})")
            print(f"   {d['file_path']}{line_str}")
            print(f"   Path: {d['dependent_path']}\n")
    except Exception as e:
        print(f"Error querying dependents: {e}", file=sys.stderr)
        sys.exit(1)


def run_graph_impact(symbol: str, depth: int = 2, graph_path: Optional[str] = None, project_dir: str = ".", as_json: bool = False):
    """Performs static impact analysis for a symbol."""
    try:
        graph = _load_or_build_graph(graph_path=graph_path, project_dir=project_dir)
        impact = get_impact(graph, symbol=symbol, depth=depth)

        if as_json:
            print(json.dumps(impact, indent=2))
            return

        print("DevPilot v1.0 - Static Dependency Impact Analysis\n")
        print(f"Target Symbol: {impact['symbol']} (Depth: {impact['depth']})")
        print(f"Total Affected Callers: {impact['total_impacted']}\n")

        if impact["direct_callers"]:
            print(f"Direct Callers ({len(impact['direct_callers'])}):")
            for c in impact["direct_callers"]:
                print(f"  - {c['name']} ({c['file_path']}:{c.get('start_line', 0)})")
            print()

        if impact["indirect_callers"]:
            print(f"Indirect Callers ({len(impact['indirect_callers'])}):")
            for c in impact["indirect_callers"]:
                print(f"  - {c['name']} ({c['file_path']}:{c.get('start_line', 0)}) [Depth {c['depth']}]")
            print()

        if impact["impacted_files"]:
            print("Impacted Files:")
            for f in impact["impacted_files"]:
                print(f"  - {f}")
            print()
        elif not impact["direct_callers"] and not impact["indirect_callers"]:
            print(f"No callers found affected by changes to '{symbol}'.")
    except Exception as e:
        print(f"Error analyzing impact: {e}", file=sys.stderr)
        sys.exit(1)


def run_graph_file_dependencies(file_path: str, graph_path: Optional[str] = None, project_dir: str = ".", as_json: bool = False):
    """Displays import dependencies for a file."""
    try:
        graph = _load_or_build_graph(graph_path=graph_path, project_dir=project_dir)
        file_deps = get_file_dependencies(graph, file_path=file_path)

        if as_json:
            print(json.dumps(file_deps, indent=2))
            return

        if "error" in file_deps:
            print(f"DevPilot v1.0 - File Dependencies: {file_path}\n")
            print(file_deps["error"])
            return

        print(f"DevPilot v1.0 - File Dependencies: {file_deps['file_path']}\n")
        if file_deps["imports_files"]:
            print(f"Imports Files ({len(file_deps['imports_files'])}):")
            for f in file_deps["imports_files"]:
                print(f"  - {f}")
            print()

        if file_deps["imports_modules"]:
            print(f"Imports Modules ({len(file_deps['imports_modules'])}):")
            for m in file_deps["imports_modules"]:
                print(f"  - {m}")
            print()

        if file_deps["imported_by"]:
            print(f"Imported By ({len(file_deps['imported_by'])}):")
            for f in file_deps["imported_by"]:
                print(f"  - {f}")
            print()

        if file_deps["defined_symbols"]:
            print(f"Defined Symbols ({len(file_deps['defined_symbols'])}):")
            for s in file_deps["defined_symbols"]:
                print(f"  - {s['node_type']}: {s['name']} (Lines {s['start_line']}-{s['end_line']})")
            print()
    except Exception as e:
        print(f"Error querying file dependencies: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main CLI entry point."""
    
    # Intercept arguments for backward compatibility
    known_commands = [
        "scan",
        "parse",
        "index",
        "embed",
        "embed-query",
        "store",
        "store-info",
        "store-get",
        "store-reset",
        "search",
        "ask",
        "agent",
        "git-log",
        "git-history",
        "git-last-change",
        "git-show",
        "git-blame",
        "graph-build",
        "graph-info",
        "graph-callers",
        "graph-callees",
        "graph-dependencies",
        "graph-dependents",
        "graph-impact",
        "graph-file-dependencies",
        "-h",
        "--help",
    ]
    if len(sys.argv) > 1 and sys.argv[1] not in known_commands and not sys.argv[1].startswith("-"):
        sys.argv.insert(1, "scan")

    parser = argparse.ArgumentParser(description="DevPilot v1.0 - Code Intelligence, Git Intelligence, Graph Dependencies, and AI Agent")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Scan subcommand
    scan_parser = subparsers.add_parser("scan", help="Scan a directory for project statistics")
    scan_parser.add_argument("directory", type=str, help="Path to the project directory to scan")
    
    # Parse subcommand
    parse_parser = subparsers.add_parser("parse", help="Parse Python files for AST metadata")
    parse_parser.add_argument("directory", type=str, help="Path to the project directory to parse")
    parse_parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    # Index subcommand
    index_parser = subparsers.add_parser("index", help="Index Python files into structured CodeChunk objects")
    index_parser.add_argument("directory", type=str, help="Path to the project directory to index")
    index_parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    # Embed subcommand (v0.4)
    embed_parser = subparsers.add_parser("embed", help="Generate local embeddings for code chunks")
    embed_parser.add_argument("directory", type=str, help="Path to the project directory to embed")
    embed_parser.add_argument("--output", type=str, default="data/embeddings/index.json", help="Path to save the embeddings index")

    # Embed-query subcommand (v0.4)
    query_parser = subparsers.add_parser("embed-query", help="Generate an embedding for a search query")
    query_parser.add_argument("query", type=str, help="Text query to embed")
    query_parser.add_argument("--show-vector", action="store_true", help="Display snippet of the generated vector")

    # Store subcommand (v0.5)
    store_parser = subparsers.add_parser("store", help="Index, embed, and store code chunks into Qdrant vector database")
    store_parser.add_argument("directory", type=str, help="Path to the project directory to store")
    store_parser.add_argument("--collection", type=str, default=DEFAULT_COLLECTION_NAME, help="Qdrant collection name")
    store_parser.add_argument("--storage", type=str, default=DEFAULT_STORAGE_PATH, help="Path to local Qdrant storage folder")

    # Store-info subcommand (v0.5)
    info_parser = subparsers.add_parser("store-info", help="Display information about the current Qdrant collection")
    info_parser.add_argument("--collection", type=str, default=DEFAULT_COLLECTION_NAME, help="Qdrant collection name")
    info_parser.add_argument("--storage", type=str, default=DEFAULT_STORAGE_PATH, help="Path to local Qdrant storage folder")

    # Store-get subcommand (v0.5)
    get_parser = subparsers.add_parser("store-get", help="Retrieve a stored vector and payload by chunk ID")
    get_parser.add_argument("chunk_id", type=str, help="CodeChunk ID or point UUID to retrieve")
    get_parser.add_argument("--collection", type=str, default=DEFAULT_COLLECTION_NAME, help="Qdrant collection name")
    get_parser.add_argument("--storage", type=str, default=DEFAULT_STORAGE_PATH, help="Path to local Qdrant storage folder")

    # Store-reset subcommand (v0.5)
    reset_parser = subparsers.add_parser("store-reset", help="Reset/delete the Qdrant vector collection")
    reset_parser.add_argument("--collection", type=str, default=DEFAULT_COLLECTION_NAME, help="Qdrant collection name")
    reset_parser.add_argument("--storage", type=str, default=DEFAULT_STORAGE_PATH, help="Path to local Qdrant storage folder")
    reset_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    # Search subcommand (v0.6)
    search_parser = subparsers.add_parser("search", help="Execute semantic search over indexed code vectors")
    search_parser.add_argument("query", type=str, help="Natural language search query")
    search_parser.add_argument("--top-k", type=int, default=5, help="Maximum number of search results to return (default: 5)")
    search_parser.add_argument("--min-score", type=float, default=None, help="Minimum similarity score threshold (e.g. 0.70)")
    search_parser.add_argument("--extension", type=str, default=None, help="Filter by file extension (e.g. .py)")
    search_parser.add_argument("--path", type=str, default=None, help="Filter by file path prefix (e.g. backend/)")
    search_parser.add_argument("--type", type=str, default=None, help="Filter by symbol type (function, class, method)")
    search_parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    search_parser.add_argument("--collection", type=str, default=DEFAULT_COLLECTION_NAME, help="Qdrant collection name")
    search_parser.add_argument("--storage", type=str, default=DEFAULT_STORAGE_PATH, help="Path to local Qdrant storage folder")

    # Ask subcommand (v0.7)
    ask_parser = subparsers.add_parser("ask", help="Ask questions about the indexed codebase using RAG")
    ask_parser.add_argument("question", type=str, help="Natural language question about the codebase")
    ask_parser.add_argument("--top-k", type=int, default=5, help="Maximum number of code chunks to retrieve (default: 5)")
    ask_parser.add_argument("--min-score", type=float, default=None, help="Minimum similarity score threshold (e.g. 0.70)")
    ask_parser.add_argument("--extension", type=str, default=None, help="Filter by file extension (e.g. .py)")
    ask_parser.add_argument("--path", type=str, default=None, help="Filter by file path prefix (e.g. backend/)")
    ask_parser.add_argument("--type", type=str, default=None, help="Filter by symbol type (function, class, method)")
    ask_parser.add_argument("--provider", type=str, default=None, help="LLM provider name (e.g. groq)")
    ask_parser.add_argument("--model", type=str, default=None, help="LLM model name (e.g. llama-3.3-70b-versatile)")
    ask_parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    ask_parser.add_argument("--collection", type=str, default=DEFAULT_COLLECTION_NAME, help="Qdrant collection name")
    ask_parser.add_argument("--storage", type=str, default=DEFAULT_STORAGE_PATH, help="Path to local Qdrant storage folder")

    # Agent subcommand (v0.8)
    agent_parser = subparsers.add_parser("agent", help="Ask questions using autonomous tool-using AI agent")
    agent_parser.add_argument("question", type=str, help="Natural language question about the codebase")
    agent_parser.add_argument("--top-k", type=int, default=5, help="Maximum search results per search_code call (default: 5)")
    agent_parser.add_argument("--min-score", type=float, default=None, help="Minimum similarity score threshold")
    agent_parser.add_argument("--project-dir", type=str, default=".", help="Root directory of the project")
    agent_parser.add_argument("--provider", type=str, default=None, help="LLM provider name (e.g. groq)")
    agent_parser.add_argument("--model", type=str, default=None, help="LLM model name (e.g. llama-3.3-70b-versatile)")
    agent_parser.add_argument("--debug", action="store_true", help="Display verbose step-by-step tool execution trace")
    agent_parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    agent_parser.add_argument("--collection", type=str, default=DEFAULT_COLLECTION_NAME, help="Qdrant collection name")
    agent_parser.add_argument("--storage", type=str, default=DEFAULT_STORAGE_PATH, help="Path to local Qdrant storage folder")

    # git-log subcommand (v0.9)
    git_log_parser = subparsers.add_parser("git-log", help="Display recent Git commits in the repository")
    git_log_parser.add_argument("--limit", type=int, default=10, help="Maximum number of commits to show (default: 10)")
    git_log_parser.add_argument("--project-dir", type=str, default=".", help="Target project directory")
    git_log_parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    # git-history subcommand (v0.9)
    git_history_parser = subparsers.add_parser("git-history", help="Display commit history affecting a specific file")
    git_history_parser.add_argument("file_path", type=str, help="Path to the file")
    git_history_parser.add_argument("--limit", type=int, default=10, help="Maximum number of commits to show (default: 10)")
    git_history_parser.add_argument("--project-dir", type=str, default=".", help="Target project directory")
    git_history_parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    # git-last-change subcommand (v0.9)
    git_last_parser = subparsers.add_parser("git-last-change", help="Display the most recent commit affecting a file")
    git_last_parser.add_argument("file_path", type=str, help="Path to the file")
    git_last_parser.add_argument("--project-dir", type=str, default=".", help="Target project directory")
    git_last_parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    # git-show subcommand (v0.9)
    git_show_parser = subparsers.add_parser("git-show", help="Display commit details, statistics, and diff summary")
    git_show_parser.add_argument("commit_hash", type=str, help="Commit hash or revision (e.g. HEAD, sha)")
    git_show_parser.add_argument("--project-dir", type=str, default=".", help="Target project directory")
    git_show_parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    # git-blame subcommand (v0.9)
    git_blame_parser = subparsers.add_parser("git-blame", help="Display line-by-line Git blame analysis")
    git_blame_parser.add_argument("file_path", type=str, help="Path to the file")
    git_blame_parser.add_argument("--start-line", type=int, default=None, help="Starting line number (1-indexed)")
    git_blame_parser.add_argument("--end-line", type=int, default=None, help="Ending line number (1-indexed)")
    git_blame_parser.add_argument("--project-dir", type=str, default=".", help="Target project directory")
    git_blame_parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    # graph-build subcommand (v1.0)
    graph_build_parser = subparsers.add_parser("graph-build", help="Build code dependency graph for a directory")
    graph_build_parser.add_argument("directory", type=str, nargs="?", default=".", help="Project directory to build graph for (default: .)")
    graph_build_parser.add_argument("--output", type=str, default="data/graph.json", help="Path to save output graph JSON (default: data/graph.json)")

    # graph-info subcommand (v1.0)
    graph_info_parser = subparsers.add_parser("graph-info", help="Display dependency graph summary statistics")
    graph_info_parser.add_argument("--graph", type=str, default=None, help="Path to graph JSON file (default: data/graph.json)")
    graph_info_parser.add_argument("--project-dir", type=str, default=".", help="Project directory")
    graph_info_parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    # graph-callers subcommand (v1.0)
    graph_callers_parser = subparsers.add_parser("graph-callers", help="Find functions/methods calling a symbol")
    graph_callers_parser.add_argument("symbol", type=str, help="Symbol name or ID to find callers for")
    graph_callers_parser.add_argument("--graph", type=str, default=None, help="Path to graph JSON file (default: data/graph.json)")
    graph_callers_parser.add_argument("--project-dir", type=str, default=".", help="Project directory")
    graph_callers_parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    # graph-callees subcommand (v1.0)
    graph_callees_parser = subparsers.add_parser("graph-callees", help="Find functions/methods called by a symbol")
    graph_callees_parser.add_argument("symbol", type=str, help="Symbol name or ID to find outgoing calls from")
    graph_callees_parser.add_argument("--graph", type=str, default=None, help="Path to graph JSON file (default: data/graph.json)")
    graph_callees_parser.add_argument("--project-dir", type=str, default=".", help="Project directory")
    graph_callees_parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    # graph-dependencies subcommand (v1.0)
    graph_dep_parser = subparsers.add_parser("graph-dependencies", help="Traverse downstream call dependencies for a symbol")
    graph_dep_parser.add_argument("symbol", type=str, help="Symbol name or ID to traverse dependencies from")
    graph_dep_parser.add_argument("--depth", type=int, default=1, help="Maximum traversal depth (default: 1, max: 10)")
    graph_dep_parser.add_argument("--graph", type=str, default=None, help="Path to graph JSON file (default: data/graph.json)")
    graph_dep_parser.add_argument("--project-dir", type=str, default=".", help="Project directory")
    graph_dep_parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    # graph-dependents subcommand (v1.0)
    graph_dependents_parser = subparsers.add_parser("graph-dependents", help="Traverse upstream reverse call dependencies for a symbol")
    graph_dependents_parser.add_argument("symbol", type=str, help="Symbol name or ID to find reverse dependents for")
    graph_dependents_parser.add_argument("--depth", type=int, default=1, help="Maximum upstream traversal depth (default: 1, max: 10)")
    graph_dependents_parser.add_argument("--graph", type=str, default=None, help="Path to graph JSON file (default: data/graph.json)")
    graph_dependents_parser.add_argument("--project-dir", type=str, default=".", help="Project directory")
    graph_dependents_parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    # graph-impact subcommand (v1.0)
    graph_impact_parser = subparsers.add_parser("graph-impact", help="Perform static dependency impact analysis for a symbol")
    graph_impact_parser.add_argument("symbol", type=str, help="Symbol name or ID to evaluate impact for")
    graph_impact_parser.add_argument("--depth", type=int, default=2, help="Maximum upstream depth (default: 2, max: 10)")
    graph_impact_parser.add_argument("--graph", type=str, default=None, help="Path to graph JSON file (default: data/graph.json)")
    graph_impact_parser.add_argument("--project-dir", type=str, default=".", help="Project directory")
    graph_impact_parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    # graph-file-dependencies subcommand (v1.0)
    graph_file_dep_parser = subparsers.add_parser("graph-file-dependencies", help="Display import dependencies for a file")
    graph_file_dep_parser.add_argument("file_path", type=str, help="Path to the file to inspect")
    graph_file_dep_parser.add_argument("--graph", type=str, default=None, help="Path to graph JSON file (default: data/graph.json)")
    graph_file_dep_parser.add_argument("--project-dir", type=str, default=".", help="Project directory")
    graph_file_dep_parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    args = parser.parse_args()
    
    if args.command == "scan":
        run_scan(args.directory)
    elif args.command == "parse":
        run_parse(args.directory, as_json=args.json)
    elif args.command == "index":
        run_index(args.directory, as_json=args.json)
    elif args.command == "embed":
        run_embed(args.directory, output_path=args.output)
    elif args.command == "embed-query":
        run_embed_query(args.query, show_vector=args.show_vector)
    elif args.command == "store":
        run_store(args.directory, storage_path=args.storage, collection_name=args.collection)
    elif args.command == "store-info":
        run_store_info(storage_path=args.storage, collection_name=args.collection)
    elif args.command == "store-get":
        run_store_get(args.chunk_id, storage_path=args.storage, collection_name=args.collection)
    elif args.command == "store-reset":
        run_store_reset(storage_path=args.storage, collection_name=args.collection, auto_confirm=args.yes)
    elif args.command == "search":
        run_search(
            query=args.query,
            top_k=args.top_k,
            min_score=args.min_score,
            extension=args.extension,
            path_prefix=args.path,
            symbol_type=args.type,
            as_json=args.json,
            storage_path=args.storage,
            collection_name=args.collection,
        )
    elif args.command == "ask":
        run_ask(
            question=args.question,
            top_k=args.top_k,
            min_score=args.min_score,
            extension=args.extension,
            path_prefix=args.path,
            symbol_type=args.type,
            as_json=args.json,
            storage_path=args.storage,
            collection_name=args.collection,
            provider_name=args.provider,
            model_name=args.model,
        )
    elif args.command == "agent":
        run_agent(
            question=args.question,
            top_k=args.top_k,
            min_score=args.min_score,
            project_dir=args.project_dir,
            as_json=args.json,
            debug=args.debug,
            storage_path=args.storage,
            collection_name=args.collection,
            provider_name=args.provider,
            model_name=args.model,
        )
    elif args.command == "git-log":
        run_git_log(
            limit=args.limit,
            project_dir=args.project_dir,
            as_json=args.json,
        )
    elif args.command == "git-history":
        run_git_history(
            file_path=args.file_path,
            limit=args.limit,
            project_dir=args.project_dir,
            as_json=args.json,
        )
    elif args.command == "git-last-change":
        run_git_last_change(
            file_path=args.file_path,
            project_dir=args.project_dir,
            as_json=args.json,
        )
    elif args.command == "git-show":
        run_git_show(
            commit_hash=args.commit_hash,
            project_dir=args.project_dir,
            as_json=args.json,
        )
    elif args.command == "git-blame":
        run_git_blame(
            file_path=args.file_path,
            start_line=args.start_line,
            end_line=args.end_line,
            project_dir=args.project_dir,
            as_json=args.json,
        )
    elif args.command == "graph-build":
        run_graph_build(
            directory=args.directory,
            output_path=args.output,
        )
    elif args.command == "graph-info":
        run_graph_info(
            graph_path=args.graph,
            project_dir=args.project_dir,
            as_json=args.json,
        )
    elif args.command == "graph-callers":
        run_graph_callers(
            symbol=args.symbol,
            graph_path=args.graph,
            project_dir=args.project_dir,
            as_json=args.json,
        )
    elif args.command == "graph-callees":
        run_graph_callees(
            symbol=args.symbol,
            graph_path=args.graph,
            project_dir=args.project_dir,
            as_json=args.json,
        )
    elif args.command == "graph-dependencies":
        run_graph_dependencies(
            symbol=args.symbol,
            depth=args.depth,
            graph_path=args.graph,
            project_dir=args.project_dir,
            as_json=args.json,
        )
    elif args.command == "graph-dependents":
        run_graph_dependents(
            symbol=args.symbol,
            depth=args.depth,
            graph_path=args.graph,
            project_dir=args.project_dir,
            as_json=args.json,
        )
    elif args.command == "graph-impact":
        run_graph_impact(
            symbol=args.symbol,
            depth=args.depth,
            graph_path=args.graph,
            project_dir=args.project_dir,
            as_json=args.json,
        )
    elif args.command == "graph-file-dependencies":
        run_graph_file_dependencies(
            file_path=args.file_path,
            graph_path=args.graph,
            project_dir=args.project_dir,
            as_json=args.json,
        )


if __name__ == "__main__":
    main()
