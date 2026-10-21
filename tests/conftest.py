from pathlib import Path

import pytest

# HC description docs and the catalog are not in git; tests marked `docs` need a local copy.
HAS_DOCS = (Path(__file__).resolve().parent.parent / "data/hcs/catalog.md").exists()


def pytest_collection_modifyitems(items):
    skip = pytest.mark.skip(reason="HC docs not present (data/hcs/docs is not in git)")
    for item in items:
        if not HAS_DOCS and item.get_closest_marker("docs"):
            item.add_marker(skip)
