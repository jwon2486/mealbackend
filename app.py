# Flask: 웹 애플리케이션을 만들기 위한 마이크로 프레임워크
# request: HTTP 요청 데이터 (GET, POST 등)를 다루기 위해 사용
# jsonify: 파이썬 데이터를 JSON 형식으로 반환하기 위해 사용
# CORS: 다른 도메인/포트에서의 요청을 허용 (프론트 연동 시 필수)
# sqlite3: 가볍고 파일 기반의 내장형 데이터베이스

import sys
print("✅ 현재 실행 중인 Python:", sys.executable)

from flask import Flask, request, jsonify, send_file, session
from flask_cors import CORS
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
from collections import defaultdict
from io import BytesIO
import calendar
import sqlite3
import pandas as pd
import os
import re
import shutil  # ✅ DB 파일 복사용
import xmltodict
import requests
import ssl
from requests.adapters import HTTPAdapter
import base64
import threading
import time
import json, uuid
from flask import send_from_directory
from werkzeug.utils import secure_filename


KST = timezone(timedelta(hours=9))
def now_kst_str():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "db.sqlite")
DB_PATH = "db.sqlite"
MENU_UPLOAD_DIR = os.path.join(BASE_DIR, "uploads", "menu")
MENU_MANIFEST_PATH = os.path.join(MENU_UPLOAD_DIR, "menu_board.json")
MENU_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MENU_MAX_MB = 20  # 필요하면 조정
os.makedirs(MENU_UPLOAD_DIR, exist_ok=True)

# ===== GitHub 백업 설정 =====
GITHUB_REPO   = "jwon2486/MealDB-Backup"   # 새로 만든 백업 레포
GITHUB_BRANCH = "main"                     # 기본 브랜치
GITHUB_PATH   = "db.sqlite"                # 레포 안에서 파일 이름/경로
GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN")
GITHUB_API    = "https://api.github.com"



def get_week_range_kst():
    now = datetime.now(KST).date()
    monday = now - timedelta(days=now.weekday())
    friday = monday + timedelta(days=4)
    return monday, friday


def create_db_snapshot():
    """
    실행 중인 db.sqlite를 안전하게 복사해서 스냅샷 파일 경로를 반환
    """
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(BASE_DIR, "db_backups")
        os.makedirs(backup_dir, exist_ok=True)

        snapshot_path = os.path.join(backup_dir, f"db_{ts}.sqlite")
        shutil.copy2(DATABASE, snapshot_path)   # 파일 직접 복사

        return snapshot_path
    except Exception as e:
        print("❌ DB 스냅샷 생성 실패:", e)
        return None


def upload_file_to_github(file_path):
    
    if not GITHUB_TOKEN:
        print("⚠️ GITHUB_TOKEN 환경변수가 설정되지 않았습니다. 백업 건너뜀.")
        return

    # 파일 base64 인코딩
    with open(file_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode("utf-8")

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"

    # 기존 sha 조회
    sha = None
    get_resp = requests.get(url, headers=headers, params={"ref": GITHUB_BRANCH})
    if get_resp.status_code == 200:
        sha = get_resp.json().get("sha")

    # 🔥 KST 날짜 적용
    now_kst_iso = datetime.now(KST).isoformat()
    now_kst_str = datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')

    payload = {
        "message": f"Automated db backup - {now_kst_str} KST",
        "content": content_b64,
        "branch": GITHUB_BRANCH,

        # 🔥 GitHub 커밋 타임존을 KST로 고정
        "committer": {
            "name": "Backup Bot",
            "email": "backup@example.com",
            "date": datetime.now(KST).isoformat()
        }
    }

    if sha:
        payload["sha"] = sha

    put_resp = requests.put(url, headers=headers, json=payload)

    if 200 <= put_resp.status_code < 300:
        print(f"✅ GitHub DB 백업 성공: {file_path}")
    else:
        print("❌ GitHub DB 백업 실패:", put_resp.status_code, put_resp.text)


def backup_db_to_github():
    """
    스냅샷 생성 후 GitHub 업로드까지 한 번에 수행
    """
    snapshot = create_db_snapshot()
    if snapshot:
        upload_file_to_github(snapshot)


def backup_worker(interval_seconds=3600):
    """
    interval_seconds 간격으로 DB를 GitHub에 백업하는 백그라운드 작업
    """
    while True:
        try:
            print("⏱ DB 자동 백업 실행...")
            backup_db_to_github()
        except Exception as e:
            print("❌ 백업 스레드 오류:", e)
        time.sleep(interval_seconds)

KST = timezone(timedelta(hours=9))

def backup_worker_midnight():
    """
    매일 오전8시(한국 시간 기준)에 DB 백업을 실행하는 워커
    """
    while True:
        # 현재 KST 시간
        now_kst = datetime.now(KST)

        # 다음 오전8시(KST) 계산
        next_run_kst = (now_kst + timedelta(days=1)).replace(
            hour=8, minute=0, second=0, microsecond=0
        )
        wait_seconds = (next_run_kst - now_kst).total_seconds()

        print(f"🕛 [백업] 다음 실행 예정(KST): {next_run_kst} (대기 {int(wait_seconds)}초)")
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        # 8시에 백업 실행
        try:
            print("⏱ [백업]8시 DB 백업 실행(KST) ...")
            backup_db_to_github()
        except Exception as e:
            print("❌ [백업] 8시 백업 중 오류:", e)

def load_menu_manifest():
    if not os.path.exists(MENU_MANIFEST_PATH):
        return []

    try:
        with open(MENU_MANIFEST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        print("❌ menu manifest 읽기 실패:", e)
        return []


def save_menu_manifest(items):
    try:
        with open(MENU_MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print("❌ menu manifest 저장 실패:", e)
        return False


def allowed_menu_file(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in MENU_ALLOWED_EXT

# Flask 앱 생성
app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY")


# 모든 도메인에서 CORS 허용 (프론트엔드가 localhost:3000 등에 있어도 접근 가능)
CORS(app) #프론트와 연동

# ---- 여기 추가 ----
# 앱 프로세스가 시작될 때 6시간마다 백업하는 워커 스레드 시작
backup_thread = threading.Thread(
    target=backup_worker,
    args=(12 * 60 * 60,),   # 6시간 = 21600초 (원하면 24시간 등으로 조절)
    daemon=True
)
backup_thread.start()
# -------------------

# ✅ SQLite 데이터베이스 연결 함수
def get_db_connection():
     # db.sqlite 파일을 연결. 없으면 새로 생성됨.
     conn = sqlite3.connect("db.sqlite")
     # DB에서 가져온 row 데이터를 딕셔너리처럼 사용할 수 있도록 설정
     conn.row_factory = sqlite3.Row
     return conn

# ✅ 앱 시작 시 테이블이 없으면 생성하는 초기화 함수
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 공휴일 테이블 생성
    conn.execute("""
        CREATE TABLE IF NOT EXISTS holidays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,  -- 고유 ID
            date TEXT NOT NULL UNIQUE,             -- YYYY-MM-DD 형식의 날짜 (중복 금지)
            description TEXT                       -- 공휴일 이름 (예: 설날)
        )
    """)

    # 식수 신청 테이블 생성
    conn.execute("""
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,  -- 고유 ID
            user_id TEXT NOT NULL,                 -- 사번
            date TEXT NOT NULL,                    -- 식사 신청 날짜
            breakfast INTEGER DEFAULT 0,           -- 조식 신청 여부 (1/0)
            lunch INTEGER DEFAULT 0,               -- 중식 신청 여부 (1/0)
            dinner INTEGER DEFAULT 0,              -- 석식 신청 여부 (1/0)
            FOREIGN KEY (user_id) REFERENCES employees(id), -- 
            UNIQUE(user_id, date)                  -- 동일한 사번 + 날짜 중복 방지
        )
    """)
    
    # 직원 정보 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id TEXT PRIMARY KEY,       -- 사번
            name TEXT NOT NULL,        -- 이름
            type TEXT DEFAULT '직영',    -- 직영/협력사/방문자
            dept TEXT NOT NULL,         -- 부서
            rank TEXT DEFAULT '',      -- 직급
            region TEXT DEFAULT '',      -- 지역
            level INTEGER DEFAULT 1,      -- 권한설정
            password TEXT DEFAULT ''  -- 향후 비밀번호용 (현재는 미사용) 권한 필드는 나중에 추가 가능
        )
    """)

    # 신청 변경 로그 테이블 생성 (신규)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS meal_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_id TEXT NOT NULL,
            date TEXT NOT NULL,
            meal_type TEXT NOT NULL,  -- breakfast, lunch, dinner
            before_status INTEGER,
            after_status INTEGER,
            changed_at TEXT DEFAULT (datetime('now', 'localtime'))  -- 변경 시간 기록
         )
    """)

    # # ✅ 방문자 식수 테이블
# ✅ [1] visitors 테이블 생성 (app 시작 시 init_db에 추가)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS visitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            applicant_id TEXT NOT NULL,
            applicant_name TEXT NOT NULL,
            date TEXT NOT NULL,
            breakfast INTEGER DEFAULT 0,
            lunch INTEGER DEFAULT 0,
            dinner INTEGER DEFAULT 0,
            reason TEXT NOT NULL,
            last_modified TEXT DEFAULT CURRENT_TIMESTAMP,
            type TEXT NOT NULL,  -- 방문자 / 협력사
            UNIQUE(applicant_id, date, type)  -- 동일 신청자+날짜+타입 중복 방지
            )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS visitor_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            applicant_id TEXT,
            applicant_name TEXT,
            date TEXT,
            reason TEXT,
            type TEXT,  -- 방문자 또는 협력사
            before_breakfast INTEGER,
            before_lunch INTEGER,
            before_dinner INTEGER,
            breakfast INTEGER,
            lunch INTEGER,
            dinner INTEGER,
            updated_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', '+9 hours')
)
        );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS selfcheck (
        user_id TEXT NOT NULL,
        date TEXT NOT NULL,
        checked INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, date)
    )
    """)

    conn.commit()
    conn.close()

def is_expired(meal_type, date_str):
    from datetime import datetime
    meal_date = datetime.strptime(date_str, "%Y-%m-%d")
    now = datetime.now()

    if meal_type == '점심':
        deadline = meal_date.replace(hour=9, minute=0)
    elif meal_type == '저녁':
        deadline = meal_date.replace(hour=14, minute=0)
    else:
        return True

    return now > deadline

def is_this_week(date_str):
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = datetime.now(KST).date()
        monday = today - timedelta(days=today.weekday())  # 이번 주 월요일
        friday = monday + timedelta(days=4)               # 이번 주 금요일
        return monday <= target <= friday
    except:
        return False

# 현재 서버에 반영된 최신DB를 받을수있게하는 API
@app.route('/admin/db/download', methods=['GET'])
def download_database():
    db_path = os.path.join(os.getcwd(), 'db.sqlite')
    if os.path.exists(db_path):
        return send_file(db_path, as_attachment=True)
    else:
        return "DB 파일이 존재하지 않습니다.", 404


# 업로드된 식단표 이미지 제공
@app.route("/uploads/menu/<path:filename>", methods=["GET"])
def serve_menu_upload(filename):
    return send_from_directory(MENU_UPLOAD_DIR, filename)


# 식단표 게시판 목록 조회
@app.route("/api/menu-board", methods=["GET"])
def get_menu_board():
    items = load_menu_manifest()

    result = []
    for item in items:
        result.append({
            "id": item.get("id"),
            "title": item.get("title", ""),
            "filename": item.get("filename", ""),
            "image_url": f"/uploads/menu/{item.get('filename', '')}"
        })

    return jsonify(result), 200


# 식단표 업로드
@app.route("/api/menu-board/upload", methods=["POST"])
def upload_menu_board():
    try:
        if "image" not in request.files:
            return jsonify({"error": "이미지 파일이 없습니다."}), 400

        file = request.files["image"]
        title = request.form.get("title", "").strip()

        if not file or not file.filename:
            return jsonify({"error": "선택된 파일이 없습니다."}), 400

        if not allowed_menu_file(file.filename):
            return jsonify({"error": "jpg, jpeg, png, webp 파일만 업로드할 수 있습니다."}), 400

        file.seek(0, os.SEEK_END)
        size_bytes = file.tell()
        file.seek(0)

        if size_bytes > MENU_MAX_MB * 1024 * 1024:
            return jsonify({"error": f"최대 {MENU_MAX_MB}MB까지 업로드할 수 있습니다."}), 400

        ext = os.path.splitext(file.filename)[1].lower()
        item_id = uuid.uuid4().hex[:8]
        saved_name = f"menu_{item_id}{ext}"
        save_path = os.path.join(MENU_UPLOAD_DIR, saved_name)

        file.save(save_path)

        items = load_menu_manifest()
        new_item = {
            "id": item_id,
            "title": title if title else file.filename,
            "filename": saved_name
        }

        items.insert(0, new_item)

        if not save_menu_manifest(items):
            if os.path.exists(save_path):
                os.remove(save_path)
            return jsonify({"error": "목록 저장 실패"}), 500

        return jsonify({
            "message": "업로드 완료",
            "item": {
                "id": new_item["id"],
                "title": new_item["title"],
                "filename": new_item["filename"],
                "image_url": f"/uploads/menu/{new_item['filename']}"
            }
        }), 201

    except Exception as e:
        print("❌ 식단표 업로드 실패:", e)
        return jsonify({"error": "업로드 실패"}), 500


# 식단표 선택 삭제
@app.route("/api/menu-board/delete", methods=["POST"])
def delete_menu_board():
    try:
        data = request.get_json()
        ids = data.get("ids", [])

        if not isinstance(ids, list) or not ids:
            return jsonify({"error": "삭제할 항목이 없습니다."}), 400

        items = load_menu_manifest()
        remain = []
        deleted_count = 0

        for item in items:
            if item.get("id") in ids:
                filename = item.get("filename")
                if filename:
                    file_path = os.path.join(MENU_UPLOAD_DIR, filename)
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                        except Exception as e:
                            print("❌ 이미지 파일 삭제 실패:", e)
                deleted_count += 1
            else:
                remain.append(item)

        if not save_menu_manifest(remain):
            return jsonify({"error": "삭제 후 목록 저장 실패"}), 500

        return jsonify({
            "message": f"{deleted_count}건 삭제 완료"
        }), 200

    except Exception as e:
        print("❌ 식단표 삭제 실패:", e)
        return jsonify({"error": "삭제 실패"}), 500



# SSL 오류 우회를 위한 requests 어댑터 클래스
class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)

# 지정된 연도(year)에 대해 공휴일 API를 갱신해야 하는지 판단 (7일 경과 여부 확인)
def should_refresh_public_holidays(year):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS public_holiday_meta (year INTEGER PRIMARY KEY, last_checked TEXT)")
    cur.execute("SELECT last_checked FROM public_holiday_meta WHERE year = ?", (year,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return True
    last_checked = datetime.fromisoformat(row[0])
    return (datetime.now() - last_checked).days >= 7

# 해당 연도(year)의 공휴일 데이터를 최신으로 갱신한 시각을 기록
def update_last_checked(year):
    now_str = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO public_holiday_meta (year, last_checked)
        VALUES (?, ?)
        ON CONFLICT(year) DO UPDATE SET last_checked = excluded.last_checked
    """, (year, now_str))
    conn.commit()
    conn.close()

