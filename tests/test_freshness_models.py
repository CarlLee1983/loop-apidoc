import pytest
from pydantic import ValidationError

from loop_apidoc.freshness.models import (
    EXIT_CODES,
    FingerprintEntry,
    FreshnessVerdict,
    SourceFingerprint,
    SourceKind,
    SourceSignal,
    SourceStatus,
)


def test_fingerprint_roundtrip_defaults():
    fp = SourceFingerprint(
        openapi_version="2.3.0",
        recorded_from="runs/abc",
        sources=[
            FingerprintEntry(
                id="https://api.example.com/openapi.json",
                kind=SourceKind.OPENAPI_URL,
                signal=SourceSignal(version="2.3.0", etag='W/"a"', sha256="deadbeef"),
            )
        ],
    )
    assert fp.schema_version == 1
    restored = SourceFingerprint.model_validate_json(fp.model_dump_json())
    assert restored == fp
    assert restored.sources[0].signal.last_modified is None


def test_signal_forbids_extra_keys():
    with pytest.raises(ValidationError):
        SourceSignal.model_validate({"version": "1", "bogus": True})


def test_exit_codes_cover_every_verdict():
    assert EXIT_CODES[FreshnessVerdict.UNCHANGED] == 0
    assert EXIT_CODES[FreshnessVerdict.CHANGED] == 1
    assert EXIT_CODES[FreshnessVerdict.INCONCLUSIVE] == 2
    assert set(EXIT_CODES) == set(FreshnessVerdict)
    assert SourceStatus.FETCH_FAILED.value == "fetch_failed"
