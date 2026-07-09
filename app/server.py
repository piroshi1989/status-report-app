"""ローカルサーバ起動エントリ.

空きポートで uvicorn を起動し、既定ブラウザで開く。exe(PyInstaller onefile)
起動時もこの関数が呼ばれる。終了は Ctrl+C またはコンソールを閉じる。
"""

from __future__ import annotations

import socket
import threading
import time
import webbrowser

import uvicorn

from . import config


def _pick_port() -> int:
    preferred = config.preferred_port()
    if preferred:
        return preferred
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _open_browser_when_ready(url: str, host: str, port: int) -> None:
    for _ in range(100):
        try:
            with socket.create_connection((host, port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    webbrowser.open(url)


def run() -> None:
    host = "127.0.0.1"
    port = _pick_port()
    url = f"http://{host}:{port}"

    print("=" * 56)
    print("  状況報告書作成アプリ")
    print(f"  {url}")
    print("  終了するにはこのウィンドウを閉じるか Ctrl+C を押してください。")
    print("=" * 56)

    if config.auto_open_browser():
        threading.Thread(
            target=_open_browser_when_ready, args=(url, host, port), daemon=True
        ).start()

    uvicorn.run("app.main:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    run()
