"""開発・配布共通のエントリポイント。

    python run.py            # サーバ起動 + ブラウザ自動オープン
    STATUS_REPORT_NO_BROWSER=1 python run.py   # ブラウザを開かない

PyInstaller の onefile ビルドもこのファイルをエントリにする。
"""

from app.server import run

if __name__ == "__main__":
    run()
