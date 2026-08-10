import sys
import argparse
import json
from pathlib import Path
from app.scanner.scanner import ProjectScanner
from app.parser.python_parser import PythonParser

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

def main():
    """Main CLI entry point."""
    
    # Intercept arguments for backward compatibility
    # If the first argument is not a known subcommand and doesn't start with '-', treat it as 'scan'
    if len(sys.argv) > 1 and sys.argv[1] not in ["scan", "parse"] and not sys.argv[1].startswith("-"):
        sys.argv.insert(1, "scan")

    parser = argparse.ArgumentParser(description="DevPilot v0.2 - Project Scanner and Parser")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Scan subcommand
    scan_parser = subparsers.add_parser("scan", help="Scan a directory for project statistics")
    scan_parser.add_argument("directory", type=str, help="Path to the project directory to scan")
    
    # Parse subcommand
    parse_parser = subparsers.add_parser("parse", help="Parse Python files for AST metadata")
    parse_parser.add_argument("directory", type=str, help="Path to the project directory to parse")
    parse_parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    args = parser.parse_args()
    
    if args.command == "scan":
        run_scan(args.directory)
    elif args.command == "parse":
        run_parse(args.directory, as_json=args.json)

if __name__ == "__main__":
    main()
