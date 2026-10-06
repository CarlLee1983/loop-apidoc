from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer


def inspect_source_risk(
    sources: Path = typer.Option(
        ..., "--sources", exists=True, file_okay=False, readable=True
    ),
    manifest: Path = typer.Option(..., "--manifest", exists=True, readable=True),
    output: Path = typer.Option(..., "--output"),
    max_bytes: Annotated[
        int,
        typer.Option(
            "--max-bytes",
            min=1,
            help="每個文字來源可完整掃描的最大位元組數",
        ),
    ] = 5 * 1024 * 1024,
) -> None:
    """Inspect manifest sources for deterministic pre-agent content risks."""
    import hashlib

    from loop_apidoc.source_quality.loader import (
        SourceQualityInputError,
        load_manifest,
    )
    from loop_apidoc.source_risk import SourceRiskInputError, inspect_source_risks
    from loop_apidoc.source_risk.report import write_reports as write_risk_reports

    try:
        manifest_bytes = manifest.read_bytes()
        parsed_manifest = load_manifest(manifest)
        report = inspect_source_risks(
            sources_root=sources,
            manifest=parsed_manifest,
            manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
            max_bytes=max_bytes,
        )
        write_risk_reports(report, output)
    except (OSError, SourceQualityInputError, SourceRiskInputError) as exc:
        typer.echo(f"inspect-source-risk error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"source risk {report.verdict.value}: reports written to {output}")
    raise typer.Exit(code=0 if report.verdict.value == "pass" else 1)


def assess_sources(
    sources: Path = typer.Option(..., "--sources", exists=True, file_okay=False),
    manifest: Path = typer.Option(..., "--manifest", exists=True),
    source_risk: Path = typer.Option(
        ...,
        "--source-risk",
        exists=True,
        file_okay=False,
        readable=True,
        help="inspect-source-risk 產出的 pass report 目錄",
    ),
    observations: Path = typer.Option(..., "--observations", exists=True),
    source_set: str = typer.Option(..., "--source-set"),
    output: Path = typer.Option(..., "--output"),
    base_manifest: Path | None = typer.Option(None, "--base-manifest", exists=True),
) -> None:
    """Assess source quality before extraction and write supplement reports."""
    import hashlib

    from loop_apidoc.source_quality.assess import assess_source_quality
    from loop_apidoc.source_quality.diff import build_source_diff
    from loop_apidoc.source_quality.loader import (
        SourceQualityInputError,
        load_manifest,
        load_observations,
    )
    from loop_apidoc.source_quality.models import SourceDiffReport
    from loop_apidoc.source_quality.report import write_reports as write_quality_reports
    from loop_apidoc.source_risk import (
        SourceRiskInputError,
        load_verified_source_risk_report,
    )

    try:
        manifest_bytes = manifest.read_bytes()
        parsed_manifest = load_manifest(manifest)
        parsed_source_risk = load_verified_source_risk_report(
            source_risk,
            manifest=parsed_manifest,
            sources_root=sources,
            manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        )
        parsed_observations = load_observations(observations)
    except (OSError, SourceQualityInputError, SourceRiskInputError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    report = assess_source_quality(
        manifest=parsed_manifest,
        source_set=source_set,
        observations=parsed_observations,
        base_report=None,
        source_risk=parsed_source_risk,
    )
    diff = (
        build_source_diff(base=load_manifest(base_manifest), head=parsed_manifest)
        if base_manifest
        else SourceDiffReport()
    )
    write_quality_reports(report, diff, output)
    typer.echo(f"source quality {report.verdict.value}: reports written to {output}")
    raise typer.Exit(code=0 if report.verdict.value == "pass" else 1)
