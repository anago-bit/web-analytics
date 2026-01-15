import os
import json
import gspread
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric
from google.oauth2.service_account import Credentials

# --- 認証情報の取得関数 ---
def get_credentials():
    # 1. GitHub Actions用 (Secrets環境変数から読み込み)
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        return json.loads(creds_json)
    
    # 2. ローカル実行用 (JSONファイルから読み込み)
    # ※ローカル実行時はこのファイルがmain.pyと同じ階層に必要です
    with open("service-account-key.json", "r") as f:
        return json.load(f)

# 認証情報の確定
credentials_dict = get_credentials()

# --- 1. 設定エリア ---
SPREADSHEET_KEY = '1FEO4sv3WP2_AQLsXezwVV32d_luGUwVRcsStuGAytOE'

TARGET_SITES = {
    "391519429": "カーリース",
    "372188028": "福祉レンタカー",
    "468612790": "HAレンタカー",
    "382138346": "ITS",
    "391533336": "レンタカー",
    "294934653": "スマイルモビリティ",
}

# --- 2. スプレッドシート書き込み関数（行マッチング＆動的追加版） ---
def update_site_sheet(site_name, data_rows):
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_KEY)
    
    try:
        worksheet = sh.worksheet(site_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sh.add_worksheet(title=site_name, rows="300", cols="100")
        worksheet.update('A1', [['項目 / 日付']])

    # A列（項目名）をすべて取得
    existing_items = worksheet.col_values(1)
    
    # 1行目（日付）を取得して書き込む列を決定
    header_row = worksheet.row_values(1)
    next_col_num = len(header_row) + 1
    next_col_letter = gspread.utils.rowcol_to_a1(1, next_col_num)[:-1]
    
    # データ準備
    date_label = data_rows[0][1]
    final_column_output = [''] * max(len(existing_items), 50) 
    final_column_output[0] = date_label

    for item_name, _, value in data_rows:
        if item_name in existing_items:
            idx = existing_items.index(item_name)
        else:
            existing_items.append(item_name)
            idx = len(existing_items) - 1
            worksheet.update_cell(idx + 1, 1, item_name)
            
            if idx >= len(final_column_output):
                final_column_output.append('')
        
        final_column_output[idx] = value

    column_data_formatted = [[v] for v in final_column_output]
    worksheet.update(f'{next_col_letter}1', column_data_formatted)

# --- 3. GA4データ取得関数 ---
def get_ga4_data(property_id, site_name):
    client = BetaAnalyticsDataClient.from_service_account_info(credentials_dict)
    date_range = [DateRange(start_date="yesterday", end_date="yesterday")]
    
    # リクエスト一式
    res_total = client.run_report(RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="date")],
        metrics=[Metric(name="screenPageViews"), Metric(name="totalUsers"), Metric(name="sessions"), Metric(name="engagementRate")],
        date_ranges=date_range
    ))
    res_source = client.run_report(RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="date"), Dimension(name="sessionSourceMedium")],
        metrics=[Metric(name="screenPageViews")], 
        date_ranges=date_range
    ))
    res_pages = client.run_report(RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="date"), Dimension(name="landingPagePlusQueryString")],
        metrics=[Metric(name="screenPageViews")], 
        date_ranges=date_range
    ))
    res_country = client.run_report(RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="date"), Dimension(name="country")],
        metrics=[Metric(name="screenPageViews")], 
        date_ranges=date_range
    ))
    
    date_val = "不明"
    formatted_rows = []
    
    if res_total.rows:
        date_val = res_total.rows[0].dimension_values[0].value
        row = res_total.rows[0]
        formatted_rows.append(["★全体PV", date_val, int(row.metric_values[0].value)])
        formatted_rows.append(["★全体UU", date_val, int(row.metric_values[1].value)])
        formatted_rows.append(["★全体Sessions", date_val, int(row.metric_values[2].value)])
        formatted_rows.append(["★エンゲージメント率", date_val, f"{float(row.metric_values[3].value)*100:.1f}%"])

    for row in res_source.rows[:5]:
        formatted_rows.append([f"流入: {row.dimension_values[1].value}", date_val, int(row.metric_values[0].value)])

    for row in res_pages.rows[:10]:
        formatted_rows.append([f"ページ: {row.dimension_values[1].value}", date_val, int(row.metric_values[0].value)])

    for row in res_country.rows[:5]:
        formatted_rows.append([f"国: {row.dimension_values[1].value}", date_val, int(row.metric_values[0].value)])
        
    return formatted_rows

# --- 4. メイン（if __name__ == "__main__": を消して左詰めにする） ---
final_data_process = True # 実行フラグ（任意）

print(f"✅ 実行開始 サービスアカウント: {credentials_dict.get('client_email')}")
for pid, name in TARGET_SITES.items():
    try:
        print(f"取得中: {name}")
        site_data = get_ga4_data(pid, name)
        if site_data:
            update_site_sheet(name, site_data)
    except Exception as e:
        print(f"⚠️ エラー（{name}）: {e}")

print("\n✨ すべてのサイトの更新が完了しました。")
