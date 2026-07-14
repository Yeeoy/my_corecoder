import difflib


def _unified_diff(
    old: str,
    new: str,
    filename: str,
    context: int = 3,
    max_result: int = 3000,
) -> str:
    """Generate a compact unified diff between old and new file content."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        n=context,
    )
    result = "".join(diff)
    # truncate enormous diffs
    if len(result) > max_result:
        result = result[:max_result] + "\n... (diff truncated)\n"
    return result
