from __future__ import annotations

from app.services import content_lake as lake


def test_put_bytes_write_once_idempotent(db_session):
    data = b"hello lake"
    first = lake.put_bytes(db_session, data, mime="text/plain", role="original", filename="a.txt")
    second = lake.put_bytes(db_session, data, mime="text/plain", role="original", filename="b.txt")

    assert first.checksum == second.checksum
    assert first.uri == second.uri
    assert first.existed is False
    assert second.existed is True
    assert lake.open_uri(first.uri).read_bytes() == data


def test_put_text_roundtrip(db_session):
    ref = lake.put_text(db_session, "原始文字 sample", role="original", filename="note.txt")
    assert ref.uri.startswith("lake://objects/")
    assert lake.read_text(ref.uri) == "原始文字 sample"


def test_never_overwrites_existing_bytes(db_session):
    data = b"immutable"
    ref = lake.put_bytes(db_session, data, mime="application/octet-stream")
    path = lake.open_uri(ref.uri)
    again = lake.put_bytes(db_session, data, mime="application/octet-stream")
    assert again.existed is True
    assert path.read_bytes() == data