# 🔒 백업 워커 중복 실행 방지용
backup_thread_started = False
backup_thread_lock = threading.Lock()


def start_backup_thread():
    """
    앱이 시작될 때 자정 백업 워커를 한 번만 시작
    (Flask 3에서는 before_first_request 데코레이터가 제거되었으므로 직접 호출)
    """
    global backup_thread_started
    with backup_thread_lock:
        if not backup_thread_started:
            print("🚀 [백업] DB 백업 워커 시작")
            t = threading.Thread(target=backup_worker_midnight, daemon=True)
            t.start()
            backup_thread_started = True

# 모듈이 로드될 때 바로 한 번 실행
start_backup_thread()


# 📌 공공 API 또는 DB 캐시를 활용하여 지정 연도의 공휴일 목록을 반환하는 엔드포인트
@app.route("/api/public-holidays")
def get_public_holidays():
    year = request.args.get("year", default=datetime.now().year, type=int)
    force = request.args.get("force", "0") == "1"

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public_holidays (
            date TEXT PRIMARY KEY,
            description TEXT,
            source TEXT
        )
    """)
    conn.commit()

    if force or should_refresh_public_holidays(year):
    
        # ✅ force=1이면 해당 연도 데이터 + 캐시 기록 삭제 후 재수집
        if force:
            cur.execute("DELETE FROM public_holidays WHERE substr(date, 1, 4) = ?", (str(year),))
            cur.execute("DELETE FROM public_holiday_meta WHERE year = ?", (year,))
            conn.commit()

        session = requests.Session()
        session.mount("https://", SSLAdapter())

        for month in range(1, 13):
            url = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"

            service_key = os.environ.get(
                "PUBLIC_HOLIDAY_SERVICE_KEY",
                "f80f73afedb3a5bd607ad7cb5a9a65bfa7975f6fd3f47d3ac0a7cadfa9e80273"  # 임시 기본값
            ).strip()

            params = {
                "serviceKey": service_key,
                "solYear": str(year),
                "solMonth": f"{month:02d}",
                "numOfRows": "100",
                "pageNo": "1",
                "_type": "json",
            }

            try:
                response = session.get(url, params=params, timeout=10)

                # HTTP 오류면 원인 파악을 위해 본문 일부를 출력
                if response.status_code != 200:
                    print("❌ 공휴일 API HTTP 오류:", response.status_code)
                    print("❌ 응답 일부:", response.text[:300])
                    continue

                text = response.text.lstrip()

                # 1) JSON이면 JSON 파싱
                if text.startswith("{"):
                    data = response.json()
                    items = (
                        data.get("response", {})
                            .get("body", {})
                            .get("items", {})
                            .get("item", [])
                    )

                # 2) JSON이 아니면 XML 파싱 (기존 방식 유지)
                else:
                    data = xmltodict.parse(response.text)
                    items = (
                        data.get("response", {})
                            .get("body", {})
                            .get("items", {})
                            .get("item", [])
                    )

                if isinstance(items, dict):
                    items = [items]

                for item in items:
                    locdate = item.get("locdate")
                    desc = item.get("dateName")

                    if locdate and desc:
                        locdate_str = str(locdate)  # ✅ int/str 모두 안전 처리
                        formatted = f"{locdate_str[:4]}-{locdate_str[4:6]}-{locdate_str[6:8]}"
                        cur.execute(
                            "INSERT OR IGNORE INTO public_holidays (date, description, source) VALUES (?, ?, ?)",
                            (formatted, desc, "api")
                        )
            except Exception as e:
                print(f"❌ {month}월 공공 공휴일 호출 실패: {e}")

        conn.commit()
        update_last_checked(year)

    cur.execute("SELECT date, description, source FROM public_holidays WHERE substr(date, 1, 4) = ?", (str(year),))
    holidays = [{"date": row[0], "description": row[1], "source": row[2]} for row in cur.fetchall()]
    conn.close()

    return jsonify(holidays)









# ✅ [GET] /holidays?year=YYYY
# 특정 연도의 공휴일 리스트를 조회하는 API
@app.route("/holidays", methods=["GET"])
def get_holidays():
    year = request.args.get("year")  # URL 파라미터에서 연도 추출
    conn = get_db_connection()
    # 날짜 문자열에서 연도만 비교해서 필터링
    cursor = conn.execute("SELECT * FROM holidays WHERE strftime('%Y', date) = ?", (year,))
    holidays = cursor.fetchall()
    conn.close()
    # 조회된 공휴일 리스트를 JSON 형식으로 반환
    return jsonify([dict(h) for h in holidays])

# ✅ [POST] /holidays
# 새로운 공휴일을 등록하는 API
@app.route("/holidays", methods=["POST"])
def add_holiday():
    data = request.get_json()
    date = data.get("date")                              # YYYY-MM-DD
    desc = data.get("description", "공휴일")             # 설명이 없으면 "공휴일" 기본값

    if not date:
        return jsonify({"error": "날짜는 필수입니다."}), 400

    conn = get_db_connection()
    try:
        # 공휴일 DB에 등록
        conn.execute("INSERT INTO holidays (date, description) VALUES (?, ?)", (date, desc))
        conn.commit()
    except sqlite3.IntegrityError:
        # 이미 등록된 날짜일 경우 예외 처리
        return jsonify({"error": "이미 등록된 날짜입니다."}), 409
    finally:
        conn.close()

    return jsonify({"message": "공휴일이 추가되었습니다."}), 201

# ✅ [DELETE] /holidays?date=YYYY-MM-DD
# 특정 날짜의 공휴일을 삭제하는 API
@app.route("/holidays", methods=["DELETE"])
def delete_holiday():
    date = request.args.get("date")  # URL 파라미터에서 삭제할 날짜 추출
    if not date:
        return jsonify({"error": "삭제할 날짜가 필요합니다."}), 400

    conn = get_db_connection()
    conn.execute("DELETE FROM holidays WHERE date = ?", (date,))
    conn.commit()
    conn.close()

    return jsonify({"message": "삭제되었습니다."}), 200

# ✅ [POST] /meals
# 직원이 식사 신청을 했을 때 데이터를 저장하는 API (프론트에서 사용)
@app.route("/meals", methods=["POST"])
def save_meals():
    try:
        data = request.get_json()
        meals = data.get("meals", [])
        if not meals:
            return jsonify({"error": "신청 데이터 없음"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        for meal in meals:
            user_id = meal["user_id"]
            date = meal["date"]
            breakfast = int(meal.get("breakfast", 0))
            lunch = int(meal.get("lunch", 0))
            dinner = int(meal.get("dinner", 0))
            created_at_in = meal.get("created_at")

            # 🔁 기존 데이터 불러오기 (변경 비교용)
            cursor.execute("""
                SELECT breakfast, lunch, dinner
                FROM meals
                WHERE user_id = ? AND date = ?
            """, (user_id, date))
            existing = cursor.fetchone()

            # 이전 값이 없으면 전부 0으로 간주
            old_b, old_l, old_d = (0, 0, 0) if not existing else existing

            # ✅ 데이터 저장 (기존 데이터가 있든 없든 업데이트 또는 삽입)
            cursor.execute("""
                INSERT INTO meals (user_id, date, breakfast, lunch, dinner, created_at)
                VALUES (?, ?, ?, ?, ?, COALESCE(?, datetime('now','localtime')))
                ON CONFLICT(user_id, date) DO UPDATE SET
                    breakfast = excluded.breakfast,
                    lunch     = excluded.lunch,
                    dinner    = excluded.dinner,
                    created_at = COALESCE(meals.created_at, excluded.created_at)
            """, (user_id, date, breakfast, lunch, dinner, created_at_in))

            # 로그 기록 (금주 + 변경된 경우만)
            try:
                today = datetime.now(KST).date()
                mon = today - timedelta(days=today.weekday())
                fri = mon + timedelta(days=4)
                this_day = datetime.strptime(date, "%Y-%m-%d").date()

                if mon <= this_day <= fri:
                    meal_types = ['breakfast', 'lunch', 'dinner']
                    old_values = [old_b, old_l, old_d]
                    new_values = [breakfast, lunch, dinner]

                    for i in range(3):
                        if old_values[i] != new_values[i]:
                            cursor.execute("""
                                INSERT INTO meal_logs (emp_id, date, meal_type, before_status, after_status)
                                VALUES (?, ?, ?, ?, ?)
                            """, (user_id, date, meal_types[i], old_values[i], new_values[i]))
            except Exception as e:
                print(f"❌ 식수 저장 실패 (date={date}, user={user_id}):", e)

        conn.commit()
        conn.close()
        return jsonify({"message": "식수 저장 완료"}), 201

    except Exception as e:
        print("❌ 식수 저장 실패:", e)
        return jsonify({"error": str(e)}), 500
    

#관리자 페이지용 selfcheck 코드
@app.route('/admin/selfcheck', methods=['GET'])
def get_admin_selfchecks():
    start_date = request.args.get('start')
    end_date = request.args.get('end')

    if not start_date or not end_date:
        return jsonify({ "error": "start 와 end 파라미터가 필요합니다." }), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
    SELECT user_id, MAX(checked) AS checked
    FROM selfcheck
    WHERE date BETWEEN ? AND ?
    GROUP BY user_id
    """
    cursor.execute(query, (start_date, end_date))
    rows = cursor.fetchall()
    conn.close()

    result = { str(row[0]): int(row[1]) for row in rows }
    return jsonify(result)

#본인 확인 여부 서버에서 조회하는 GET코드
@app.route('/selfcheck', methods=['GET'])
def get_selfcheck():
    user_id = request.args.get('user_id')  # ✅ 세션 대신 URL 파라미터에서 받음
    date = request.args.get('date')

    if not user_id or not date:
        return jsonify({'error': 'Missing session or date'}), 400

    conn = get_db_connection()
    row = conn.execute(
        'SELECT checked, created_at FROM selfcheck WHERE user_id = ? AND date = ?',
        (user_id, date)
    ).fetchone()
    conn.close()

    return jsonify({
        'checked': row['checked'] if row else 0,
        'created_at': row['created_at'] if row else None
    })


