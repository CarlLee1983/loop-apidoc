from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.manifest.models import Manifest, UrlSource


NOW = datetime(2026, 8, 30, tzinfo=timezone.utc)
SIGNED = "https://docs.example.com/spec?token=s3cret"
SIGNED_ID = "https://docs.example.com/spec?token=[REDACTED]"


def _manifest() -> Manifest:
    return Manifest(
        sources_root="/src",
        generated_at=NOW,
        url_sources=[
            UrlSource(
                url=SIGNED,
                fetched_at=NOW,
                http_status=200,
                content_sha256="a" * 64,
                snapshot_file="spec.json",
            )
        ],
    )


def test_a_url_source_keeps_the_credential_for_fetching_and_not_for_naming():
    source = _manifest().url_sources[0]

    assert source.fetch_url == SIGNED
    assert source.citation_id == SIGNED_ID


def test_source_identities_are_the_vocabulary_the_agent_actually_sees():
    """Issue #158. `readable_source_identities` is compared against the `source`
    field an agent writes, and the agent only ever read redacted artifacts. An
    identity set spelled with the credential can never match what it wrote."""
    manifest = _manifest()

    assert manifest.readable_source_identities() == {SIGNED_ID}
    assert manifest.all_source_identities() == {SIGNED_ID}


def test_coverage_check_names_an_uncited_url_by_its_identity_and_joins_on_it():
    """Issue #158. `document_ids` here is matched against the `manifest_source`
    values in provenance, so this is a join as well as a written message: spell
    one side with the credential and the other without, and every URL source
    reports as uncited while the credential lands in `Issue.location`."""
    from loop_apidoc.generate.models import ProvenanceDocument, ProvenanceEntry
    from loop_apidoc.plan.models import PlanItemStatus
    from loop_apidoc.validate.coverage import check_manifest_coverage

    manifest = _manifest()
    cited = ProvenanceDocument(
        notebook_url="",
        entries=[
            ProvenanceEntry(
                target="paths./x.get",
                manifest_source=SIGNED_ID,
                status=PlanItemStatus.SUPPORTED,
            )
        ],
    )

    # `validate_run_dir` reads both models back off disk before calling this,
    # and that is the path the join was broken on: the manifest side was already
    # redacted at write time while `manifest_source` was not, so
    # `loop-apidoc validate` reported every signed URL source as uncited.
    from_disk = Manifest.model_validate_json(manifest.model_dump_json())
    cited_from_disk = ProvenanceDocument.model_validate_json(cited.model_dump_json())

    assert check_manifest_coverage(manifest, cited) == []
    assert check_manifest_coverage(from_disk, cited_from_disk) == []

    issues = check_manifest_coverage(
        manifest, ProvenanceDocument(notebook_url="", entries=[])
    )
    assert issues
    assert all("s3cret" not in (issue.location or "") for issue in issues)
    assert any(SIGNED_ID == issue.location for issue in issues)


def test_the_generated_markdown_and_review_html_name_the_identity():
    """The two artifacts a reader actually opens. Nothing joins on these — they
    are pure display — but they are the ones that get pasted into a ticket."""
    from loop_apidoc.generate.markdown import _scope
    from loop_apidoc.generate.review import _source_rows
    from loop_apidoc.plan.models import NormalizationPlan

    manifest = _manifest()
    plan = NormalizationPlan(notebook_url="", overview_note="x")

    scope = "\n".join(_scope(plan, manifest))
    assert "s3cret" not in scope
    assert SIGNED_ID in scope

    rows = _source_rows(manifest)
    assert "s3cret" not in rows
    assert "token=[REDACTED]" in rows


def test_the_extraction_evidence_source_set_names_a_url_by_its_identity():
    """Issue #158. `_source_set` builds the descriptors the extraction evidence
    adapter is checked against, and its locator is hashed into the source-set
    id — so a raw URL here both leaks and pins a digest to a credential that
    will not exist next run."""
    from loop_apidoc.agentcli.evidence import _source_set

    source_set, _ = _source_set(_manifest())

    url_descriptors = [item for item in source_set.sources if item.kind == "url"]
    assert [item.locator for item in url_descriptors] == [SIGNED_ID]


def test_the_coverage_check_reports_a_collapsed_url_source_once():
    """Two links differing only in their signature share one identity, so the
    document list must not name it twice."""
    from loop_apidoc.generate.models import ProvenanceDocument
    from loop_apidoc.validate.coverage import check_manifest_coverage

    manifest = Manifest(
        sources_root="/src",
        generated_at=NOW,
        url_sources=[
            UrlSource(url=f"{SIGNED}A", fetched_at=NOW, http_status=200),
            UrlSource(url=f"{SIGNED}B", fetched_at=NOW, http_status=200),
        ],
    )

    issues = check_manifest_coverage(
        manifest, ProvenanceDocument(notebook_url="", entries=[])
    )

    assert len(issues) == 1
