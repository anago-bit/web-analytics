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
SPREADSHEET_KEY = '1FEO4sv3WP2_AQLsXezwVV32d_luGUwVRcsStuGAytOE'

TARGET_SITES = {
    "391519429": "カーリース",
    "372188028": "福祉レンタカー",
    "468612790": "HAレンタカー",
    "382138346": "ITS",
    "391533336": "レンタカー",
    "294934653": "スマイルモビリティ",
}
import os
import json
import gspread
import requests
import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate
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

# モデル名を安定版の 2.0 に修正
GEMINI_MODEL = "gemini-2.0-flash"

# --- 2. 認証情報取得 ---
def get_credentials_dict():
    if SERVICE_ACCOUNT_JSON:
        return json.loads(SERVICE_ACCOUNT_JSON)
    raise FileNotFoundError("認証情報が見つかりません。")

credentials_dict = get_credentials_dict()

# --- デバッグ用：アクセス可能なプロパティを確認する ---
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

# --- 3. Gemini分析エンジン ---
def analyze_with_gemini(site_name, data_rows):
    data_summary = "\n".join([f"{r[0]}: {r[2]}" for r in data_rows])
    if not GEMINI_API_KEY:
        return "❌ エラー: API_KEY未設定"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    prompt = f"プロのマーケターとして以下のGA4データを分析し、{site_name}の日報を300字程度で作成してください。\n\n{data_summary}"
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {'Content-Type': 'application/json'}
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        res_json = response.json()
        return res_json["candidates"][0]["content"]["parts"][0]["text"]
    except:
        return "分析エラーが発生しました。"

# --- 4. GA4データ取得エンジン ---
def get_ga4_data(property_id):
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
        res_total = client.run_report(RunReportRequest(property=f"properties/{property_id}", dimensions=[Dimension(name="date")], metrics=metrics, date_ranges=dr))
        # (簡易化のため一部省略、構造は維持)
        if not res_total.rows: return None
        
        date_val = res_total.rows[0].dimension_values[0].value
        r = res_total.rows[0]
        return [
            ["★全体PV", date_val, int(r.metric_values[0].value)],
            ["★全体UU", date_val, int(r.metric_values[1].value)],
            ["★全体Sessions", date_val, int(r.metric_values[2].value)],
            ["★エンゲージメント率", date_val, f"{float(r.metric_values[3].value)*100:.1f}%"]
        ]
    except Exception as e:
        print(f"    ⚠️ GA4エラー: {e}")
        return None

