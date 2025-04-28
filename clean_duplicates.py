import os
import pickle
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv

# 구글 스프레드시트 API 설정
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = '1IgpwLo4P9ISt43ZOzkiz6YedWSL0Yh3LZpwmSzmp3u0'

def get_google_sheets_service():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    return build('sheets', 'v4', credentials=creds)

def clean_duplicates():
    print("Google Sheets 서비스 초기화 중...")
    service = get_google_sheets_service()
    
    print("스프레드시트에서 데이터 가져오는 중...")
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range='법인 PR!A2:E'
    ).execute()
    
    values = result.get('values', [])
    if not values:
        print("데이터가 없습니다.")
        return
    
    print(f"총 {len(values)}개의 기사를 찾았습니다.")
    
    # URL을 기준으로 중복 제거
    unique_articles = {}
    for row in values:
        if len(row) >= 5:  # 모든 필수 필드가 있는지 확인
            url = row[4]  # URL은 5번째 열
            if url not in unique_articles:
                unique_articles[url] = row
    
    print(f"중복 제거 후 {len(unique_articles)}개의 기사가 남았습니다.")
    print(f"{len(values) - len(unique_articles)}개의 중복 기사가 제거되었습니다.")
    
    if len(unique_articles) == len(values):
        print("중복된 기사가 없습니다.")
        return
    
    # 기존 데이터 삭제 (헤더 제외)
    service.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID,
        range='법인 PR!A2:E',
        body={}
    ).execute()
    
    # 중복이 제거된 데이터 다시 쓰기
    body = {
        'values': list(unique_articles.values())
    }
    
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range='법인 PR!A2',
        valueInputOption='RAW',
        body=body
    ).execute()
    
    print("중복 제거가 완료되었습니다.")

if __name__ == '__main__':
    clean_duplicates() 