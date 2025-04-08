# ✅ backup_worker.py
from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime, timedelta
import shutil
import os

# ✅ 백업 실행 함수
def backup_database():
    now = datetime.now().strftime("%Y-%m-%d_%H-%M")
    os.makedirs("backups", exist_ok=True)
    shutil.copyfile("db.sqlite", f"backups/backup_{now}.db")
    print(f"[✅ 백업 완료] backup_{now}.db")

# ✅ 오래된 백업 삭제 함수
def clean_old_backups(days=7):
    cutoff = datetime.now().timestamp() - days * 86400
    for file in os.listdir("backups"):
        path = os.path.join("backups", file)
        if file.endswith(".db") and os.path.getmtime(path) < cutoff:
            os.remove(path)
            print(f"[🧹 삭제됨] {file}")

# ✅ 예약 작업 등록
def job():
    print("⏰ 자동 백업 시작")
    backup_database()
    clean_old_backups()

# ✅ 스케줄러 실행 (매일 자정)
sched = BlockingScheduler()
sched.add_job(job, "cron", hour=0, minute=0)
sched.start()

# import os
# import shutil
# from datetime import datetime

# def job():
#     db_path = "db.sqlite"
#     if not os.path.exists(db_path):
#         print("❌ 백업 실패: db.sqlite 파일이 없습니다.")
#         return

#     today = datetime.now().strftime("%Y%m%d")
#     backup_dir = "backups"
#     os.makedirs(backup_dir, exist_ok=True)

#     backup_file = os.path.join(backup_dir, f"backup_{today}.sqlite")
#     shutil.copy2(db_path, backup_file)

#     print(f"✅ DB 백업 완료: {backup_file}")

# # 로컬에서 테스트 시 직접 실행
# if __name__ == "__main__":
#     job()
