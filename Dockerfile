FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/data REQUIRE_PROXY=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY xraw.py fetch_v2.py export_combined.py export_jobs.py worker.py job_worker.py taskqueue.py stress_test.py run.sh \
     members.csv related_accounts.csv ./
COPY jobs ./jobs
CMD ["sh", "run.sh"]
