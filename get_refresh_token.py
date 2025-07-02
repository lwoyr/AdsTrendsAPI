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
