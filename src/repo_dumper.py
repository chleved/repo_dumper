#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path
import os
import datetime

try:
    import pathspec
except ImportError:
    print("ERROR: The 'pathspec' library is required but not found.", file=sys.stderr)
    print("Please install it using: pip install pathspec", file=sys.stderr)
    sys.exit(1)

try:
    from binaryornot.check import is_binary
except ImportError:
    print("ERROR: The 'binaryornot' library is required for checking file types.", file=sys.stderr)
    print("Please install it using: pip install binaryornot", file=sys.stderr)
    sys.exit(1)

DEFAULT_EXCLUDE_STRUCTURE = [
    "**/.git/*",
    "**/lib/*/*",
    "**/.cspell/*",
    "**/repo_dump.md"
]

DEFAULT_EXCLUDE_EDITABLE_FILES = [
    "**/lib/*",
]

DEFAULT_OUTPUT_FILENAME = "repo_dump.md"

def get_all_paths(root_dir: Path) -> list[Path]:
    """Collects all unique files and folders recursively from the root_dir."""
    return list(set(p for p in root_dir.rglob('*') if p.exists() or p.is_symlink()))

def apply_exclusions(
    paths_to_filter: list[Path],
    exclusion_patterns: list[str],
    reference_dir: Path
) -> list[Path]:
    """Applies exclusion patterns to a list of Path objects using pathspec."""
    if not exclusion_patterns or not paths_to_filter:
        return list(paths_to_filter)

    relative_path_strings_map = {}
    for item in paths_to_filter:
        try:
            if item.exists() or item.is_symlink():
                 relative_path_strings_map[str(item.relative_to(reference_dir)).replace(os.sep, '/')] = item
        except ValueError:
            continue
        except Exception:
            continue
    
    if not relative_path_strings_map:
        return []

    normalized_patterns = [p.replace(os.sep, '/') for p in exclusion_patterns]
    
    try:
        spec = pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, normalized_patterns)
    except Exception as e:
        print(f"ERROR: Could not compile pathspec patterns: {normalized_patterns}. Error: {e}", file=sys.stderr)
        return [path_map_item for path_map_item in relative_path_strings_map.values()]

    excluded_relative_strings = set(spec.match_files(relative_path_strings_map.keys()))
    
    final_paths = [
        original_item for rel_str, original_item in relative_path_strings_map.items()
        if rel_str not in excluded_relative_strings
    ]
    return final_paths

def format_paths_for_markdown_list(paths: list[Path], reference_dir: Path) -> list[str]:
    """Formats a list of Path objects into strings for a Markdown list."""
    output_lines = []
    try:
        sorted_paths = sorted(paths, key=lambda p: str(p.relative_to(reference_dir) if p.is_relative_to(reference_dir) else p))
    except TypeError:
        sorted_paths = paths

    for item in sorted_paths:
        try:
            display_path_str = str(item.relative_to(reference_dir))
            if item.is_dir():
                output_lines.append(f"- `{display_path_str}{os.sep}`")
            else:
                output_lines.append(f"- `{display_path_str}`")
        except (ValueError, TypeError):
            output_lines.append(f"- `{str(item)}{' (Error: Not relative)' if isinstance(item, Path) and item.is_absolute() else ''}`")
        except Exception:
             output_lines.append(f"- `{str(item)} (Error: Path processing)`")
    return output_lines

