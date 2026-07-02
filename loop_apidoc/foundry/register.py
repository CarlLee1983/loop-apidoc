from __future__ import annotations

from pathlib import Path

from loop_apidoc.foundry import paths, store
from loop_apidoc.foundry.models import CatalogDocsetEntry, Docset, FoundryInputError


def register_docset(
    project_root: Path, docset: Docset, *, exist_ok: bool = False
) -> Docset:
    manifest_path = paths.docset_manifest_path(project_root, docset.docset_id)
    if manifest_path.is_file():
        if not exist_ok:
            raise FoundryInputError(
                f"docset already exists: {docset.docset_id} (use exist_ok to update)"
            )
        existing = store.load_docset(project_root, docset.docset_id)
        docset = docset.model_copy(update={"current_asset": existing.current_asset})

    store.save_docset(project_root, docset)
    catalog = store.upsert_catalog_entry(
        store.load_catalog(project_root),
        CatalogDocsetEntry(
            docset_id=docset.docset_id,
            title=docset.title,
            provider=docset.provider,
            product=docset.product,
            current_asset=docset.current_asset,
        ),
    )
    store.save_catalog(project_root, catalog)
    return docset
