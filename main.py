import os
import json
import gspread
import requests
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric
from google.oauth2.service_account import Credentials

# ==========================================
# 1. 設定情報
# ==========================================
# スプレッドシートのID
SPREADSHEET_KEY = '1FEO4sv3WP2_AQLsXezwVV32d_luGUwVRcsStuGAytOE'

# 分析対象のサイト（GA4プロパティID: サイト名）
TARGET_SITES = {
    "391519429": "カーリース",
    "372188028": "福祉レンタカー",
    "468612790": "HAレンタカー",
    "382138346": "ITS",
    "391533336": "レンタカー",
    "294934653": "スマイルモビリティ",
}

# GitHub Secrets または環境変数から取得
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SERVICE_ACCOUNT_JSON = os.environ.get("SERVICE_ACCOUNT_JSON")

# モデル名
GEMINI_MODEL = "gemini-2.5-flash"

# --- 2. 認証情報取得 ---
def get_credentials_dict():
    # GitHub Actions環境を優先
    if SERVICE_ACCOUNT_JSON:
        return json.loads(SERVICE_ACCOUNT_JSON)
    
    # ローカル実行用（Macにファイルがある場合）
    local_files = ["service-account-key.json", "SERVICE_ACCOUNT.json"]
    for filename in local_files:
        if os.path.exists(filename):
            with open(filename, "r") as f:
                return json.load(f)
    
    raise FileNotFoundError("認証情報が見つかりません。GitHubのSecrets設定を確認してください。")

# 共通で使用する認証辞書
credentials_dict = get_credentials_dict()

# --- 3. Gemini分析エンジン (Gemini 2.5 Flash 対応) ---
def analyze_with_gemini(site_name, data_rows):
    # GA4データをテキストに変換
    data_summary = "\n".join([f"{r[0]}: {r[2]}" for r in data_rows])
    
    if not GEMINI_API_KEY:
        return "❌ エラー: GEMINI_API_KEY が設定されていません。"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    あなたはプロのWebマーケターです。以下のGA4データ（昨日分）を分析し、{site_name}の担当者向けに日本語で日報を作成してください。
    
    【データ】
    {data_summary}
    
    【要件】
    1. 前日のPVやユーザー数の推移から読み取れる概況を伝える。
    2. 特筆すべき流入元やページの変化を指摘する。
    3. 明日以降のアクション案を1つ提示する。
    
    専門用語は避け、300文字程度でお願いします。
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {'Content-Type': 'application/json'}
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        res_json = response.json()
        if "candidates" in res_json:
            return res_json["candidates"][0]["content"]["parts"][0]["text"]
        else:
            error_msg = res_json.get('error', {}).get('message', '不明なエラー')
            return f"AI分析エラー: {error_msg}"
    except Exception as e:
        return f"通信エラー: {e}"

# --- 4. スプレッドシート更新ロジック ---
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

    existing_items = worksheet.col_values(1)
    header_row = worksheet.row_values(1)
    next_col_num = len(header_row) + 1
    next_col_letter = gspread.utils.rowcol_to_a1(1, next_col_num)[:-1]
    
    date_label = data_rows[0][1]
    
    print(f"   -> Gemini分析中...")
    analysis_text = analyze_with_gemini(site_name, data_rows)
    data_rows.append(["AI分析レポート", date_label, analysis_text])

    # 最終的な列データを作成
    final_column_output = [''] * max(len(existing_items), 100)
    final_column_output[0] = date_label

    for item_name, _, value in data_rows:
        if item_name in existing_items:
            idx = existing_items.index(item_name)
        else:
            idx = len(existing_items)
            existing_items.append(item_name)
            worksheet.update_cell(idx + 1, 1, item_name)
        
        if idx < len(final_column_output):
            final_column_output[idx] = value

    column_data_formatted = [[v] for v in final_column_output]
    worksheet.update(range_name=f'{next_col_letter}1', values=column_data_formatted)

# --- 5. GA4データ取得エンジン ---
def get_ga4_data(property_id):
    client = BetaAnalyticsDataClient.from_service_account_info(credentials_dict)
    dr = [DateRange(start_date="yesterday", end_date="yesterday")]
    
    metrics = [
        Metric(name="screenPageViews"),
        Metric(name="totalUsers"),
        Metric(name="sessions"),
        Metric(name="engagementRate")
    ]
    
    try:
        res_total = client.run_report(RunReportRequest(property=f"properties/{property_id}", dimensions=[Dimension(name="date")], metrics=metrics, date_ranges=dr))
        res_source = client.run_report(RunReportRequest(property=f"properties/{property_id}", dimensions=[Dimension(name="date"), Dimension(name="sessionSourceMedium")], metrics=[Metric(name="screenPageViews")], date_ranges=dr))
        res_pages = client.run_report(RunReportRequest(property=f"properties/{property_id}", dimensions=[Dimension(name="date"), Dimension(name="landingPagePlusQueryString")], metrics=[Metric(name="screenPageViews")], date_ranges=dr))
        
        if not res_total.rows: return None

        date_val = res_total.rows[0].dimension_values[0].value
        formatted = []
        r = res_total.rows[0]
        formatted.extend([
            ["★全体PV", date_val, int(r.metric_values[0].value)],
            ["★全体UU", date_val, int(r.metric_values[1].value)],
            ["★全体Sessions", date_val, int(r.metric_values[2].value)],
            ["★エンゲージメント率", date_val, f"{float(r.metric_values[3].value)*100:.1f}%"]
        ])
        for r in res_source.rows[:5]:
            formatted.append([f"流入: {r.dimension_values[1].value}", date_val, int(r.metric_values[0].value)])
        for r in res_pages.rows[:10]:
            formatted.append([f"ページ: {r.dimension_values[1].value}", date_val, int(r.metric_values[0].value)])
        return formatted
    except Exception as e:
        print(f"   ⚠️ GA4取得エラー (ID:{property_id}): {e}")
        return None

# --- 6. メイン実行 ---
if __name__ == "__main__":
    print("🚀 GA4自動レポート & Gemini 2.5 Flash 起動")
    for pid, name in TARGET_SITES.items():
        print(f"--- {name} ({pid}) 処理中 ---")
        site_data = get_ga4_data(pid)
        if site_data:
            update_site_sheet(name, site_data)
            print(f"✅ {name} の更新が完了しました。")
        else:
            print(f"❌ {name} のデータ取得に失敗しました。")
    print("\n✨ すべての処理が完了しました。")
