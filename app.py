# Flask: 웹 애플리케이션을 만들기 위한 마이크로 프레임워크
# request: HTTP 요청 데이터 (GET, POST 등)를 다루기 위해 사용
# jsonify: 파이썬 데이터를 JSON 형식으로 반환하기 위해 사용
# CORS: 다른 도메인/포트에서의 요청을 허용 (프론트 연동 시 필수)
# sqlite3: 가볍고 파일 기반의 내장형 데이터베이스

import sys
print("✅ 현재 실행 중인 Python:", sys.executable)

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from collections import OrderedDict
from datetime import datetime, timedelta
from collections import defaultdict
from flask import send_file
from io import BytesIO
from datetime import datetime
import calendar
import sqlite3
import pandas as pd
import os
import re
import shutil  # ✅ DB 파일 복사용


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "db.sqlite")

# Flask 앱 생성
app = Flask(__name__)


# 모든 도메인에서 CORS 허용 (프론트엔드가 localhost:3000 등에 있어도 접근 가능)
CORS(app) #프론트와 연동

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
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
        

    conn.commit()
    conn.close()


def is_this_week(date_str):
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = datetime.today().date()
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
                INSERT INTO meals (user_id, date, breakfast, lunch, dinner)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, date)
                DO UPDATE SET
                    breakfast = excluded.breakfast,
                    lunch = excluded.lunch,
                    dinner = excluded.dinner
            """, (user_id, date, breakfast, lunch, dinner))

            # 로그 기록 (금주 + 변경된 경우만)
            try:
                today = datetime.today().date()
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
        SELECT m.date, m.breakfast, m.lunch, m.dinner,
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
            "lunch": row["lunch"] == 1,
            "dinner": row["dinner"] == 1,
            "name": row["name"],
            "dept": row["dept"],
            "rank": row["rank"]
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
                    m.date,
                    IFNULL(m.breakfast, 0) AS breakfast,
                    IFNULL(m.lunch, 0) AS lunch,
                    IFNULL(m.dinner, 0) AS dinner
                FROM employees e
                LEFT JOIN meals m
                    ON e.id = m.user_id AND m.date BETWEEN ? AND ?
                ORDER BY e.dept ASC, e.name ASC, m.date ASC
            """, (start, end))
        else:
            # ✅ 신청한 직원만 조회 (기본 모드 + apply 모드)
            cursor.execute("""
                SELECT 
                    m.user_id,
                    e.name,
                    e.dept,
                    m.date,
                    m.breakfast,
                    m.lunch,
                    m.dinner
                FROM meals m
                JOIN employees e ON m.user_id = e.id
                WHERE m.date BETWEEN ? AND ?
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

    today = datetime.today().date()  # 👈 날짜 객체로 변경
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

    if not emp_id or not name or not dept or not emp_type or not emp_region:
        return jsonify({"error": "입력값 부족"}), 400

    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO employees (id, name, dept, rank, type, region) VALUES (?, ?, ?, ?, ?, ?)",
                     (emp_id, name, dept, rank, emp_type, emp_region))
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

    if not emp_id or not name or not dept or not emp_type or not emp_region:
        return jsonify({"error": "입력값 부족"}), 400

    conn = get_db_connection()
    conn.execute("UPDATE employees SET name = ?, dept = ?, rank = ?, type = ?, region = ? WHERE id = ?",
                 (name, dept, rank, emp_type, emp_region, emp_id))
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
        "SELECT id, name, dept, rank, type, level FROM employees WHERE id = ? AND name = ?",
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
             "level": user["level"]  # ✅ level 포함
            
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
    from collections import defaultdict
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
    from flask import send_file

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
def download_weekly_raw_excel():
    start = request.args.get("start")
    end = request.args.get("end")
    if not start or not end:
        return "날짜를 지정해주세요", 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # meals 테이블
        cursor.execute("""
            SELECT m.date, e.type, e.name, e.dept,
                   m.breakfast, m.lunch, m.dinner
            FROM meals m
            JOIN employees e ON m.user_id = e.id
            WHERE m.date BETWEEN ? AND ?
        """, (start, end))
        meal_rows = cursor.fetchall()

        # visitors 테이블
        cursor.execute("""
            SELECT v.date, v.type, v.applicant_name AS name, e.dept,
                   v.breakfast, v.lunch, v.dinner
            FROM visitors v
            LEFT JOIN employees e ON v.applicant_id = e.id
            WHERE v.date BETWEEN ? AND ?
        """, (start, end))
        visitor_rows = cursor.fetchall()

        records = []

        for row in meal_rows + visitor_rows:
            date = row["date"]
            type_ = row["type"]
            name = row["name"]
            dept = row["dept"] if "dept" in row.keys() and row["dept"] else ""
            # 조식, 중식, 석식 확인
            for meal_key, meal_name in [("breakfast", "조식"), ("lunch", "중식"), ("dinner", "석식")]:
                if meal_key in row.keys() and row[meal_key]:
                    records.append({
                        "구분": type_,
                        "식사일자": date,
                        "이름": name,
                        "부서": dept,
                        "식사구분": meal_name
                    })

        df = pd.DataFrame(records)
        df = df.sort_values(by=["식사일자", "부서", "이름", "식사구분"])

        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="신청자별 식사기록")

        output.seek(0)
        filename = f"신청자별_주간식사기록_{start}_to_{end}.xlsx"
        return send_file(output, as_attachment=True, download_name=filename,
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    except Exception as e:
        print("❌ 엑셀 다운로드 오류:", str(e))
        return jsonify({"error": "엑셀 다운로드 실패", "detail": str(e)}), 500

    finally:
        conn.close()








# ✅ [2] POST /visitors - 저장
@app.route("/visitors", methods=["POST"])
def save_visitors():
    data = request.get_json()

    applicant_id = data.get("applicant_id")
    applicant_name = data.get("applicant_name")
    date = data.get("date")
    breakfast = int(data.get("breakfast", 0))
    lunch = int(data.get("lunch", 0))
    dinner = int(data.get("dinner", 0))
    reason = data.get("reason", "")
    vtype = data.get("type", "방문자")              # 👉 실제 신청자 타입 저장
    is_admin = data.get("requested_by_admin", False)  # 👉 관리자 권한 여부는 별도
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not (applicant_id and applicant_name and date and reason):
        return jsonify({"error": "필수 정보 누락"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # ✅ 공휴일 체크 추가
    cursor.execute("SELECT COUNT(*) as count FROM holidays WHERE date = ?", (date,))
    if cursor.fetchone()["count"] > 0:
        conn.close()
        return jsonify({"error": f"{date}는 공휴일입니다. 신청할 수 없습니다."}), 400

      # ✅ 기존 데이터 조회
    cursor.execute("""
        SELECT breakfast, lunch, dinner FROM visitors
        WHERE applicant_id = ? AND date = ? AND type = ?
    """, (applicant_id, date, vtype))
    
    # existing = cursor.fetchone()

    # ✅ 기존 데이터가 있고, 마감된 항목이면 기존 값 유지
    row = cursor.fetchone()

    # 이전 값 초기화
    old_b, old_l, old_d = (0, 0, 0)

    if row:
        old_b = row["breakfast"]
        old_l = row["lunch"]
        old_d = row["dinner"]

        def is_expired(meal_type, is_admin=False):
            meal_date = datetime.strptime(date, "%Y-%m-%d")
            now = datetime.now()
            if meal_type == "breakfast":
                deadline = meal_date - timedelta(days=1)
                hour = 20 if is_admin else 15
                deadline = deadline.replace(hour=hour, minute=0, second=0)
            elif meal_type == "lunch":
                hour = 12 if is_admin else 10
                deadline = meal_date.replace(hour=hour, minute=0, second=0)
            elif meal_type == "dinner":
                hour = 17 if is_admin else 15
                deadline = meal_date.replace(hour=hour, minute=0, second=0)
            else:
                return False
            return now > deadline

        if is_expired("breakfast", is_admin):
            breakfast = old_b
        if is_expired("lunch", is_admin):
            lunch = old_l
        if is_expired("dinner", is_admin):
            dinner = old_d

    # ✅ 2. 기존과 변경된 값이 다를 경우 + 금주에 해당할 경우만 visitor_logs 기록
    today = datetime.today().date()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)
    this_day = datetime.strptime(date, "%Y-%m-%d").date()


    # 🔄 2. 기존과 변경된 값이 다를 경우 visitor_logs 테이블에 로그 기록
    if (monday <= this_day <= friday) and (
        (old_b != breakfast) or (old_l != lunch) or (old_d != dinner)
    ):
        cursor.execute("""
            INSERT INTO visitor_logs (
                applicant_id, applicant_name, date, reason, type,
                before_breakfast, before_lunch, before_dinner,
                breakfast, lunch, dinner, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            applicant_id, applicant_name, date, reason, vtype,
            old_b, old_l, old_d,
            breakfast, lunch, dinner, now
        ))


    # ✅ 삽입 or 수정
    cursor.execute("""
        INSERT INTO visitors (applicant_id, applicant_name, date, breakfast, lunch, dinner, reason, last_modified, type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(applicant_id, date, type)
        DO UPDATE SET 
            breakfast = excluded.breakfast,
            lunch = excluded.lunch,
            dinner = excluded.dinner,
            reason = excluded.reason,
            last_modified = excluded.last_modified
    """, (applicant_id, applicant_name, date, breakfast, lunch, dinner, reason, now, vtype))

    conn.commit()
    conn.close()
    return jsonify({"message": "신청이 저장되었습니다."}), 201

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
    today = datetime.today().date()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)

    if monday <= date_obj <= friday:
        cursor.execute("""
            INSERT INTO visitor_logs (
                applicant_id, applicant_name, date, reason, type,
                before_breakfast, before_lunch, before_dinner,
                breakfast, lunch, dinner, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

    cursor.execute("DELETE FROM visitors WHERE id = ?", (vid,))
    conn.commit()
    conn.close()
    return jsonify({"message": "삭제되었습니다."}), 200

# ✅ [5] 방문자 주간 신청 현황 (협력사/방문자 포함)
@app.route("/visitors/weekly", methods=["GET"])
def get_weekly_visitors():
    start = request.args.get("start")
    end = request.args.get("end")
    applicant_id = request.args.get("id")  # 개인별 필터링 용도 (필요 시)

    if not (start and end):
        return jsonify({"error": "start, end 파라미터가 필요합니다."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    if applicant_id:
        cursor.execute("""
            SELECT id, applicant_id, applicant_name, date, breakfast, lunch, dinner, reason, last_modified, type
            FROM visitors
            WHERE date BETWEEN ? AND ? AND applicant_id = ?
            ORDER BY date
        """, (start, end, applicant_id))
    else:
        cursor.execute("""
            SELECT id, applicant_id, applicant_name, date, breakfast, lunch, dinner, reason, last_modified, type
            FROM visitors
            WHERE date BETWEEN ? AND ?
            ORDER BY date
        """, (start, end))

    rows = cursor.fetchall()
    conn.close()

    return jsonify([dict(row) for row in rows]), 200

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
        data = request.json
        breakfast = int(data.get("breakfast", 0))
        lunch = int(data.get("lunch", 0))
        dinner = int(data.get("dinner", 0))
        reason = data.get("reason", "").strip()

        if (breakfast + lunch + dinner) == 0 or reason == "":
            return jsonify({"error": "입력 값 부족"}), 400

        with sqlite3.connect(DATABASE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # ✅ 기존 값 조회
            cursor.execute("SELECT * FROM visitors WHERE id = ?", (visitor_id,))
            original = cursor.fetchone()

            if not original:
                return jsonify({"error": "신청 내역 없음"}), 404

            old_b, old_l, old_d = original["breakfast"], original["lunch"], original["dinner"]

            # 🔧 수정 후 코드
            # ✅ 변경사항이 있고 + 금주(월~금)일 경우만 로그 기록
            this_day = datetime.strptime(original["date"], "%Y-%m-%d").date()
            today = datetime.today().date()
            monday = today - timedelta(days=today.weekday())
            friday = monday + timedelta(days=4)

            
            
            # ✅ 값이 변경된 경우 로그 기록
            if (monday <= this_day <= friday) and (
                old_b != breakfast or old_l != lunch or old_d != dinner
            ):
                cursor.execute("""
                    INSERT INTO visitor_logs (
                        applicant_id, applicant_name, date, reason, type,
                        before_breakfast, before_lunch, before_dinner,
                        breakfast, lunch, dinner
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    original["applicant_id"],
                    original["applicant_name"],
                    original["date"],
                    reason,
                    original["type"],
                    old_b, old_l, old_d,
                    breakfast, lunch, dinner
                ))

            # ✅ DB 업데이트
            cursor.execute("""
                UPDATE visitors
                SET breakfast = ?, lunch = ?, dinner = ?, reason = ?, last_modified = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (breakfast, lunch, dinner, reason, visitor_id))

            conn.commit()

        return jsonify({"message": "수정 완료"}), 200

    except Exception as e:
        print("❌ 방문자 수정 오류:", e)
        return jsonify({"error": "수정 실패"}), 500


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

    # import os                                #실제사용
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

