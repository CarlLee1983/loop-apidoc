from __future__ import annotations

import os
from pathlib import Path

from . import descriptor_namespace, governed, head_io, store
from loop_apidoc.foundry.models import (
    Catalog,
    CatalogDocsetEntry,
    Docset,
    FoundryInputError,
    FoundryPublicationError,
)


def register_docset(
    project_root: Path, docset: Docset, *, exist_ok: bool = False
) -> Docset:
    if (
        not docset.docset_id
        or docset.docset_id in {".", ".."}
        or "/" in docset.docset_id
        or "\\" in docset.docset_id
    ):
        raise FoundryInputError("unsafe docset id")

    transaction = store.begin_catalog_transaction(project_root)
    publication = store.AssetPublication()
    docset_fd = -1
    docset_identity: tuple[int, int] | None = None
    staging_name: str | None = None
    existing_docset = False
    catalog_snapshot: head_io.HeadSnapshot | None = None
    docset_snapshot: head_io.HeadSnapshot | None = None
    catalog_bytes: bytes | None
    docset_bytes: bytes | None = None
    preflight_complete = False

    def close_docset_fd() -> None:
        nonlocal docset_fd
        if docset_fd >= 0:
            os.close(docset_fd)
            docset_fd = -1

    def validate_catalog_namespace() -> None:
        governed.validate_catalog_namespace(
            transaction.project_root,
            root_fd=transaction.root_fd,
            foundry_fd=transaction.foundry_fd,
            api_fd=transaction.api_fd,
            docsets_fd=transaction.docsets_fd,
        )

    def rollback() -> list[tuple[str, BaseException]]:
        failures: list[tuple[str, BaseException]] = []
        if catalog_snapshot is not None:
            try:
                head_io.restore_head_relative(
                    transaction.api_fd, "catalog.json", catalog_snapshot
                )
            except BaseException as exc:
                failures.append(("catalog.json", exc))
        if existing_docset:
            if docset_snapshot is not None:
                try:
                    head_io.restore_head_relative(
                        docset_fd, "docset.json", docset_snapshot
                    )
                except BaseException as exc:
                    failures.append(("docset.json", exc))
            try:
                descriptor_namespace.validate_directory_relative(
                    transaction.docsets_fd, docset.docset_id, docset_fd
                )
            except BaseException as exc:
                failures.append(("docset namespace", exc))
        elif docset_identity is not None and not failures:
            try:
                target = docset.docset_id if publication.owned_root else staging_name
                if target is not None:
                    descriptor_namespace.remove_owned_entry_relative(
                        transaction.docsets_fd, target, docset_identity
                    )
            except BaseException as exc:
                failures.append(("docset directory", exc))
        return failures

    try:
        # Complete all fallible head capture before the first mutation.
        catalog_snapshot = head_io.read_head_snapshot_relative(
            transaction.api_fd, "catalog.json"
        )
        catalog_bytes = catalog_snapshot.content
        existing_identity = descriptor_namespace.entry_identity_relative(
            transaction.docsets_fd, docset.docset_id
        )
        if existing_identity is None:
            staging_name, docset_fd, docset_identity = (
                descriptor_namespace.create_owned_directory_relative(
                    transaction.docsets_fd,
                    prefix=f".{docset.docset_id}-register-",
                )
            )
        else:
            existing_docset = True
            docset_identity = existing_identity
            docset_fd = descriptor_namespace.open_directory_relative(
                transaction.docsets_fd, docset.docset_id
            )
            opened = os.fstat(docset_fd)
            if (opened.st_dev, opened.st_ino) != existing_identity:
                raise FoundryPublicationError(
                    "governance namespace changed during publication: "
                    f"{docset.docset_id}"
                )
            docset_snapshot = head_io.read_head_snapshot_relative(
                docset_fd, "docset.json"
            )
            docset_bytes = docset_snapshot.content
            if docset_bytes is not None:
                if not exist_ok:
                    raise FoundryInputError(
                        f"docset already exists: {docset.docset_id} "
                        "(use exist_ok to update)"
                    )
                try:
                    existing = Docset.model_validate_json(docset_bytes)
                except ValueError as exc:
                    raise FoundryInputError("invalid docset.json") from exc
                docset = docset.model_copy(
                    update={"current_asset": existing.current_asset}
                )
        preflight_complete = True

        store.save_docset(
            transaction.project_root,
            docset,
            parent_fd=docset_fd,
            outcome=docset_snapshot,
        )
        if not existing_docset:
            assert staging_name is not None and docset_identity is not None
            store.publish_asset(
                Path(staging_name),
                Path(docset.docset_id),
                outcome=publication,
                parent_fd=transaction.docsets_fd,
                expected_identity=docset_identity,
            )
        descriptor_namespace.validate_directory_relative(
            transaction.docsets_fd, docset.docset_id, docset_fd
        )

        try:
            catalog = (
                Catalog.model_validate_json(catalog_bytes)
                if catalog_bytes is not None
                else Catalog()
            )
        except ValueError as exc:
            raise FoundryInputError("invalid catalog.json") from exc
        catalog = store.upsert_catalog_entry(
            catalog,
            CatalogDocsetEntry(
                docset_id=docset.docset_id,
                title=docset.title,
                provider=docset.provider,
                product=docset.product,
                current_asset=docset.current_asset,
            ),
        )
        store.save_catalog(
            transaction.project_root,
            catalog,
            parent_fd=transaction.api_fd,
            outcome=catalog_snapshot,
        )
        descriptor_namespace.validate_directory_relative(
            transaction.docsets_fd, docset.docset_id, docset_fd
        )
        validate_catalog_namespace()
    except BaseException as primary:
        failures = rollback() if preflight_complete else []
        close_docset_fd()
        if getattr(primary, "recovery_required", False):
            transaction.abandon()
            raise
        if failures:
            transaction.abandon()
            details = "; ".join(
                f"{label}: {type(error).__name__}: {error}"
                for label, error in failures
            )
            raise FoundryPublicationError(
                f"docset registration failed: {primary}; rollback failures: {details}"
            ) from primary
        try:
            validate_catalog_namespace()
        except FoundryPublicationError as namespace_error:
            transaction.abandon()
            raise FoundryPublicationError(
                f"docset registration failed: {primary}; {namespace_error}; "
                "rollback completed in the pinned tree and its lock was retained"
            ) from primary
        transaction.close()
        raise

    try:
        transaction.close()
    except FoundryPublicationError as lock_error:
        failures = rollback()
        close_docset_fd()
        if failures:
            transaction.abandon()
            details = "; ".join(
                f"{label}: {type(error).__name__}: {error}"
                for label, error in failures
            )
            raise FoundryPublicationError(
                f"registration lock cleanup failed: {lock_error}; "
                f"rollback failures: {details}"
            ) from lock_error
        try:
            validate_catalog_namespace()
        except FoundryPublicationError as namespace_error:
            transaction.abandon()
            raise FoundryPublicationError(
                f"registration lock cleanup failed: {lock_error}; "
                f"{namespace_error}; rollback completed in the pinned tree "
                "and its lock was retained"
            ) from lock_error
        transaction.force_close()
        raise
    close_docset_fd()
    return docset
