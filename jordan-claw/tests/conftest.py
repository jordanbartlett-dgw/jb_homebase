from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _auto_patch_ingest_db_functions():
    """Ensure ingest DB functions are always mocked to avoid real DB calls in unit tests.

    Tests that explicitly patch these functions will override these defaults via
    the @patch decorator, which takes effect on top of this fixture's patches.
    """
    try:
        with (
            patch(
                "scripts.obsidian_sync.ingest.insert_note",
                new_callable=AsyncMock,
                return_value={"id": "auto-mock-id"},
            ),
            patch(
                "scripts.obsidian_sync.ingest.update_note",
                new_callable=AsyncMock,
            ),
            patch(
                "scripts.obsidian_sync.ingest.delete_chunks_for_note",
                new_callable=AsyncMock,
            ),
        ):
            yield
    except ModuleNotFoundError:
        # Not running ingest tests; skip patching
        yield
