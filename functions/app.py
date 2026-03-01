"""
LOFA 복지기금 v2.0
Apple-inspired design | Dynamic Forms | SMS Notification System
"""

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore, storage as fb_storage
import os, uuid, json, re
from datetime import datetime, timedelta
from io import BytesIO
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from PIL import Image
import pandas as pd
from werkzeug.utils import secure_filename
import requests

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'lofa2-secret-key-change-in-production')
CORS(app)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=3600,
    MAX_CONTENT_LENGTH=32 * 1024 * 1024,
)

# ─── Firebase Init ────────────────────────────────────────────────────────────
if not firebase_admin._apps:
    if os.path.exists('serviceAccountKey.json'):
        cred = credentials.Certificate('serviceAccountKey.json')
    else:
        cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {
        'storageBucket': os.environ.get('FIREBASE_STORAGE_BUCKET', 'lofa2-xxxxx.appspot.com')
    })

db = firestore.client()

# ─── Banks ────────────────────────────────────────────────────────────────────
BANKS = [
    '국민은행','신한은행','하나은행','우리은행','농협은행','기업은행','카카오뱅크',
    '케이뱅크','토스뱅크','SC제일은행','씨티은행','대구은행','부산은행','경남은행',
    '광주은행','전북은행','제주은행','우체국','새마을금고','신협','산업은행','수협은행'
]

