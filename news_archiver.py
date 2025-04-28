import os
import pickle
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import time
from dateutil import parser
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from dotenv import load_dotenv
import re
import pandas as pd
from google.oauth2 import service_account
import json

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID', '1IgpwLo4P9ISt43ZOzkiz6YedWSL0Yh3LZpwmSzmp3u0')

# 네이버 API 키 설정
NAVER_CLIENT_ID = os.getenv('NAVER_CLIENT_ID', 'xfwEXaagnGe2G_5Mquhb')
NAVER_CLIENT_SECRET = os.getenv('NAVER_CLIENT_SECRET', 'XEsKiDLtUC')

def get_google_sheets_service():
    try:
        # 환경 변수에서 서비스 계정 키 정보 가져오기
        service_account_info = {
            "type": "service_account",
            "project_id": os.getenv('GOOGLE_PROJECT_ID'),
            "private_key_id": os.getenv('GOOGLE_PRIVATE_KEY_ID'),
            "private_key": os.getenv('GOOGLE_PRIVATE_KEY', '').replace('\\n', '\n'),
            "client_email": os.getenv('GOOGLE_CLIENT_EMAIL'),
            "client_id": os.getenv('GOOGLE_CLIENT_ID'),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": os.getenv('GOOGLE_CLIENT_X509_CERT_URL')
        }
        
        # 필수 필드 확인
        required_fields = ['project_id', 'private_key_id', 'private_key', 'client_email']
        for field in required_fields:
            if not service_account_info.get(field):
                raise ValueError(f"Missing required field: {field}")
        
        creds = service_account.Credentials.from_service_account_info(
            service_account_info, scopes=SCOPES)
        
        return build('sheets', 'v4', credentials=creds)
    except Exception as e:
        print(f"Google Sheets 서비스 초기화 중 오류 발생: {str(e)}")
        return None

def get_corporations(service):
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range='법인 리스트!A2:A'
    ).execute()
    
    values = result.get('values', [])
    if not values:
        print('No data found.')
        return []
    
    return [row[0] for row in values]

def get_all_news_data(service):
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range='법인 PR!A2:E'  # 헤더 제외하고 데이터만 가져옴
    ).execute()
    
    values = result.get('values', [])
    if not values:
        return []
    
    return values

def remove_duplicates(service):
    print("\n중복 기사 제거 중...")
    
    # 모든 뉴스 데이터 가져오기
    news_data = get_all_news_data(service)
    
    # 링크를 기준으로 중복 체크
    seen_links = {}
    unique_news = []
    duplicates_count = 0
    
    for row in news_data:
        if len(row) < 5:  # 데이터가 불완전한 경우 건너뛰기
            continue
            
        link = row[3]  # 링크는 4번째 열
        
        if link not in seen_links:
            seen_links[link] = row
            unique_news.append(row)
        else:
            duplicates_count += 1
    
    if duplicates_count > 0:
        # 기존 데이터 모두 지우기
        service.spreadsheets().values().clear(
            spreadsheetId=SPREADSHEET_ID,
            range='법인 PR!A2:E',
        ).execute()
        
        # 중복이 제거된 데이터 다시 쓰기
        body = {
            'values': unique_news
        }
        
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range='법인 PR!A2',
            valueInputOption='RAW',
            body=body
        ).execute()
        
        print(f"{duplicates_count}개의 중복 기사가 제거되었습니다.")
    else:
        print("중복된 기사가 없습니다.")

def get_existing_urls(service):
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range='법인 PR!D:D'
    ).execute()
    
    values = result.get('values', [])
    if not values:
        return set()
    
    return set(row[0] for row in values[1:])  # 헤더 제외

def clean_html(text):
    return text.replace('<b>', '').replace('</b>', '').strip()

def extract_press_name(originallink, description):
    """
    originallink와 description에서 언론사 정보를 추출합니다.
    """
    # originallink에서 도메인 추출 시도
    try:
        from urllib.parse import urlparse
        domain = urlparse(originallink).netloc
        if domain:
            # .co.kr, .com 등의 TLD 제거
            press_name = domain.split('.')[0]
            # 대문자로 시작하는 경우 첫 글자만 대문자로
            if press_name[0].isupper():
                press_name = press_name[0] + press_name[1:].lower()
            return press_name
    except:
        pass
    
    # description에서 언론사 정보 추출 시도
    try:
        # "기자 (언론사명)" 패턴 찾기
        import re
        match = re.search(r'기자\s*\(([^)]+)\)', description)
        if match:
            return match.group(1)
    except:
        pass
    
    return "알 수 없음"

