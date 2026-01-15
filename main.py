import os
import json
import gspread
import google.generativeai as genai
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric
from google.oauth2.service_account import Credentials

# --- 認証情報 ---
def get_credentials():
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        return json.loads(creds_json)
    with open("service-account-key.json", "r") as f:
        return json.load(f)

credentials_dict = get_credentials()

# --- Gemini設定 ---
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY") # GitHub Secretsに登録
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

SPREADSHEET_KEY = '1FEO4sv3WP2_AQLsXezwVV32d_luGUwVRcsStuGAytOE'
TARGET_SITES = {
    "391519429": "カーリース",
    "372188028": "福祉レンタカー",
    "468612790": "HAレンタカー",
    "382138346": "ITS",
    "391533336": "レンタカー",
    "294934653": "スマイルモビリティ",
}

def analyze_with_gemini(site_name, data_rows):
    """取得したデータをGeminiに渡し、Web担当者向けのレポートを生成する"""
    data_summary = "\n".join([f"{r[0]}: {r[2]}" for r in data_rows])
    prompt = f"""
    あなたは敏腕Webマーケターです。以下のGA4データ（昨日分）に基づき、{site_name}のWeb担当者へ向けた日報を作成してください。
    
    【データ】
    {data_summary}
    
    【指示】
    - 専門用語を使いすぎず、具体的かつ前向きなトーンで。
    - PV、流入、人気ページ、国の傾向から気づくことを3点以内で。
    - 次のアクション（例：このページの改修、この流入元の強化など）を1つ提案してください。
    - 全体で300文字程度にまとめてください。
    """
    try:
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"分析エラー: {e}"

def update_site_sheet(site_name, data_rows):
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_KEY)
    
    try:
        worksheet = sh.worksheet(site_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sh.add_worksheet(title=site_name, rows="500", cols="100")
        worksheet.update('A1', [['項目 / 日付']])

    existing_items = worksheet.col_values(1)
    header_row = worksheet.row_values(1)
    next_col_num = len(header_row) + 1
    next_col_letter = gspread.utils.rowcol_to_a1(1, next_col_num)[:-1]
    
    date_label = data_rows[0][1]
    # Geminiの分析結果をデータセットに追加
    analysis_text = analyze_with_gemini(site_name, data_rows)
    data_rows.append(["AI分析レポート", date_label, analysis_text])

    # 列データの整形と書き込み
    final_column_output = [''] * max(len(existing_items), 100)
    final_column_output[0] = date_label

    for item_name, _, value in data_rows:
        if item_name in existing_items:
            idx = existing_items.index(item_name)
        else:
            existing_items.append(item_name)
            idx = len(existing_items) - 1
            worksheet.update_cell(idx + 1, 1, item_name)
            if idx >= len(final_column_output): final_column_output.append('')
        final_column_output[idx] = value

    column_data_formatted = [[v] for v in final_column_output]
    worksheet.update(f'{next_col_letter}1', column_data_formatted)

def get_ga4_data(property_id, site_name):
    client = BetaAnalyticsDataClient.from_service_account_info(credentials_dict)
    dr = [DateRange(start_date="yesterday", end_date="yesterday")]
    
    reqs = {
        "total": RunReportRequest(property=f"properties/{property_id}", dimensions=[Dimension(name="date")], metrics=[Metric(name="screenPageViews"), Metric(name="totalUsers"), Metric(name="sessions"), Metric(name="engagementRate")], date_ranges=dr),
        "source": RunReportRequest(property=f"properties/{property_id}", dimensions=[Dimension(name="date"), Dimension(name="sessionSourceMedium")], metrics=[Metric(name="screenPageViews")], date_ranges=dr),
        "pages": RunReportRequest(property=f"properties/{property_id}", dimensions=[Dimension(name="date"), Dimension(name="landingPagePlusQueryString")], metrics=[Metric(name="screenPageViews")], date_ranges=dr),
        "country": RunReportRequest(property=f"properties/{property_id}", dimensions=[Dimension(name="date"), Dimension(name="country")], metrics=[Metric(name="screenPageViews")], date_ranges=dr)
    }

    res = {k: client.run_report(v) for k, v in reqs.items()}
    
    date_val = res["total"].rows[0].dimension_values[0].value if res["total"].rows else "不明"
    formatted = []
    
    if res["total"].rows:
        r = res["total"].rows[0]
        formatted.extend([
            ["★全体PV", date_val, int(r.metric_values[0].value)],
            ["★全体UU", date_val, int(r.metric_values[1].value)],
            ["★全体Sessions", date_val, int(r.metric_values[2].value)],
            ["★エンゲージメント率", date_val, f"{float(r.metric_values[3].value)*100:.1f}%"]
        ])
    for r in res["source"].rows[:5]: formatted.append([f"流入: {r.dimension_values[1].value}", date_val, int(r.metric_values[0].value)])
    for r in res["pages"].rows[:10]: formatted.append([f"ページ: {r.dimension_values[1].value}", date_val, int(r.metric_values[0].value)])
    for r in res["country"].rows[:5]: formatted.append([f"国: {r.dimension_values[1].value}", date_val, int(r.metric_values[0].value)])
        
    return formatted

if __name__ == "__main__":
    for pid, name in TARGET_SITES.items():
        try:
            print(f"分析中...: {name}")
            site_data = get_ga4_data(pid, name)
            if site_data:
                update_site_sheet(name, site_data)
        except Exception as e:
            print(f"エラー（{name}）: {e}")
    print("\nすべての分析と更新が完了しました。")