def is_file_readable_text(filepath: Path) -> bool:
    """Checks if a file is likely readable text (not binary)."""
    if not filepath.is_file() or not filepath.exists():
        return False
    try:
        return not is_binary(str(filepath))
    except Exception:
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Filters and lists repository contents, optionally printing readable files. Output is Markdown.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "root_path", type=str,
        help="The root directory of the repository/project to scan."
    )
    parser.add_argument(
        "-i", "--initial_list", action="store_true",
        help="Print all collected paths (Markdown format) before any exclusions and exit."
    )
    parser.add_argument(
        "-e", "--exclude_structure", nargs="+", metavar="PATTERN", default=[],
        help="gitignore-style patterns to exclude from the 'Repository Structure'."
    )
    parser.add_argument(
        "-s", "--exclude_editable", nargs="+", metavar="PATTERN", default=[],
        help="gitignore-style patterns to *additionally* exclude from 'Editable Files'."
    )
    parser.add_argument(
        "-d", "--default_patterns", action="store_true",
        help="Enable predefined default exclusion patterns."
    )
    parser.add_argument(
        "-o", "--output_file", type=str, default=DEFAULT_OUTPUT_FILENAME,
        help=f"Name of the Markdown output file. Default: {DEFAULT_OUTPUT_FILENAME}"
    )

    args = parser.parse_args()
    
    target_root_path = Path(args.root_path).resolve()
    if not target_root_path.is_dir():
        print(f"Error: Specified root path '{args.root_path}' is not a valid directory.", file=sys.stderr)
        sys.exit(1)

    output_filename_to_use = args.output_file
    
    current_default_exclude_editable_files = list(DEFAULT_EXCLUDE_EDITABLE_FILES)
    current_default_exclude_editable_files.append(output_filename_to_use)
    current_default_exclude_editable_files.append(f"**/{output_filename_to_use}")


    if args.initial_list:
        scan_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        print(f"Scanning directory: {target_root_path} for initial list...\n")
        initial_paths = get_all_paths(target_root_path)
        
        output_md_content = [
            "---",
            f"scan_timestamp: \"{scan_time}\"",
            f"root_path: \"{str(target_root_path).replace(os.sep, '/')}\"",
            f"filter_mode: Initial List",
            "---",
            "",
            "# Initial Collected Paths (Folders and Files)",
            ""
        ]
        output_md_content.extend(format_paths_for_markdown_list(initial_paths, target_root_path))
        
        for line in output_md_content:
            print(line)
        sys.exit(0)

    print(f"Scanning directory: {target_root_path}\n")
    all_collected_paths = get_all_paths(target_root_path)
    
    repository_structure_paths = list(all_collected_paths) 

    effective_e_patterns = list(args.exclude_structure) 
    if args.default_patterns:
        effective_e_patterns.extend(DEFAULT_EXCLUDE_STRUCTURE)

    if effective_e_patterns:
        repository_structure_paths = apply_exclusions(
            repository_structure_paths, effective_e_patterns, target_root_path
        )
    
    intermediate_editable_files = [
        item for item in repository_structure_paths if item.is_file()
    ]
    
    editable_files_paths = list(intermediate_editable_files)

    effective_s_patterns = list(args.exclude_editable)
    if args.default_patterns:
        effective_s_patterns.extend(current_default_exclude_editable_files)

    if effective_s_patterns:
        editable_files_paths = apply_exclusions(
            editable_files_paths, effective_s_patterns, target_root_path
        )

    # --- Prepare Markdown Output ---
    scan_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    output_md_content = [
        "---",
        f"scan_timestamp: \"{scan_time}\"",
        f"root_path: \"{str(target_root_path).replace(os.sep, '/')}\"",
        f"default_patterns_enabled: {args.default_patterns}",
        f"custom_exclude_structure_patterns: {args.exclude_structure}",
        f"custom_exclude_editable_patterns: {args.exclude_editable}",
        "---",
        "",
        "# Repository Structure",
        ""
    ]
    repo_structure_formatted_md = format_paths_for_markdown_list(repository_structure_paths, target_root_path)
    output_md_content.extend(repo_structure_formatted_md)
    output_md_content.append("")

    output_md_content.append("# Editable Files (List)")
    output_md_content.append("")
    editable_files_formatted_md = format_paths_for_markdown_list(editable_files_paths, target_root_path)
    output_md_content.extend(editable_files_formatted_md)
    output_md_content.append("")

    output_md_content.append("# Content of Editable Files")
    output_md_content.append("")

    sorted_editable_files_for_content = sorted(editable_files_paths, key=lambda p: str(p.relative_to(target_root_path) if p.is_relative_to(target_root_path) else p))

    for file_path in sorted_editable_files_for_content:
        relative_file_path_str = str(file_path.relative_to(target_root_path)).replace(os.sep, '/')
        output_md_content.append(f"## FILE: `{relative_file_path_str}`")
        output_md_content.append("")

        lang_hint = file_path.suffix[1:] if file_path.suffix else "text"

        if is_file_readable_text(file_path):
            try:
                content = file_path.read_text(encoding="utf-8")
                output_md_content.append(f"```{lang_hint}")
                output_md_content.append(content.strip())
                output_md_content.append("```")
            except UnicodeDecodeError:
                output_md_content.append("```text")
                output_md_content.append("[Error: Could not decode file content with UTF-8]")
                output_md_content.append("```")
            except Exception as e:
                output_md_content.append("```text")
                output_md_content.append(f"[Error reading file: {e}]")
                output_md_content.append("```")
        else:
            output_md_content.append("```text")
            output_md_content.append("[File is binary or unreadable]")
            output_md_content.append("```")
        output_md_content.append("")

    print(f"\nContent of editable files processed. Full output in '{output_filename_to_use}'.")

    output_file_on_disk = target_root_path / output_filename_to_use
    try:
        with open(output_file_on_disk, "w", encoding="utf-8") as f:
            for line in output_md_content:
                f.write(line + "\n")
        print(f"\nFormatted output written to: {output_file_on_disk}")
    except IOError as e:
        print(f"\nError writing output to file '{output_file_on_disk}': {e}", file=sys.stderr)

if __name__ == "__main__":
    main()