#본인 확인 체크박스 상태를 서버로 전송하는 함수
@app.route('/selfcheck', methods=['POST'])
def post_selfcheck():
    user_id = request.json.get('user_id')
    date = request.json.get('date')
    checked = request.json.get('checked')
    created_at_in = request.json.get('created_at')
    force_update = request.json.get('force_update', False)  # 🔥 추가

    if not user_id or not date:
        return jsonify({'error': 'Missing session or date'}), 400

    conn = get_db_connection()
    existing = conn.execute(
        'SELECT 1 FROM selfcheck WHERE user_id = ? AND date = ?',
        (user_id, date)
    ).fetchone()

    if existing:
        if force_update:
            # ✅ 관리자 요청이면 created_at을 새로 덮어씀
            conn.execute("""
                UPDATE selfcheck
                   SET checked = ?, created_at = ?
                 WHERE user_id = ? AND date = ?
            """, (checked, created_at_in, user_id, date))
        else:
            # 일반 사용자 — 기존 created_at 유지
            conn.execute("""
                UPDATE selfcheck
                   SET checked = ?, created_at = COALESCE(created_at, ?)
                 WHERE user_id = ? AND date = ?
            """, (checked, created_at_in, user_id, date))
    else:
        conn.execute("""
            INSERT INTO selfcheck (user_id, date, checked, created_at)
            VALUES (?, ?, ?, COALESCE(?, datetime('now','localtime')))
        """, (user_id, date, checked, created_at_in))

    conn.commit()
    conn.close()

    return jsonify({'status': 'success'})


# ✅ [POST] /update_meals
# 관리자 페이지에서 전체 직원 식수 데이터를 수정/저장하는 API
@app.route("/update_meals", methods=["POST"])
def update_meals():
    data = request.get_json()
    meals = data.get("meals", [])  # 관리자 화면에서 보내는 meals 리스트

    conn = get_db_connection()
    cursor = conn.cursor()

    for meal in meals:
        user_id = meal.get("user_id")
        #name = meal.get("name")
        #dept = meal.get("dept")
        date = meal.get("date")
        breakfast = int(meal.get("breakfast", 0))
        lunch = int(meal.get("lunch", 0))
        dinner = int(meal.get("dinner", 0))

        # 기존 값이 있으면 업데이트, 없으면 새로 삽입
        cursor.execute("""
            INSERT INTO meals (user_id, date, breakfast, lunch, dinner)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET
                breakfast=excluded.breakfast,
                lunch=excluded.lunch,
                dinner=excluded.dinner
        """, (user_id, date, breakfast, lunch, dinner))

    conn.commit()
    conn.close()

    return jsonify({"message": "변경 사항이 저장되었습니다."}), 200

# ✅ [GET] /meals - 사용자 식수 신청 내역 조회
@app.route("/meals", methods=["GET"])
def get_user_meals():
    user_id = request.args.get("user_id")
    start_date = request.args.get("start")
    end_date = request.args.get("end")

    if not user_id or not start_date or not end_date:
        return jsonify({"error": "user_id, start, end는 필수입니다."}), 400

    conn = get_db_connection()
    cursor = conn.execute("""
        SELECT m.date, m.breakfast, m.lunch, m.dinner, m.created_at,   -- ← 추가
               e.name, e.dept, e.rank
        FROM meals m
        JOIN employees e ON m.user_id = e.id
        WHERE m.user_id = ? AND m.date BETWEEN ? AND ?
    """, (user_id, start_date, end_date))
    
    rows = cursor.fetchall()
    conn.close()

    # 결과를 날짜별로 정리
    result = {}
    for row in rows:
        result[row["date"]] = {
            "breakfast": row["breakfast"] == 1,
            "lunch"    : row["lunch"] == 1,
            "dinner"   : row["dinner"] == 1,
            "name"     : row["name"],
            "dept"     : row["dept"],
            "rank"     : row["rank"],
            "created_at": row["created_at"],   # ← 추가
        }
    return jsonify(result), 200