# ─── Default Form Types ───────────────────────────────────────────────────────
DEFAULT_FORM_TYPES = [
    {
        'id': 'housing', 'name': '주택지원', 'icon': '🏠',
        'description': '근로자 주거 안정을 위한 주택 관련 지원금',
        'color': '#0071e3', 'order': 1, 'is_active': True, 'annual_limit': 4800000,
        'fields': [
            {'id': 'f1','type':'select','label':'신청구분','name':'housing_type','required':True,
             'options':['전세자금','월세지원','주택구입','기타'],'placeholder':''},
            {'id': 'f2','type':'textarea','label':'신청사유','name':'reason','required':True,'placeholder':'신청 사유를 상세히 입력하세요'},
            {'id': 'f3','type':'amount','label':'신청금액','name':'amount','required':True,'placeholder':''},
            {'id': 'f4','type':'account','label':'입금계좌','name':'account','required':True,'placeholder':''},
            {'id': 'f5','type':'file','label':'첨부파일','name':'attachment','required':False,'placeholder':''},
        ]
    },
    {
        'id': 'pension', 'name': '복지연금', 'icon': '🏦',
        'description': '근로자 노후 대비 복지연금 지원',
        'color': '#5856d6', 'order': 2, 'is_active': True, 'annual_limit': 4800000,
        'fields': [
            {'id': 'f1','type':'select','label':'연금유형','name':'pension_type','required':True,
             'options':['개인연금','퇴직연금','기타'],'placeholder':''},
            {'id': 'f2','type':'amount','label':'신청금액','name':'amount','required':True,'placeholder':''},
            {'id': 'f3','type':'account','label':'입금계좌','name':'account','required':True,'placeholder':''},
            {'id': 'f4','type':'file','label':'첨부파일','name':'attachment','required':False,'placeholder':''},
        ]
    },
    {
        'id': 'medical', 'name': '의료비지원', 'icon': '🏥',
        'description': '본인 및 가족 의료비 지원',
        'color': '#ff3b30', 'order': 3, 'is_active': True, 'annual_limit': 4800000,
        'fields': [
            {'id': 'f1','type':'text','label':'환자성명','name':'patient_name','required':True,'placeholder':'환자 이름'},
            {'id': 'f2','type':'select','label':'관계','name':'relation','required':True,
             'options':['본인','배우자','자녀','부모','기타'],'placeholder':''},
            {'id': 'f3','type':'text','label':'병원명','name':'hospital','required':True,'placeholder':'병원/의원명'},
            {'id': 'f4','type':'textarea','label':'치료내용','name':'treatment','required':True,'placeholder':'치료 내용을 입력하세요'},
            {'id': 'f5','type':'amount','label':'신청금액','name':'amount','required':True,'placeholder':''},
            {'id': 'f6','type':'account','label':'입금계좌','name':'account','required':True,'placeholder':''},
            {'id': 'f7','type':'file','label':'영수증 첨부','name':'attachment','required':True,'placeholder':''},
        ]
    },
    {
        'id': 'life_welfare', 'name': '생활복지지원', 'icon': '🌿',
        'description': '근로자 생활 안정을 위한 다양한 복지 지원',
        'color': '#34c759', 'order': 4, 'is_active': True, 'annual_limit': 0,
        'fields': [
            {'id': 'f1','type':'select','label':'지원유형','name':'welfare_type','required':True,
             'options':['생활비지원','긴급지원','기타'],'placeholder':''},
            {'id': 'f2','type':'textarea','label':'세부내용','name':'detail','required':True,'placeholder':'세부 내용을 입력하세요'},
            {'id': 'f3','type':'amount','label':'신청금액','name':'amount','required':True,'placeholder':''},
            {'id': 'f4','type':'account','label':'입금계좌','name':'account','required':True,'placeholder':''},
            {'id': 'f5','type':'file','label':'첨부파일','name':'attachment','required':False,'placeholder':''},
        ]
    },
    {
        'id': 'maternity', 'name': '모성보호지원', 'icon': '👶',
        'description': '출산·육아 관련 모성보호 지원금',
        'color': '#ff9500', 'order': 5, 'is_active': True, 'annual_limit': 0,
        'fields': [
            {'id': 'f1','type':'text','label':'대상자성명','name':'target_name','required':True,'placeholder':''},
            {'id': 'f2','type':'date','label':'출산일','name':'birth_date','required':True,'placeholder':''},
            {'id': 'f3','type':'select','label':'지원구분','name':'support_type','required':True,
             'options':['출산축하금','산전검진비','육아용품비','기타'],'placeholder':''},
            {'id': 'f4','type':'amount','label':'신청금액','name':'amount','required':True,'placeholder':''},
            {'id': 'f5','type':'account','label':'입금계좌','name':'account','required':True,'placeholder':''},
            {'id': 'f6','type':'file','label':'첨부파일 (출생증명서 등)','name':'attachment','required':True,'placeholder':''},
        ]
    },
    {
        'id': 'solace', 'name': '위로금지원', 'icon': '🕊️',
        'description': '경조사 시 위로금 지원',
        'color': '#636366', 'order': 6, 'is_active': True, 'annual_limit': 0,
        'fields': [
            {'id': 'f1','type':'text','label':'대상자성명','name':'target_name','required':True,'placeholder':''},
            {'id': 'f2','type':'select','label':'관계','name':'relation','required':True,
             'options':['본인','배우자','자녀','부모','형제자매','기타'],'placeholder':''},
            {'id': 'f3','type':'select','label':'사유구분','name':'event_type','required':True,
             'options':['사망','질병','재해','기타'],'placeholder':''},
            {'id': 'f4','type':'date','label':'사유일자','name':'event_date','required':True,'placeholder':''},
            {'id': 'f5','type':'amount','label':'신청금액','name':'amount','required':True,'placeholder':''},
            {'id': 'f6','type':'account','label':'입금계좌','name':'account','required':True,'placeholder':''},
            {'id': 'f7','type':'file','label':'관련 서류','name':'attachment','required':False,'placeholder':''},
        ]
    },
    {
        'id': 'cultural_activity', 'name': '문화활동비', 'icon': '🎭',
        'description': '근로자 및 가족 문화·여가 활동 지원 (반기 30만원)',
        'color': '#af52de', 'order': 7, 'is_active': True, 'annual_limit': 600000,
        'fields': [
            {'id': 'f1','type':'text','label':'활동내용','name':'activity_name','required':True,'placeholder':'예) 가족 여행, 문화 공연 관람'},
            {'id': 'f2','type':'date','label':'활동일자','name':'activity_date','required':True,'placeholder':''},
            {'id': 'f3','type':'amount','label':'신청금액','name':'amount','required':True,'placeholder':''},
            {'id': 'f4','type':'account','label':'입금계좌','name':'account','required':True,'placeholder':''},
            {'id': 'f5','type':'file','label':'영수증 첨부','name':'attachment','required':True,'placeholder':''},
        ]
    },
    {
        'id': 'vaccination', 'name': '예방접종비', 'icon': '💉',
        'description': '정기 예방접종 비용 지원 (연 15만원)',
        'color': '#30b0c7', 'order': 8, 'is_active': True, 'annual_limit': 150000,
        'fields': [
            {'id': 'f1','type':'text','label':'예방접종종류','name':'vaccine_type','required':True,'placeholder':'예) 독감, B형간염'},
            {'id': 'f2','type':'date','label':'접종일자','name':'vaccination_date','required':True,'placeholder':''},
            {'id': 'f3','type':'amount','label':'신청금액','name':'amount','required':True,'placeholder':''},
            {'id': 'f4','type':'account','label':'입금계좌','name':'account','required':True,'placeholder':''},
            {'id': 'f5','type':'file','label':'영수증 첨부','name':'attachment','required':True,'placeholder':''},
        ]
    },
    {
        'id': 'loan', 'name': '대부신청', 'icon': '💳',
        'description': '긴급 자금 대부 신청',
        'color': '#ff6b35', 'order': 9, 'is_active': True, 'annual_limit': 0,
        'fields': [
            {'id': 'f1','type':'select','label':'대출목적','name':'purpose','required':True,
             'options':['생활안정자금','의료비','교육비','주거비','기타'],'placeholder':''},
            {'id': 'f2','type':'textarea','label':'신청사유','name':'reason','required':True,'placeholder':'신청 사유를 상세히 입력하세요'},
            {'id': 'f3','type':'amount','label':'신청금액','name':'amount','required':True,'placeholder':''},
            {'id': 'f4','type':'select','label':'상환기간','name':'repayment_period','required':True,
             'options':['6개월','12개월','18개월','24개월','36개월'],'placeholder':''},
            {'id': 'f5','type':'account','label':'입금계좌','name':'account','required':True,'placeholder':''},
            {'id': 'f6','type':'file','label':'첨부서류','name':'attachment','required':False,'placeholder':''},
        ]
    },
    {
        'id': 'congratulation', 'name': '경조비지원', 'icon': '🎊',
        'description': '결혼·출산·회갑 등 경조사 지원',
        'color': '#ff2d55', 'order': 10, 'is_active': True, 'annual_limit': 0,
        'fields': [
            {'id': 'f1','type':'text','label':'대상자성명','name':'target_name','required':True,'placeholder':''},
            {'id': 'f2','type':'select','label':'관계','name':'relation','required':True,
             'options':['본인','배우자','자녀','부모','형제자매','기타'],'placeholder':''},
            {'id': 'f3','type':'select','label':'경조사구분','name':'event_type','required':True,
             'options':['결혼','출산','돌','회갑','칠순','팔순','사망','기타'],'placeholder':''},
            {'id': 'f4','type':'date','label':'경조사일자','name':'event_date','required':True,'placeholder':''},
            {'id': 'f5','type':'amount','label':'신청금액','name':'amount','required':True,'placeholder':''},
            {'id': 'f6','type':'account','label':'입금계좌','name':'account','required':True,'placeholder':''},
            {'id': 'f7','type':'file','label':'청첩장/증명서','name':'attachment','required':False,'placeholder':''},
        ]
    },
    {
        'id': 'scholarship', 'name': '장학금지원', 'icon': '🎓',
        'description': '본인 및 자녀 학자금 지원',
        'color': '#007aff', 'order': 11, 'is_active': True, 'annual_limit': 0,
        'fields': [
            {'id': 'f1','type':'text','label':'대상자성명','name':'target_name','required':True,'placeholder':''},
            {'id': 'f2','type':'select','label':'관계','name':'relation','required':True,
             'options':['본인','자녀'],'placeholder':''},
            {'id': 'f3','type':'text','label':'학교명','name':'school_name','required':True,'placeholder':''},
            {'id': 'f4','type':'text','label':'학년','name':'grade','required':True,'placeholder':'예) 3학년'},
            {'id': 'f5','type':'select','label':'학기','name':'semester','required':True,
             'options':['1학기','2학기'],'placeholder':''},
            {'id': 'f6','type':'amount','label':'신청금액','name':'amount','required':True,'placeholder':''},
            {'id': 'f7','type':'account','label':'입금계좌','name':'account','required':True,'placeholder':''},
            {'id': 'f8','type':'file','label':'재학증명서 등록금고지서','name':'attachment','required':True,'placeholder':''},
        ]
    },
    {
        'id': 'multichild', 'name': '다자녀지원', 'icon': '👨‍👩‍👧‍👦',
        'description': '다자녀 가정 특별 지원금',
        'color': '#34c759', 'order': 12, 'is_active': True, 'annual_limit': 0,
        'fields': [
            {'id': 'f1','type':'number','label':'자녀수','name':'children_count','required':True,'placeholder':'자녀 수를 입력하세요'},
            {'id': 'f2','type':'text','label':'막내 자녀 나이','name':'youngest_age','required':True,'placeholder':''},
            {'id': 'f3','type':'amount','label':'신청금액','name':'amount','required':True,'placeholder':''},
            {'id': 'f4','type':'account','label':'입금계좌','name':'account','required':True,'placeholder':''},
            {'id': 'f5','type':'file','label':'가족관계증명서','name':'attachment','required':True,'placeholder':''},
        ]
    },
    {
        'id': 'inspection', 'name': '산업시찰', 'icon': '🏭',
        'description': '선진 산업체 시찰 비용 지원',
        'color': '#8e8e93', 'order': 13, 'is_active': True, 'annual_limit': 0,
        'fields': [
            {'id': 'f1','type':'text','label':'방문기관','name':'destination','required':True,'placeholder':'방문 기업/기관명'},
            {'id': 'f2','type':'date','label':'방문일자','name':'visit_date','required':True,'placeholder':''},
            {'id': 'f3','type':'textarea','label':'시찰목적','name':'purpose','required':True,'placeholder':'시찰 목적 및 내용'},
            {'id': 'f4','type':'amount','label':'신청금액','name':'amount','required':True,'placeholder':''},
            {'id': 'f5','type':'account','label':'입금계좌','name':'account','required':True,'placeholder':''},
            {'id': 'f6','type':'file','label':'관련 서류','name':'attachment','required':False,'placeholder':''},
        ]
    },
]

