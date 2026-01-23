import os
import json
import gspread
import requests
from google.oauth2.service_account import Credentials
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric

# ==========================================
# 1. 設定情報
# ==========================================
SPREADSHEET_KEY = '1FEO4sv3WP2_AQLsXezwVV32d_luGUwVRcsStuGAytOE'

TARGET_SITES = {
    "391519429": "カーリース",
    "372188028": "福祉レンタカー",
    "468612790": "HAレンタカー",
    "382138346": "ITS",
    "391533336": "レンタカー",
    "294934653": "スマイルモビリティ",
}

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SERVICE_ACCOUNT_JSON = os.environ.get("SERVICE_ACCOUNT_JSON")

# 最新の安定モデル名
GEMINI_MODEL = "gemini-2.0-flash"

# --- 2. 認証情報取得 ---
def get_credentials_dict():
    if SERVICE_ACCOUNT_JSON:
        return json.loads(SERVICE_ACCOUNT_JSON)
    raise FileNotFoundError("認証情報が見つかりません。GitHubのSecrets設定を確認してください。")

credentials_dict = get_credentials_dict()

# --- 3. デバッグ用：アクセス権限の可視化 ---
def check_accessible_properties():
    """サービスアカウントが現在どのIDにアクセスできるか一覧表示する"""
    from google.analytics.admin_v1alpha import AnalyticsAdminServiceClient
    try:
        creds = Credentials.from_service_account_info(credentials_dict)
        admin_client = AnalyticsAdminServiceClient(credentials=creds)
        print(">>> サービスアカウントの権限をスキャン中...")
        
        summaries = admin_client.list_account_summaries()
        accessible_ids = []
        for account in summaries:
            for prop in account.property_summaries:
                p_id = prop.property.replace("properties/", "")
                accessible_ids.append(p_id)
                print(f"    ✅ 権限確認済み: {prop.display_name} (ID: {p_id})")
        
        if not accessible_ids:
            print("    ⚠️ 警告: アクセス可能なプロパティが1つも見つかりませんでした。")
        return accessible_ids
    except Exception as e:
        print(f"    ⚠️ アクセス確認中にエラー（Admin API未有効など）: {e}")
        return []

# --- 4. Gemini分析エンジン ---
def analyze_with_gemini(site_name, data_rows):
    data_summary = "\n".join([f"{r[0]}: {r[2]}" for r in data_rows])
    if not GEMINI_API_KEY:
        return "❌ エラー: GEMINI_API_KEYが設定されていません。"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    prompt = f"プロのWebマーケターとして以下のGA4データ（昨日分）を分析し、{site_name}の担当者向けに日本語で日報を作成してください。\n\n【データ】\n{data_summary}\n\n300文字程度でお願いします。"
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {'Content-Type': 'application/json'}
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        res_json = response.json()
        if "candidates" in res_json:
            return res_json["candidates"][0]["content"]["parts"][0]["text"]
        return "AI分析エラー: レスポンスが不正です。"
    except Exception as e:
        return f"通信エラー: {e}"

# --- 5. GA4データ取得エンジン (ここがエラー箇所でした) ---
def get_ga4_data(property_id):
    """GA4からデータを取得する"""
    creds = Credentials.from_service_account_info(credentials_dict)
    client = BetaAnalyticsDataClient(credentials=creds)
    
    dr = [DateRange(start_date="yesterday", end_date="yesterday")]
    metrics = [
        Metric(name="screenPageViews"),
        Metric(name="totalUsers"),
        Metric(name="sessions"),
        Metric(name="engagementRate")
    ]
    
    try:
        # メインレポート
        res_total = client.run_report(RunReportRequest(
            property=f"properties/{property_id}", 
            dimensions=[Dimension(name="date")], 
            metrics=metrics, 
            date_ranges=dr
        ))
        
        if not res_total.rows:
            return None

        date_val = res_total.rows[0].dimension_values[0].value
        r = res_total.rows[0]
        formatted = [
            ["★全体PV", date_val, int(r.metric_values[0].value)],
            ["★全体UU", date_val, int(r.metric_values[1].value)],
            ["★全体Sessions", date_val, int(r.metric_values[2].value)],
            ["★エンゲージメント率", date_val, f"{float(r.metric_values[3].value)*100:.1f}%"]
        ]
        return formatted
    except Exception as e:
        print(f"    ⚠️ GA4詳細エラー (ID:{property_id}): {e}")
        return None

# --- 6. スプレッドシート更新 ---
def update_site_sheet(site_name, data_rows):
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_KEY)
    
    try:
        worksheet = sh.worksheet(site_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sh.add_worksheet(title=site_name, rows="500", cols="100")
        worksheet.update(range_name='A1', values=[['項目 / 日付']])

    print(f"    -> Gemini分析中...")
    analysis_text = analyze_with_gemini(site_name, data_rows)
    
    # 既存データの取得
    existing_items = worksheet.col_values(1)
    header_row = worksheet.row_values(1)
    next_col_num = len(header_row) + 1
    next_col_letter = gspread.utils.rowcol_to_a1(1, next_col_num)[:-1]
    
    date_label = data_rows[0][1]
    data_rows.append(["AI分析レポート", date_label, analysis_text])

    # 列データの作成
    final_column = [''] * max(len(existing_items), 50)
    final_column[0] = date_label

    for item_name, _, value in data_rows:
        if item_name in existing_items:
            idx = existing_items.index(item_name)
        else:
            idx = len(existing_items)
            existing_items.append(item_name)
            worksheet.update_cell(idx + 1, 1, item_name)
        
        if idx < len(final_column):
            final_column[idx] = value

    col_values = [[v] for v in final_column]
    worksheet.update(range_name=f'{next_col_letter}1', values=col_values)

# --- 7. メイン実行 ---
if __name__ == "__main__":
    print("🚀 GA4自動レポート & Gemini 2.0 Flash 起動")
    
    # 権限スキャン（デバッグ）
    accessible_ids = check_accessible_properties()
    
    for pid, name in TARGET_SITES.items():
        print(f"\n--- {name} ({pid}) 処理中 ---")
        
        if accessible_ids and pid not in accessible_ids:
            print(f"    ❌ 注意: このIDはGoogleの権限リストに含まれていません。")
        
        site_data = get_ga4_data(pid)
        if site_data:
            update_site_sheet(name, site_data)
            print(f"✅ {name} の更新が完了しました。")
        else:
            print(f"❌ {name} のデータ取得に失敗しました。")
            
    print("\n✨ すべての処理が完了しました。")
