# app.py

import sys
print("✅ 현재 실행 중인 Python:", sys.executable)

from flask import Flask, request, jsonify, send_file, session, make_response
from flask_cors import CORS
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
from collections import defaultdict
from io import BytesIO
import io
import calendar
import sqlite3
import pandas as pd
import os
import re
import shutil  
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

# [데이터 해독 익스텐션] 특수 포맷 실적 자료 해독을 위한 코어 모듈 추가
import zipfile
import xml.etree.ElementTree as ET

# ============================================================================
# 1. 환경 설정 및 상수 정의
# ============================================================================
KST = timezone(timedelta(hours=9))
def now_kst_str():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "db.sqlite")
DB_PATH = "db.sqlite"
MENU_UPLOAD_DIR = os.path.join(BASE_DIR, "uploads", "menu")
MENU_MANIFEST_PATH = os.path.join(MENU_UPLOAD_DIR, "menu_board.json")
MENU_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MENU_MAX_MB = 20   
os.makedirs(MENU_UPLOAD_DIR, exist_ok=True)

# ===== GitHub 백업 설정 =====
GITHUB_REPO   = "jwon2486/MealDB-Backup"    
GITHUB_BRANCH = "main"                      
GITHUB_PATH   = "db.sqlite"                 
GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN")
GITHUB_API    = "https://api.github.com"

# ============================================================================
# 2. 깃허브 백업 및 스냅샷 코어 시스템
# ============================================================================
def get_week_range_kst():
    now = datetime.now(KST).date()
    monday = now - timedelta(days=now.weekday())
    friday = monday + timedelta(days=4)
    return monday, friday

def create_db_snapshot():
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(BASE_DIR, "db_backups")
        os.makedirs(backup_dir, exist_ok=True)
        snapshot_path = os.path.join(backup_dir, f"db_{ts}.sqlite")
        shutil.copy2(DATABASE, snapshot_path)    
        return snapshot_path
    except Exception as e:
        print("❌ DB 스냅샷 생성 실패:", e)
        return None

