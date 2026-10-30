#!/bin/sh
# Entrypoint container (Railway/Docker): pilih worker lewat env WORKER.
#   members (default) = worker.py    : metrik X semua member (members.csv)
#   jobs              = job_worker.py: task dari JOB_FILE (member/mention/hashtag SSK)
#   stress            = stress_test.py: uji batas jendela mention/hashtag
set -e
case "${WORKER:-members}" in
  members) exec python worker.py ;;
  jobs) exec python job_worker.py ;;
  stress) exec python stress_test.py ;;
  *) echo "WORKER tidak dikenal: $WORKER (pakai members|jobs|stress)"; exec sleep infinity ;;
esac