# --- 5. スプレッドシート更新 ---
def update_site_sheet(site_name, data_rows):
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_KEY)
    
    try:
        worksheet = sh.worksheet(site_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sh.add_worksheet(title=site_name, rows="500", cols="100")
    
    analysis_text = analyze_with_gemini(site_name, data_rows)
    # 簡易的に最終行へ追加（詳細は元のロジックを継承）
    # ... (既存の更新ロジック) ...
    print(f"    -> スプレッドシート更新完了")

# --- 6. メイン実行 ---
if __name__ == "__main__":
    print("🚀 GA4自動レポート & Gemini 2.0 Flash 起動")
    
    # 【重要】デバッグ：アクセス可能なIDを一覧表示
    accessible_ids = check_accessible_properties()
    
    for pid, name in TARGET_SITES.items():
        print(f"\n--- {name} ({pid}) 処理中 ---")
        
        if accessible_ids and pid not in accessible_ids:
            print(f"    ❌ 注意: Google側はこのIDに対するアクセス権限を認識していません。")
        
        site_data = get_ga4_data(pid)
        if site_data:
            update_site_sheet(name, site_data)
            print(f"✅ {name} 完了")
        else:
            print(f"❌ {name} 失敗")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SERVICE_ACCOUNT_JSON = os.environ.get("SERVICE_ACCOUNT_JSON")

GEMINI_MODEL = "gemini-2.5-flash"

# ==========================================
# 2. 認証情報取得
# ==========================================
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

credentials_dict = get_credentials_dict()

# どのサービスアカウントで動いているか必ず出す（切り分け用）
print("SERVICE ACCOUNT client_email:", credentials_dict.get("client_email"))
print("SERVICE ACCOUNT project_id:", credentials_dict.get("project_id"))

# GA4 / Sheets でスコープを明示して認証を統一
GA4_SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

ga4_creds = Credentials.from_service_account_info(credentials_dict, scopes=GA4_SCOPES)
sheets_creds = Credentials.from_service_account_info(credentials_dict, scopes=SHEETS_SCOPES)

# ==========================================
# 3. Gemini分析エンジン (Gemini 2.5 Flash)
# ==========================================
def analyze_with_gemini(site_name, data_rows):
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
""".strip()

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        res_json = response.json()

        if "candidates" in res_json and res_json["candidates"]:
            return res_json["candidates"][0]["content"]["parts"][0]["text"]

        error_msg = res_json.get("error", {}).get("message", "不明なエラー")
        return f"AI分析エラー: {error_msg}"

    except Exception as e:
        return f"通信エラー: {e}"

# ==========================================
# 4. スプレッドシート更新ロジック
# ==========================================
def update_site_sheet(site_name, data_rows):
    gc = gspread.authorize(sheets_creds)
    sh = gc.open_by_key(SPREADSHEET_KEY)

    try:
        worksheet = sh.worksheet(site_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sh.add_worksheet(title=site_name, rows="500", cols="100")
        worksheet.update(range_name="A1", values=[["項目 / 日付"]])

    existing_items = worksheet.col_values(1)
    header_row = worksheet.row_values(1)
    next_col_num = len(header_row) + 1
    next_col_letter = gspread.utils.rowcol_to_a1(1, next_col_num)[:-1]

    date_label = data_rows[0][1]

    print("   -> Gemini分析中...")
    analysis_text = analyze_with_gemini(site_name, data_rows)
    data_rows.append(["AI分析レポート", date_label, analysis_text])

    final_column_output = [""] * max(len(existing_items), 100)
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
    worksheet.update(range_name=f"{next_col_letter}1", values=column_data_formatted)

# ==========================================
# 5. GA4データ取得エンジン
# ==========================================
def get_ga4_data(property_id):
    # 実行時にGA4がどのSAを使っているかも出す
    print("   -> GA4 using service account:", getattr(ga4_creds, "service_account_email", None))

    client = BetaAnalyticsDataClient(credentials=ga4_creds)
    dr = [DateRange(start_date="yesterday", end_date="yesterday")]

    metrics_total = [
        Metric(name="screenPageViews"),
        Metric(name="totalUsers"),
        Metric(name="sessions"),
        Metric(name="engagementRate"),
    ]

    try:
        res_total = client.run_report(
            RunReportRequest(
                property=f"properties/{property_id}",
                dimensions=[Dimension(name="date")],
                metrics=metrics_total,
                date_ranges=dr,
            )
        )

        res_source = client.run_report(
            RunReportRequest(
                property=f"properties/{property_id}",
                dimensions=[Dimension(name="date"), Dimension(name="sessionSourceMedium")],
                metrics=[Metric(name="screenPageViews")],
                date_ranges=dr,
            )
        )

        res_pages = client.run_report(
            RunReportRequest(
                property=f"properties/{property_id}",
                dimensions=[Dimension(name="date"), Dimension(name="landingPagePlusQueryString")],
                metrics=[Metric(name="screenPageViews")],
                date_ranges=dr,
            )
        )

        if not res_total.rows:
            return None

        date_val = res_total.rows[0].dimension_values[0].value
        r = res_total.rows[0]

        formatted = [
            ["★全体PV", date_val, int(r.metric_values[0].value)],
            ["★全体UU", date_val, int(r.metric_values[1].value)],
            ["★全体Sessions", date_val, int(r.metric_values[2].value)],
            ["★エンゲージメント率", date_val, f"{float(r.metric_values[3].value) * 100:.1f}%"],
        ]

        for row in res_source.rows[:5]:
            formatted.append([f"流入: {row.dimension_values[1].value}", date_val, int(row.metric_values[0].value)])

        for row in res_pages.rows[:10]:
            formatted.append([f"ページ: {row.dimension_values[1].value}", date_val, int(row.metric_values[0].value)])

        return formatted

    except Exception as e:
        print(f"   ⚠️ GA4取得エラー (ID:{property_id}): {e}")
        return None

# ==========================================
# 6. メイン実行
# ==========================================
if __name__ == "__main__":
    
    def check_accessible_properties():
    client = BetaAnalyticsDataClient(credentials=Credentials.from_service_account_info(credentials_dict))
    # サービスアカウントが触れるアカウント一覧を取得（簡易版）
    print(">>> サービスアカウントがアクセス可能なプロパティを確認中...")
    # ※この機能はAdmin APIが必要な場合がありますが、Data APIの接続テストとして有効です
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
