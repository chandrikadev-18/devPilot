import sys
import argparse
import json
import time
from pathlib import Path
from typing import List
from app.scanner.scanner import ProjectScanner
from app.parser.python_parser import PythonParser
from app.indexer.chunker import CodeChunk, CodeChunker
from app.embeddings.embedder import (
    CodeEmbedder,
    save_embedding_index,
    DEFAULT_EMBEDDING_MODEL,
)

def run_scan(directory):
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

def run_parse(directory, as_json=False):
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

def main():
    """Main CLI entry point."""
    
    # Intercept arguments for backward compatibility
    # If the first argument is not a known subcommand and doesn't start with '-', treat it as 'scan'
    known_commands = ["scan", "parse", "index", "embed", "embed-query", "-h", "--help"]
    if len(sys.argv) > 1 and sys.argv[1] not in known_commands and not sys.argv[1].startswith("-"):
        sys.argv.insert(1, "scan")

    parser = argparse.ArgumentParser(description="DevPilot v0.4 - Code Intelligence and Embeddings")
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

if __name__ == "__main__":
    main()
