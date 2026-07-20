from __future__ import annotations

import pytest

from loop_apidoc.adapters.memory import InMemoryEvidenceStore
from loop_apidoc.core.models import SourceDescriptor, SourceSet


def test_memory_store_refuses_to_replace_source_set_version():
    store = InMemoryEvidenceStore()
    source_set = SourceSet(
        id="sources",
        version="1",
        sources=(SourceDescriptor(id="manual", kind="memory", locator="manual"),),
    )
    store.put_source_set(source_set)

    with pytest.raises(ValueError, match="immutable"):
        store.put_source_set(source_set.model_copy(update={"sources": ()}))
