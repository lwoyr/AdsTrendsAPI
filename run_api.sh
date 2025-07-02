#!/bin/bash

# APIを起動するスクリプト（Ctrl+Cで確実に終了）

echo "キーワードメトリクスバッチAPIを起動します..."
echo "終了するには Ctrl+C を押してください"
echo ""

# 環境変数を設定
export API_PORT=8002
export API_WORKERS=1

# トラップを設定してクリーンアップを確実に実行
cleanup() {
    echo ""
    echo "APIを終了しています..."
    # すべての関連プロセスを終了
    pkill -f "python main.py"
    echo "APIが終了しました。"
    exit 0
}

# Ctrl+CとTERMシグナルをトラップ
trap cleanup INT TERM

# APIを起動
python main.py

# 正常終了時もクリーンアップ
cleanup