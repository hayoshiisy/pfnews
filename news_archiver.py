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
        print("\n=== 환경 변수 확인 ===")
        
        # GOOGLE_PRIVATE_KEY 특별 처리
        private_key = os.getenv('GOOGLE_PRIVATE_KEY', '')
        if private_key:
            # 리터럴 문자열 \n을 실제 줄바꿈으로 변환
            private_key = private_key.replace('\\n', '\n')
        
        env_vars = {
            'GOOGLE_PROJECT_ID': os.getenv('GOOGLE_PROJECT_ID', '').strip('"'),
            'GOOGLE_PRIVATE_KEY_ID': os.getenv('GOOGLE_PRIVATE_KEY_ID', '').strip('"'),
            'GOOGLE_PRIVATE_KEY': private_key,
            'GOOGLE_CLIENT_EMAIL': os.getenv('GOOGLE_CLIENT_EMAIL', '').strip('"'),
            'GOOGLE_CLIENT_ID': os.getenv('GOOGLE_CLIENT_ID', '').strip('"'),
            'GOOGLE_CLIENT_X509_CERT_URL': os.getenv('GOOGLE_CLIENT_X509_CERT_URL', '').strip('"'),
            'SPREADSHEET_ID': os.getenv('SPREADSHEET_ID', '').strip('"')
        }
        
        # 환경 변수 검증 및 출력
        for key, value in env_vars.items():
            if not value:
                print(f"\n{key}:")
                print("- 설정되지 않음")
                return None
            else:
                print(f"\n{key}:")
                print(f"- 설정됨: 예")
                print(f"- 길이: {len(value)}")
                if key == 'GOOGLE_PRIVATE_KEY':
                    print(f"- 시작 부분: {value[:50]}")
                    print(f"- 끝 부분: {value[-50:]}")
                    newline_count = value.count(chr(10))
                    print(f"- 줄바꿈 수: {newline_count}")
                else:
                    print(f"- 값: {value}")
        
        # 서비스 계정 정보 구성
        service_account_info = {
            "type": "service_account",
            "project_id": env_vars['GOOGLE_PROJECT_ID'],
            "private_key_id": env_vars['GOOGLE_PRIVATE_KEY_ID'],
            "private_key": env_vars['GOOGLE_PRIVATE_KEY'],
            "client_email": env_vars['GOOGLE_CLIENT_EMAIL'],
            "client_id": env_vars['GOOGLE_CLIENT_ID'],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": env_vars['GOOGLE_CLIENT_X509_CERT_URL']
        }
        
        print("\n=== 서비스 계정 정보 구성 ===")
        debug_info = service_account_info.copy()
        debug_info['private_key'] = '***HIDDEN***'
        print(json.dumps(debug_info, indent=2, ensure_ascii=False))
        
        # 직접 인증 시도
        try:
            print("\n=== 직접 인증 시도 ===")
            creds = service_account.Credentials.from_service_account_info(
                service_account_info, scopes=SCOPES)
            
            service = build('sheets', 'v4', credentials=creds)
            print("Google Sheets 서비스 초기화 성공")
            return service
            
        except Exception as e:
            print(f"\n=== 직접 인증 실패, 파일 기반 인증 시도 ===")
            print(f"오류 메시지: {str(e)}")
            
            # 임시 JSON 파일 생성
            import tempfile
            
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_file:
                json.dump(service_account_info, temp_file, indent=2)
                temp_file_path = temp_file.name
            
            print(f"\n=== 서비스 계정 키 파일 생성 ===")
            print(f"임시 파일 경로: {temp_file_path}")
            
            try:
                # 서비스 계정 키 파일을 사용하여 인증
                creds = service_account.Credentials.from_service_account_file(
                    temp_file_path, scopes=SCOPES)
                
                service = build('sheets', 'v4', credentials=creds)
                print("Google Sheets 서비스 초기화 성공")
                
                # 임시 파일 삭제
                os.unlink(temp_file_path)
                return service
                
            except Exception as e:
                print(f"\n=== 파일 기반 인증 실패 ===")
                print(f"오류 메시지: {str(e)}")
                print(f"오류 유형: {type(e).__name__}")
                import traceback
                print("상세 오류 정보:")
                print(traceback.format_exc())
                
                # 임시 파일 삭제 시도
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
                return None
            
    except Exception as e:
        print(f"\n=== 일반 오류 발생 ===")
        print(f"오류 메시지: {str(e)}")
        print(f"오류 유형: {type(e).__name__}")
        import traceback
        print("상세 오류 정보:")
        print(traceback.format_exc())
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
        print(f"\n=== 저장 프로세스 디버깅 ===")
        print(f"회사명: {company_name}")
        print(f"초기 기사 수: {len(articles)}")
        
        # 새로운 데이터를 DataFrame으로 변환
        df_new = pd.DataFrame(articles)
        
        # 날짜순 정렬
        df_new['pubDate'] = pd.to_datetime(df_new['pubDate']).dt.tz_localize(None)
        df_new = df_new.sort_values('pubDate', ascending=False)
        
        # 날짜를 문자열로 변환 (YYYY-MM-DD 형식)
        df_new['pubDate'] = df_new['pubDate'].dt.strftime('%Y-%m-%d')
        
        # 중복 제거 (제목과 회사명 기준)
        df_new = df_new.drop_duplicates(subset=['title', 'company'], keep='first')
        print(f"중복 제거 후 데이터 수: {len(df_new)}")
        
        # Google Sheets에 저장
        service = get_google_sheets_service()
        if service:
            # 데이터를 2D 리스트로 변환
            values = df_new[['pubDate', 'company', 'title', 'link', 'content']].values.tolist()
            
            # 기존 데이터 지우기
            service.spreadsheets().values().clear(
                spreadsheetId=SPREADSHEET_ID,
                range='법인 PR!A2:E'
            ).execute()
            
            # 새 데이터 쓰기
            body = {
                'values': values
            }
            service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID,
                range='법인 PR!A2',
                valueInputOption='RAW',
                body=body
            ).execute()
            
            print(f"최종 저장된 데이터 수: {len(values)}")
        
    except Exception as e:
        print(f"Error saving to spreadsheet: {str(e)}")
        import traceback
        print(traceback.format_exc())

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
    
    print("\n법인 목록 가져오는 중...")
    corporations = get_corporations(service)
    print(f"{len(corporations)}개 법인 발견")
    
    all_news_items = []
    for company in corporations:
        print(f"\n'{company}'의 뉴스 검색 중...")
        news_items = search_naver_news(company, NAVER_CLIENT_ID, NAVER_CLIENT_SECRET)
        if news_items:
            print(f"{len(news_items)}개의 기사를 찾았습니다.")
            # 각 기사의 회사명 추가
            for item in news_items:
                item['company'] = company
            all_news_items.extend(news_items)
            print(f"누적 기사 수: {len(all_news_items)}")
        else:
            print("유효한 기사를 찾지 못했습니다.")
    
    if all_news_items:
        print(f"\n총 {len(all_news_items)}개의 기사 중 중복 제거 시작...")
        save_to_spreadsheet(all_news_items, "all")
        print("저장 완료!")

if __name__ == '__main__':
    main()