# ─── Default SMS Templates ────────────────────────────────────────────────────
DEFAULT_SMS_TEMPLATES = {
    'submit': {
        'name': '신청 접수 완료',
        'message': '[LOFA복지기금] {user_name}님의 {form_name} 신청이 접수되었습니다.\n신청금액: {amount}원\n처리 결과는 별도 안내드립니다.',
        'enabled': True
    },
    'approve': {
        'name': '신청 승인',
        'message': '[LOFA복지기금] {user_name}님의 {form_name} 신청이 승인되었습니다.\n신청금액: {amount}원\n입금 예정일: 처리 후 3~5일 이내',
        'enabled': True
    },
    'reject': {
        'name': '신청 반려',
        'message': '[LOFA복지기금] {user_name}님의 {form_name} 신청이 반려되었습니다.\n반려사유: {reject_reason}\n수정 후 재신청 가능합니다.',
        'enabled': True
    },
    'admin_new': {
        'name': '관리자 신규 신청 알림',
        'message': '[LOFA복지기금 관리자] 신규 신청이 접수되었습니다.\n신청자: {user_name}({user_dept})\n신청항목: {form_name}\n금액: {amount}원',
        'enabled': False
    }
}

# ─── Utility Functions ────────────────────────────────────────────────────────
def upload_file_to_storage(file, user_id, user_name, form_key):
    try:
        bucket = fb_storage.bucket()
        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'bin'
        storage_path = f"attachments/{form_key}/{user_id}_{uuid.uuid4().hex[:8]}.{ext}"

        file.seek(0)
        content = file.read()

        if ext in ('jpg', 'jpeg', 'png', 'webp'):
            img = Image.open(BytesIO(content))
            if max(img.size) > 1600:
                img.thumbnail((1600, 1600), Image.LANCZOS)
            buf = BytesIO()
            fmt = 'JPEG' if ext in ('jpg','jpeg') else ext.upper()
            img.save(buf, format=fmt, quality=80, optimize=True)
            content = buf.getvalue()

        token = uuid.uuid4().hex
        blob = bucket.blob(storage_path)
        blob.metadata = {'firebaseStorageDownloadTokens': token}
        blob.upload_from_string(content, content_type=file.content_type or 'application/octet-stream')
        url = f"https://firebasestorage.googleapis.com/v0/b/{bucket.name}/o/{storage_path.replace('/', '%2F')}?alt=media&token={token}"
        return url
    except Exception as e:
        print(f"[Storage Error] {e}")
        return None