# ✅ [GET] /admin/meals
# 관리자: 전체 직원의 식수 신청 내역을 조회 (기간 기반)
@app.route("/admin/meals", methods=["GET"])
def admin_get_meals():
    start = request.args.get("start")
    end = request.args.get("end")
    mode = request.args.get("mode", "apply")  # ✅ mode 파라미터
    
    if not start or not end:
        return jsonify({"error": "start, end는 필수입니다."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if mode == "all":
            # ✅ 전체 직원 + 신청 내역 LEFT JOIN
            cursor.execute("""
                SELECT 
                    e.id AS user_id,
                    e.name,
                    e.dept,
                    e.region,
                    m.date,
                    IFNULL(m.breakfast, 0) AS breakfast,
                    IFNULL(m.lunch, 0) AS lunch,
                    IFNULL(m.dinner, 0) AS dinner
                FROM employees e
                LEFT JOIN meals m
                    ON e.id = m.user_id AND m.date BETWEEN ? AND ?
                WHERE e.type = '직영'
                ORDER BY e.dept ASC, e.name ASC, m.date ASC
            """, (start, end))
        else:
            # ✅ 신청한 직원만 조회 (기본 모드 + apply 모드)
            cursor.execute("""
                SELECT 
                    m.user_id,
                    e.name,
                    e.dept,
                    e.region,
                    m.date,
                    m.breakfast,
                    m.lunch,
                    m.dinner
                FROM meals m
                JOIN employees e ON m.user_id = e.id
                WHERE m.date BETWEEN ? AND ?
                AND e.type = '직영'
                ORDER BY e.dept ASC, e.name ASC, m.date ASC
            """, (start, end))

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            print("⚠️ admin_get_meals 결과 없음 (start, end, mode):", start, end, mode)
            return jsonify([]), 200

        result = []
        for row in rows:
            result.append({
                "user_id": row["user_id"],
                "name": row["name"],
                "dept": row["dept"],
                "date": row["date"],
                "region": row["region"],
                "breakfast": row["breakfast"],
                "lunch": row["lunch"],
                "dinner": row["dinner"]
            })

        return jsonify(result), 200

    except Exception as e:
        conn.close()
        print("❌ /admin/meals 오류:", str(e))  # 💬 디버깅용 콘솔 출력
        return jsonify({"error": str(e)}), 500

    # meals = [dict(row) for row in cursor.fetchall()]
    # conn.close()
    # return jsonify(meals), 200

def safe_int(val):
    try:
        return int(val)
    except:
        return 0

# ✅ [POST] /admin/edit_meals
# 관리자: 특정 사용자의 식수 신청 내역을 수정 (해당 날짜 삭제 후 재입력)
@app.route("/admin/edit_meals", methods=["POST"])
def admin_edit_meals():
    data = request.get_json()
    meals = data.get("meals", [])

    if not meals:
        return jsonify({"error": "meals 데이터가 필요합니다."}), 400

    today = datetime.now(KST).date()  # 👈 날짜 객체로 변경
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)

    conn = get_db_connection()
    cursor = conn.cursor()

    for meal in meals:
        user_id = meal.get("user_id")
        date_str = meal.get("date")
        breakfast = safe_int(meal.get("breakfast"))
        lunch = safe_int(meal.get("lunch"))
        dinner = safe_int(meal.get("dinner"))

        # 기존 값 가져오기
        cursor.execute("""
            SELECT breakfast, lunch, dinner
            FROM meals
            WHERE user_id = ? AND date = ?
        """, (user_id, date_str))
        original = cursor.fetchone()

        # 변경 로그 기록 (금주일 경우만)
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        if original and monday <= date_obj <= friday:
            before = dict(original)
            after = {"breakfast": breakfast, "lunch": lunch, "dinner": dinner}
            for meal_type in ["breakfast", "lunch", "dinner"]:
                if before[meal_type] != after[meal_type]:
                    cursor.execute("""
                        INSERT INTO meal_logs (emp_id, date, meal_type, before_status, after_status)
                        VALUES (?, ?, ?, ?, ?)
                    """, (user_id, date_str, meal_type, before[meal_type], after[meal_type]))

        # 기존 삭제 후 삽입
        cursor.execute("DELETE FROM meals WHERE user_id = ? AND date = ?", (user_id, date_str))
        cursor.execute("""
            INSERT INTO meals (user_id, date, breakfast, lunch, dinner)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, date_str, breakfast, lunch, dinner))

    conn.commit()
    conn.close()
    return jsonify({"message": f"{len(meals)}건이 수정되었습니다."}), 201

@app.route("/admin/insert_dummy", methods=["POST"])
def insert_dummy_data():
    conn = get_db_connection()
    cursor = conn.cursor()

    dummy = [
        ("1001", "홍길동", "영업부", "2025-03-25", 1, 1, 0),
        ("1002", "김철수", "설계부", "2025-03-25", 0, 1, 1),
        ("1001", "홍길동", "영업부", "2025-03-26", 1, 0, 0),
        ("1002", "김철수", "설계부", "2025-03-26", 1, 1, 1),
    ]

    for d in dummy:
        cursor.execute("""
            INSERT INTO meals (user_id, name, dept, date, breakfast, lunch, dinner)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET
                breakfast=excluded.breakfast,
                lunch=excluded.lunch,
                dinner=excluded.dinner
        """, d)

    conn.commit()
    conn.close()
    return jsonify({"message": "✅ 테스트용 더미 데이터가 저장되었습니다."}), 201

# 직원 전체 조회
@app.route("/admin/employees", methods=["GET"])
def get_employees():
    name = request.args.get("name", "").strip()

    conn = get_db_connection()

    if name:
         # ✅ 정확히 일치하는 이름만 검색
        cursor = conn.execute("SELECT * FROM employees WHERE name = ?", (name,))

    else:
         # 이름 없이 호출하면 전체 반환
        cursor = conn.execute("SELECT * FROM employees")

    
    employees = cursor.fetchall()
    conn.close()
    
    return jsonify([dict(emp) for emp in employees])


# 직원 추가
@app.route("/admin/employees", methods=["POST"])
def add_employee():
    data = request.get_json()
    emp_id = data.get("id")
    name = data.get("name")
    dept = data.get("dept")
    rank = data.get("rank", "")
    emp_type = data.get("type", "직영")  # 기본값: 직영
    emp_region = data.get("region", "에코센터")  # ✅ 지역 추가
    level = int(data.get("level", 1))
    if level not in (1, 2, 3):
        level = 1

    if not emp_id or not name or not dept or not emp_type or not emp_region:
        return jsonify({"error": "입력값 부족"}), 400

    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO employees (id, name, dept, rank, type, region, level) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (emp_id, name, dept, rank, emp_type, emp_region, level))
        conn.commit()
        return jsonify({"success": True}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "⚠️ 이미 등록된 사번입니다."}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()


# 직원 수정
@app.route("/admin/employees/<emp_id>", methods=["PUT"])
def update_employee(emp_id):
    data = request.get_json()
    name = data.get("name")
    dept = data.get("dept")
    rank = data.get("rank", "")
    emp_type = data.get("type", "직영")  # 기본값: 직영
    emp_region = data.get("region", "에코센터")  # ✅ 지역 추가
    level = int(data.get("level", 1))
    if level not in (1, 2, 3):
        level = 1

    if not emp_id or not name or not dept or not emp_type or not emp_region:
        return jsonify({"error": "입력값 부족"}), 400

    conn = get_db_connection()
    conn.execute("UPDATE employees SET name = ?, dept = ?, rank = ?, type = ?, region = ?, level = ? WHERE id = ?",
            (name, dept, rank, emp_type, emp_region, level, emp_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True}), 200


# 직원 삭제
@app.route("/admin/employees/<emp_id>", methods=["DELETE"])
def delete_employee(emp_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM employees WHERE id = ?", (emp_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/admin/employees/upload", methods=["POST"])
def upload_employees():
    if "file" not in request.files:
        return jsonify({"error": "파일이 없습니다."}), 400

    file = request.files["file"]
    filename = file.filename

    if not filename.endswith((".csv", ".xlsx")):
        return jsonify({"error": "지원되지 않는 파일 형식입니다."}), 400

    try:
        # 파일 읽기
        if filename.endswith(".csv"):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)

        required_cols = {"id", "name", "dept", "type", "region"}
        optional_cols = {"rank"}

        if not required_cols.issubset(set(df.columns)):
            return jsonify({"error": "파일에 'id', 'name', 'dept', 'type', '지역' 컬럼이 있어야 합니다."}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        for _, row in df.iterrows():
            # rank = row["rank"] if "rank" in row else ""
            cursor.execute("""
                INSERT INTO employees (id, name, dept, rank, type, region)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    dept = excluded.dept,
                    type = excluded.type,
                    region = excluded.region,
                    rank = excluded.rank
            """, (
                row["id"],
                row["name"],
                row["dept"],
                row["rank"] if "rank" in row else "",
                row["type"],
                row["region"]
            ))

        conn.commit()
        # conn.close()

        # 업로드 후 전체 직원 데이터를 함께 반환
        cursor = conn.execute("SELECT * FROM employees")
        employees = [dict(emp) for emp in cursor.fetchall()]
        conn.close()
        return jsonify(employees), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/admin/employees/template")
def download_employee_template():
    # 템플릿 파일 경로
    filename = "employee_template.xlsx"
    filepath = os.path.join(os.getcwd(), filename)

    # ✅ 파일이 이미 존재하면 삭제 (덮어쓰기 방지)
    if os.path.exists(filepath):
        os.remove(filepath)

    # 컬럼만 포함된 빈 DataFrame 생성
    df = pd.DataFrame(columns=["사번", "이름", "부서", "직영/협력사/방문자" , "에코센터/테크센터/기타","직급(옵션)"])
    df.to_excel(filepath, index=False)

    return send_file(filepath, as_attachment=True)

@app.route("/login_check")
def login_check():
    emp_id = request.args.get("id")
    name = request.args.get("name")

    print(f"🔍 로그인 시도: 사번={emp_id}, 이름={name}")  # ✅ 추가

    if not emp_id or not name:
        return jsonify({"error": "사번과 이름을 모두 입력하세요"}), 400

    conn = get_db_connection()

    cursor = conn.execute(
        "SELECT id, name, dept, rank, type, level, region FROM employees WHERE id = ? AND name = ?",
        (emp_id, name)
    )
    user = cursor.fetchone()
    conn.close()

    if user:
        return jsonify({
            "valid": True,
            "id": user["id"],
            "name": user["name"],
            "dept": user["dept"],
            "rank": user["rank"],
            "type": user["type"], # ✅ 여기서 type 추가 (직영 / 협력사 / 방문자)
            "level": user["level"],  # ✅ level 포함
            "region": user["region"]  # ✅ 추가
            
        })
    else:
        return jsonify({"valid": False}), 401


@app.route("/admin/logs", methods=["GET"])
def get_change_logs():
    start = request.args.get("start")
    end = request.args.get("end")
    name = request.args.get("name", "")
    dept = request.args.get("dept", "")

    conn = get_db_connection()
    try:
        cursor = conn.execute("""
            SELECT l.date, e.dept, e.name, l.meal_type,
                l.before_status, l.after_status, l.changed_at
            FROM meal_logs l
            JOIN employees e ON l.emp_id = e.id
            WHERE l.date BETWEEN ? AND ?
                AND e.name LIKE ?
                AND e.dept LIKE ?
            ORDER BY 
                l.date ASC,
                CASE l.meal_type 
                    WHEN 'breakfast' THEN 1
                    WHEN 'lunch' THEN 2
                    WHEN 'dinner' THEN 3
                    ELSE 4
                END,
                e.dept ASC,
                e.name ASC,
                l.changed_at DESC
        """, (start, end, f"%{name}%", f"%{dept}%"))
        logs = [dict(row) for row in cursor.fetchall()]
        return  jsonify(logs), 200
    except Exception as e:
        print("❌ 로그 쿼리 에러:", e)
        return jsonify({"error": "로그 쿼리 실패"}), 500
    finally:
        conn.close()

@app.route("/admin/logs/download", methods=["GET"])
def download_logs_excel():
    start = request.args.get("start")
    end = request.args.get("end")
    name = request.args.get("name", "")
    dept = request.args.get("dept", "")

    conn = get_db_connection()
    try:
        cursor = conn.execute("""
            SELECT l.date, e.dept, e.name, l.meal_type,
                   l.before_status, l.after_status, l.changed_at
            FROM meal_logs l
            JOIN employees e ON l.emp_id = e.id
            WHERE l.date BETWEEN ? AND ?
              AND e.name LIKE ?
              AND e.dept LIKE ?
            ORDER BY 
                l.date ASC,
                CASE l.meal_type 
                    WHEN 'breakfast' THEN 1
                    WHEN 'lunch' THEN 2
                    WHEN 'dinner' THEN 3
                    ELSE 4
                END,
                e.dept ASC,
                e.name ASC,
                l.changed_at DESC
        """, (start, end, f"%{name}%", f"%{dept}%"))
        
        logs = [dict(row) for row in cursor.fetchall()]
        df = pd.DataFrame(logs)

        # ✅ 포맷 변경
        df["식수일"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d") + " (" + pd.to_datetime(df["date"]).dt.day_name(locale="ko_KR").str[:1] + ")"
        df["식사유형"] = df["meal_type"].map({
            "breakfast": "아침", 
            "lunch": "점심", 
            "dinner": "저녁"
        })
        df["부서"] = df["dept"]
        df["이름"] = df["name"]
        df["변경전"] = df["before_status"].map({0: "미신청", 1: "신청"})
        df["변경후"] = df["after_status"].map({0: "미신청", 1: "신청"})
        df["변경시간"] = df["changed_at"]

        # ✅ 원하는 컬럼 순서로 재정렬
        final_df = df[["식수일", "식사유형", "부서", "이름", "변경전", "변경후", "변경시간"]]

        filename = "meal_log_export.xlsx"
        filename = "meal_log_export.xlsx"
        filepath = os.path.join(os.getcwd(), filename)
        final_df.to_excel(filepath, index=False)

        return send_file(filepath, as_attachment=True)

    except Exception as e:
        print("❌ 엑셀 다운로드 오류:", e)
        return jsonify({"error": "엑셀 다운로드 실패"}), 500
    finally:
        conn.close()

# 👉 방문자/협력사 로그 조회
@app.route("/admin/visitor_logs", methods=["GET"])
def get_visitor_logs():
    start = request.args.get("start")
    end = request.args.get("end")
    name = request.args.get("name", "").strip()
    dept = request.args.get("dept", "").strip()
    vtype = request.args.get("type", "").strip()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # ✅ 기본 SELECT 문 + JOIN
        query = """
            SELECT l.date, e.dept, l.applicant_name,
                   l.before_breakfast, l.before_lunch, l.before_dinner,
                   l.breakfast, l.lunch, l.dinner, l.updated_at
            FROM visitor_logs l
            LEFT JOIN employees e ON l.applicant_id = e.id
            WHERE 1 = 1
        """

        # ✅ 파라미터 조건 추가
        conditions = []
        params = []

        if start and end:
            conditions.append("l.date BETWEEN ? AND ?")
            params.extend([start, end])
        if name:
            conditions.append("l.applicant_name LIKE ?")
            params.append(f"%{name}%")
        if dept:
            conditions.append("IFNULL(e.dept, '') LIKE ?")
            params.append(f"%{dept}%")
        if vtype:
            conditions.append("l.type = ?")
            params.append(vtype)

        if conditions:
            query += " AND " + " AND ".join(conditions)

        query += """
            ORDER BY 
                l.date ASC,
                e.dept ASC,
                l.applicant_name ASC,
                l.updated_at DESC
        """

        cursor.execute(query, params)

        logs = [dict(row) for row in cursor.fetchall()]
        return jsonify(logs), 200


    except Exception as e:
        print("❌ 방문자 로그 조회 오류:", e)
        return jsonify({"error": "조회 실패"}), 500
    finally:
        conn.close()

@app.route("/admin/visitor_logs/download", methods=["GET"])
def download_visitor_logs_excel():
    start = request.args.get("start")
    end = request.args.get("end")
    name = request.args.get("name", "")
    dept = request.args.get("dept", "")
    vtype = request.args.get("type", "")

    if not start or not end:
        return "기간을 지정해주세요", 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        query = """
            SELECT l.date, e.dept, l.applicant_name,
                   l.before_breakfast, l.before_lunch, l.before_dinner,
                   l.breakfast, l.lunch, l.dinner, l.updated_at
            FROM visitor_logs l
            LEFT JOIN employees e ON l.applicant_id = e.id
            WHERE l.date BETWEEN ? AND ?
              AND l.applicant_name LIKE ?
              AND IFNULL(e.dept, '') LIKE ?
        """
        params = [start, end, f"%{name}%", f"%{dept}%"]

        if vtype:
            query += " AND l.type = ?"
            params.append(vtype)

        query += """
            ORDER BY 
                l.date ASC,
                e.dept ASC,
                l.applicant_name ASC,
                l.updated_at DESC
        """

        cursor.execute(query, params)
        logs = [dict(row) for row in cursor.fetchall()]
        df = pd.DataFrame(logs)

        if df.empty:
            return "엑셀로 출력할 데이터가 없습니다.", 404

        # ✅ 포맷 구성
        df["식수일"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d (%a)")
        df["부서"] = df["dept"]
        df["이름"] = df["applicant_name"]
        df["변경전"] = df.apply(
            lambda row: f"조식({row['before_breakfast']}), 중식({row['before_lunch']}), 석식({row['before_dinner']})", axis=1)
        df["변경후"] = df.apply(
            lambda row: f"조식({row['breakfast']}), 중식({row['lunch']}), 석식({row['dinner']})", axis=1)
        df["변경시각"] = df["updated_at"]

        final_df = df[["식수일", "부서", "이름", "변경전", "변경후", "변경시각"]]

        # ✅ Excel 생성
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            final_df.to_excel(writer, index=False, sheet_name="방문자 식수 로그")

        output.seek(0)
        filename = f"visitor_logs_{start}_to_{end}.xlsx"
        return send_file(output,
                         as_attachment=True,
                         download_name=filename,
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    except Exception as e:
        print("❌ 방문자 엑셀 오류:", e)
        return jsonify({"error": "엑셀 다운로드 실패"}), 500
    finally:
        conn.close()

@app.route("/admin/stats/period", methods=["GET"])
def get_stats_period():
    start = request.args.get("start")
    end = request.args.get("end")

    if not start or not end:
        return jsonify({"error": "기간이 지정되지 않았습니다."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT date, 
               SUM(breakfast) as breakfast, 
                SUM(lunch) as lunch, 
                SUM(dinner) as dinner
        FROM (
            SELECT date, breakfast, lunch, dinner FROM meals
            UNION ALL
            SELECT date, breakfast, lunch, dinner FROM visitors
        )
        WHERE date BETWEEN ? AND ?
        GROUP BY date
        ORDER BY date
    """, (start, end))

    rows = cursor.fetchall()
    conn.close()

    stats = []
    for row in rows:
        weekday = datetime.strptime(row["date"], "%Y-%m-%d").weekday()
        weekday_kr = ["월", "화", "수", "목", "금", "토", "일"][weekday]
        stats.append({
            "date": row["date"],
            "day": weekday_kr,   # ✅ 추가
            "breakfast": row["breakfast"],
            "lunch": row["lunch"],
            "dinner": row["dinner"]
        })

    return jsonify(stats), 200

@app.route("/admin/stats/period/excel", methods=["GET"])
def download_stats_period_excel():
    start = request.args.get("start")
    end = request.args.get("end")
    if not start or not end:
        return jsonify({"error": "기간이 지정되지 않았습니다."}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT date,
               SUM(breakfast) AS breakfast,
               SUM(lunch)     AS lunch,
               SUM(dinner)    AS dinner
        FROM (
            SELECT date, breakfast, lunch, dinner FROM meals
            UNION ALL
            SELECT date, breakfast, lunch, dinner FROM visitors
        )
        WHERE date BETWEEN ? AND ?
        GROUP BY date
        ORDER BY date
    """, (start, end))
    rows = cur.fetchall()
    conn.close()

    def week_key(date_str):
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{dt.year}-{dt.isocalendar().week:02d}주차"

    weekly = OrderedDict()
    month_total = {"breakfast": 0, "lunch": 0, "dinner": 0}
    for r in rows:
        b, l, d = r["breakfast"], r["lunch"], r["dinner"]
        if b == 0 and l == 0 and d == 0:
            continue

        dt = datetime.strptime(r["date"], "%Y-%m-%d")
        weekday_kr = "월화수목금토일"[dt.weekday()]
        key = week_key(r["date"])
        weekly.setdefault(key, []).append({
            "날짜": r["date"], "요일": weekday_kr,
            "조식": b, "중식": l, "석식": d
        })

        month_total["breakfast"] += b
        month_total["lunch"]     += l
        month_total["dinner"]    += d

    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        dfs = []
        row_ends = []
        current = 0

        for rows in weekly.values():
            df = pd.DataFrame(rows)
            dfs.append(df)
            current += len(df)
            row_ends.append(current)

        final_df = pd.concat(dfs, ignore_index=True)
        sheet = "기간별 식수통계"
        final_df.to_excel(writer, sheet_name=sheet, index=False, startrow=0)

        wb = writer.book
        worksheet = writer.sheets[sheet]
        border_format = wb.add_format({'bottom': 2})

        num_cols = final_df.shape[1]
        for r in row_ends:
            for c in range(num_cols):  # ← 실제 생성된 열까지 테두리 적용
                value = final_df.iat[r - 1, c]
                worksheet.write(r, c, value, border_format)

        # 총계 행 직접 작성 (요일은 공란)
        last_row = len(final_df) + 1
        total_row = ["기간별 총계", "", month_total["breakfast"], month_total["lunch"], month_total["dinner"]]
        for col, val in enumerate(total_row):
            worksheet.write(last_row, col, val)

    output.seek(0)
    filename = f"meal_stats_period_{start}_to_{end}.xlsx"
    return send_file(output, as_attachment=True, download_name=filename,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")




# ✅ 날짜별 그래프 데이터를 변환하는 함수
def convert_graph_data(rows):
    """
    입력: rows = [ {label: 날짜, weekday: 0~6, breakfast, lunch, dinner}, ... ]
    출력: {
        labels: ['2025-04-01', '2025-04-02', ...],
        breakfast: [10, 12, ...],
        lunch: [20, 23, ...],
        dinner: [5, 8, ...]
    }
    """
    labels = []
    breakfast_data = []
    lunch_data = []
    dinner_data = []

    for row in rows:
        # label: YYYY-MM-DD
        labels.append(row["label"])
        breakfast_data.append(row["breakfast"])
        lunch_data.append(row["lunch"])
        dinner_data.append(row["dinner"])

    return {
        "labels": labels,
        "breakfast": breakfast_data,
        "lunch": lunch_data,
        "dinner": dinner_data
    }


@app.route("/admin/graph/week_trend")
def graph_week_trend():
    start = request.args.get("start")
    end = request.args.get("end")

    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT 
            strftime('%Y-%m-%d', date) as label,
            strftime('%w', date) as weekday,
            SUM(breakfast) as breakfast,
            SUM(lunch) as lunch,
            SUM(dinner) as dinner
        FROM (
            SELECT date, breakfast, lunch, dinner FROM meals
            UNION ALL
            SELECT date, breakfast, lunch, dinner FROM visitors
        )
        WHERE date BETWEEN ? AND ?
        GROUP BY date
        ORDER BY date
    """
    cursor.execute(query, (start, end))
    rows = cursor.fetchall()
    conn.close()


    return jsonify([dict(row) for row in rows])


@app.route("/admin/stats/dept_summary")
def get_dept_summary():
    start = request.args.get("start")
    end = request.args.get("end")

    if not start or not end:
        return jsonify({"error": "기간이 지정되지 않았습니다."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # ✅ 1. meals: 사번 기준으로 employees에서 타입 가져옴
    cursor.execute("""
        SELECT 
            e.dept AS dept,
            e.type AS type,
            m.breakfast,
            m.lunch,
            m.dinner
        FROM meals m
        JOIN employees e ON m.user_id = e.id
        WHERE m.date BETWEEN ? AND ?
    """, (start, end))
    meal_rows = cursor.fetchall()

    # ✅ 2. visitors: 신청 목적(type 컬럼)을 그대로 사용해야 정확함
    cursor.execute("""
        SELECT 
            e.dept AS dept,
            v.type AS type,  -- 🔥 실제 신청목적 기준 분류
            v.breakfast,
            v.lunch,
            v.dinner
        FROM visitors v
        JOIN employees e ON v.applicant_id = e.id
        WHERE v.date BETWEEN ? AND ?
    """, (start, end))
    visitor_rows = cursor.fetchall()

    conn.close()

    # ✅ 3. 결과 합산
    summary = defaultdict(lambda: {"breakfast": 0, "lunch": 0, "dinner": 0})

    for row in meal_rows + visitor_rows:
        dept = row["dept"]
        type_ = row["type"]
    
        # ✅ 방문자일 경우 부서명 변형
        if type_ == "방문자":
            dept = f"{dept[:2]}(방문자)"
        # 👇 아래 추가로 처리
        elif type_ == "협력사":
            dept = dept  # 필요 시 dept[:4] 등으로 변경 가능 (가독성)

        key = (dept, type_)
        summary[key]["breakfast"] += row["breakfast"]
        summary[key]["lunch"] += row["lunch"]
        summary[key]["dinner"] += row["dinner"]

    result = []
    for (dept, t), meals in summary.items():
        result.append({
            "dept": dept,
            "type": t,
            "breakfast": meals["breakfast"],
            "lunch": meals["lunch"],
            "dinner": meals["dinner"]
        })

    return jsonify(result), 200

@app.route("/admin/stats/dept_summary/excel")
def download_dept_summary_excel():
    start = request.args.get("start")
    end = request.args.get("end")

    if not start or not end:
        return "날짜를 지정해주세요", 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # ✅ meals 테이블: 직원의 실제 타입 사용
    cursor.execute("""
        SELECT 
            e.dept AS dept,
            e.type AS type,
            m.breakfast,
            m.lunch,
            m.dinner
        FROM meals m
        JOIN employees e ON m.user_id = e.id
        WHERE m.date BETWEEN ? AND ?
    """, (start, end))
    meal_rows = cursor.fetchall()

    # ✅ visitors 테이블: 신청 목적 기준(type)
    cursor.execute("""
        SELECT 
            e.dept AS dept,
            v.type AS type,
            v.breakfast,
            v.lunch,
            v.dinner
        FROM visitors v
        JOIN employees e ON v.applicant_id = e.id
        WHERE v.date BETWEEN ? AND ?
    """, (start, end))
    visitor_rows = cursor.fetchall()

    conn.close()

    # ✅ 통합 집계
    summary = defaultdict(lambda: {"breakfast": 0, "lunch": 0, "dinner": 0})

    for row in meal_rows + visitor_rows:
        dept = row["dept"]
        type_ = row["type"]

        # ✅ 방문자일 경우, 부서명 치환
        if type_ == "방문자":
            dept = f"{dept[:2]}(방문자)"

        key = (dept, type_)
        summary[key]["breakfast"] += row["breakfast"]
        summary[key]["lunch"] += row["lunch"]
        summary[key]["dinner"] += row["dinner"]

    # ✅ DataFrame 구성
    import pandas as pd
    from io import BytesIO

    result = []
    for (dept, t), meals in summary.items():
        result.append({
            "dept": dept,
            "type": t,
            "breakfast": meals["breakfast"],
            "lunch": meals["lunch"],
            "dinner": meals["dinner"]
        })

    df = pd.DataFrame(result)
    df["total"] = df["breakfast"] + df["lunch"] + df["dinner"]

    # ✅ 분류 및 정렬
    direct = df[df["type"] == "직영"].sort_values("dept")
    partner = df[df["type"] == "협력사"].sort_values("dept")
    visitor = df[df["type"] == "방문자"].sort_values("dept")

    def make_subtotal(df_part, label):
        subtotal = pd.DataFrame({
            "dept": [f"{label} 소계"],
            "type": [label],
            "breakfast": [df_part["breakfast"].sum()],
            "lunch": [df_part["lunch"].sum()],
            "dinner": [df_part["dinner"].sum()],
        })
        subtotal["total"] = subtotal["breakfast"] + subtotal["lunch"] + subtotal["dinner"]
        return subtotal

    direct_total = make_subtotal(direct, "직영")
    partner_total = make_subtotal(partner, "협력사")
    visitor_total = make_subtotal(visitor, "방문자")
    grand_total = make_subtotal(df, "총계")

    final_df = pd.concat([
        direct,
        direct_total,
        partner,
        partner_total,
        visitor,
        visitor_total,
        grand_total
    ], ignore_index=True)

    final_df = final_df[["dept", "total", "breakfast", "lunch", "dinner"]]  # 열 순서 조정

    # ✅ Excel 파일 생성
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        final_df.to_excel(writer, index=False, sheet_name="부서별 신청현황")
    output.seek(0)

    filename = f"dept_stats_{start}_to_{end}.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.route("/admin/stats/weekly_dept")
def weekly_dept_stats():
    start = request.args.get("start")
    end = request.args.get("end")

    if not (start and end):
        return jsonify({"error": "start, end 파라미터가 필요합니다"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # ✅ 1. 전체 직원 목록 조회 (직영, 협력사 구분 및 부서 인원 계산용)
    cursor.execute("SELECT id, name, dept, type, region FROM employees")
    employees = cursor.fetchall()

    emp_info = {e["id"]: dict(e) for e in employees}
     
    # 2. 부서별 인원수 (dept + type + region 조합 기준)
    dept_members = {}
    for e in employees:
        key = (e["dept"], e["type"], e["region"])
        dept_members.setdefault(key, []).append(e["id"])

    # 3. dept_map 사전 등록 (모든 부서를 먼저 넣어둠)
    dept_map = {}

    # ✅ 전체 부서를 dept_map에 선등록 (식수 신청 없어도 표시 위해)
    for (dept, type_, region), ids in dept_members.items():
        # 출장자: "직영(출장자)" 키 사용, 표시명은 원래 부서명
        if type_ == "직영" and region != "에코센터":
            # dept_key = f"{dept[:4]}(출장)"
            # display_dept = f"{dept[:4]}(출장)"
            continue  # ❌ 출장자는 선등록하지 않음
        else:
            dept_key = dept
            display_dept = dept

        # 중복 생성 방지
        # if dept_key not in dept_map:
        dept_map[dept_key] = {
            "type": type_ if dept_key != "직영(출장자)" else "직영",
            "dept": dept_key,
            "display_dept": display_dept,
            "total": len(ids),
            "days": {}
        }
    
    

    # ✅ 4. meals 테이블 데이터 조회
    cursor.execute("""
        SELECT m.date, m.user_id, m.breakfast, m.lunch, m.dinner,
            e.name, e.dept, e.type, e.region
        FROM meals m
        JOIN employees e ON m.user_id = e.id
        WHERE m.date BETWEEN ? AND ?
    """, (start, end))
    meal_rows = cursor.fetchall()

    for row in meal_rows:
        date = row["date"]
        name = row["name"]
        dept = row["dept"]
        type_ = row["type"]
        region = row["region"]

        # ✅ 출장자 구분
        if type_ == "직영" and region != "에코센터":
            dept_key = f"{dept[:4]}(출장)"
            display_dept = f"{dept[:4]}(출장)"  # 원래 부서명 유지 (표시용)
        else:
            dept_key = dept
            display_dept = dept

        # ✅ 신청자 존재 시만 출장자 등록
        if dept_key not in dept_map:
            dept_map[dept_key] = {
                "type": type_,
                "dept": dept_key,
                "display_dept": display_dept,
                "total": len([
                    e["id"] for e in employees if e["dept"] == dept and e["type"] == type_ and e["region"] == region
                ]),
                "days": {}
            }

        # ✅ 식사별 인원수 및 명단 기록
        for meal, key in zip(["breakfast", "lunch", "dinner"], ["b", "l", "d"]):
            qty = row[meal]
            if qty > 0:
                if date not in dept_map[dept_key]["days"]:
                    dept_map[dept_key]["days"][date] = {"b": [], "l": [], "d": []}
                dept_map[dept_key]["days"][date][key].append(name)
                    # name if dept_key != "직영(출장자)" else f"{name}")



    # ✅ 3. 방문자 신청(visitors) 데이터 조회
    cursor.execute("""
        SELECT v.date, v.breakfast, v.lunch, v.dinner, v.applicant_id, v.type,
               e.name, e.dept
        FROM visitors v
        JOIN employees e ON v.applicant_id = e.id
        WHERE v.date BETWEEN ? AND ?
    """, (start, end))
    visitor_rows = cursor.fetchall()

    # ✅ 4. 부서별 집계 초기화 (모든 직영/협력사/방문자 포함)
    # dept_map = {}

    # for (dept, t) in dept_members:
    #     if t == "방문자":
    #         dept_name = f"{dept[:2]}(방문자)"
    #     else:
    #         dept_name = dept

    #     dept_map[dept_name] = {
    #         "type": t,
    #         "dept": dept_name,
    #         "total": len(dept_members[(dept, t)]),
    #         "days": {}
    #     }
    
    # # ✅ 5. meals 처리
    # for row in meal_rows:
    #     date = row["date"]
    #     name = row["name"]
    #     dept = row["dept"]
    #     type_ = row["type"]
    #     label = name

    #     if dept not in dept_map:
    #         continue  # safety check

    #     for meal, key in zip(["breakfast", "lunch", "dinner"], ["b", "l", "d"]):
    #         qty = row[meal]
    #         if qty > 0:
    #             dept_map[dept]["days"].setdefault(date, { "b": [], "l": [], "d": [] })[key].append(label)

    # ✅ 6. visitors 처리 (방문자 전용)
    for row in visitor_rows:
        date = row["date"]
        name = row["name"]  # 신청자 이름
        dept = row["dept"]  # 신청자의 부서
        vtype = row["type"]             # 방문자 or 협력사
        # total_qty = row["breakfast"] + row["lunch"] + row["dinner"]
        # label = f"{name}({total_qty})"
        
        # ✅ 타입에 따라 부서 키 처리
        if vtype == "방문자":
            dept_key = f"{dept[:2]}(방문자)"
        elif vtype == "협력사":
            dept_key = dept  # 협력사는 일반 부서 그대로 사용
        else:
            continue  # 방어적 코딩

        # ✅ dept_map에 부서 등록 (없으면 초기화)
        # if dept_key not in dept_map:
        #     total_emp = len([e for e in employees if e["dept"] == dept and e["type"] == vtype])
        #     dept_map[dept_key] = {
        #         "type": vtype,
        #         "dept": dept_key,
        #         "total": total_emp,
        #         "days": {}
        #     }

        if dept_key not in dept_map:
            total_emp = len([
                e for e in employees
                if e["dept"] == dept and e["type"] == vtype
            ])
            dept_map[dept_key] = {
                "type": vtype,
                "dept": dept_key,
                "display_dept": dept_key,  # ✅ 프론트에서 표시할 부서명
                "total": total_emp,
                "days": {}
            }



        # ✅ 식사 유형별로 개별 수량 반영
        for meal, key in zip(["breakfast", "lunch", "dinner"], ["b", "l", "d"]):
            qty = row[meal]
            if qty > 0:
                label = f"{name}({qty})"
                dept_map[dept_key]["days"].setdefault(date, { "b": [], "l": [], "d": [] })[key].append(label)

    
    # ✅ 신청 내역이 없는 부서는 제외 (단, '직영(출장자)'만 예외적으로 제외)
    result = []
    for info in dept_map.values():
        has_data = any(
            len(meal_list) > 0
            for day_data in info["days"].values()
            for meal_list in day_data.values()
        )

        if info["dept"] == "직영(출장자)" and not has_data:
            continue  # 신청 없으면 표시하지 않음
        result.append(info)

    # # ✅ 7. 최종 결과 구성 및 반환
    # result = list(dept_map.values())

    conn.close()
    # import json

    # try:
    #     # 직렬화 검증
    #     json.dumps(result)
    # except Exception as e:
    #     print("❌ JSON 직렬화 오류:", e)
    #     return jsonify({"error": "JSON 직렬화 실패"}), 500

    # print("📊 반환 데이터 길이:", len(result))
    # if result:
    #     print("📊 첫 항목:", result[0])

    return jsonify(result)


# @app.route("/admin/stats/weekly_dept")
# def weekly_dept_stats():
#     start = request.args.get("start")
#     end = request.args.get("end")

#     conn = get_db_connection()
#     cursor = conn.cursor()

#     # ✅ ① 모든 직원 불러오기 (부서 인원수 및 기본 출력용)
#     cursor.execute("SELECT id, name, dept, type FROM employees")
#     employees = cursor.fetchall()
#     emp_info = {e["id"]: dict(e) for e in employees}

#     # ✅ ② 부서별 type별 인원수 계산
#     dept_members = {}
#     for e in employees:
#         dept_members.setdefault((e["dept"], e["type"]), []).append(e["id"])

#     # ✅ ③ 식수 신청 + 방문자 신청 통합 조회
#     cursor.execute("""
#         SELECT m.date, m.user_id, m.breakfast, m.lunch, m.dinner,
#                e.name, e.dept,
#                CASE
#                    WHEN m.source = 'visitors' THEN m.vtype
#                    ELSE e.type
#                END AS type
#         FROM (
#             SELECT 'meals' AS source, user_id, date, breakfast, lunch, dinner, NULL AS vtype FROM meals
#             UNION ALL
#             SELECT 'visitors' AS source, applicant_id AS user_id, date, breakfast, lunch, dinner, type AS vtype FROM visitors
#         ) m
#         JOIN employees e ON m.user_id = e.id
#         WHERE m.date BETWEEN ? AND ?
#     """, (start, end))
#     rows = cursor.fetchall()

#     # ✅ ④ 부서별 데이터 초기화 (신청 없어도 모든 부서 포함)
#     dept_map = {}
#     for (dept, t) in dept_members:
#         type_label = t
#         if t == "방문자":
#             # type_label = "방문자"
#             dept_name = f"{dept[:2]}(방문자)"
#         elif t == "협력사":
#             # type_label = "협력사"
#             dept_name = dept
#         else:
#             # type_label = "직영"
#             dept_name = dept

#         dept_map[dept_name] = {
#             "type": t,
#             "dept": dept_name,
#             "total": len(dept_members[(dept, t)]),
#             "days": {}  # 날짜별 식사 신청 정보
#         }

#     # ✅ ⑤ 신청 내역 반영 (신청자 명단 구성)
#     for row in rows:
#         date = row["date"]
#         name = row["name"]
#         dept = row["dept"]
#         type_ = row["type"]

#         if type_ == "방문자":
#             dept_key = f"{dept[:2]}(방문자)"
#             label = f"{name}({row['breakfast'] + row['lunch'] + row['dinner']})"
#         elif type_ == "협력사":
#             dept_key = dept
#             label = f"{name}({row['breakfast'] + row['lunch'] + row['dinner']})"
#         else:
#             dept_key = dept
#             label = name

#         # ✅ 누락된 부서 초기화
#         if dept_key not in dept_map:
#             dept_map[dept_key] = {
#                 "type": type_,
#                 "dept": dept_key,
#                 "total": len(dept_members.get((dept, type_), [])),
#                 "days": {}
#             }

#         for meal, key in zip(["breakfast", "lunch", "dinner"], ["b", "l", "d"]):
#             qty = row[meal]
#             if qty > 0:
#                 dept_map[dept_key]["days"].setdefault(date, { "b": [], "l": [], "d": [] })[key].append(label)

#     # ✅ ⑥ JSON으로 반환
#     return jsonify(list(dept_map.values()))


# @app.route("/admin/stats/weekly_dept")
# def weekly_dept_stats():
#     start = request.args.get("start")
#     end = request.args.get("end")

#     if not start or not end:
#         return jsonify({"error": "start 또는 end 파라미터가 누락되었습니다."}), 400

#     conn = get_db_connection()
#     cursor = conn.cursor()

#     # 전체 직원 목록 (부서별 인원 수 확인용)
#     cursor.execute("""
#         SELECT id, name, dept, type
#         FROM employees
#     """)
#     employees = cursor.fetchall()
#     emp_info = {e["id"]: dict(e) for e in employees}

#     # ✅ 1-1. 부서별 실제 직영 인원 수 계산
#     emp_info_by_dept = {}
#     for e in employees:
#         if e["type"] == "직영":
#             emp_info_by_dept.setdefault(e["dept"], set()).add(e["id"])

#     # 식사 신청 내역
#     # ✅ 2. meals + visitors 통합 조회
#     # ✅ meals + visitors 통합 쿼리 (source, vtype 포함)
#     cursor.execute("""
#         SELECT m.date, m.user_id, m.breakfast, m.lunch, m.dinner,
#                e.name, e.dept,
#                CASE
#                    WHEN m.source = 'visitors' THEN m.vtype
#                    ELSE e.type
#                END AS type
#         FROM (
#             SELECT 'meals' AS source, user_id, date, breakfast, lunch, dinner, NULL AS vtype FROM meals
#             UNION ALL
#             SELECT 'visitors' AS source, applicant_id AS user_id, date, breakfast, lunch, dinner, type AS vtype FROM visitors
#         ) m
#         JOIN employees e ON m.user_id = e.id
#         WHERE m.date BETWEEN ? AND ?
#     """, (start, end))
#     rows = cursor.fetchall()
#     conn.close()

#     dept_map = {}

#     for row in rows:
#         date = row["date"]
#         uid = row["user_id"]
#         name = row["name"]
#         dept = row["dept"]
#         utype = row["type"]

#         # ✅ 방문자 or 협력사일 경우 → 부서는 신청자 부서지만, 타입은 "방문자"/"협력사"
#         true_dept = dept
#         if utype in ("방문자", "협력사"):
#             # 👇 방문자 소계 / 협력사 소계로 분리됨
#             dept_key = f"{dept}__{utype}"
#         else:
#             dept_key = dept

#         if dept_key not in dept_map:
#             dept_map[dept_key] = {
#                 "original_dept": dept,
#                 "type": utype,
#                 "days": {},
#                 "uids": set(),
#                 "count": 0
#             }

#         if utype == "직영":
#             dept_map[dept_key]["uids"].add(uid)

#         if date not in dept_map[dept_key]["days"]:
#             dept_map[dept_key]["days"][date] = {
#                 "b": [], "l": [], "d": []
#             }

#         def append_meal(meal_key, quantity):
#             if quantity and quantity > 0:
#                 if utype in ("방문자", "협력사"):
#                     dept_map[dept_key]["days"][date][meal_key].append(f"{name}({quantity})")
#                     dept_map[dept_key]["count"] += quantity
#                 else:
#                     dept_map[dept_key]["days"][date][meal_key].append(name)
#                     dept_map[dept_key]["count"] += 1

#         append_meal("b", row["breakfast"])
#         append_meal("l", row["lunch"])
#         append_meal("d", row["dinner"])

#     # ✅ JSON 구조 구성
#     result = []
#     for key, val in dept_map.items():
#         result.append({
#             "dept": val["original_dept"],
#             "type": val["type"],
#             "total": len(val["uids"]) if val["type"] == "직영" else val["count"],
#             "days": val["days"]
#         })

#     return jsonify(result)

# @app.route("/admin/stats/weekly_dept/excel")
# def weekly_dept_excel():
#     start = request.args.get("start")
#     end = request.args.get("end")

#     if not start or not end:
#         return "start 또는 end 파라미터가 누락되었습니다.", 400

#     conn = get_db_connection()
#     cursor = conn.cursor()

#     # 🔹 사원정보
#     cursor.execute("SELECT id, name, dept, type FROM employees")
#     employees = cursor.fetchall()

#     emp_info = {e["id"]: dict(e) for e in employees}

#     # 🔹 meals + visitors 통합 데이터
#     cursor.execute("""
#         SELECT date, user_id, breakfast, lunch, dinner
#         FROM (
#             SELECT date, user_id, breakfast, lunch, dinner FROM meals
#             UNION ALL
#             SELECT date, applicant_id AS user_id, breakfast, lunch, dinner FROM visitors
#         )
#         WHERE date BETWEEN ? AND ?
#     """, (start, end))
#     meals = cursor.fetchall()
#     conn.close()

#     # 🔹 부서별 정리
#     dept_map = {}
#     for uid, info in emp_info.items():
#         dept = info["dept"]
#         if dept not in dept_map:
#             dept_map[dept] = {
#                 "type": info["type"],
#                 "people": set(),
#                 "days": {}
#             }
#         dept_map[dept]["people"].add(uid)

#     for m in meals:
#         uid = m["user_id"]
#         if uid not in emp_info:
#             continue
#         emp = emp_info[uid]
#         dept = emp["dept"]
#         name = emp["name"]
#         utype = emp["type"]
#         date = m["date"]

#         if dept not in dept_map:
#             continue

#         if date not in dept_map[dept]["days"]:
#             dept_map[dept]["days"][date] = {"b": [], "l": [], "d": []}

#         for key, meal_type in zip(["breakfast", "lunch", "dinner"], ["b", "l", "d"]):
#             qty = m[key]
#             if qty and qty > 0:
#                 display_name = f"{name}({qty})" if utype in ("협력사", "방문자") else name
#                 dept_map[dept]["days"][date][meal_type].append(display_name)

#     # 🔹 날짜 정리
#     all_dates = sorted(set(m["date"] for m in meals))
#     weekday_map = ["월", "화", "수", "목", "금", "토", "일"]

#     # 🔹 DataFrame 생성
#     def extract_quantity(name_str):
#         import re
#         match = re.search(r'\((\d+)\)$', name_str)
#         return int(match.group(1)) if match else 1

#     def build_rows(dept_list):
#         rows = []
#         for dept in sorted(dept_list):
#             info = dept_map[dept]
#             row = {
#                 "부서": dept,
#                 "인원수": 0
#             }

#             total = 0
#             for d in all_dates:
#                 meals = info["days"].get(d, {"b": [], "l": [], "d": []})

#                 for key, label in [("b", "조식"), ("l", "중식"), ("d", "석식")]:
#                     names = meals[key]
#                     count = sum(extract_quantity(n) for n in names)
#                     row[f"{d}_{label}인원"] = count
#                     row[f"{d}_{label}명단"] = ", ".join(names)
#                     total += count

#             row["인원수"] = total
#             rows.append(row)
#         return rows

#     direct = [k for k, v in dept_map.items() if v["type"] == "직영"]
#     partner = [k for k, v in dept_map.items() if v["type"] == "협력사"]
#     visitor = [k for k, v in dept_map.items() if v["type"] == "방문자"]

#     def subtotal(df, label):
#         if df.empty:
#             return pd.DataFrame()
#         subtotal_row = {"부서": label, "인원수": df["인원수"].sum()}
#         for col in df.columns:
#             if "인원" in col and col != "인원수":
#                 subtotal_row[col] = df[col].sum()
#             elif "명단" in col:
#                 subtotal_row[col] = ""
#         return pd.DataFrame([subtotal_row])

#     df_direct = pd.DataFrame(build_rows(direct))
#     df_partner = pd.DataFrame(build_rows(partner))
#     df_visitor = pd.DataFrame(build_rows(visitor))

#     df_all = pd.concat([
#         df_direct,
#         subtotal(df_direct, "직영 소계"),
#         df_partner,
#         subtotal(df_partner, "협력사 소계"),
#         df_visitor,
#         subtotal(df_visitor, "방문자 소계"),
#         subtotal(pd.concat([df_direct, df_partner, df_visitor]), "총계")
#     ], ignore_index=True)

#     output = BytesIO()
#     with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
#         df_all.to_excel(writer, index=False, sheet_name="주간 부서별 신청현황")

#     output.seek(0)
#     filename = f"weekly_dept_{start}_to_{end}.xlsx"
#     return send_file(output, as_attachment=True, download_name=filename,
#                      mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/admin/stats/weekly_dept/excel")
def weekly_dept_excel():


    def extract_quantity(name_str):
        match = re.search(r"\((\d+)\)", name_str)
        return int(match.group(1)) if match else 1

    start = request.args.get("start")
    end = request.args.get("end")

    if not start or not end:
        return "start 또는 end 파라미터가 누락되었습니다.", 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # ✅ 전체 사원 정보
    cursor.execute("SELECT id, name, dept, type FROM employees")
    employees = cursor.fetchall()
    emp_info = {e["id"]: dict(e) for e in employees}

    # ✅ 부서+타입 조합 확보 → 직영/협력사/방문자 포함
    dept_map = {}
    for e in employees:
        key = (e["dept"], e["type"])
        if key not in dept_map:
            dept_map[key] = {
                "type": e["type"],
                "dept": f"{e['dept'][:2]}(방문자)" if e["type"] == "방문자" else e["dept"],
                "total": 0,
                "days": defaultdict(lambda: {"b": [], "l": [], "d": []})
            }
        dept_map[key]["total"] += 1

    # ✅ 식수 신청 데이터 (meals + visitors)
    cursor.execute("""
        SELECT m.date, m.user_id, m.breakfast, m.lunch, m.dinner,
               e.name, e.dept,
               CASE 
                    WHEN m.source = 'visitors' THEN m.vtype
                    ELSE e.type
               END AS type
        FROM (
            SELECT 'meals' AS source, user_id, date, breakfast, lunch, dinner, NULL AS vtype FROM meals
            UNION ALL
            SELECT 'visitors' AS source, applicant_id AS user_id, date, breakfast, lunch, dinner, type AS vtype FROM visitors
        ) m
        JOIN employees e ON m.user_id = e.id
        WHERE m.date BETWEEN ? AND ?
    """, (start, end))
    rows = cursor.fetchall()
    conn.close()

    for row in rows:
        date = row["date"]
        name = row["name"]
        dept = row["dept"]
        utype = row["type"]
        key = (dept, utype)
        label = f"{name}({row['breakfast']})" if utype in ("협력사", "방문자") and row["breakfast"] else name

        if key not in dept_map:
            dept_map[key] = {
                "type": utype,
                "dept": f"{dept[:2]}(방문자)" if utype == "방문자" else dept,
                "total": 0,
                "days": defaultdict(lambda: {"b": [], "l": [], "d": []})
            }

        for meal, short in zip(["breakfast", "lunch", "dinner"], ["b", "l", "d"]):
            qty = row[meal]
            if qty > 0:
                label = f"{name}({qty})" if utype in ("협력사", "방문자") else name
                dept_map[key]["days"][date][short].append(label)

    # ✅ 날짜 목록
    all_dates = sorted({r["date"] for r in rows})

    # ✅ 테이블 구성
    def build_rows(filtered_keys):
        rows = []
        for key in sorted(filtered_keys, key=lambda k: dept_map[k]["dept"]):
            data = dept_map[key]
            row = {
                "부서": data["dept"],
                "인원수": data["total"]
            }
            for d in all_dates:
                for k, label in zip(["b", "l", "d"], ["조식", "중식", "석식"]):
                    names = data["days"][d][k]
                    qty = sum(extract_quantity(n) for n in names)
                    row[f"{d}_{label}인원"] = qty
                    row[f"{d}_{label}명단"] = ", ".join(names) if names else "-"
            rows.append(row)
        return rows

    # ✅ 분류
    direct_keys = [k for k in dept_map if k[1] == "직영"]
    partner_keys = [k for k in dept_map if k[1] == "협력사"]
    visitor_keys = [k for k in dept_map if k[1] == "방문자"]

    df_direct = pd.DataFrame(build_rows(direct_keys))
    df_partner = pd.DataFrame(build_rows(partner_keys))
    df_visitor = pd.DataFrame(build_rows(visitor_keys))

    def subtotal(df, label):
        if df.empty: return pd.DataFrame()
        row = {"부서": label, "인원수": df["인원수"].sum()}
        for col in df.columns:
            if "인원" in col and col != "인원수":
                row[col] = df[col].sum()
            elif "명단" in col:
                row[col] = ""
        return pd.DataFrame([row])

    df_all = pd.concat([
        df_direct,
        subtotal(df_direct, "직영 소계"),
        df_partner,
        subtotal(df_partner, "협력사 소계"),
        df_visitor,
        subtotal(df_visitor, "방문자 소계"),
        subtotal(pd.concat([df_direct, df_partner, df_visitor]), "총계")
    ], ignore_index=True)

    # ✅ Excel 출력
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df_all.to_excel(writer, index=False, sheet_name="주간 부서별 신청현황")
    output.seek(0)

    filename = f"weekly_dept_{start}_to_{end}.xlsx"
    return send_file(output, as_attachment=True, download_name=filename,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

#식수신청 피벗 엑셀 라우트
@app.route("/admin/stats/pivot_excel")
def download_pivot_excel():
    from io import BytesIO
    from datetime import datetime, timedelta, timezone
    import pandas as pd
    import sqlite3

    start = request.args.get("start")
    end   = request.args.get("end")
    days_param = request.args.get("days")  # "YYYY-MM-DD,YYYY-MM-DD,..."

    if not start or not end:
        return "start, end 날짜를 지정해주세요.", 400

    # --- DB 조회 ---
    conn = sqlite3.connect("db.sqlite")

    # 직원(직영) 식수 신청
    query_meals = """
        SELECT m.date, m.breakfast, m.lunch, m.dinner,
               e.name, e.dept, e.type, e.region
        FROM meals m
        JOIN employees e ON m.user_id = e.id
        WHERE m.date BETWEEN ? AND ?
        ORDER BY m.date, e.name
    """
    df_meals = pd.read_sql_query(query_meals, conn, params=(start, end))

    # 방문자/협력사 신청
    query_visitors = """
        SELECT v.applicant_name, v.date, v.breakfast, v.lunch, v.dinner, v.type,
               e.dept, e.type as emp_type
        FROM visitors v
        LEFT JOIN employees e ON v.applicant_id = e.id
        WHERE v.date BETWEEN ? AND ?
        ORDER BY v.date, v.applicant_name
    """
    df_visitors = pd.read_sql_query(query_visitors, conn, params=(start, end))
    conn.close()

    # --- 선택 날짜 필터 (옵션) ---
    if days_param:
        only_days = set(d.strip() for d in days_param.split(",") if d.strip())
        if not df_meals.empty:
            df_meals = df_meals[df_meals["date"].isin(only_days)]
        if not df_visitors.empty:
            df_visitors = df_visitors[df_visitors["date"].isin(only_days)]

    # --- 피벗용 리스트 구성 ---
    eco_center = []   # 직영-에코센터
    tech_center = []  # 직영-출장

    for _, row in df_meals.iterrows():
        # 직영만 출력
        if row.get("type") != "직영":
            continue
        base = [row["date"], row["name"], row["dept"]]
        target = eco_center if row.get("region") == "에코센터" else tech_center
        if int(row.get("breakfast", 0)) == 1: target.append(base + ["조식"])
        if int(row.get("lunch", 0))     == 1: target.append(base + ["중식"])
        if int(row.get("dinner", 0))    == 1: target.append(base + ["석식"])

    # 방문자/협력사는 신청자 타입(emp_type)으로 블록 분리
    visitor_direct = []  # 직영 직원이 신청한 방문객
    visitor_others = []  # 협력사/방문자 신청
    for _, row in df_visitors.iterrows():
        base = [row["date"], row["type"], row["dept"]]
        emp_type = row.get("emp_type")
        def push(meal_label, cnt):
            if int(cnt or 0) > 0:
                rec = base + [int(cnt), meal_label]
                (visitor_direct if emp_type == "직영" else visitor_others).append(rec)
        push("조식", row.get("breakfast"))
        push("중식", row.get("lunch"))
        push("석식", row.get("dinner"))

    # --- 엑셀 출력 ---
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        # 직영 시트 2개
        pd.DataFrame(eco_center, columns=["식사일자", "이름", "부서", "식사 구분"])\
            .to_excel(writer, index=False, sheet_name="직영_에코센터")
        pd.DataFrame(tech_center, columns=["식사일자", "이름", "부서", "식사 구분"])\
            .to_excel(writer, index=False, sheet_name="직영_출장")

        # ✅ '협력사_방문객' 시트는 항상 생성 (빈 헤더 방지: 데이터 있는 블록만 작성)
        sheetname = "협력사_방문객"
        ws = writer.book.add_worksheet(sheetname)   # 시트만 생성
        writer.sheets[sheetname] = ws

        start_row = 0

        # 블록1: 직영 직원이 신청한 방문객
        if len(visitor_direct) > 0:
            df_direct = pd.DataFrame(
                visitor_direct,
                columns=["식사일자", "구분", "부서", "인원수", "식사 구분"]
            )
            df_direct.to_excel(writer, index=False, sheet_name=sheetname, startrow=start_row)
            start_row += len(df_direct) + 2  # 다음 블록과 한 줄 띄우기

        # 블록2: 협력사/방문자가 신청
        if len(visitor_others) > 0:
            df_others = pd.DataFrame(
                visitor_others,
                columns=["식사일자", "구분", "부서", "인원수", "식사 구분"]
            )
            df_others.to_excel(writer, index=False, sheet_name=sheetname, startrow=start_row)
            # start_row 갱신은 필요 시 추가

    output.seek(0)

    # 한국시간 파일명
    kst = timezone(timedelta(hours=9))
    now_str = datetime.now(kst).strftime("%Y%m%d_%H%M")
    filename = f"식수신청_피벗_{now_str}.xlsx"

    return send_file(output,
                     download_name=filename,
                     as_attachment=True,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")








# ✅ [2] POST /visitors - 저장
@app.route("/visitors", methods=["POST"])
def save_visitors():
    try:
        data = request.json or {}
        applicant_id   = data.get("applicant_id")
        applicant_name = data.get("applicant_name")
        date_str       = data.get("date")          # YYYY-MM-DD
        reason         = (data.get("reason") or "").strip()
        vtype          = data.get("type", "방문자")  # 방문자 / 협력사
        is_admin       = bool(data.get("requested_by_admin", False))

        if not all([applicant_id, applicant_name, date_str, reason]):
            return jsonify({"error": "필수 값 누락"}), 400

        # ❶ 전송된 값만 읽기 (None 허용)
        breakfast = data.get("breakfast")   # None → 보내지 않음
        lunch     = data.get("lunch")
        dinner    = data.get("dinner")

        with sqlite3.connect(DATABASE) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # ❷ 기존 레코드 조회 (있을 수도, 없을 수도)
            cur.execute("""
              SELECT * FROM visitors
              WHERE applicant_id = ? AND date = ? AND type = ?
            """, (applicant_id, date_str, vtype))
            row = cur.fetchone()

            # ❸ 최종 저장할 수량 계산 함수
            def final_qty(old, new, meal):
                if new is None:                 # 보내지 않았으면 그대로
                    return old
                # 마감됐으면(관리자 제외) 그대로
                if not is_admin and is_expired(meal, date_str):
                    return old
                return int(new)

            if row:  # ⇢ 재신청/수정
                breakfast_final = final_qty(row["breakfast"], breakfast, "breakfast")
                lunch_final     = final_qty(row["lunch"],     lunch,     "lunch")
                dinner_final    = final_qty(row["dinner"],    dinner,    "dinner")
            else:    # ⇢ 최초 신청
                breakfast_final = int(breakfast or 0)
                lunch_final     = int(lunch or 0)
                dinner_final    = int(dinner or 0)

            # ❹ INSERT … ON CONFLICT → 전송한 컬럼만 업데이트
            fields = ["applicant_id", "applicant_name", "date",
                      "reason", "last_modified", "type"]
            placeholders = "?, ?, ?, ?, CURRENT_TIMESTAMP, ?"
            values = [applicant_id, applicant_name, date_str, reason, vtype]

            # 식사 필드는 실제로 보냈을 때만 포함
            for col, val, sent in [
                ("breakfast", breakfast_final, breakfast is not None),
                ("lunch",     lunch_final,     lunch     is not None),
                ("dinner",    dinner_final,    dinner    is not None)
            ]:
                if sent:
                    fields.append(col)
                    placeholders += ", ?"
                    values.append(val)

            cur.execute(f"""
              INSERT INTO visitors ({', '.join(fields)})
              VALUES ({placeholders})
              ON CONFLICT(applicant_id, date, type)
              DO UPDATE SET
                {', '.join(f"{c}=excluded.{c}" for c in fields
                           if c not in ('applicant_id','applicant_name','date','type'))}
            """, values)
            conn.commit()

        return jsonify({"message": "저장 완료"}), 201

    except Exception as e:
        print("❌ save_visitors 오류:", e)
        return jsonify({"error": "저장 실패"}), 500


# ✅ [3] GET /visitors - 신청 현황 조회
@app.route("/visitors", methods=["GET"])
def get_visitors():
    applicant_id = request.args.get("id")
    start = request.args.get("start")
    end = request.args.get("end")

    if not (applicant_id and start and end):
        return jsonify({"error": "파라미터 부족"}), 400

    conn = get_db_connection()
    cursor = conn.execute("""
        SELECT id, date, breakfast, lunch, dinner, reason, last_modified, type
        FROM visitors
        WHERE applicant_id = ? AND date BETWEEN ? AND ?
        ORDER BY date
    """, (applicant_id, start, end))

    rows = cursor.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows]), 200


# ✅ [4] DELETE /visitors/<int:id>
@app.route("/visitors/<int:vid>", methods=["DELETE"])
def delete_visitor_entry(vid):
    conn = get_db_connection()
    cursor = conn.cursor()

    # ✅ 기존 데이터 조회
    cursor.execute("SELECT * FROM visitors WHERE id = ?", (vid,))
    original = cursor.fetchone()

    if not original:
        conn.close()
        return jsonify({"error": "신청 내역 없음"}), 404

    # ✅ 로그 기록 (조건: 금주에 한함)
    date_obj = datetime.strptime(original["date"], "%Y-%m-%d").date()
    today = datetime.now(KST).date()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)

    if monday <= date_obj <= friday:
        cursor.execute("""
        INSERT INTO visitor_logs (
            applicant_id, applicant_name, date, reason, type,
            before_breakfast, before_lunch, before_dinner,
            breakfast, lunch, dinner, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        original["applicant_id"],
        original["applicant_name"],
        original["date"],
        original["reason"],
        original["type"],
        original["breakfast"],
        original["lunch"],
        original["dinner"],
        '삭제', '삭제', '삭제',
        now_kst_str()   # ✅ 여기
    ))

    cursor.execute("DELETE FROM visitors WHERE id = ?", (vid,))
    conn.commit()
    conn.close()
    return jsonify({"message": "삭제되었습니다."}), 200

# ✅ [5] 방문자 주간 신청 현황 (협력사/방문자 포함)
@app.route("/visitors/weekly")
def get_weekly_visitors():
    start = request.args.get("start")
    end = request.args.get("end")
    dept = request.args.get("dept")
    name = request.args.get("name")
    type_ = request.args.get("type")

    query = """
        SELECT v.*, e.name AS applicant_name, e.dept, e.type
        FROM visitors v
        LEFT JOIN employees e ON v.applicant_id = e.id
        WHERE v.date BETWEEN ? AND ?
    """
    params = [start, end]

    if dept:
        query += " AND e.dept LIKE ?"
        params.append(f"%{dept}%")
    if name:
        query += " AND e.name LIKE ?"
        params.append(f"%{name}%")
    if type_:
        query += " AND e.type = ?"
        params.append(type_)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return jsonify([dict(row) for row in rows])


# ✅ [6] 방문자 신청 중복 확인용 API
@app.route("/visitors/check", methods=["GET"])
def check_visitor_duplicate():
    applicant_id = request.args.get("id")
    date = request.args.get("date")
    vtype = request.args.get("type", "방문자")

    if not (applicant_id and date):
        return jsonify({"error": "필수 파라미터 누락"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # ✅ 동일한 신청자가 같은 날짜에 이미 등록했는지 확인
    cursor.execute("""
        SELECT * FROM visitors
        WHERE applicant_id = ? AND date = ? AND type = ?
    """, (applicant_id, date, vtype))

    row = cursor.fetchone()
    conn.close()

    #  exists = row["count"] > 0

    if row:
        return jsonify({
            "exists": True,
            "record": {
                "breakfast": row["breakfast"],
                "lunch": row["lunch"],
                "dinner": row["dinner"]
            }
        })
    else:
        return jsonify({ "exists": False }), 200

@app.route("/visitors/<int:visitor_id>", methods=["PUT"])
def update_visitor(visitor_id):
    try:
        data = request.json or {}

        # 1) 기존 레코드 조회
        with sqlite3.connect(DATABASE) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM visitors WHERE id = ?", (visitor_id,))
            original = cur.fetchone()
            if not original:
                return jsonify({"error": "신청 내역 없음"}), 404

        old_b, old_l, old_d = original["breakfast"], original["lunch"], original["dinner"]

        # 2) 보낸 필드만 반영
        new_b = int(data["breakfast"]) if "breakfast" in data else old_b
        new_l = int(data["lunch"])     if "lunch"     in data else old_l
        new_d = int(data["dinner"])    if "dinner"    in data else old_d
        new_reason = data.get("reason", original["reason"]).strip()

        if "reason" in data and new_reason == "":
            return jsonify({"error": "사유를 입력하세요"}), 400
        if {"breakfast", "lunch", "dinner"} & data.keys() and (new_b + new_l + new_d) == 0:
            return jsonify({"error": "모든 수량이 0입니다"}), 400

        fields, params = [], []
        for col, val in [("breakfast", new_b), ("lunch", new_l), ("dinner", new_d)]:
            if col in data:
                fields.append(f"{col} = ?")
                params.append(val)

        if "reason" in data:
            fields.append("reason = ?")
            params.append(new_reason)

        if not fields:
            return jsonify({"message": "변경 없음"}), 200

        fields.append("last_modified = CURRENT_TIMESTAMP")
        params.append(visitor_id)

        # 3) UPDATE + (조건부) 로그 INSERT
        with sqlite3.connect(DATABASE) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            cur.execute(f"UPDATE visitors SET {', '.join(fields)} WHERE id = ?", params)

            # ✅ UPDATE는 항상 커밋되도록
            conn.commit()

            # ✅ 금주 & 실제 값 변경일 때만 로그
            date_obj = datetime.strptime(original["date"], "%Y-%m-%d").date()
            today = datetime.now(KST).date()
            monday = today - timedelta(days=today.weekday())
            friday = monday + timedelta(days=4)

            changed = (old_b != new_b) or (old_l != new_l) or (old_d != new_d)

            if changed and (monday <= date_obj <= friday):
                cur.execute("""
                    INSERT INTO visitor_logs (
                        applicant_id, applicant_name, date, type, reason,
                        before_breakfast, before_lunch, before_dinner,
                        breakfast, lunch, dinner, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    original["applicant_id"],
                    original["applicant_name"],
                    original["date"],
                    original["type"],
                    new_reason,
                    old_b, old_l, old_d,
                    new_b, new_l, new_d,
                    now_kst_str()   # ✅ 여기
                ))
                conn.commit()

        return jsonify({"message": "수정 완료"}), 200

    except Exception as e:
        print("❌ 방문자 수정 오류:", e)
        return jsonify({"error": "수정 실패"}), 500


@app.route("/backup/test")
def backup_test():
    backup_db_to_github()
    return "Backup Done", 200


# ✅ 최소 응답을 위한 ping 엔드포인트
@app.route("/ping")
def ping():
    return "pong", 200


# ✅ (선택) 기본 접속 페이지 - 브라우저에서 확인용
@app.route("/")
def home():
    return "✅ Flask 백엔드 서버 정상 실행 중입니다."




# ✅ 앱 실행 진입점 (init_db로 테이블 자동 생성 → 서버 실행)
if __name__ == "__main__":
    init_db()               # 앱 시작 시 DB 테이블 없으면 자동 생성

    # clear_all_employees()  # ← 이 줄은 1회만 사용하고 주석 처리해도 됨
    # alter_employees_add_region()  # ← 딱 한 번만 실행! 지역추가
    # drop_and_recreate_visitors()
    #migrate_meals_table()
    #alter_meals_table_unique_key()
    # alter_employees_add_type()  # ✅ 여기에 추가하세요

    
    port = int(os.environ.get("PORT", 5000)) #실제사용
    app.run(host="0.0.0.0", port=port)       #실제사용

    #app.run(debug=True)     # 디버그 모드 (코드 변경 시 자동 재시작)


# # 테이블 삭제.
# def clear_all_employees():
#     conn = get_db_connection()
#     cursor = conn.cursor()
#     cursor.execute("DELETE FROM employees")
#     conn.commit()
#     conn.close()
#     print("✅ 모든 직원 데이터가 삭제되었습니다.")


# 직원 table 내 지역 추가
# def alter_employees_add_region():
#     conn = get_db_connection()
#     cursor = conn.cursor()

#     try:
#         cursor.execute("ALTER TABLE employees ADD COLUMN region TEXT DEFAULT ''")
#         print("✅ 'region' 필드 추가 완료")
#     except Exception as e:
#         print("⚠️ 'region' 필드 추가 실패 또는 이미 존재함:", e)

#     conn.commit()
#     conn.close()


# table삭제 후 재실행
# DB_FILE = os.path.join(os.path.dirname(__file__), "db.sqlite")
# 
# def drop_and_recreate_visitors():
#     with sqlite3.connect(DB_FILE) as conn:
#         cursor = conn.cursor()
#         print("⚠️ 기존 visitors 테이블을 삭제하고 재생성합니다.")
#         cursor.execute("DROP TABLE IF EXISTS visitors")
#         cursor.execute("""
#             CREATE TABLE visitors (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 applicant_id TEXT NOT NULL,
#                 applicant_name TEXT NOT NULL,
#                 date TEXT NOT NULL,
#                 breakfast INTEGER DEFAULT 0,
#                 lunch INTEGER DEFAULT 0,
#                 dinner INTEGER DEFAULT 0,
#                 reason TEXT NOT NULL,
#                 last_modified TEXT DEFAULT CURRENT_TIMESTAMP,
#                 type TEXT NOT NULL,  -- 방문자 / 협력사
#                 UNIQUE(applicant_id, date, type)
#             )
#         """)
#         conn.commit()


# # 앱 시작 시 한 번만 실행되면 됩니다.
# def add_unique_index():
#     conn = get_db_connection()
#     cursor = conn.cursor()
#     cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_user_date_unique ON meals(user_id, date);")
#     conn.commit()
#     conn.close()
#     print("✅ meals 테이블에 UNIQUE 인덱스 추가 완료")

# add_unique_index()  # ⭐️ 이 라인도 app.py에 임시로 추가하세요.


#def list_tables():
#    conn = sqlite3.connect("db.sqlite")
#    cursor = conn.cursor()
#    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
#    tables = cursor.fetchall()
#    print("📋 현재 DB에 있는 테이블 목록:", tables)
#    conn.close()

#list_tables()

#def alter_employee_table():
#    conn = get_db_connection()
#    cursor = conn.cursor()

#    try:
#        cursor.execute("ALTER TABLE employees ADD COLUMN rank TEXT DEFAULT ''")
#        print("✅ 'rank' 컬럼 추가 완료")
#    except Exception as e:
#        print("⚠️ 'rank' 컬럼 추가 실패 또는 이미 존재:", e)

#    try:
#        cursor.execute("ALTER TABLE employees ADD COLUMN password TEXT DEFAULT ''")
#        print("✅ 'password' 컬럼 추가 완료")
#    except Exception as e:
#        print("⚠️ 'password' 컬럼 추가 실패 또는 이미 존재:", e)

#    conn.commit()
#    conn.close()

# 실행 (1회만)
#alter_employee_table()

# def migrate_meals_table():
#     conn = get_db_connection()
#     cursor = conn.cursor()

#     # ✅ 기존 테이블 백업
#     cursor.execute("DROP TABLE IF EXISTS meals_backup")
#     cursor.execute("CREATE TABLE meals_backup AS SELECT * FROM meals")
#     print("✅ meals 백업 완료")

#     # ✅ 새 테이블 생성 (name, dept 제거됨)
#     cursor.execute("""
#         CREATE TABLE IF NOT EXISTS meals_new (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             user_id TEXT NOT NULL,
#             date TEXT NOT NULL,
#             breakfast INTEGER DEFAULT 0,
#             lunch INTEGER DEFAULT 0,
#             dinner INTEGER DEFAULT 0,
#             FOREIGN KEY (user_id) REFERENCES employees(id)
#         )
#     """)
#     print("✅ meals_new 테이블 생성")

#     # ✅ 기존 데이터 복사
#     cursor.execute("""
#         INSERT INTO meals_new (user_id, date, breakfast, lunch, dinner)
#         SELECT user_id, date, breakfast, lunch, dinner FROM meals
#     """)
#     print("✅ 데이터 복사 완료")

#     # ✅ 기존 테이블 제거 및 이름 변경
#     cursor.execute("DROP TABLE meals")
#     cursor.execute("ALTER TABLE meals_new RENAME TO meals")
#     print("✅ 테이블 교체 완료")

#     conn.commit()
#     conn.close()

# def alter_meals_table_unique_key():
#     conn = get_db_connection()
#     cursor = conn.cursor()

#     # 1. 기존 테이블 백업
#     cursor.execute("DROP TABLE IF EXISTS meals_backup")
#     cursor.execute("CREATE TABLE meals_backup AS SELECT * FROM meals")
#     print("✅ meals 백업 완료")

#     # 2. 새 테이블 생성 (UNIQUE 제약 포함)
#     cursor.execute("""
#         CREATE TABLE IF NOT EXISTS meals_new (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             user_id TEXT NOT NULL,
#             date TEXT NOT NULL,
#             breakfast INTEGER DEFAULT 0,
#             lunch INTEGER DEFAULT 0,
#             dinner INTEGER DEFAULT 0,
#             FOREIGN KEY (user_id) REFERENCES employees(id),
#             UNIQUE(user_id, date)
#         )
#     """)
#     print("✅ meals_new 테이블 생성")

#     # 3. 기존 데이터 복사
#     cursor.execute("""
#         INSERT INTO meals_new (user_id, date, breakfast, lunch, dinner)
#         SELECT user_id, date, breakfast, lunch, dinner FROM meals
#     """)

#     # 4. 기존 테이블 교체
#     cursor.execute("DROP TABLE meals")
#     cursor.execute("ALTER TABLE meals_new RENAME TO meals")
#     print("✅ 테이블 교체 완료")

#     conn.commit()
#     conn.close()