def search_naver_news(company_name, api_key, api_secret):
    """네이버 뉴스 API를 사용하여 기업 관련 뉴스를 검색합니다."""
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": api_key,
        "X-Naver-Client-Secret": api_secret
    }
    
    # 검색어 설정 (회사명 + 관련 키워드)
    search_queries = [
        f'"{company_name}"',
        f'"{company_name}(주)"',
        f'"{company_name} 주식회사"',
        f'"(주){company_name}"',
        f'"{company_name} 회사"'
    ]
    
    all_articles = []
    
    for query in search_queries:
        params = {
            "query": query,
            "display": 100,  # 최대 100개 결과
            "sort": "date"   # 최신순 정렬
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            result = response.json()
            
            if 'items' in result:
                for item in result['items']:
                    # HTML 태그 제거
                    title = re.sub(r'<[^>]+>', '', item['title'])
                    description = re.sub(r'<[^>]+>', '', item['description'])
                    
                    # 회사명이 제목이나 본문에 포함된 경우만 저장
                    if company_name in title or company_name in description:
                        all_articles.append({
                            'title': title,
                            'content': description,
                            'link': item['link'],
                            'pubDate': item['pubDate']
                        })
            
            time.sleep(0.1)  # API 호출 간격 조절
            
        except Exception as e:
            print(f"Error searching for {query}: {str(e)}")
            continue
    
    return all_articles

def save_to_spreadsheet(articles, company_name):
    """수집된 기사를 스프레드시트에 저장합니다."""
    try:
        # 스프레드시트 파일 경로
        spreadsheet_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'news_data.xlsx')
        
        # 기존 파일이 있으면 읽어오기
        if os.path.exists(spreadsheet_path):
            df_existing = pd.read_excel(spreadsheet_path)
        else:
            df_existing = pd.DataFrame(columns=['company', 'title', 'content', 'link', 'pubDate'])
        
        # 새로운 데이터를 DataFrame으로 변환
        df_new = pd.DataFrame(articles)
        df_new['company'] = company_name
        
        # 기존 데이터와 새 데이터 병합
        df_combined = pd.concat([df_existing, df_new], ignore_index=True)
        
        # 중복 제거 (제목 기준)
        df_combined = df_combined.drop_duplicates(subset=['title'], keep='first')
        
        # 날짜순 정렬 (타임존 제거)
        df_combined['pubDate'] = pd.to_datetime(df_combined['pubDate']).dt.tz_localize(None)
        df_combined = df_combined.sort_values('pubDate', ascending=False)
        
        # Excel 파일로 저장
        df_combined.to_excel(spreadsheet_path, index=False)
        print(f"\n총 {len(articles)}개의 기사를 스프레드시트에 저장합니다...")
        print("저장 완료!")
        
    except Exception as e:
        print(f"Error saving to spreadsheet: {str(e)}")

def get_news_data():
    """
    Google Sheets에서 뉴스 데이터를 가져옵니다.
    """
    try:
        service = get_google_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range='법인 PR!A2:D'  # 헤더 제외하고 데이터만 가져옴
        ).execute()
        
        values = result.get('values', [])
        if not values:
            print('데이터가 없습니다.')
            return []
        
        # 데이터 정리
        news_data = []
        for row in values:
            try:
                if len(row) < 4:  # 데이터가 불완전한 경우 건너뛰기
                    continue
                
                news_data.append({
                    'date': row[0],
                    'company': row[1],
                    'content': row[2],
                    'link': row[3]
                })
            except Exception as e:
                print(f"데이터 처리 중 오류 발생: {str(e)}")
                continue
        
        # 날짜별로 정렬 (날짜 형식: YYYY-MM-DD)
        news_data.sort(key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'), reverse=True)
        return news_data
        
    except Exception as e:
        print(f"뉴스 데이터 로딩 중 오류 발생: {str(e)}")
        return []

def main():
    print("Google Sheets 서비스 초기화 중...")
    service = get_google_sheets_service()
    
    # 중복 제거 실행
    remove_duplicates(service)
    
    print("\n법인 목록 가져오는 중...")
    corporations = get_corporations(service)
    print(f"{len(corporations)}개 법인 발견")
    
    # 기존 URL 목록 가져오기
    existing_urls = get_existing_urls(service)
    
    all_news_items = []
    for company in corporations:
        print(f"\n'{company}'의 뉴스 검색 중...")
        news_items = search_naver_news(company, NAVER_CLIENT_ID, NAVER_CLIENT_SECRET)
        if news_items:
            print(f"{len(news_items)}개의 기사를 찾았습니다.")
            all_news_items.extend(news_items)
        else:
            print("유효한 기사를 찾지 못했습니다.")
    
    if all_news_items:
        print(f"\n총 {len(all_news_items)}개의 기사를 스프레드시트에 저장합니다...")
        save_to_spreadsheet(all_news_items, company)
        print("저장 완료!")

if __name__ == '__main__':
    main()