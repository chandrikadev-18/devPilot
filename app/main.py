import sys
import argparse
from pathlib import Path
from app.scanner.scanner import ProjectScanner

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="DevPilot v0.1 - Project Scanner")
    parser.add_argument(
        "directory", 
        type=str, 
        help="Path to the project directory to scan"
    )
    
    args = parser.parse_args()
    scanner = ProjectScanner()
    
    try:
        files, stats = scanner.scan(args.directory)
        
        print(f"Project: {Path(args.directory).name}\n")
        print(f"Files: {stats.total_files}")
        print(f"Directories: {stats.total_dirs}\n")
        
        print("Extensions:")
        # Sort extensions by count descending
        sorted_exts = sorted(stats.extensions.items(), key=lambda item: item[1], reverse=True)
        for ext, count in sorted_exts:
            ext_display = ext if ext else "(none)"
            print(f"{ext_display:<8} {count}")
            
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except NotADirectoryError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except PermissionError:
        print("Error: Permission denied accessing directory.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
