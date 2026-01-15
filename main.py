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
    final_
