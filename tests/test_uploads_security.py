"""アップロードトークンのパストラバーサル対策テスト."""

from __future__ import annotations

import pytest


@pytest.mark.parametrize("bad", [
    "../../../etc/passwd",
    "..%2f..%2fetc%2fpasswd",
    "/etc/passwd",
    "abc.txt",
    "deadbeef.xlsx",                       # 32桁hexでない
    "0123456789abcdef0123456789abcdef.txt",  # 拡張子不正
    "0123456789abcdef0123456789abcde.xlsx",  # 31桁
    "",
])
def test_resolve_token_rejects_bad(tmp_env, bad):
    from app import uploads
    assert uploads.resolve_token(bad) is None


def test_save_and_resolve_roundtrip(tmp_env):
    from app import uploads
    token = uploads.save_upload(b"hello", "measurements.xlsx")
    assert token.endswith(".xlsx")
    path = uploads.resolve_token(token)
    assert path is not None and path.is_file()
    assert path.read_bytes() == b"hello"


def test_save_upload_constrains_suffix(tmp_env):
    from app import uploads
    # 想定外拡張子は .xlsx に矯正される
    token = uploads.save_upload(b"x", "evil.php")
    assert token.endswith(".xlsx")
    token2 = uploads.save_upload(b"x", "legacy.xls")
    assert token2.endswith(".xls")


def test_commit_endpoint_ignores_traversal_token(client, tmp_path):
    # 実在する外部ファイルを指す不正トークンでも読まれない
    secret = tmp_path / "secret.xlsx"
    secret.write_bytes(b"PK\x03\x04dummy")
    r = client.post(
        "/patients/import/commit",
        data={"token": "../../secret.xlsx", "update_existing": "1"},
        follow_redirects=False,
    )
    # 検証に失敗して取込フォームへ戻る(commit されない)
    assert r.status_code == 303
    assert r.headers["location"] == "/patients/import"
