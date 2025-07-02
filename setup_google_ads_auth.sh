#!/bin/bash

echo "Google Ads API認証設定スクリプト"
echo "================================"

# 1. Google Cloud認証
echo ""
echo "ステップ1: Google Cloudにログイン"
echo "以下のコマンドを実行してください："
echo ""
echo "gcloud auth login"
echo ""
echo "ブラウザが開いて認証を求められます。"
echo ""
read -p "認証が完了したらEnterを押してください..."

# 2. アプリケーションデフォルト認証
echo ""
echo "ステップ2: アプリケーションデフォルト認証の設定"
echo "以下のコマンドを実行してください："
echo ""
echo "gcloud auth application-default login"
echo ""
read -p "認証が完了したらEnterを押してください..."

# 3. 必要な情報の収集
echo ""
echo "ステップ3: Google Ads API情報の入力"
echo ""
echo "以下の情報が必要です："
echo "1. Google Ads Developer Token"
echo "2. Google Ads Customer ID (ハイフンなし)"
echo "3. OAuth2 Client ID"
echo "4. OAuth2 Client Secret"
echo ""
echo "これらの情報は以下から取得できます："
echo "- Developer Token: https://ads.google.com/aw/apicenter"
echo "- OAuth2認証情報: https://console.cloud.google.com/apis/credentials"
echo ""

read -p "情報を取得したらEnterを押してください..."

# 4. OAuth2認証情報の作成手順
echo ""
echo "ステップ4: OAuth2認証情報の作成（まだ作成していない場合）"
echo ""
echo "1. https://console.cloud.google.com/apis/credentials にアクセス"
echo "2. '認証情報を作成' → 'OAuth クライアント ID' を選択"
echo "3. アプリケーションの種類: 'デスクトップアプリ' を選択"
echo "4. 名前を入力（例: 'Keyword Metrics API'）"
echo "5. 作成されたClient IDとClient Secretをメモ"
echo ""
read -p "準備ができたらEnterを押してください..."

# 5. Refresh Tokenの取得
echo ""
echo "ステップ5: Refresh Tokenの取得"
echo ""
echo "以下のPythonスクリプトを実行してRefresh Tokenを取得します："
echo ""

cat > get_refresh_token.py << 'EOF'
#!/usr/bin/env python3
"""Google Ads API用のRefresh Tokenを取得するスクリプト"""

import sys
from google_auth_oauthlib.flow import Flow

# Google Ads APIのスコープ
SCOPES = ['https://www.googleapis.com/auth/adwords']

def main():
    print("\nGoogle Ads API Refresh Token取得ツール")
    print("=" * 50)
    
    client_id = input("OAuth2 Client IDを入力してください: ").strip()
    client_secret = input("OAuth2 Client Secretを入力してください: ").strip()
    
    if not client_id or not client_secret:
        print("エラー: Client IDとClient Secretは必須です。")
        sys.exit(1)
    
    # OAuth2設定
    client_config = {
        'installed': {
            'client_id': client_id,
            'client_secret': client_secret,
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
        }
    }
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri='http://localhost:8080'
    )
    
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    
    print(f"\n以下のURLをブラウザで開いて認証してください:")
    print(f"\n{auth_url}\n")
    
    auth_code = input("認証後に表示されるコードを入力してください: ").strip()
    
    try:
        flow.fetch_token(code=auth_code)
        credentials = flow.credentials
        
        print("\n認証成功！")
        print(f"\nRefresh Token: {credentials.refresh_token}")
        print("\nこのRefresh Tokenを.envファイルのGOOGLE_ADS_REFRESH_TOKENに設定してください。")
        
    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
EOF

echo "get_refresh_token.pyを作成しました。"
echo ""
echo "次のコマンドでRefresh Tokenを取得してください："
echo "python3 get_refresh_token.py"
echo ""
echo "取得後、.envファイルを更新してください。"