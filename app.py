# Flask: 웹 애플리케이션을 만들기 위한 마이크로 프레임워크
# request: HTTP 요청 데이터 (GET, POST 등)를 다루기 위해 사용
# jsonify: 파이썬 데이터를 JSON 형식으로 반환하기 위해 사용
# CORS: 다른 도메인/포트에서의 요청을 허용 (프론트 연동 시 필수)
# sqlite3: 가볍고 파일 기반의 내장형 데이터베이스

import sys
print("✅ 현재 실행 중인 Python:", sys.executable)

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from datetime import datetime, timedelta
#from collections import defaultdict
from io import BytesIO
import sqlite3
import pandas as pd
import os
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
            type TEXT DEFAULT '직영',    -- 직영/협력사
            dept TEXT NOT NULL,         -- 부서
            rank TEXT DEFAULT '',      -- 직급
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
    # cursor.execute("""
    #     CREATE TABLE IF NOT EXISTS visitors (
    #     id INTEGER PRIMARY KEY AUTOINCREMENT,
    #     date TEXT NOT NULL,              -- 날짜 (YYYY-MM-DD)
    #     breakfast INTEGER DEFAULT 0,     -- 조식 방문자 수
    #     lunch INTEGER DEFAULT 0,         -- 중식 방문자 수
    #     dinner INTEGER DEFAULT 0,        -- 석식 방문자 수
    #     applicant_name TEXT NOT NULL,    -- 신청자 이름
    #     applicant_id TEXT NOT NULL,      -- 신청자 사번
    #     reason TEXT                      -- 방문 목적/사유
    #     last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP       -- 최종 변경시간
    #     )
    # """)

    

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
    mode = request.args.get("mode", "")  # ✅ mode 파라미터
    
    if not start or not end:
        return jsonify({"error": "start, end는 필수입니다."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    if mode == "all":
        # ✅ 신청 여부와 관계없이 전체 인력 + 신청 내역 LEFT JOIN
        cursor.execute("""
            SELECT 
                e.id AS user_id,
                e.name,
                e.dept,
                m.date,
                m.breakfast,
                m.lunch,
                m.dinner
            FROM employees e
            LEFT JOIN meals m ON e.id = m.user_id AND m.date BETWEEN ? AND ?
            ORDER BY e.dept, e.id, m.date
        """, (start, end))

    else:
        # ✅ 기존 로직: 신청한 사람만
        cursor.execute("""
            SELECT m.user_id, e.name, e.dept, m.date, 
                   m.breakfast, m.lunch, m.dinner
            FROM meals m
            JOIN employees e ON m.user_id = e.id
            WHERE m.date BETWEEN ? AND ?
            ORDER BY m.user_id, m.date
        """, (start, end))
    
    rows = cursor.fetchall()
    conn.close()

    # if not rows:
    #     return jsonify([]), 200   # ✅ 빈 리스트도 JSON으로 반환

    results = [dict(row) for row in rows]
    return jsonify(results), 200

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

    # for meal in meals:
    #     user_id = meal.get("user_id")
    #     date = meal.get("date")
    #     breakfast = int(meal.get("breakfast", 0))
    #     lunch = int(meal.get("lunch", 0))
    #     dinner = int(meal.get("dinner", 0))



    #     # 먼저 해당 user_id+date 조합 삭제
    #     cursor.execute("DELETE FROM meals WHERE user_id = ? AND date = ?", (user_id, date))

    #     # 이후 새로 삽입
    #     cursor.execute("""
    #         INSERT INTO meals (user_id, date, breakfast, lunch, dinner)
    #         VALUES (?, ?, ?, ?, ?)
    #     """, (user_id, date, breakfast, lunch, dinner))

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
    conn = get_db_connection()
    employees = conn.execute("SELECT * FROM employees").fetchall()
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

    if not emp_id or not name or not dept:
        return jsonify({"error": "입력값 부족"}), 400

    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO employees (id, name, dept, rank, type) VALUES (?, ?, ?, ?, ?)",
                     (emp_id, name, dept, rank, emp_type))
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

    if not name or not dept:
        return jsonify({"error": "입력값 부족"}), 400

    conn = get_db_connection()
    conn.execute("UPDATE employees SET name = ?, dept = ?, rank = ?, type = ?  WHERE id = ?",
                 (name, dept, rank, emp_type, emp_id))
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

        required_cols = {"id", "name", "dept", "type"}
        optional_cols = {"rank"}

        if not required_cols.issubset(set(df.columns)):
            return jsonify({"error": "파일에 'id', 'name', 'dept' 컬럼이 있어야 합니다."}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        for _, row in df.iterrows():
            rank = row["rank"] if "rank" in row else ""
            cursor.execute("""
                INSERT INTO employees (id, name, dept, rank, type)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    dept = excluded.dept,
                    type = excluded.type,
                    rank = excluded.rank
            """, (row["id"], row["name"], row["dept"], row["type"], rank))

        conn.commit()
        conn.close()
        return jsonify({"success": True})

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
    df = pd.DataFrame(columns=["사번", "이름", "부서", "직영/협력사" , "직급(옵션)"])
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
        "SELECT id, name, dept, rank FROM employees WHERE id = ? AND name = ?",
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
            "rank": user["rank"]
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


# @app.route("/stats/period_meals", methods=["GET"])
# def get_period_meal_stats():
#     start_str = request.args.get("start")
#     end_str = request.args.get("end")

#     try:
#         # 기본값: 이번 달 1일부터 말일까지
#         today = datetime.today()
#         if not start_str or not end_str:
#             start_date = datetime(today.year, today.month, 1).date()
#             if today.month == 12:
#                 end_date = datetime(today.year + 1, 1, 1).date() - timedelta(days=1)
#             else:
#                 end_date = datetime(today.year, today.month + 1, 1).date() - timedelta(days=1)
#         else:
#             start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
#             end_date = datetime.strptime(end_str, "%Y-%m-%d").date()

#         conn = get_db_connection()
#         cursor = conn.execute("""
#             SELECT date, 
#                    SUM(breakfast) AS breakfast_count,
#                    SUM(lunch) AS lunch_count,
#                    SUM(dinner) AS dinner_count
#             FROM meals
#             WHERE date BETWEEN ? AND ?
#             GROUP BY date
#             ORDER BY date ASC
#         """, (start_date.isoformat(), end_date.isoformat()))

#         rows = cursor.fetchall()
#         conn.close()

#         result = []
#         for row in rows:
#             date_obj = datetime.strptime(row["date"], "%Y-%m-%d").date()
#             weekday = date_obj.weekday()
#             if weekday < 5:  # 월~금만 포함
#                 result.append({
#                     "date": row["date"],
#                     "weekday": ["월", "화", "수", "목", "금"][weekday],
#                     "breakfast": row["breakfast_count"],
#                     "lunch": row["lunch_count"],
#                     "dinner": row["dinner_count"]
#                 })

#         return jsonify(result), 200

#     except Exception as e:
#         print("❌ 기간별 통계 조회 오류:", e)
#         return jsonify({"error": "기간별 통계 조회 실패"}), 500

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
        FROM meals
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
    cursor = conn.cursor()
    cursor.execute("""
        SELECT date, 
               SUM(breakfast) as breakfast, 
               SUM(lunch) as lunch, 
               SUM(dinner) as dinner
        FROM meals
        WHERE date BETWEEN ? AND ?
        GROUP BY date
        ORDER BY date
    """, (start, end))

    rows = cursor.fetchall()
    conn.close()

    # 📊 데이터 프레임 변환
    data = []
    for row in rows:
        date_str = row["date"]
        weekday = datetime.strptime(date_str, "%Y-%m-%d").weekday()
        weekday_kr = ["월", "화", "수", "목", "금", "토", "일"][weekday]

        # 평일(월~금)만 포함
        if weekday < 5:
            data.append({
                "날짜": row["date"],
                "요일": weekday_kr,
                "조식": row["breakfast"],
                "중식": row["lunch"],
                "석식": row["dinner"]
            })

    df = pd.DataFrame(data)

    # 파일 경로 및 저장
    filename = "meal_stats_period.xlsx"
    filepath = os.path.join(os.getcwd(), filename)
    df.to_excel(filepath, index=False)

    return send_file(filepath, as_attachment=True)

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
        FROM meals
        WHERE date BETWEEN ? AND ?
        GROUP BY date
        ORDER BY date
    """
    cursor.execute(query, (start, end))
    rows = cursor.fetchall()
    conn.close()


    return jsonify([dict(row) for row in rows])

    # 예시 변환 (금주/차주/평균/주차 등 분리)
    # return jsonify({
    #     "week_current": convert_graph_data(rows),  # 가공함수 필요
    #     "week_next": convert_graph_data(rows),     # 예시 동일
    #     "dow_average": convert_graph_data(rows),
    #     "week_trend": convert_graph_data(rows)
    # })


@app.route("/admin/stats/dept_summary")
def get_dept_summary():
    start = request.args.get("start")
    end = request.args.get("end")

    if not start or not end:
        return jsonify({"error": "기간이 지정되지 않았습니다."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            e.dept,
            e.type,  -- ✅ 가정: employees 테이블에 'type' 필드 (직영/협력사)
            SUM(m.breakfast) AS breakfast,
            SUM(m.lunch) AS lunch,
            SUM(m.dinner) AS dinner
        FROM meals m
        JOIN employees e ON m.user_id = e.id
        WHERE m.date BETWEEN ? AND ?
        GROUP BY e.dept, e.type
        ORDER BY e.type, e.dept
    """, (start, end))

    rows = cursor.fetchall()
    conn.close()

    return jsonify([dict(r) for r in rows])

@app.route("/admin/stats/dept_summary/excel")
def download_dept_summary_excel():
    start = request.args.get("start")
    end = request.args.get("end")

    if not start or not end:
        return "날짜를 지정해주세요", 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            e.dept,
            e.type,
            SUM(m.breakfast) AS breakfast,
            SUM(m.lunch) AS lunch,
            SUM(m.dinner) AS dinner
        FROM meals m
        JOIN employees e ON m.user_id = e.id
        WHERE m.date BETWEEN ? AND ?
        GROUP BY e.dept, e.type
        ORDER BY e.type, e.dept
    """, (start, end))

    rows = cursor.fetchall()
    conn.close()

    # Pandas DataFrame 생성
    df = pd.DataFrame(rows, columns=["dept", "type", "breakfast", "lunch", "dinner"])
    df["total"] = df["breakfast"] + df["lunch"] + df["dinner"]

    # 직영/협력사 분리 및 정렬
    direct = df[df["type"] == "직영"].sort_values("dept")
    partner = df[df["type"] != "직영"].sort_values("dept")

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
    grand_total = make_subtotal(df, "총계")

    final_df = pd.concat([direct, direct_total, partner, partner_total, grand_total], ignore_index=True)
    final_df = final_df[["dept", "total", "breakfast", "lunch", "dinner"]]  # 열 순서 정리

    # 엑셀 바이너리로 변환
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        final_df.to_excel(writer, index=False, sheet_name="부서별 신청현황")
    output.seek(0)

    filename = f"dept_stats_{start}_to_{end}.xlsx"
    return send_file(output, as_attachment=True, download_name=filename, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/admin/stats/weekly_dept")
def weekly_dept_stats():
    start = request.args.get("start")
    end = request.args.get("end")

    if not start or not end:
        return jsonify({"error": "start 또는 end 파라미터가 누락되었습니다."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # 전체 직원 목록 (부서별 인원 수 확인용)
    cursor.execute("""
        SELECT id, name, dept, type
        FROM employees
    """)
    employees = cursor.fetchall()

    # 식사 신청 내역
    cursor.execute("""
        SELECT m.date, m.user_id, m.breakfast, m.lunch, m.dinner
        FROM meals m
        WHERE m.date BETWEEN ? AND ?
    """, (start, end))
    meals = cursor.fetchall()
    conn.close()

    # dept 기준으로 데이터 정리
    dept_map = {}  # { dept: { people: [...], days: { date: {b:[], l:[], d:[]} } } }

    emp_info = {}  # { user_id: { name, dept, type } }
    for e in employees:
        emp_info[e["id"]] = {
            "name": e["name"],
            "dept": e["dept"],
            "type": e["type"]
        }
        if e["dept"] not in dept_map:
            dept_map[e["dept"]] = {
                "people": [],   # ✅ 문자열 key로 수정
                "type": e["type"],
                "days": {}
            }
        dept_map[e["dept"]]["people"].append(e["id"])

    for m in meals:
        uid = m["user_id"]
        if uid not in emp_info:
            continue
        info = emp_info[uid]
        dept = info["dept"]
        name = info["name"]
        date = m["date"]

        if date not in dept_map[dept]["days"]:
            dept_map[dept]["days"][date] = { "b": [], "l": [], "d": [] }

        if m["breakfast"]:
            dept_map[dept]["days"][date]["b"].append(name)
        if m["lunch"]:
            dept_map[dept]["days"][date]["l"].append(name)
        if m["dinner"]:
            dept_map[dept]["days"][date]["d"].append(name)

    # 최종 정리
    result = []
    for dept, info in dept_map.items():
        result.append({
            "dept": dept,
            "type": info["type"],
            "total": len(info["people"]),
            "days": info["days"]  # key=date, value={b:[], l:[], d:[]}
        })

    return jsonify(result)

@app.route("/admin/stats/weekly_dept/excel")
def weekly_dept_excel():
    start = request.args.get("start")
    end = request.args.get("end")

    if not start or not end:
        return "start 또는 end 파라미터가 누락되었습니다.", 400

    # ✅ 기존 라우터 재사용
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, dept, type FROM employees")
    employees = cursor.fetchall()

    cursor.execute("""
        SELECT date, user_id, breakfast, lunch, dinner
        FROM meals
        WHERE date BETWEEN ? AND ?
    """, (start, end))
    meals = cursor.fetchall()
    conn.close()

    emp_info = {}
    dept_map = {}

    for e in employees:
        emp_info[e["id"]] = {
            "name": e["name"],
            "dept": e["dept"],
            "type": e["type"]
        }
        if e["dept"] not in dept_map:
            dept_map[e["dept"]] = {
                "people": [],
                "type": e["type"],
                "days": {}
            }
        dept_map[e["dept"]]["people"].append(e["id"])

    for m in meals:
        uid = m["user_id"]
        if uid not in emp_info:
            continue
        info = emp_info[uid]
        dept = info["dept"]
        name = info["name"]
        date = m["date"]

        if date not in dept_map[dept]["days"]:
            dept_map[dept]["days"][date] = { "b": [], "l": [], "d": [] }

        if m["breakfast"]:
            dept_map[dept]["days"][date]["b"].append(name)
        if m["lunch"]:
            dept_map[dept]["days"][date]["l"].append(name)
        if m["dinner"]:
            dept_map[dept]["days"][date]["d"].append(name)

    # 날짜 정렬
    all_dates = sorted(list(set(m["date"] for m in meals)))
    weekday_map = ["월", "화", "수", "목", "금", "토", "일"]

    # 각 부서별 row 구성
    def build_rows(depts):
        rows = []
        for dept in sorted(depts):
            entry = dept_map[dept]
            row = {
                "부서": dept,
                "인원수": len(entry["people"])
            }
            for d in all_dates:
                val = entry["days"].get(d, {"b": [], "l": [], "d": []})
                row[f"{d}_조식인원"] = len(val["b"])
                row[f"{d}_조식명단"] = ", ".join(val["b"])
                row[f"{d}_중식인원"] = len(val["l"])
                row[f"{d}_석식인원"] = len(val["d"])
                row[f"{d}_석식명단"] = ", ".join(val["d"])
            rows.append(row)
        return rows

    direct = [k for k, v in dept_map.items() if v["type"] == "직영"]
    partner = [k for k, v in dept_map.items() if v["type"] != "직영"]

    df_direct = pd.DataFrame(build_rows(direct))
    df_partner = pd.DataFrame(build_rows(partner))

    def subtotal(df, label):
        if df.empty:
            return pd.DataFrame()
        subtotal_row = {"부서": label, "인원수": df["인원수"].sum()}
        for col in df.columns:
            if "인원" in col and col != "인원수":
                subtotal_row[col] = df[col].sum()
            elif "명단" in col:
                subtotal_row[col] = ""
        return pd.DataFrame([subtotal_row])

    df_all = pd.concat([
        df_direct,
        subtotal(df_direct, "직영 소계"),
        df_partner,
        subtotal(df_partner, "협력사 소계"),
        subtotal(pd.concat([df_direct, df_partner]), "총계")
    ], ignore_index=True)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df_all.to_excel(writer, index=False, sheet_name="주간 부서별 신청현황")
    output.seek(0)

    filename = f"weekly_dept_{start}_to_{end}.xlsx"
    return send_file(output, as_attachment=True, download_name=filename,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# # 방문자 신청 저장 API (POST /visitors)
# @app.route("/visitors", methods=["POST"])
# def save_visitors():
#     data = request.get_json()
#     items = data.get("visitors", [])

#     if not items:
#         return jsonify({"error": "방문자 식수 정보가 없습니다."}), 400

#     conn = get_db_connection()
#     cursor = conn.cursor()

#     for item in items:
#         date = item.get("date")
#         breakfast = int(item.get("breakfast", 0))
#         lunch = int(item.get("lunch", 0))
#         dinner = int(item.get("dinner", 0))
#         applicant_name = item.get("applicant_name")
#         applicant_id = item.get("applicant_id")
#         reason = item.get("reason", "")

#         # 유효성 체크
#         if not (date and applicant_name and applicant_id):
#             continue

#         # 날짜별 중복 시 덮어쓰기
#         cursor.execute("""
#             INSERT INTO visitors (date, breakfast, lunch, dinner, applicant_name, applicant_id, reason)
#             VALUES (?, ?, ?, ?, ?, ?, ?)
#             ON CONFLICT(date)
#             DO UPDATE SET
#                 breakfast = excluded.breakfast,
#                 lunch = excluded.lunch,
#                 dinner = excluded.dinner,
#                 applicant_name = excluded.applicant_name,
#                 applicant_id = excluded.applicant_id,
#                 reason = excluded.reason
#                 last_modified = CURRENT_TIMESTAMP
#         """, (date, breakfast, lunch, dinner, applicant_name, applicant_id, reason))

#     conn.commit()
#     conn.close()
#     return jsonify({"message": "방문자 식수가 저장되었습니다."}), 201

# # 2) 방문자 신청 내역 조회 API (GET /visitors)
# @app.route("/visitors", methods=["GET"])
# def get_visitors():
#     start = request.args.get("start")
#     end = request.args.get("end")

#     if not start or not end:
#         return jsonify({"error": "start, end 파라미터가 필요합니다."}), 400

#     conn = get_db_connection()
#     cursor = conn.cursor()
#     cursor.execute("""
#         SELECT date, breakfast, lunch, dinner,
#                applicant_name, applicant_id, reason,
#                last_modified
#         FROM visitors
#         WHERE date BETWEEN ? AND ?
#         ORDER BY date
#     """, (start, end))

#     rows = cursor.fetchall()
#     conn.close()
#     return jsonify([dict(r) for r in rows])



# ✅ (선택) 기본 접속 페이지 - 브라우저에서 확인용
@app.route("/")
def home():
    return "✅ Flask 백엔드 서버 정상 실행 중입니다."


# ✅ 앱 실행 진입점 (init_db로 테이블 자동 생성 → 서버 실행)
if __name__ == "__main__":
    init_db()               # 앱 시작 시 DB 테이블 없으면 자동 생성
    #migrate_meals_table()
    #alter_meals_table_unique_key()
    # alter_employees_add_type()  # ✅ 여기에 추가하세요

    app.run(debug=True)     # 디버그 모드 (코드 변경 시 자동 재시작)



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

