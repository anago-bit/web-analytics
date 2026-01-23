import os
import json
from google.oauth2.service_account import Credentials
from google.analytics.admin_v1alpha import AnalyticsAdminServiceClient

# GitHub SecretsからJSONを取得
SERVICE_ACCOUNT_JSON = os.environ.get("SERVICE_ACCOUNT_JSON")

def test_connection():
    print("🔍 --- GA4接続テスト開始 ---")
    
    if not SERVICE_ACCOUNT_JSON:
        print("❌ エラー: GitHub Secrets 'SERVICE_ACCOUNT_JSON' が空です。")
        return

    try:
        # 認証情報の読み込み
        creds_dict = json.loads(SERVICE_ACCOUNT_JSON)
        client_email = creds_dict.get("client_email")
        print(f"🔑 使用中のサービスアカウント: {client_email}")
        
        # 認証オブジェクトの作成
        creds = Credentials.from_service_account_info(creds_dict)
        admin_client = AnalyticsAdminServiceClient(credentials=creds)
        
        print("📡 Googleサーバーに問い合わせ中...")
        
        # アクセス可能なアカウントサマリーを取得
        summaries = admin_client.list_account_summaries()
        
        found_count = 0
        for account in summaries:
            for prop in account.property_summaries:
                p_id = prop.property.replace("properties/", "")
                print(f"✅ 接続成功！発見したプロパティ: {prop.display_name} (ID: {p_id})")
                found_count += 1
        
        if found_count == 0:
            print("⚠️ 警告: 認証は通りましたが、アクセス可能なプロパティが1つも見つかりません。")
            print("   -> GA4の管理画面で、上記のメールアドレスが『アカウント』または『プロパティ』に追加されているか再確認してください。")
        else:
            print(f"\n✨ テスト完了: 合計 {found_count} 件のプロパティを認識しました。")

    except Exception as e:
        print(f"❌ 通信エラー発生: {e}")
        print("\n💡 ヒント: 'Google Analytics Admin API' がGoogle Cloudで有効になっているか確認してください。")

if __name__ == "__main__":
    test_connection()