def upload_file_to_github(file_path):
    if not GITHUB_TOKEN:
        print("⚠️ GITHUB_TOKEN 환경변수가 설정되지 않았습니다. 백업 건너뜀.")
        return

    with open(file_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode("utf-8")

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"

    sha = None
    get_resp = requests.get(url, headers=headers, params={"ref": GITHUB_BRANCH})
    if get_resp.status_code == 200:
        sha = get_resp.json().get("sha")

    now_kst_iso = datetime.now(KST).isoformat()
    now_kst_string = datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')

    payload = {
        "message": f"Automated db backup - {now_kst_string} KST",
        "content": content_b64,
        "branch": GITHUB_BRANCH,
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
    snapshot = create_db_snapshot()
    if snapshot:
        upload_file_to_github(snapshot)

def backup_worker_midnight():
    while True:
        now_kst = datetime.now(KST)
        target_hours = [2, 5, 8, 11, 14, 17, 20, 23]
        next_hour = next((h for h in target_hours if h > now_kst.hour), target_hours[0])
        
        if next_hour <= now_kst.hour:
            next_run_kst = (now_kst + timedelta(days=1)).replace(
                hour=next_hour, minute=0, second=0, microsecond=0
            )
        else:
            next_run_kst = now_kst.replace(
                hour=next_hour, minute=0, second=0, microsecond=0
            )
            
        wait_seconds = (next_run_kst - now_kst).total_seconds()
        print(f"🕛 [백업] 다음 예약 실행(KST): {next_run_kst.strftime('%Y-%m-%d %H:%M:%S')} (대기 {int(wait_seconds)}초)")
        
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        try:
            print(f"⏱ [백업] {next_run_kst.hour}시 정기 DB 백업 실행(KST) ...")
            backup_db_to_github()
        except Exception as e:
            print(f"❌ [백업] {next_run_kst.hour}시 백업 중 오류:", e)
        
        time.sleep(1)

# ============================================================================
# 3. 식단표 매니페스트 관리 유틸
# ============================================================================
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

# ============================================================================
# 4. Flask 인스턴스 초기화 및 CORS 구성
# ============================================================================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "snsys_meal_secret_fallback_key")
CORS(app)

def get_db_connection():
     conn = sqlite3.connect("db.sqlite")
     conn.row_factory = sqlite3.Row
     return conn

def init_db_deadline_extensions(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS deadline_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    default_settings = [
        ("breakfast_days_before", "1"), ("breakfast_time", "09:00"),  
        ("lunch_days_before", "0"),     ("lunch_time", "10:30"),      
        ("dinner_days_before", "0"),    ("dinner_time", "14:30"),     
        ("next_week_day_of_week", "3"), 
        ("next_week_time", "16:00")     
    ]
    for key, val in default_settings:
        cursor.execute("INSERT OR IGNORE INTO deadline_settings (key, value) VALUES (?, ?)", (key, val))

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS holidays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,  
            date TEXT NOT NULL UNIQUE,             
            description TEXT                       
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,  
            user_id TEXT NOT NULL,                 
            date TEXT NOT NULL,                    
            breakfast INTEGER DEFAULT 0,           
            lunch INTEGER DEFAULT 0,               
            dinner INTEGER DEFAULT 0,              
            created_at TEXT,
            FOREIGN KEY (user_id) REFERENCES employees(id), 
            UNIQUE(user_id, date)                  
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id TEXT PRIMARY KEY,       
            name TEXT NOT NULL,        
            type TEXT DEFAULT '직영',    
            dept TEXT NOT NULL,         
            rank TEXT DEFAULT '',      
            region TEXT DEFAULT '',      
            level INTEGER DEFAULT 1,      
            password TEXT DEFAULT ''  
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS meal_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_id TEXT NOT NULL,
            date TEXT NOT NULL,
            meal_type TEXT NOT NULL,  
            before_status INTEGER,
            after_status INTEGER,
            changed_at TEXT DEFAULT (datetime('now', 'localtime'))  
         )
    """)

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
            type TEXT NOT NULL,  
            UNIQUE(applicant_id, date, type)  
            )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS visitor_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            applicant_id TEXT,
            applicant_name TEXT,
            date TEXT,
            reason TEXT,
            type TEXT,  
            before_breakfast INTEGER,
            before_lunch INTEGER,
            before_dinner INTEGER,
            breakfast INTEGER,
            lunch INTEGER,
            dinner INTEGER,
            updated_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', '+9 hours'))
        );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS selfcheck (
        user_id TEXT NOT NULL,
        date TEXT NOT NULL,
        checked INTEGER DEFAULT 0,
        created_at TEXT,
        PRIMARY KEY (user_id, date)
    )
    """)

    init_db_deadline_extensions(cursor)

    conn.commit()
    conn.close()

# ============================================================================
# 5. 실시간 보정용 서버 시각 엔드포인트 API
# ============================================================================
@app.route("/api/server-time", methods=["GET"])
def get_server_time():
    return jsonify({
        "server_time": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
        "server_date": datetime.now(KST).strftime("%Y-%m-%d")
    }), 200
    
# ============================================================================
# 6. 마감시간 조건 동적 파싱 인프라
# ============================================================================
@app.route("/admin/api/deadlines", methods=["GET"])
def get_deadlines():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM deadline_settings")
        rows = cursor.fetchall()
        conn.close()
        return jsonify({row["key"]: row["value"] for row in rows}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin/api/deadlines", methods=["POST"])
def save_deadlines():
    data = request.get_json() or {}
    requester_id = data.get("requester_id") 
    
    if not requester_id:
        print("🚨 [보안 위반 감시] 사번 정보가 누락된 익명의 마감 변경 시도가 차단되었습니다.")
        return jsonify({"error": "인증 정보가 올바르지 않습니다."}), 401

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT level, name, dept FROM employees WHERE id = ?", (requester_id,))
        user = cursor.fetchone()
        
        if not user or int(user["level"]) != 3:
            u_name = user["name"] if user else "알수없음"
            u_dept = user["dept"] if user else "알수없음"
            print(f"🔥 [보안 경고] 일반 유저 권한 우회/API 변조 시도 감시됨! 사번: {requester_id}, 이름: {u_name}({u_dept})")
            return jsonify({"error": "권한이 없습니다. 최고 관리자만 접근 가능합니다."}), 403

        settings = data.get("settings", {})
        for key, value in settings.items():
            cursor.execute("""
                INSERT INTO deadline_settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (key, str(value)))
        conn.commit()
        print(f"✅ [설정 변경 기록] 최고 관리자 {user['name']}({user['dept']})님이 마감 제어 규칙을 수정했습니다.")
        return jsonify({"message": "금주 및 차주 마감 제어 규칙이 시스템에 안전하게 반영되었습니다."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

def is_meal_expired_db(meal_type, date_str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM deadline_settings")
    settings = {row["key"]: row["value"] for row in cursor.fetchall()}
    conn.close()
    
    if not settings:
        return True 
        
    m_type = meal_type.strip()
    if m_type in ("조식", "breakfast"):
        prefix = "breakfast"
    elif m_type in ("중식", "lunch", "점심"):
        prefix = "lunch"
    elif m_type in ("석식", "dinner", "저녁"):
        prefix = "dinner"
    else:
        return True

    days_before = int(settings.get(f"{prefix}_days_before", 0))
    time_str = settings.get(f"{prefix}_time", "00:00")
    
    try:
        hour, minute = map(int, time_str.split(":"))
        meal_date = datetime.strptime(date_str, "%Y-%m-%d")
        deadline = meal_date - timedelta(days=days_before)
        deadline = deadline.replace(hour=hour, minute=minute, second=0, microsecond=0, tzinfo=KST)
        return datetime.now(KST) > deadline 
    except Exception as e:
        print(f"❌ 마감 계산 파싱 에러 ({meal_type}, {date_str}):", e)
        return True    

def is_expired(meal_type, date_str):
    return is_meal_expired_db(meal_type, date_str)

def is_this_week(date_str):
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = datetime.now(KST).date()
        monday = today - timedelta(days=today.weekday())  
        friday = monday + timedelta(days=4)               
        return monday <= target <= friday
    except:
        return False

# ============================================================================
# 7. 식단표 게시판 & DB 백업 유틸 API 엔드포인트
# ============================================================================
@app.route('/admin/db/download', methods=['GET'])
def download_database():
    db_path = os.path.join(os.getcwd(), 'db.sqlite')
    if os.path.exists(db_path):
        return send_file(db_path, as_attachment=True)
    else:
        return "DB 파일이 존재하지 않습니다.", 404

@app.route("/uploads/menu/<path:filename>", methods=["GET"])
def serve_menu_upload(filename):
    return send_from_directory(MENU_UPLOAD_DIR, filename)

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
        return jsonify({"message": f"{deleted_count}건 삭제 완료"}), 200
    except Exception as e:
        print("❌ 식단표 삭제 실패:", e)
        return jsonify({"error": "삭제 실패"}), 500

# ============================================================================
# 8. 공공 API 공휴일 수집 엔진
# ============================================================================
class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)

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
                "f80f73afedb3a5bd607ad7cb5a9a65bfa7975f6fd3f47d3ac0a7cadfa9e80273"  
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
                if response.status_code != 200:
                    continue
                text = response.text.lstrip()
                if text.startswith("{"):
                    data = response.json()
                    items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
                else:
                    data = xmltodict.parse(response.text)
                    items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])

                if isinstance(items, dict):
                    items = [items]

                for item in items:
                    locdate = item.get("locdate")
                    desc = item.get("dateName")
                    if locdate and desc:
                        locdate_str = str(locdate)  
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

@app.route("/holidays", methods=["GET"])
def get_holidays():
    year = request.args.get("year")  
    conn = get_db_connection()
    cursor = conn.execute("SELECT * FROM holidays WHERE strftime('%Y', date) = ?", (year,))
    holidays = cursor.fetchall()
    conn.close()
    return jsonify([dict(h) for h in holidays])

@app.route("/holidays", methods=["POST"])
def add_holiday():
    data = request.get_json()
    date = data.get("date")                              
    desc = data.get("description", "공휴일")             

    if not date:
        return jsonify({"error": "날짜는 필수입니다."}), 400

    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO holidays (date, description) VALUES (?, ?)", (date, desc))
        conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "이미 등록된 날짜입니다."}), 409
    finally:
        conn.close()
    return jsonify({"message": "공휴일이 추가되었습니다."}), 201

@app.route("/holidays", methods=["DELETE"])
def delete_holiday():
    date = request.args.get("date")  
    if not date:
        return jsonify({"error": "삭제할 날짜가 필요합니다."}), 400

    conn = get_db_connection()
    conn.execute("DELETE FROM holidays WHERE date = ?", (date,))
    conn.commit()
    conn.close()
    return jsonify({"message": "삭제되었습니다."}), 200

# ============================================================================
# 9. 식수 신청 및 데이터 처리 API 
# ============================================================================
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

            cursor.execute("""
                SELECT breakfast, lunch, dinner
                FROM meals
                WHERE user_id = ? AND date = ?
            """, (user_id, date))
            existing = cursor.fetchone()
            old_b, old_l, old_d = (0, 0, 0) if not existing else existing

            cursor.execute("""
                INSERT INTO meals (user_id, date, breakfast, lunch, dinner, created_at)
                VALUES (?, ?, ?, ?, ?, COALESCE(?, datetime('now','localtime')))
                ON CONFLICT(user_id, date) DO UPDATE SET
                    breakfast = excluded.breakfast,
                    lunch     = excluded.lunch,
                    dinner    = excluded.dinner,
                    created_at = COALESCE(meals.created_at, excluded.created_at)
            """, (user_id, date, breakfast, lunch, dinner, created_at_in))

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
                print(f"❌ 로그 기록 실패 (date={date}, user={user_id}):", e)

        conn.commit()
        conn.close()
        return jsonify({"message": "식수 저장 완료"}), 201
    except Exception as e:
        print("❌ 식수 저장 실패:", e)
        return jsonify({"error": str(e)}), 500
    
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

@app.route('/selfcheck', methods=['GET'])
def get_selfcheck():
    user_id = request.args.get('user_id')  
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

@app.route('/selfcheck', methods=['POST'])
def post_selfcheck():
    user_id = request.json.get('user_id')
    date = request.json.get('date')
    checked = request.json.get('checked')
    created_at_in = request.json.get('created_at')
    force_update = request.json.get('force_update', False)  

    if not user_id or not date:
        return jsonify({'error': 'Missing session or date'}), 400

    conn = get_db_connection()
    existing = conn.execute(
        'SELECT 1 FROM selfcheck WHERE user_id = ? AND date = ?',
        (user_id, date)
    ).fetchone()

    if existing:
        if force_update:
            conn.execute("""
                UPDATE selfcheck
                   SET checked = ?, created_at = ?
                 WHERE user_id = ? AND date = ?
            """, (checked, created_at_in, user_id, date))
        else:
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

@app.route("/update_meals", methods=["POST"])
def update_meals():
    data = request.get_json()
    meals = data.get("meals", [])  

    conn = get_db_connection()
    cursor = conn.cursor()
    for meal in meals:
        user_id = meal.get("user_id")
        date = meal.get("date")
        breakfast = int(meal.get("breakfast", 0))
        lunch = int(meal.get("lunch", 0))
        dinner = int(meal.get("dinner", 0))

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

@app.route("/meals", methods=["GET"])
def get_user_meals():
    user_id = request.args.get("user_id")
    start_date = request.args.get("start")
    end_date = request.args.get("end")

    if not user_id or not start_date or not end_date:
        return jsonify({"error": "user_id, start, end는 필수입니다."}), 400

    conn = get_db_connection()
    cursor = conn.execute("""
        SELECT m.date, m.breakfast, m.lunch, m.dinner, m.created_at,   
               e.name, e.dept, e.rank
        FROM meals m
        JOIN employees e ON m.user_id = e.id
        WHERE m.user_id = ? AND m.date BETWEEN ? AND ?
    """, (user_id, start_date, end_date))
    rows = cursor.fetchall()
    conn.close()

    result = {}
    for row in rows:
        result[row["date"]] = {
            "breakfast": row["breakfast"] == 1,
            "lunch"    : row["lunch"] == 1,
            "dinner"   : row["dinner"] == 1,
            "name"     : row["name"],
            "dept"     : row["dept"],
            "rank"     : row["rank"],
            "created_at": row["created_at"],   
        }
    return jsonify(result), 200

# ============================================================================
# 10. 관리자 권한 전용 어드민 API 포트
# ============================================================================
@app.route("/admin/meals", methods=["GET"])
def admin_get_meals():
    start = request.args.get("start")
    end = request.args.get("end")
    mode = request.args.get("mode", "apply")  
    
    if not start or not end:
        return jsonify({"error": "start, end는 필수입니다."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if mode == "all":
            cursor.execute("""
                SELECT e.id AS user_id, e.name, e.dept, e.region, m.date,
                    IFNULL(m.breakfast, 0) AS breakfast, IFNULL(m.lunch, 0) AS lunch, IFNULL(m.dinner, 0) AS dinner
                FROM employees e
                LEFT JOIN meals m ON e.id = m.user_id AND m.date BETWEEN ? AND ?
                WHERE e.type = '직영'
                ORDER BY e.dept ASC, e.name ASC, m.date ASC
            """, (start, end))
        else:
            cursor.execute("""
                SELECT m.user_id, e.name, e.dept, e.region, m.date, m.breakfast, m.lunch, m.dinner
                FROM meals m
                JOIN employees e ON m.user_id = e.id
                WHERE m.date BETWEEN ? AND ? AND e.type = '직영'
                ORDER BY e.dept ASC, e.name ASC, m.date ASC
            """, (start, end))

        rows = cursor.fetchall()
        conn.close()
        return jsonify([dict(row) for row in rows]), 200
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500

def safe_int(val):
    try: return int(val)
    except: return 0

@app.route("/admin/edit_meals", methods=["POST"])
def admin_edit_meals():
    data = request.get_json()
    meals = data.get("meals", [])
    if not meals:
        return jsonify({"error": "meals 데이터가 필요합니다."}), 400

    today = datetime.now(KST).date()  
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

        cursor.execute("SELECT breakfast, lunch, dinner FROM meals WHERE user_id = ? AND date = ?", (user_id, date_str))
        original = cursor.fetchone()
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

        cursor.execute("DELETE FROM meals WHERE user_id = ? AND date = ?", (user_id, date_str))
        cursor.execute("INSERT INTO meals (user_id, date, breakfast, lunch, dinner) VALUES (?, ?, ?, ?, ?)",
                       (user_id, date_str, breakfast, lunch, dinner))

    conn.commit()
    conn.close()
    return jsonify({"message": f"{len(meals)}건이 수정되었습니다."}), 201

@app.route("/admin/employees", methods=["GET"])
def get_employees():
    name = request.args.get("name", "").strip()
    conn = get_db_connection()
    if name:
        cursor = conn.execute("SELECT * FROM employees WHERE name = ?", (name,))
    else:
        cursor = conn.execute("SELECT * FROM employees")
    employees = cursor.fetchall()
    conn.close()
    return jsonify([dict(emp) for emp in employees])

@app.route("/admin/employees", methods=["POST"])
def add_employee():
    data = request.get_json()
    emp_id = data.get("id")
    name = data.get("name")
    dept = data.get("dept")
    rank = data.get("rank", "")
    emp_type = data.get("type", "직영")  
    emp_region = data.get("region", "에코센터")  
    level = int(data.get("level", 1))
    if level not in (1, 2, 3): level = 1

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
    finally:
        conn.close()

@app.route("/admin/employees/<emp_id>", methods=["PUT"])
def update_employee(emp_id):
    data = request.get_json()
    name = data.get("name")
    dept = data.get("dept")
    rank = data.get("rank", "")
    emp_type = data.get("type", "직영")  
    emp_region = data.get("region", "에코센터")  
    level = int(data.get("level", 1))
    if level not in (1, 2, 3): level = 1

    if not emp_id or not name or not dept or not emp_type or not emp_region:
        return jsonify({"error": "입력값 부족"}), 400

    conn = get_db_connection()
    conn.execute("UPDATE employees SET name = ?, dept = ?, rank = ?, type = ?, region = ?, level = ? WHERE id = ?",
            (name, dept, rank, emp_type, emp_region, level, emp_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True}), 200

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
    if not file.filename.endswith((".csv", ".xlsx")):
        return jsonify({"error": "지원되지 않는 파일 형식입니다."}), 400

    try:
        df = pd.read_csv(file) if file.filename.endswith(".csv") else pd.read_excel(file)
        if not {"id", "name", "dept", "type", "region"}.issubset(set(df.columns)):
            return jsonify({"error": "파일 필수 필드 유실"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        for _, row in df.iterrows():
            cursor.execute("""
                INSERT INTO employees (id, name, dept, rank, type, region) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, dept=excluded.dept, type=excluded.type, region=excluded.region, rank=excluded.rank
            """, (row["id"], row["name"], row["dept"], row["rank"] if "rank" in row else "", row["type"], row["region"]))
        conn.commit()
        cursor = conn.execute("SELECT * FROM employees")
        employees = [dict(emp) for emp in cursor.fetchall()]
        conn.close()
        return jsonify(employees), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/admin/employees/template")
def download_employee_template():
    filename = "employee_template.xlsx"
    filepath = os.path.join(os.getcwd(), filename)
    if os.path.exists(filepath): os.remove(filepath)
    df = pd.DataFrame(columns=["사번", "이름", "부서", "직영/협력사/방문자" , "에코센터/테크센터/기타","직급(옵션)"])
    df.to_excel(filepath, index=False)
    return send_file(filepath, as_attachment=True)

@app.route("/login_check")
def login_check():
    emp_id = request.args.get("id")
    name = request.args.get("name")
    if not emp_id or not name:
        return jsonify({"error": "사번과 이름을 모두 입력하세요"}), 400

    conn = get_db_connection()
    cursor = conn.execute("SELECT id, name, dept, rank, type, level, region FROM employees WHERE id = ? AND name = ?", (emp_id, name))
    user = cursor.fetchone()
    conn.close()

    if user:
        return jsonify({"valid": True, "id": user["id"], "name": user["name"], "dept": user["dept"], "rank": user["rank"], "type": user["type"], "level": user["level"], "region": user["region"]})
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
            SELECT l.date, e.dept, e.name, l.meal_type, l.before_status, l.after_status, l.changed_at
            FROM meal_logs l JOIN employees e ON l.emp_id = e.id
            WHERE l.date BETWEEN ? AND ? AND e.name LIKE ? AND e.dept LIKE ?
            ORDER BY l.date ASC, CASE l.meal_type WHEN 'breakfast' THEN 1 WHEN 'lunch' THEN 2 WHEN 'dinner' THEN 3 ELSE 4 END, e.dept ASC, e.name ASC, l.changed_at DESC
        """, (start, end, f"%{name}%", f"%{dept}%"))
        return jsonify([dict(row) for row in cursor.fetchall()]), 200
    except Exception as e:
        return jsonify({"error": "로그 조회 실패"}), 500
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
            SELECT l.date, e.dept, e.name, l.meal_type, l.before_status, l.after_status, l.changed_at
            FROM meal_logs l JOIN employees e ON l.emp_id = e.id
            WHERE l.date BETWEEN ? AND ? AND e.name LIKE ? AND e.dept LIKE ?
        """, (start, end, f"%{name}%", f"%{dept}%"))
        
        logs = [dict(row) for row in cursor.fetchall()]
        if not logs: return "데이터 없음", 404
        df = pd.DataFrame(logs)
        df["식수일"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df["식사유형"] = df["meal_type"].map({"breakfast": "아침", "lunch": "점심", "dinner": "저녁"})
        df["변경전"] = df["before_status"].map({0: "미신청", 1: "신청"})
        df["변경후"] = df["after_status"].map({0: "미신청", 1: "신청"})
        
        final_df = df[["식수일", "식사유형", "dept", "name", "변경전", "변경후", "changed_at"]].rename(columns={"dept":"부서","name":"이름","changed_at":"변경시간"})
        output = BytesIO()
        final_df.to_excel(output, index=False)
        output.seek(0)
        return send_file(output, as_attachment=True, download_name="meal_log_export.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route("/admin/visitor_logs", methods=["GET"])
def get_visitor_logs():
    start = request.args.get("start")
    end = request.args.get("end")
    name = request.args.get("name", "").strip()
    dept = request.args.get("dept", "").strip()
    vtype = request.args.get("type", "").strip()

    try:
        conn = get_db_connection()
        query = """
            SELECT l.date, e.dept, l.applicant_name, l.before_breakfast, l.before_lunch, l.before_dinner, l.breakfast, l.lunch, l.dinner, l.updated_at
            FROM visitor_logs l LEFT JOIN employees e ON l.applicant_id = e.id WHERE 1 = 1
        """
        params = []
        if start and end: query += " AND l.date BETWEEN ? AND ?"; params.extend([start, end])
        if name: query += " AND l.applicant_name LIKE ?"; params.append(f"%{name}%")
        if dept: query += " AND IFNULL(e.dept, '') LIKE ?"; params.append(f"%{dept}%")
        if vtype: query += " AND l.type = ?"; params.append(vtype)

        query += " ORDER BY l.date ASC, l.updated_at DESC"
        cursor = conn.execute(query, params)
        return jsonify([dict(row) for row in cursor.fetchall()]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route("/admin/visitor_logs/download", methods=["GET"])
def download_visitor_logs_excel():
    start, end = request.args.get("start"), request.args.get("end")
    name, dept, vtype = request.args.get("name", ""), request.args.get("dept", ""), request.args.get("type", "")

    conn = get_db_connection()
    try:
        query = """
            SELECT l.date, e.dept, l.applicant_name, l.before_breakfast, l.before_lunch, l.before_dinner, l.breakfast, l.lunch, l.dinner, l.updated_at
            FROM visitor_logs l LEFT JOIN employees e ON l.applicant_id = e.id WHERE l.date BETWEEN ? AND ?
        """
        params = [start, end]
        cursor = conn.execute(query, params)
        df = pd.DataFrame([dict(row) for row in cursor.fetchall()])
        if df.empty: return "데이터 분량 부족", 404

        output = BytesIO()
        df.to_excel(output, index=False)
        output.seek(0)
        return send_file(output, as_attachment=True, download_name="visitor_logs.xlsx")
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# ============================================================================
# 11. 식수 분석 실적 대조 및 통계 분석 대시보드 API
# ============================================================================
@app.route("/admin/stats/period", methods=["GET"])
def get_stats_period():
    start, end = request.args.get("start"), request.args.get("end")
    if not start or not end: return jsonify({"error": "기간 조건 부족"}), 400

    conn = get_db_connection()
    cursor = conn.execute("""
        SELECT date, SUM(breakfast) as breakfast, SUM(lunch) as lunch, SUM(dinner) as dinner
        FROM (SELECT date, breakfast, lunch, dinner FROM meals UNION ALL SELECT date, breakfast, lunch, dinner FROM visitors)
        WHERE date BETWEEN ? AND ? GROUP BY date ORDER BY date
    """, (start, end))
    
    result = []
    for row in cursor.fetchall():
        wk = datetime.strptime(row["date"], "%Y-%m-%d").weekday()
        result.append({"date": row["date"], "day": ["월","화","수","목","금","토","일"][wk], "breakfast": row["breakfast"], "lunch": row["lunch"], "dinner": row["dinner"]})
    conn.close()
    return jsonify(result), 200

# [API 개편] 특수 서식 포맷 자료와 정식 XLSX를 통합 판별하는 정산 엔진
@app.route('/admin/stats/compare-auto', methods=['POST'])
def compare_auto():
    if 'actual' not in request.files: 
        return jsonify({"error": "실적자료 누락"}), 400
    file_actual = request.files['actual']
    partner_depts = ['DEX', 'FBF-ENG', '하이테크주택', '신명전력', '주노텍']

    clean_name = lambda n: re.sub(r'\s+', '', re.sub(r'([가-힣]{2,4})[a-zA-Z0-9]$', r'\1', str(n).strip())) if n else ""
    clean_dept = lambda d: re.sub(r'\(.*?\)', '', str(d).strip()).strip() if d else ""

    try:
        file_bytes = file_actual.read()
        in_memory_file = io.BytesIO(file_bytes)
        
        if zipfile.is_zipfile(in_memory_file):
            print("📊 [데이터 라이브러리] 특수 포맷 실적 자료 데이터 분석을 가동합니다.")
            in_memory_file.seek(0)
            
            with zipfile.ZipFile(in_memory_file, 'r') as z:
                if "xl/worksheets/sheet1.xml" in z.namelist():
                    xml_data = z.read("xl/worksheets/sheet1.xml")
                    root_xml = ET.fromstring(xml_data)
                    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
                    
                    rows_list = []
                    for row_node in root_xml.findall(f".//{{{ns}}}row"):
                        row_cells = {}
                        for c_node in row_node.findall(f".//{{{ns}}}c"):
                            cell_ref = c_node.get("r")
                            c_char = "".join([ch for ch in cell_ref if ch.isalpha()])
                            
                            t_node = c_node.find(f".//{{{ns}}}t")
                            if t_node is not None and t_node.text:
                                row_cells[c_char] = t_node.text.strip()
                        
                        if row_cells:
                            # 💡 [핵심 버그 수정] 복사할 때 딸려 들어온 제목 행("식사일자")은 데이터 목록에 넣지 않고 패스합니다.
                            if row_cells.get('A') == "식사일자":
                                continue
                            rows_list.append(row_cells)
                    
                    df_actual = pd.DataFrame(rows_list)
                    df_actual.rename(columns={'A': '식사일자', 'B': '이름', 'C': '부서', 'D': '식사구분'}, inplace=True)
                else:
                    return jsonify({"error": "실적 데이터 파일 내부에 유효한 데이터 구조가 없습니다."}), 400
        else:
            print("📊 [표준 로드 라이브러리] 표준형 엑셀(XLSX) 포맷으로 실적 데이터를 변환합니다.")
            in_memory_file.seek(0)
            df_actual = pd.read_excel(in_memory_file, engine='openpyxl')
            df_actual.columns = df_actual.columns.str.strip()
            if '조직' in df_actual.columns: df_actual.rename(columns={'조직': '부서'}, inplace=True)

        # 💡 "식사일자" 글자가 필터링되므로, 아래 pd.to_datetime 연산이 에러 없이 깨끗하게 통과합니다.
        df_actual['부서'] = df_actual['부서'].apply(clean_dept)
        df_actual['이름'] = df_actual['이름'].apply(clean_name)
        df_actual['식사일자'] = pd.to_datetime(df_actual['식사일자']).dt.strftime('%Y-%m-%d')
        
        start_date, end_date = df_actual['식사일자'].min(), df_actual['식사일자'].max()

        conn = sqlite3.connect(DATABASE)
        df_db = pd.read_sql_query("SELECT m.date as 식사일자, e.name as 이름, e.dept as 부서, m.breakfast, m.lunch, m.dinner FROM meals m JOIN employees e ON m.user_id = e.id WHERE m.date BETWEEN ? AND ?", conn, params=(start_date, end_date))
        conn.close()

        df_db['부서'] = df_db['부서'].apply(clean_dept)
        applied_rows = []
        for _, row in df_db.iterrows():
            c_name = clean_name(row['이름'])
            if row['breakfast'] == 1: applied_rows.append({'식사일자': row['식사일자'], '이름': c_name, '부서': row['부서'], '식사구분': '조식'})
            if row['lunch'] == 1: applied_rows.append({'식사일자': row['식사일자'], '이름': c_name, '부서': row['부서'], '식사구분': '중식'})
            if row['dinner'] == 1: applied_rows.append({'식사일자': row['식사일자'], '이름': c_name, '부서': row['부서'], '식사구분': '석식'})
        
        df_applied = pd.DataFrame(applied_rows) if applied_rows else pd.DataFrame(columns=['식사일자', '이름', '부서', '식사구분'])
        
        if df_applied.empty:
            no_show = pd.DataFrame(columns=['식사일자', '이름', '부서', '식사구분'])
            unreg = df_actual.copy()
        else:
            no_show = pd.merge(df_applied, df_actual, on=['식사일자', '이름', '식사구분'], how='left', indicator=True)
            no_show = no_show[no_show['_merge'] == 'left_only'].drop(columns=['_merge']).rename(columns={'부서_x':'부서'})
            if not no_show.empty:
                no_show = no_show[['식사일자', '이름', '부서', '식사구분']]

            unreg = pd.merge(df_applied, df_actual, on=['식사일자', '이름', '식사구분'], how='right', indicator=True)
            unreg = unreg[unreg['_merge'] == 'right_only'].drop(columns=['_merge']).rename(columns={'부서_y':'부서'})
            unreg = unreg[~unreg['부서'].isin(partner_depts)]
            if not unreg.empty:
                unreg = unreg[['식사일자', '이름', '부서', '식사구분']]

        partner_summary = df_actual[df_actual['부서'].isin(partner_depts)].groupby(['식사일자', '부서', '식사구분']).size().reset_index(name='인원수')

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            no_show.to_excel(writer, sheet_name='노쇼 명단', index=False)
            unreg.to_excel(writer, sheet_name='미신청 식사', index=False)
            partner_summary.to_excel(writer, sheet_name='협력사 식사 현황', index=False)

        output.seek(0)
        excel_base64 = base64.b64encode(output.getvalue()).decode('utf-8')
        return jsonify({"success": True, "summary": {"no_show_count": len(no_show), "unreg_count": len(unreg), "partner_count": int(partner_summary['인원수'].sum()) if not partner_summary.empty else 0, "start_date": start_date, "end_date": end_date, "no_show_list": no_show.to_dict(orient='records'), "unreg_list": unreg.to_dict(orient='records'), "partner_list": partner_summary.to_dict(orient='records')}, "excel_file": excel_base64, "file_name": f"식수비교_{start_date}_{end_date}.xlsx"})
    except Exception as e:
        print("❌ 위장 데이터 연산 및 대조 분석 실패:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/admin/stats/period/excel", methods=["GET"])
def download_stats_period_excel():
    start, end = request.args.get("start"), request.args.get("end")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT date, SUM(breakfast) AS breakfast, SUM(lunch) AS lunch, SUM(dinner) AS dinner FROM (SELECT date, breakfast, lunch, dinner FROM meals UNION ALL SELECT date, breakfast, lunch, dinner FROM visitors) WHERE date BETWEEN ? AND ? GROUP BY date ORDER BY date", (start, end))
    rows = cur.fetchall()
    conn.close()

    output = BytesIO()
    df = pd.DataFrame([dict(r) for r in rows])
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="period_stats.xlsx")

@app.route("/admin/graph/week_trend")
def graph_week_trend():
    start, end = request.args.get("start"), request.args.get("end")
    conn = get_db_connection()
    cursor = conn.execute("SELECT strftime('%Y-%m-%d', date) as label, strftime('%w', date) as weekday, SUM(breakfast) as breakfast, SUM(lunch) as lunch, SUM(dinner) as dinner FROM (SELECT date, breakfast, lunch, dinner FROM meals UNION ALL SELECT date, breakfast, lunch, dinner FROM visitors) WHERE date BETWEEN ? AND ? GROUP BY date ORDER BY date", (start, end))
    res = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(res)

@app.route("/admin/stats/dept_summary")
def get_dept_summary():
    start, end = request.args.get("start"), request.args.get("end")
    conn = get_db_connection()
    m_rows = conn.execute("SELECT e.dept, e.type, m.breakfast, m.lunch, m.dinner FROM meals m JOIN employees e ON m.user_id = e.id WHERE m.date BETWEEN ? AND ?", (start, end)).fetchall()
    v_rows = conn.execute("SELECT e.dept, v.type, v.breakfast, v.lunch, v.dinner FROM visitors v JOIN employees e ON v.applicant_id = e.id WHERE v.date BETWEEN ? AND ?", (start, end)).fetchall()
    conn.close()

    summary = defaultdict(lambda: {"breakfast": 0, "lunch": 0, "dinner": 0})
    for row in m_rows + v_rows:
        dept, t = row["dept"], row["type"]
        if t == "방문자": dept = f"{dept[:2]}(방문자)"
        summary[(dept, t)]["breakfast"] += row["breakfast"]
        summary[(dept, t)]["lunch"] += row["lunch"]
        summary[(dept, t)]["dinner"] += row["dinner"]

    return jsonify([{"dept":k[0],"type":k[1],"breakfast":v["breakfast"],"lunch":v["lunch"],"dinner":v["dinner"]} for k,v in summary.items()]), 200

@app.route("/admin/stats/dept_summary/excel")
def download_dept_summary_excel():
    start, end = request.args.get("start"), request.args.get("end")
    conn = get_db_connection()
    m_rows = conn.execute("SELECT e.dept, e.type, m.breakfast, m.lunch, m.dinner FROM meals m JOIN employees e ON m.user_id = e.id WHERE m.date BETWEEN ? AND ?", (start, end)).fetchall()
    v_rows = conn.execute("SELECT e.dept, v.type, v.breakfast, v.lunch, v.dinner FROM visitors v JOIN employees e ON v.applicant_id = e.id WHERE v.date BETWEEN ? AND ?", (start, end)).fetchall()
    conn.close()

    summary = defaultdict(lambda: {"breakfast": 0, "lunch": 0, "dinner": 0})
    for row in m_rows + v_rows:
        dept, t = row["dept"], row["type"]
        if t == "방문자": dept = f"{dept[:2]}(방문자)"
        summary[(dept, t)]["breakfast"] += row["breakfast"]
        summary[(dept, t)]["lunch"] += row["lunch"]
        summary[(dept, t)]["dinner"] += row["dinner"]

    df = pd.DataFrame([{"dept":k[0],"type":k[1],"breakfast":v["breakfast"],"lunch":v["lunch"],"dinner":v["dinner"]} for k,v in summary.items()])
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="dept_summary.xlsx")

@app.route("/admin/stats/weekly_dept")
def weekly_dept_stats():
    start, end = request.args.get("start"), request.args.get("end")
    conn = get_db_connection()
    employees = conn.execute("SELECT id, name, dept, type, region FROM employees").fetchall()
    dept_members = defaultdict(list)
    for e in employees: dept_members[(e["dept"], e["type"], e["region"])].append(e["id"])

    dept_map = {}
    for (dept, type_, region), ids in dept_members.items():
        if type_ == "직영" and region != "에코센터": continue
        dept_map[dept] = {"type": type_, "dept": dept, "display_dept": dept, "total": len(ids), "days": {}}
    
    meal_rows = conn.execute("SELECT m.date, e.name, e.dept, e.type, e.region, m.breakfast, m.lunch, m.dinner FROM meals m JOIN employees e ON m.user_id = e.id WHERE m.date BETWEEN ? AND ?", (start, end)).fetchall()
    for row in meal_rows:
        date, name, dept, type_, region = row["date"], row["name"], row["dept"], row["type"], row["region"]
        dept_key = f"{dept[:4]}(출장)" if type_ == "직영" and region != "에코센터" else dept
        if dept_key not in dept_map:
            dept_map[dept_key] = {"type": type_, "dept": dept_key, "display_dept": dept_key, "total": 1, "days": {}}
        
        for meal, key in zip(["breakfast", "lunch", "dinner"], ["b", "l", "d"]):
            if row[meal] > 0:
                dept_map[dept_key]["days"].setdefault(date, {"b":[], "l":[], "d":[]})[key].append(name)

    visitor_rows = conn.execute("SELECT v.date, v.breakfast, v.lunch, v.dinner, e.name, e.dept, v.type FROM visitors v JOIN employees e ON v.applicant_id = e.id WHERE v.date BETWEEN ? AND ?", (start, end)).fetchall()
    for row in visitor_rows:
        date, name, dept, vtype = row["date"], row["name"], row["dept"], row["type"]
        dept_key = f"{dept[:2]}(방문자)" if vtype == "방문자" else dept
        if dept_key not in dept_map:
            dept_map[dept_key] = {"type": vtype, "dept": dept_key, "display_dept": dept_key, "total": 1, "days": {}}
        
        for meal, key in zip(["breakfast", "lunch", "dinner"], ["b", "l", "d"]):
            if row[meal] > 0:
                dept_map[dept_key]["days"].setdefault(date, {"b":[], "l":[], "d":[]})[key].append(f"{name}({row[meal]})")

    conn.close()
    return jsonify(list(dept_map.values()))

@app.route("/admin/stats/weekly_dept/excel")
def download_weekly_dept_excel():
    start, end = request.args.get("start"), request.args.get("end")
    conn = get_db_connection()
    rows = conn.execute("SELECT m.date, m.breakfast, m.lunch, m.dinner, e.name, e.dept, e.type FROM meals m JOIN employees e ON m.user_id = e.id WHERE m.date BETWEEN ? AND ?", (start, end)).fetchall()
    conn.close()
    
    df = pd.DataFrame([dict(r) for r in rows])
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="weekly_dept.xlsx")

@app.route("/admin/stats/pivot_excel")
def download_pivot_excel():
    start, end = request.args.get("start"), request.args.get("end")
    conn = sqlite3.connect("db.sqlite")
    df_meals = pd.read_sql_query("SELECT m.date, m.breakfast, m.lunch, m.dinner, e.name, e.dept, e.type, e.region FROM meals m JOIN employees e ON m.user_id = e.id WHERE m.date BETWEEN ? AND ?", conn, params=(start, end))
    df_visitors = pd.read_sql_query("SELECT v.applicant_name, v.date, v.breakfast, v.lunch, v.dinner, v.type, e.dept, e.type as emp_type FROM visitors v LEFT JOIN employees e ON v.applicant_id = e.id WHERE v.date BETWEEN ? AND ?", conn, params=(start, end))
    conn.close()

    eco_center, tech_center = [], []
    for _, row in df_meals.iterrows():
        if row.get("type") != "직영": continue
        base = [row["date"], row["name"], row["dept"]]
        target = eco_center if row.get("region") == "에코센터" else tech_center
        if int(row.get("breakfast", 0)) == 1: target.append(base + ["조식"])
        if int(row.get("lunch", 0)) == 1: target.append(base + ["중식"])
        if int(row.get("dinner", 0)) == 1: target.append(base + ["석식"])

    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        pd.DataFrame(eco_center, columns=["식사일자", "이름", "부서", "식사 구분"]).to_excel(writer, index=False, sheet_name="직영_에코센터")
        pd.DataFrame(tech_center, columns=["식사일자", "이름", "부서", "식사 구분"]).to_excel(writer, index=False, sheet_name="직영_출장")
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="pivot_meals.xlsx")

# ============================================================================
# 12. 방문자 전용 API 포트
# ============================================================================
@app.route("/visitors", methods=["POST"])
def save_visitors():
    try:
        data = request.json or {}
        applicant_id, applicant_name, date_str, reason = data.get("applicant_id"), data.get("applicant_name"), data.get("date"), (data.get("reason") or "").strip()
        vtype = data.get("type", "방문자")
        is_admin = bool(data.get("requested_by_admin", False))

        if not all([applicant_id, applicant_name, date_str, reason]): return jsonify({"error": "값 누락"}), 400
        breakfast, lunch, dinner = data.get("breakfast"), data.get("lunch"), data.get("dinner")

        conn = get_db_connection()
        row = conn.execute("SELECT * FROM visitors WHERE applicant_id = ? AND date = ? AND type = ?", (applicant_id, date_str, vtype)).fetchone()

        def final_qty(old, new, meal):
            if new is None or (not is_admin and is_expired(meal, date_str)): return old
            return int(new)

        b_final = final_qty(row["breakfast"] if row else 0, breakfast, "breakfast")
        l_final = final_qty(row["lunch"] if row else 0, lunch, "lunch")
        d_final = final_qty(row["dinner"] if row else 0, dinner, "dinner")

        conn.execute("""
            INSERT INTO visitors (applicant_id, applicant_name, date, reason, type, breakfast, lunch, dinner, last_modified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(applicant_id, date, type) DO UPDATE SET reason=excluded.reason, breakfast=excluded.breakfast, lunch=excluded.lunch, dinner=excluded.dinner, last_modified=CURRENT_TIMESTAMP
        """, (applicant_id, applicant_name, date_str, reason, vtype, b_final, l_final, d_final))
        conn.commit()
        conn.close()
        return jsonify({"message": "저장 완료"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/visitors", methods=["GET"])
def get_visitors():
    applicant_id, start, end = request.args.get("id"), request.args.get("start"), request.args.get("end")
    conn = get_db_connection()
    rows = conn.execute("SELECT id, date, breakfast, lunch, dinner, reason, last_modified, type FROM visitors WHERE applicant_id = ? AND date BETWEEN ? AND ? ORDER BY date", (applicant_id, start, end)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows]), 200

@app.route("/visitors/<int:vid>", methods=["DELETE"])
def delete_visitor_entry(vid):
    conn = get_db_connection()
    original = conn.execute("SELECT * FROM visitors WHERE id = ?", (vid,)).fetchone()
    if not original: conn.close(); return jsonify({"error": "내역 없음"}), 404

    date_obj = datetime.strptime(original["date"], "%Y-%m-%d").date()
    today = datetime.now(KST).date()
    if (today - timedelta(days=today.weekday())) <= date_obj <= (today - timedelta(days=today.weekday()) + timedelta(days=4)):
        conn.execute("INSERT INTO visitor_logs (applicant_id, applicant_name, date, reason, type, before_breakfast, before_lunch, before_dinner, breakfast, lunch, dinner, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '삭제', '삭제', '삭제', ?)",
                     (original["applicant_id"], original["applicant_name"], original["date"], original["reason"], original["type"], original["breakfast"], original["lunch"], original["dinner"], now_kst_str()))

    conn.execute("DELETE FROM visitors WHERE id = ?", (vid,))
    conn.commit()
    conn.close()
    return jsonify({"message": "삭제 완료"}), 200

@app.route("/visitors/weekly")
def get_weekly_visitors():
    start, end = request.args.get("start"), request.args.get("end")
    conn = get_db_connection()
    rows = conn.execute("SELECT v.*, e.name AS applicant_name, e.dept, e.type FROM visitors v LEFT JOIN employees e ON v.applicant_id = e.id WHERE v.date BETWEEN ? AND ?", (start, end)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route("/visitors/check", methods=["GET"])
def check_visitor_duplicate():
    applicant_id, date, vtype = request.args.get("id"), request.args.get("date"), request.args.get("type", "방문자")
    conn = get_db_connection()
    row = conn.execute("SELECT breakfast, lunch, dinner FROM visitors WHERE applicant_id = ? AND date = ? AND type = ?", (applicant_id, date, vtype)).fetchone()
    conn.close()
    if row: return jsonify({"exists": True, "record": dict(row)})
    return jsonify({"exists": False}), 200

@app.route("/visitors/<int:visitor_id>", methods=["PUT"])
def update_visitor(visitor_id):
    try:
        data = request.json or {}
        conn = get_db_connection()
        original = conn.execute("SELECT * FROM visitors WHERE id = ?", (visitor_id,)).fetchone()
        if not original: conn.close(); return jsonify({"error": "내역 없음"}), 404

        old_b, old_l, old_d = original["breakfast"], original["lunch"], original["dinner"]
        new_b = int(data["breakfast"]) if "breakfast" in data else old_b
        new_l = int(data["lunch"])     if "lunch"     in data else old_l
        new_d = int(data["dinner"])    if "dinner"    in data else old_d
        new_reason = data.get("reason", original["reason"]).strip()

        conn.execute("UPDATE visitors SET breakfast=?, lunch=?, dinner=?, reason=?, last_modified=CURRENT_TIMESTAMP WHERE id=?", (new_b, new_l, new_d, new_reason, visitor_id))
        
        date_obj = datetime.strptime(original["date"], "%Y-%m-%d").date()
        today = datetime.now(KST).date()
        if (old_b != new_b or old_l != new_l or old_d != new_d) and ((today - timedelta(days=today.weekday())) <= date_obj <= (today - timedelta(days=today.weekday()) + timedelta(days=4))):
            conn.execute("INSERT INTO visitor_logs (applicant_id, applicant_name, date, type, reason, before_breakfast, before_lunch, before_dinner, breakfast, lunch, dinner, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (original["applicant_id"], original["applicant_name"], original["date"], original["type"], new_reason, old_b, old_l, old_d, new_b, new_l, new_d, now_kst_str()))
        conn.commit()
        conn.close()
        return jsonify({"message": "수정 성공"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/backup/test")
def backup_test():
    backup_db_to_github()
    return "Backup Done", 200

@app.route("/ping")
def ping():
    return "pong", 200

@app.route("/")
def home():
    return "✅ Flask 백엔드 서버 정상 실행 중입니다."

# ============================================================================
# 13. 인프라 부트스트랩 지점 (스레드 세이프 최적화)
# ============================================================================
backup_thread_started = False
backup_thread_lock = threading.Lock()

def start_backup_thread():
    global backup_thread_started
    with backup_thread_lock:
        if not backup_thread_started:
            print("🚀 [백업] 안전망 분리: DB 백업 대기 워커 스레드 시동 완료")
            t = threading.Thread(target=backup_worker_midnight, daemon=True)
            t.start()
            backup_thread_started = True

if __name__ == "__main__":
    init_db()               
    start_backup_thread()   
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)