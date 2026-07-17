from pathlib import Path

from loop_apidoc.freshness.models import (
    FingerprintEntry,
    SourceKind,
    SourceSignal,
    SourceStatus,
)
from loop_apidoc.freshness.signals import (
    ObservedSignal,
    classify,
    detect_openapi,
    file_signal,
    hash_bytes,
)


def test_hash_bytes_stable():
    assert hash_bytes(b"abc") == hash_bytes(b"abc")
    assert hash_bytes(b"abc") != hash_bytes(b"abd")


def test_file_signal(tmp_path: Path):
    f = tmp_path / "s.pdf"
    f.write_bytes(b"hello")
    assert file_signal(f).sha256 == hash_bytes(b"hello")


def test_detect_openapi_true_and_version():
    ok, ver = detect_openapi(b'{"openapi":"3.1.0","info":{"version":"2.3.0"}}', "application/json")
    assert ok is True and ver == "2.3.0"


def test_detect_openapi_false_on_html():
    ok, ver = detect_openapi(b"<html><body>hi</body></html>", "text/html")
    assert ok is False and ver is None


def _entry(kind, **sig):
    return FingerprintEntry(id="x", kind=kind, signal=SourceSignal(**sig))


def test_classify_not_modified_is_unchanged():
    status, _ = classify(_entry(SourceKind.WEB_URL, sha256="a"), ObservedSignal(signal=None, not_modified=True))
    assert status is SourceStatus.UNCHANGED


def test_classify_failed_is_fetch_failed():
    status, reason = classify(
        _entry(SourceKind.WEB_URL, sha256="a"),
        ObservedSignal(signal=None, failed=True, error="boom"),
    )
    assert status is SourceStatus.FETCH_FAILED and "boom" in reason


def test_classify_openapi_same_version_unchanged_even_if_sha_differs():
    entry = _entry(SourceKind.OPENAPI_URL, version="2.3.0", sha256="old")
    observed = ObservedSignal(signal=SourceSignal(version="2.3.0", sha256="new"), kind=SourceKind.OPENAPI_URL)
    status, _ = classify(entry, observed)
    assert status is SourceStatus.UNCHANGED


def test_classify_openapi_version_bump_is_changed():
    entry = _entry(SourceKind.OPENAPI_URL, version="2.3.0", sha256="old")
    observed = ObservedSignal(signal=SourceSignal(version="2.4.0", sha256="old"), kind=SourceKind.OPENAPI_URL)
    status, reason = classify(entry, observed)
    assert status is SourceStatus.CHANGED and "2.3.0" in reason and "2.4.0" in reason


def test_classify_openapi_missing_version_falls_back_to_sha():
    entry = _entry(SourceKind.OPENAPI_URL, version=None, sha256="old")
    observed = ObservedSignal(signal=SourceSignal(version=None, sha256="new"), kind=SourceKind.OPENAPI_URL)
    status, _ = classify(entry, observed)
    assert status is SourceStatus.CHANGED


def test_classify_web_sha_match_unchanged():
    entry = _entry(SourceKind.WEB_URL, sha256="same")
    observed = ObservedSignal(signal=SourceSignal(sha256="same"), kind=SourceKind.WEB_URL)
    status, _ = classify(entry, observed)
    assert status is SourceStatus.UNCHANGED


def test_classify_local_sha_mismatch_changed():
    entry = _entry(SourceKind.LOCAL_FILE, sha256="a")
    observed = ObservedSignal(signal=SourceSignal(sha256="b"), kind=SourceKind.LOCAL_FILE)
    status, _ = classify(entry, observed)
    assert status is SourceStatus.CHANGED
