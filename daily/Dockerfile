FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/data TZ=Asia/Jakarta
WORKDIR /app
COPY daily/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# modul bersama dari root proyek + paket daily
COPY xraw.py fetch_v2.py worker.py export_combined.py members.csv ./
COPY daily/ ./daily/
# seed data full1 (store member awal) supaya dashboard langsung tampil sebelum cron pertama
COPY daily/seed.tgz ./daily/seed.tgz
EXPOSE 8080
# 1 worker: scheduler jalan sekali di proses ini; web melayani dashboard
CMD ["gunicorn","-w","1","-b","0.0.0.0:8080","--chdir","daily","--timeout","120","app:app"]
