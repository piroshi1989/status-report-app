#!/usr/bin/env bash
# 状況報告書作成アプリ — Nuitka standalone ビルド(Linux / macOS)
#
#   bash scripts/build_nuitka.sh
#
# 主に開発中の動作確認用。実配布(Windows exe)は scripts/build_nuitka.ps1 を
# GitHub Actions(windows-latest)で実行して生成する。
# 生成物: build/run.dist/
set -euo pipefail

NAME="${1:-status-report-app}"

python -m nuitka \
  --standalone \
  --assume-yes-for-downloads \
  --output-dir=build \
  --output-filename="$NAME" \
  --include-data-dir=app/templates=app/templates \
  --include-data-dir=app/static=app/static \
  --include-data-file=app/schema.sql=app/schema.sql \
  --include-package=app \
  --include-package=uvicorn \
  --include-package-data=matplotlib \
  --nofollow-import-to=tkinter \
  --nofollow-import-to=pytest \
  run.py

echo ""
echo "生成しました: build/run.dist/$NAME"
