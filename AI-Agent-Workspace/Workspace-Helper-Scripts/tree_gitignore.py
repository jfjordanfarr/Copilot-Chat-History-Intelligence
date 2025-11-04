import os
import argparse
from pathlib import Path
import pathspec

def find_gitignore(start_path):
    """Find the .gitignore file in the start_path or its parents."""
    current_path = Path(start_path).resolve()
    while True:
        gitignore_path = current_path / '.gitignore'
        if gitignore_path.is_file():
            return gitignore_path
        parent = current_path.parent
        if parent == current_path:  # Reached root
            return None
        current_path = parent

def load_gitignore_patterns(gitignore_path):
    """Load patterns from a .gitignore file."""
    if not gitignore_path:
        return []
    with open(gitignore_path, 'r') as f:
        return [line for line in f.read().splitlines() if line and not line.strip().startswith('#')]

def build_tree(directory, spec, gitignore_root, dirs_only=False, prefix=''):
    """Generate a tree-like listing of ``directory`` while honoring ``.gitignore`` rules.
    The function walks ``directory`` recursively, skipping any files or folders whose
    relative paths match the provided ``spec``. Each entry is streamed to standard output
    with characters that resemble the layout produced by ``tree(1)`` in a terminal.
    Args:
        directory: Filesystem location to traverse.
        spec: Compiled ``pathspec`` instance used to filter ignored paths.
        gitignore_root: Base directory from which ignore patterns are evaluated.
        dirs_only: If ``True``, omit files and display directories only.
        prefix: Visual prefix carried forward to nested levels of the tree.
    Returns:
        None: The directory structure is printed directly to standard output.
    """
    """Recursively build the directory tree string."""
    current_dir_path = Path(directory).resolve()
    try:
        items_abs = sorted(list(current_dir_path.iterdir()), key=lambda x: (x.is_file(), x.name.lower()))
    except PermissionError:
        print(f"{prefix}└── [ACCESS DENIED] {current_dir_path.name}/")
        return
    except FileNotFoundError:
        print(f"Error: Directory not found: {current_dir_path}")
        return

    filtered_items_abs = [
        item_abs for item_abs in items_abs
        if not spec.match_file(str(item_abs.relative_to(gitignore_root)))
    ]

    if dirs_only:
        filtered_items_abs = [item for item in filtered_items_abs if item.is_dir()]

    if not filtered_items_abs:
        return

    pointers = ['├── ' for _ in range(len(filtered_items_abs) - 1)] + ['└── ']

    for pointer, item_abs_path in zip(pointers, filtered_items_abs):
        print(f"{prefix}{pointer}{item_abs_path.name}{'/' if item_abs_path.is_dir() else ''}")

        if item_abs_path.is_dir():
            extension = '│   ' if pointer == '├── ' else '    '
            build_tree(item_abs_path, spec, gitignore_root, dirs_only=dirs_only, prefix=prefix + extension)

def main():
    parser = argparse.ArgumentParser(description='List directory contents like tree, respecting .gitignore.')
    parser.add_argument('directory', nargs='?', default='.', help='The directory to list (default: current directory)')
    parser.add_argument('--dirs-only', action='store_true', help='Only print directory names')
    args = parser.parse_args()

    start_dir = Path(args.directory).resolve()

    if not start_dir.is_dir():
        print(f"Error: '{start_dir}' is not a valid directory.")
        return

    gitignore_path = find_gitignore(start_dir)
    gitignore_root = gitignore_path.parent if gitignore_path else start_dir
    patterns = load_gitignore_patterns(gitignore_path)
    patterns.extend(['.git'])
    patterns.extend(['.venv/', '__pycache__/'])
    spec = pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, patterns)

    print(f"{start_dir.name}/ ({gitignore_root})")
    build_tree(start_dir, spec, gitignore_root, dirs_only=args.dirs_only)

if __name__ == "__main__":
    main()