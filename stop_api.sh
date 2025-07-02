#!/bin/bash

# APIを停止するスクリプト

echo "キーワードメトリクスバッチAPIを停止します..."

# 実行中のAPIプロセスを検索
PID=$(ps aux | grep "[p]ython main.py" | awk '{print $2}')

if [ -z "$PID" ]; then
    echo "APIは実行されていません。"
else
    echo "PID $PID のプロセスを停止します..."
    kill -TERM $PID
    
    # プロセスが終了するまで待機（最大5秒）
    for i in {1..5}; do
        if ! ps -p $PID > /dev/null 2>&1; then
            echo "APIが正常に停止しました。"
            exit 0
        fi
        sleep 1
    done
    
    # まだ実行中の場合は強制終了
    if ps -p $PID > /dev/null 2>&1; then
        echo "プロセスを強制終了します..."
        kill -9 $PID
    fi
fi

echo "APIの停止が完了しました。"