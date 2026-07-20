from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from loop_apidoc.core.models import (
    EvidenceBundle,
    EvidenceFragment,
    SourceArtifact,
    SourceSet,
)
from loop_apidoc.domain.projections import Projection


class LocalFileSourceAdapter:
    def acquire(self, source_set: SourceSet) -> EvidenceBundle:
        artifacts: list[SourceArtifact] = []
        fragments: list[EvidenceFragment] = []
        now = datetime.now(timezone.utc)
        for source in source_set.sources:
            if source.kind != "file":
                raise ValueError(f"unsupported local source kind: {source.kind}")
            path = Path(source.locator)
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            artifact_id = f"artifact-{digest[:24]}"
            artifacts.append(
                SourceArtifact(
                    id=artifact_id,
                    source_id=source.id,
                    media_type=source.media_type or "application/octet-stream",
                    content_digest=digest,
                    acquired_at=now,
                    acquisition_metadata=(("filename", path.name),),
                )
            )
            fragments.append(
                EvidenceFragment(
                    id=f"fragment-{digest[:24]}",
                    source_artifact_id=artifact_id,
                    locator="whole",
                    fragment_digest=digest,
                )
            )
        return EvidenceBundle(
            source_set_id=source_set.id,
            source_set_version=source_set.version,
            artifacts=tuple(artifacts),
            fragments=tuple(fragments),
        )


class DirectoryArtifactSink:
    def __init__(self, root: Path) -> None:
        self.root = root

    def publish(
        self,
        release_id: str,
        projections: tuple[Projection, ...],
    ) -> tuple[str, ...]:
        destination = self.root / release_id
        destination.mkdir(parents=True, exist_ok=False)
        refs: list[str] = []
        for projection in projections:
            path = destination / projection.name
            path.write_bytes(projection.content)
            refs.append(str(path))
        return tuple(refs)
