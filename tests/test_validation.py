"""Test output validation: truncated body detection."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.common import _is_truncated


def test_is_truncated():
    assert _is_truncated("hello..."), "trailing ellipsis"
    assert _is_truncated("hello...\n"), "trailing ellipsis + newline"
    assert not _is_truncated("hello"), "clean text"
    assert not _is_truncated(""), "empty"
    assert not _is_truncated("hello\nworld"), "multi-line clean"
    print("_is_truncated OK")


if __name__ == "__main__":
    test_is_truncated()
    print("VALIDATION TEST OK")
