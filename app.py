from flask import Flask, render_template, jsonify, request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
import os
from datetime import datetime, timedelta
from news_archiver import get_news_data, get_corporations

app = Flask(__name__)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

def get_google_sheets_service():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return build('sheets', 'v4', credentials=creds)

@app.route('/')
def index():
    news_data = get_news_data()
    return render_template('index.html', news_data=news_data)

@app.route('/api/news')
def api_news():
    # 날짜 필터 파라미터 가져오기
    days = request.args.get('days', type=int, default=30)
    company = request.args.get('company', type=str, default=None)
    
    # 날짜 범위 계산
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # 뉴스 데이터 가져오기
    news_data = get_news_data()
    
    # 날짜 필터링
    filtered_news = []
    for news in news_data:
        try:
            news_date = datetime.strptime(news['date'], '%Y년 %m월 %d일')
            if news_date >= start_date:
                if company is None or news['company'] == company:
                    filtered_news.append(news)
        except:
            continue
    
    return jsonify(filtered_news)

@app.route('/api/companies')
def api_companies():
    service = get_google_sheets_service()
    companies = get_corporations(service)
    return jsonify(companies)

if __name__ == '__main__':
    app.run(debug=True) 