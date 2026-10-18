import re
from pathlib import Path

from office import labels as L

DOC = Path(__file__).resolve().parent.parent / "docs" / "LABELS.md"


def documented() -> dict[str, str]:
    """Label name -> color, from the first two columns of every table row in LABELS.md."""
    rows = re.findall(r"^\| `([^`]+)` \| `#([0-9A-Fa-f]{6})` \|", DOC.read_text(), re.M)
    return {name: color.upper() for name, color in rows}


def test_every_office_label_is_documented_with_its_color():
    docs = documented()
    for label in L.LABELS:
        assert label.name in docs, f"{label.name} missing from docs/LABELS.md"
        assert docs[label.name] == label.color.upper(), f"{label.name} color differs"


def test_doc_lists_no_labels_the_office_does_not_create():
    assert set(documented()) == {lb.name for lb in L.LABELS}


def test_repo_aliases_are_documented():
    text = DOC.read_text()
    for alias in L.BLOCKED_ALIASES:
        assert f"| `{alias}` |" in text
