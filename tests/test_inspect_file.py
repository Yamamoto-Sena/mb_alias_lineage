import io
import zipfile

import inspect_file as insp


def test_inspect_bytes_xml(capsys):
    insp._inspect_bytes(b'<Board name="test"><Item id="1"/></Board>', max_depth=4)
    out = capsys.readouterr().out
    assert "XMLの可能性が高い" in out
    assert "<Board>" in out


def test_inspect_bytes_json(capsys):
    insp._inspect_bytes(b'{"board": {"name": "test"}}', max_depth=4)
    out = capsys.readouterr().out
    assert "JSONの可能性が高い" in out
    assert "board: dict" in out


def test_inspect_bytes_shift_jis_xml_does_not_crash(capsys):
    content = '<?xml version="1.0" encoding="Shift_JIS"?><Board name="単価"/>'.encode("shift_jis")
    insp._inspect_bytes(content, max_depth=4)
    out = capsys.readouterr().out
    assert "XMLとして読めませんでした" not in out
    assert "<Board>" in out


def test_inspect_bytes_malformed_xml_shows_friendly_message(capsys):
    insp._inspect_bytes(b"<Board><Unclosed>", max_depth=4)
    out = capsys.readouterr().out
    assert "XMLとして読めませんでした" in out


def test_inspect_bytes_unknown_binary(capsys):
    insp._inspect_bytes(b"\x00\x01\x02not xml or json", max_depth=4)
    out = capsys.readouterr().out
    assert "未知/バイナリの可能性あり" in out


def test_inspect_bytes_zip_recurses_into_entries(capsys):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("inner.xml", '<Board name="in-zip"/>')
    insp._inspect_bytes(buf.getvalue(), max_depth=4)
    out = capsys.readouterr().out
    assert "ZIP圧縮ファイル" in out
    assert "ZIP内: inner.xml" in out
    assert "<Board>" in out


def test_inspect_bytes_bad_zip_shows_friendly_message(capsys):
    insp._inspect_bytes(b"PK\x03\x04not a real zip", max_depth=4)
    out = capsys.readouterr().out
    assert "ZIPとして読めませんでした" in out
