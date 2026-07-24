# 状況報告書作成アプリ — Nuitka standalone ビルド(Windows)
#
#   powershell -ExecutionPolicy Bypass -File scripts/build_nuitka.ps1
#
# --standalone(フォルダ配布)で本物のネイティブ実行ファイルにコンパイルする。
# PyInstaller の自己展開型より Windows Defender の誤検知が起きにくい。
# 生成物: build\run.dist\ (フォルダごと配布する)

$ErrorActionPreference = "Stop"
$Name = "状況報告書アプリ"

$NuitkaArgs = @(
    "--standalone",
    "--assume-yes-for-downloads",
    "--output-dir=build",
    "--output-filename=$Name",
    "--include-data-dir=app/templates=app/templates",
    "--include-data-dir=app/static=app/static",
    "--include-data-file=app/schema.sql=app/schema.sql",
    "--include-package=app",
    "--include-package=uvicorn",
    "--include-package-data=matplotlib",
    "--nofollow-import-to=tkinter",
    "--nofollow-import-to=pytest",
    "--company-name=status-report-app",
    "--product-name=状況報告書作成アプリ",
    "--file-version=1.0.0",
    "--product-version=1.0.0",
    "run.py"
)

python -m nuitka @NuitkaArgs
Write-Host "`n生成しました: build\run.dist\$Name.exe"
Write-Host "配布時は build\run.dist フォルダごと渡してください。"