def send_sms(phone, message):
    """Send SMS via Aligo API"""
    api_key = os.environ.get('ALIGO_API_KEY', '')
    user_id = os.environ.get('ALIGO_USER_ID', '')
    sender = os.environ.get('ALIGO_SENDER_PHONE', '')
    if not all([api_key, user_id, sender]):
        print(f"[SMS Skip] 설정 미완료. To: {phone}, Msg: {message[:30]}")
        return False
    try:
        resp = requests.post('https://apis.aligo.in/send/', data={
            'key': api_key, 'user_id': user_id, 'sender': sender,
            'receiver': phone, 'msg': message, 'title': 'LOFA복지기금'
        }, timeout=10)
        result = resp.json()
        return result.get('result_code') == '1'
    except Exception as e:
        print(f"[SMS Error] {e}")
        return False


def send_alimtalk(phone, message, template_code=None):
    """Send KakaoTalk notification via Aligo"""
    api_key = os.environ.get('ALIGO_API_KEY', '')
    user_id = os.environ.get('ALIGO_USER_ID', '')
    sender_key = os.environ.get('ALIGO_SENDER_KEY', '')
    sender_phone = os.environ.get('ALIGO_SENDER_PHONE', '')
    if not all([api_key, user_id, sender_key]):
        return send_sms(phone, message)
    try:
        data = {
            'apikey': api_key, 'userid': user_id,
            'senderkey': sender_key, 'tpl_code': template_code or 'LOFA001',
            'sender': sender_phone, 'receiver_1': phone,
            'subject_1': 'LOFA복지기금 알림', 'message_1': message,
            'failover': 'Y', 'fsubject_1': 'LOFA복지기금', 'fmessage_1': message
        }
        resp = requests.post('https://kakaoapi.aligo.in/akv10/alimtalk/send/', data=data, timeout=10)
        result = resp.json()
        return result.get('code') == 0
    except Exception as e:
        print(f"[AlimTalk Error] {e}")
        return send_sms(phone, message)


def send_notification(event_type, app_data, reject_reason=''):
    """Send notification based on event type using stored templates"""
    try:
        settings_ref = db.collection('settings').document('site_content')
        settings = settings_ref.get()
        sms_templates = DEFAULT_SMS_TEMPLATES.copy()
        if settings.exists:
            stored = settings.to_dict().get('sms_templates', {})
            sms_templates.update(stored)

        tmpl = sms_templates.get(event_type, {})
        if not tmpl.get('enabled', False):
            return

        amount_str = f"{int(app_data.get('amount', 0)):,}"
        message = tmpl['message'].format(
            user_name=app_data.get('user_name', ''),
            form_name=app_data.get('form_name', ''),
            amount=amount_str,
            user_dept=app_data.get('user_dept', ''),
            reject_reason=reject_reason
        )

        phone = app_data.get('user_phone', '')
        if phone:
            send_alimtalk(phone, message)

        # Admin notification
        if event_type == 'submit':
            admin_tmpl = sms_templates.get('admin_new', {})
            if admin_tmpl.get('enabled', False):
                admin_phone = os.environ.get('ADMIN_PHONE', '')
                if admin_phone:
                    admin_msg = admin_tmpl['message'].format(
                        user_name=app_data.get('user_name', ''),
                        user_dept=app_data.get('user_dept', ''),
                        form_name=app_data.get('form_name', ''),
                        amount=amount_str
                    )
                    send_sms(admin_phone, admin_msg)
    except Exception as e:
        print(f"[Notification Error] {e}")


def get_form_types(active_only=True):
    query = db.collection('form_types')
    if active_only:
        query = query.where('is_active', '==', True)
    docs = query.stream()
    forms = [d.to_dict() for d in docs]
    forms.sort(key=lambda x: x.get('order', 99))
    return forms


def get_user(user_id):
    doc = db.collection('users').document(user_id).get()
    return doc.to_dict() if doc.exists else None


def fmt_amount(val):
    try:
        return f"{int(val):,}"
    except:
        return '0'


# ─── Middleware ───────────────────────────────────────────────────────────────
PUBLIC_ENDPOINTS = {'login', 'login_process', 'signup', 'signup_process', 'static', 'index'}

@app.before_request
def enforce_login():
    if request.endpoint in PUBLIC_ENDPOINTS:
        return
    if not session.get('user_id'):
        return redirect(url_for('login'))

@app.after_request
def add_headers(response):
    if 'text/html' in response.content_type:
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


# ══════════════════════════════════════════════════════════════════════════════
# AUTH ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    if session.get('user_id'):
        return redirect(url_for('main_page'))
    return redirect(url_for('login'))


@app.route('/login')
def login():
    if session.get('user_id'):
        return redirect(url_for('main_page'))
    return render_template('login.html')


