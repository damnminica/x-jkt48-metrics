FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/data TZ=Asia/Jakarta
WORKDIR /app
COPY instagram/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# roster member (dibaca aggregate_ig untuk nama/tim) + paket instagram (termasuk seed snapshots/)
COPY members.csv ./
COPY instagram/ ./instagram/
# opsional: data X untuk panel lintas-platform (aman bila tidak ada)
COPY dash_ds/members.json ./dash_ds/members.json
EXPOSE 8080
# 1 worker: scheduler jalan sekali; web melayani dashboard + ig_data.json
CMD ["gunicorn","-w","1","-b","0.0.0.0:8080","--chdir","instagram","--timeout","180","app:app"]