@app.route('/login_process', methods=['POST'])
def login_process():
    user_id = request.form.get('user_id', '').strip()
    password = request.form.get('password', '').strip()
    user = get_user(user_id)
    if not user:
        return render_template('login.html', error='사번 또는 비밀번호가 올바르지 않습니다.')
    if not user.get('is_active', True):
        return render_template('login.html', error='비활성화된 계정입니다. 관리자에게 문의하세요.')
    if user.get('비밀번호') != password:
        return render_template('login.html', error='사번 또는 비밀번호가 올바르지 않습니다.')
    session.permanent = True
    session.update({
        'user_id': user_id,
        'user_name': user.get('이름', ''),
        'user_dept': user.get('부서', ''),
        'user_rank': user.get('직급', ''),
        'user_email': user.get('이메일', ''),
        'user_phone': user.get('전화번호', ''),
        'join_date': user.get('입사일', ''),
        'is_admin': user.get('is_admin', False),
    })
    return redirect(url_for('main_page'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/signup')
def signup():
    return render_template('signup.html')


@app.route('/signup_process', methods=['POST'])
def signup_process():
    user_id = request.form.get('user_id', '').strip()
    if not user_id:
        return render_template('signup.html', error='사번을 입력하세요.')
    if get_user(user_id):
        return render_template('signup.html', error='이미 등록된 사번입니다.')
    user_data = {
        '사번': user_id,
        '비밀번호': request.form.get('password', ''),
        '이름': request.form.get('name', ''),
        '직급': request.form.get('rank', ''),
        '부서': request.form.get('dept', ''),
        '이메일': request.form.get('email', ''),
        '전화번호': request.form.get('phone', ''),
        '입사일': request.form.get('join_date', ''),
        'is_active': True,
        'is_admin': False,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    db.collection('users').document(user_id).set(user_data)
    return redirect(url_for('login'))


# ══════════════════════════════════════════════════════════════════════════════
# MAIN DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/main')
def main_page():
    user_id = session['user_id']
    year = datetime.now().year
    form_types = get_form_types(active_only=True)

    # Get usage per form type for current year
    apps = db.collection('applications') \
        .where('user_id', '==', user_id) \
        .where('status', '==', '승인') \
        .stream()

    usage = {}
    for a in apps:
        d = a.to_dict()
        app_year = d.get('apply_date', '')[:4]
        if app_year == str(year):
            ft_id = d.get('form_type_id', '')
            usage[ft_id] = usage.get(ft_id, 0) + int(d.get('amount', 0))

    # Get site notice
    settings_doc = db.collection('settings').document('site_content').get()
    notice = ''
    if settings_doc.exists:
        notice = settings_doc.to_dict().get('notice', '')

    return render_template('main.html',
        form_types=form_types,
        usage=usage,
        notice=notice,
        year=year,
        fmt_amount=fmt_amount,
    )


# ══════════════════════════════════════════════════════════════════════════════
# APPLY & SUBMIT
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/apply/<form_key>')
def apply_page(form_key):
    doc = db.collection('form_types').document(form_key).get()
    if not doc.exists:
        return redirect(url_for('main_page'))
    form_type = doc.to_dict()
    if not form_type.get('is_active', True):
        return redirect(url_for('main_page'))
    return render_template('apply.html', form_type=form_type, banks=BANKS)


@app.route('/submit', methods=['GET', 'POST'])
def handle_submit():
    if request.method == 'GET':
        return 'OK', 200

    user_id = session['user_id']
    form_type_id = request.form.get('_form_type_id', '')
    edit_app_id = request.form.get('_edit_app_id', '')

    doc = db.collection('form_types').document(form_type_id).get()
    if not doc.exists:
        return jsonify({'error': '폼을 찾을 수 없습니다'}), 404
    form_type = doc.to_dict()

    # Duplicate check (5 min window, new applications only)
    if not edit_app_id:
        five_min_ago = (datetime.now() - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
        recent = db.collection('applications') \
            .where('user_id', '==', user_id) \
            .where('form_type_id', '==', form_type_id) \
            .where('apply_date', '>=', five_min_ago).limit(1).stream()
        if any(True for _ in recent):
            return render_template('apply.html', form_type=form_type, banks=BANKS,
                                   error='잠시 후 다시 시도해주세요 (중복 방지).')

    # Process fields
    raw_data = {}
    amount = 0
    account = ''
    attachment_url = ''

    for field in form_type.get('fields', []):
        fname = field['name']
        ftype = field['type']

        if ftype == 'file':
            f = request.files.get(fname)
            if f and f.filename:
                url = upload_file_to_storage(f, user_id, session.get('user_name',''), form_type_id)
                raw_data[fname] = url or ''
                if fname == 'attachment':
                    attachment_url = raw_data[fname]
            else:
                raw_data[fname] = ''
        elif ftype == 'amount':
            val = request.form.get(fname, '0').replace(',', '').strip()
            amount = int(val) if val.isdigit() else 0
            raw_data[fname] = amount
        elif ftype == 'account':
            bank = request.form.get(f'{fname}_bank', '')
            num = request.form.get(f'{fname}_num', '')
            holder = request.form.get(f'{fname}_holder', '')
            account = f"{bank}/{num}/{holder}"
            raw_data[fname] = account
        else:
            raw_data[fname] = request.form.get(fname, '')

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if edit_app_id:
        # Edit existing application
        db.collection('applications').document(edit_app_id).update({
            'amount': amount,
            'account': account,
            'attachment': attachment_url,
            'status': '대기',
            'edit_date': now_str,
            'raw_data': raw_data,
        })
        return redirect(url_for('my_status'))

    # New application
    app_id = f"{form_type_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
    app_data = {
        'app_id': app_id,
        'form_type_id': form_type_id,
        'form_name': form_type.get('name', ''),
        'user_id': user_id,
        'user_name': session.get('user_name', ''),
        'user_dept': session.get('user_dept', ''),
        'user_rank': session.get('user_rank', ''),
        'user_phone': session.get('user_phone', ''),
        'join_date': session.get('join_date', ''),
        'amount': amount,
        'account': account,
        'attachment': attachment_url,
        'status': '대기',
        'apply_date': now_str,
        'raw_data': raw_data,
    }
    db.collection('applications').document(app_id).set(app_data)
    send_notification('submit', app_data)
    return redirect(url_for('my_status'))


@app.route('/my_status')
def my_status():
    user_id = session['user_id']
    now_year = datetime.now().year
    selected_year = int(request.args.get('year', now_year))
    years = list(range(now_year, now_year - 5, -1))

    apps = db.collection('applications') \
        .where('user_id', '==', user_id) \
        .order_by('apply_date', direction=firestore.Query.DESCENDING) \
        .stream()

    all_apps = [a.to_dict() for a in apps]
    filtered = [a for a in all_apps if a.get('apply_date', '')[:4] == str(selected_year)]

    return render_template('my_status.html',
        applications=filtered,
        years=years,
        selected_year=selected_year,
        fmt_amount=fmt_amount,
    )


@app.route('/cancel_apply', methods=['POST'])
def cancel_apply():
    app_id = request.form.get('app_id', '')
    user_id = session['user_id']
    doc = db.collection('applications').document(app_id).get()
    if doc.exists and doc.to_dict().get('user_id') == user_id:
        status = doc.to_dict().get('status', '')
        if status == '대기':
            db.collection('applications').document(app_id).update({'status': '취소'})
        elif status in ('반려', '취소') and session.get('is_admin'):
            db.collection('applications').document(app_id).delete()
    return redirect(url_for('my_status'))


@app.route('/apply_edit/<app_id>')
def apply_edit(app_id):
    user_id = session['user_id']
    doc = db.collection('applications').document(app_id).get()
    if not doc.exists:
        return redirect(url_for('my_status'))
    app_data = doc.to_dict()
    if app_data.get('user_id') != user_id or app_data.get('status') not in ('반려',):
        return redirect(url_for('my_status'))

    form_doc = db.collection('form_types').document(app_data['form_type_id']).get()
    if not form_doc.exists:
        return redirect(url_for('my_status'))

    form_type = form_doc.to_dict()
    return render_template('apply.html',
        form_type=form_type,
        banks=BANKS,
        edit_app=app_data,
    )


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

def require_admin(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('main_page'))
        return f(*args, **kwargs)
    return decorated


@app.route('/admin')
@require_admin
def admin_dashboard():
    now_year = datetime.now().year
    selected_year = int(request.args.get('year', now_year))
    status_filter = request.args.get('status', '')
    form_filter = request.args.get('form', '')
    years = list(range(now_year, now_year - 5, -1))

    query = db.collection('applications').order_by('apply_date', direction=firestore.Query.DESCENDING)
    apps = [a.to_dict() for a in query.stream()]

    filtered = [a for a in apps if a.get('apply_date', '')[:4] == str(selected_year)]
    if status_filter:
        filtered = [a for a in filtered if a.get('status') == status_filter]
    if form_filter:
        filtered = [a for a in filtered if a.get('form_type_id') == form_filter]

    stats = {
        'total': len(filtered),
        'pending': sum(1 for a in filtered if a.get('status') == '대기'),
        'approved': sum(1 for a in filtered if a.get('status') == '승인'),
        'rejected': sum(1 for a in filtered if a.get('status') == '반려'),
        'total_amount': sum(int(a.get('amount', 0)) for a in filtered if a.get('status') == '승인'),
    }

    form_types = get_form_types(active_only=False)

    # Users
    users = [u.to_dict() for u in db.collection('users').stream()]

    # Settings
    settings_doc = db.collection('settings').document('site_content').get()
    settings = settings_doc.to_dict() if settings_doc.exists else {}
    sms_templates = {**DEFAULT_SMS_TEMPLATES, **settings.get('sms_templates', {})}

    return render_template('admin_dashboard.html',
        applications=filtered,
        stats=stats,
        form_types=form_types,
        users=users,
        sms_templates=sms_templates,
        years=years,
        selected_year=selected_year,
        status_filter=status_filter,
        form_filter=form_filter,
        notice=settings.get('notice', ''),
        fmt_amount=fmt_amount,
    )


@app.route('/admin_process', methods=['POST'])
@require_admin
def admin_process():
    app_id = request.form.get('app_id', '')
    action = request.form.get('action', '')
    reject_reason = request.form.get('reject_reason', '')

    doc = db.collection('applications').document(app_id).get()
    if not doc.exists:
        return redirect(url_for('admin_dashboard'))

    app_data = doc.to_dict()
    updates = {'processed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
               'processed_by': session['user_id']}

    if action == 'approve':
        updates['status'] = '승인'
        db.collection('applications').document(app_id).update(updates)
        send_notification('approve', app_data)
    elif action == 'reject':
        updates['status'] = '반려'
        updates['reject_reason'] = reject_reason
        db.collection('applications').document(app_id).update(updates)
        send_notification('reject', {**app_data, 'reject_reason': reject_reason}, reject_reason)

    return redirect(url_for('admin_dashboard'))


@app.route('/download_excel')
@require_admin
def download_excel():
    year = request.args.get('year', datetime.now().year)
    apps = db.collection('applications').order_by('apply_date', direction=firestore.Query.DESCENDING).stream()
    rows = []
    for a in apps:
        d = a.to_dict()
        if str(d.get('apply_date', ''))[:4] == str(year):
            rows.append({
                '신청일': d.get('apply_date', ''),
                '신청항목': d.get('form_name', ''),
                '사번': d.get('user_id', ''),
                '이름': d.get('user_name', ''),
                '부서': d.get('user_dept', ''),
                '직급': d.get('user_rank', ''),
                '신청금액': d.get('amount', 0),
                '상태': d.get('status', ''),
                '반려의견': d.get('reject_reason', ''),
                '처리일': d.get('processed_at', ''),
            })
    df = pd.DataFrame(rows)
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=f'{year}년 신청내역')
    buf.seek(0)
    return send_file(buf, download_name=f'lofa_복지기금_{year}.xlsx',
                     as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN - FORM TYPE MANAGEMENT (신청서 관리)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/admin/forms')
@require_admin
def admin_forms():
    forms = get_form_types(active_only=False)
    return render_template('admin/form_list.html', forms=forms)


@app.route('/admin/forms/new', methods=['GET', 'POST'])
@require_admin
def admin_form_new():
    if request.method == 'GET':
        return render_template('admin/form_editor.html', form_type=None)

    form_id = request.form.get('form_id', '').strip().lower()
    form_id = re.sub(r'[^a-z0-9_]', '_', form_id)
    if not form_id:
        return render_template('admin/form_editor.html', form_type=None, error='영문 ID를 입력하세요.')

    if db.collection('form_types').document(form_id).get().exists:
        return render_template('admin/form_editor.html', form_type=None, error='이미 사용 중인 ID입니다.')

    # Get max order
    existing = get_form_types(active_only=False)
    max_order = max((f.get('order', 0) for f in existing), default=0) + 1

    form_type = {
        'id': form_id,
        'name': request.form.get('name', ''),
        'icon': request.form.get('icon', '📋'),
        'description': request.form.get('description', ''),
        'color': request.form.get('color', '#0071e3'),
        'annual_limit': int(request.form.get('annual_limit', 0) or 0),
        'is_active': True,
        'order': max_order,
        'fields': [],
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    db.collection('form_types').document(form_id).set(form_type)
    return redirect(url_for('admin_form_edit', form_id=form_id))


@app.route('/admin/forms/<form_id>/edit', methods=['GET', 'POST'])
@require_admin
def admin_form_edit(form_id):
    doc = db.collection('form_types').document(form_id).get()
    if not doc.exists:
        return redirect(url_for('admin_forms'))
    form_type = doc.to_dict()

    if request.method == 'POST':
        updates = {
            'name': request.form.get('name', form_type['name']),
            'icon': request.form.get('icon', form_type.get('icon', '📋')),
            'description': request.form.get('description', ''),
            'color': request.form.get('color', '#0071e3'),
            'annual_limit': int(request.form.get('annual_limit', 0) or 0),
            'is_active': request.form.get('is_active') == 'on',
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        db.collection('form_types').document(form_id).update(updates)
        form_type.update(updates)
        return render_template('admin/form_editor.html', form_type=form_type, success='저장되었습니다.')

    return render_template('admin/form_editor.html', form_type=form_type)


@app.route('/admin/forms/<form_id>/toggle', methods=['POST'])
@require_admin
def admin_form_toggle(form_id):
    doc = db.collection('form_types').document(form_id).get()
    if doc.exists:
        current = doc.to_dict().get('is_active', True)
        db.collection('form_types').document(form_id).update({'is_active': not current})
    return redirect(url_for('admin_forms'))


@app.route('/admin/forms/<form_id>/delete', methods=['POST'])
@require_admin
def admin_form_delete(form_id):
    # Check if there are applications using this form
    apps = db.collection('applications').where('form_type_id', '==', form_id).limit(1).stream()
    if any(True for _ in apps):
        forms = get_form_types(active_only=False)
        return render_template('admin/form_list.html', forms=forms,
                               error=f'"{form_id}" 항목에 신청 내역이 있어 삭제할 수 없습니다. 비활성화를 이용하세요.')
    db.collection('form_types').document(form_id).delete()
    return redirect(url_for('admin_forms'))


@app.route('/admin/forms/<form_id>/fields/add', methods=['POST'])
@require_admin
def admin_field_add(form_id):
    doc = db.collection('form_types').document(form_id).get()
    if not doc.exists:
        return redirect(url_for('admin_forms'))
    form_type = doc.to_dict()
    fields = form_type.get('fields', [])

    new_field = {
        'id': f'f{uuid.uuid4().hex[:8]}',
        'type': request.form.get('field_type', 'text'),
        'label': request.form.get('label', '새 항목'),
        'name': request.form.get('name', f'field_{len(fields)+1}'),
        'required': request.form.get('required') == 'on',
        'placeholder': request.form.get('placeholder', ''),
        'help_text': request.form.get('help_text', ''),
        'options': [o.strip() for o in request.form.get('options', '').split('\n') if o.strip()],
        'order': len(fields) + 1,
    }
    fields.append(new_field)
    db.collection('form_types').document(form_id).update({'fields': fields})
    return redirect(url_for('admin_form_edit', form_id=form_id))


@app.route('/admin/forms/<form_id>/fields/<field_id>/update', methods=['POST'])
@require_admin
def admin_field_update(form_id, field_id):
    doc = db.collection('form_types').document(form_id).get()
    if not doc.exists:
        return redirect(url_for('admin_forms'))
    form_type = doc.to_dict()
    fields = form_type.get('fields', [])

    for f in fields:
        if f['id'] == field_id:
            f['label'] = request.form.get('label', f['label'])
            f['name'] = request.form.get('name', f['name'])
            f['type'] = request.form.get('field_type', f['type'])
            f['required'] = request.form.get('required') == 'on'
            f['placeholder'] = request.form.get('placeholder', '')
            f['help_text'] = request.form.get('help_text', '')
            f['options'] = [o.strip() for o in request.form.get('options', '').split('\n') if o.strip()]
            break

    db.collection('form_types').document(form_id).update({'fields': fields})
    return redirect(url_for('admin_form_edit', form_id=form_id))


@app.route('/admin/forms/<form_id>/fields/<field_id>/delete', methods=['POST'])
@require_admin
def admin_field_delete(form_id, field_id):
    doc = db.collection('form_types').document(form_id).get()
    if not doc.exists:
        return redirect(url_for('admin_forms'))
    form_type = doc.to_dict()
    fields = [f for f in form_type.get('fields', []) if f['id'] != field_id]
    db.collection('form_types').document(form_id).update({'fields': fields})
    return redirect(url_for('admin_form_edit', form_id=form_id))


@app.route('/admin/forms/<form_id>/fields/reorder', methods=['POST'])
@require_admin
def admin_field_reorder(form_id):
    order = request.json.get('order', [])  # list of field ids
    doc = db.collection('form_types').document(form_id).get()
    if not doc.exists:
        return jsonify({'ok': False})
    form_type = doc.to_dict()
    fields = form_type.get('fields', [])
    field_map = {f['id']: f for f in fields}
    reordered = [field_map[fid] for fid in order if fid in field_map]
    db.collection('form_types').document(form_id).update({'fields': reordered})
    return jsonify({'ok': True})


@app.route('/admin/forms/reorder', methods=['POST'])
@require_admin
def admin_forms_reorder():
    order = request.json.get('order', [])
    for i, form_id in enumerate(order):
        db.collection('form_types').document(form_id).update({'order': i + 1})
    return jsonify({'ok': True})


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN - USER MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/admin/user/update', methods=['POST'])
@require_admin
def admin_user_update():
    user_id = request.form.get('user_id', '')
    updates = {
        '이름': request.form.get('name', ''),
        '부서': request.form.get('dept', ''),
        '직급': request.form.get('rank', ''),
        '이메일': request.form.get('email', ''),
        '전화번호': request.form.get('phone', ''),
        'is_admin': request.form.get('is_admin') == 'on',
    }
    db.collection('users').document(user_id).update(updates)
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/user/deactivate', methods=['POST'])
@require_admin
def admin_user_deactivate():
    user_id = request.form.get('user_id', '')
    db.collection('users').document(user_id).update({
        'is_active': False,
        '퇴사일': datetime.now().strftime('%Y-%m-%d'),
    })
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/user/restore', methods=['POST'])
@require_admin
def admin_user_restore():
    user_id = request.form.get('user_id', '')
    db.collection('users').document(user_id).update({'is_active': True, '퇴사일': ''})
    return redirect(url_for('admin_dashboard'))


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN - SETTINGS & SMS
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/admin/settings/update', methods=['POST'])
@require_admin
def admin_settings_update():
    notice = request.form.get('notice', '')
    db.collection('settings').document('site_content').set({
        'notice': notice,
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }, merge=True)
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/sms/update', methods=['POST'])
@require_admin
def admin_sms_update():
    """Update SMS template settings"""
    sms_templates = {}
    for key in DEFAULT_SMS_TEMPLATES:
        sms_templates[key] = {
            'name': DEFAULT_SMS_TEMPLATES[key]['name'],
            'message': request.form.get(f'sms_{key}_message', DEFAULT_SMS_TEMPLATES[key]['message']),
            'enabled': request.form.get(f'sms_{key}_enabled') == 'on',
        }
    db.collection('settings').document('site_content').set({
        'sms_templates': sms_templates,
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }, merge=True)
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/sms/test', methods=['POST'])
@require_admin
def admin_sms_test():
    """Send a test SMS"""
    phone = request.form.get('phone', '')
    message = request.form.get('message', '[LOFA복지기금] 테스트 메시지입니다.')
    if phone:
        result = send_sms(phone, message)
        return jsonify({'ok': result, 'message': '발송 완료' if result else 'API 설정을 확인하세요'})
    return jsonify({'ok': False, 'message': '전화번호를 입력하세요'})


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN - INIT DEFAULT DATA
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/admin/init-defaults', methods=['POST'])
@require_admin
def admin_init_defaults():
    """Seed default form types into Firestore"""
    for ft in DEFAULT_FORM_TYPES:
        doc = db.collection('form_types').document(ft['id'])
        if not doc.get().exists:
            doc.set(ft)

    # Init SMS settings
    settings_doc = db.collection('settings').document('site_content')
    if not settings_doc.get().exists:
        settings_doc.set({
            'notice': '',
            'sms_templates': DEFAULT_SMS_TEMPLATES,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        })
    return jsonify({'ok': True, 'message': f'{len(DEFAULT_FORM_TYPES)}개 신청서 기본값이 초기화되었습니다.'})


# ══════════════════════════════════════════════════════════════════════════════
# API
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/users')
@require_admin
def api_users():
    users = [u.to_dict() for u in db.collection('users').stream()]
    return jsonify(users)


@app.route('/api/form_types')
def api_form_types():
    forms = get_form_types(active_only=True)
    return jsonify(forms)


if __name__ == '__main__':
    app.run(debug=True, port=5001)
