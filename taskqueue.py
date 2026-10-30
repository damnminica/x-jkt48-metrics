"""Antrean task bersama berbasis file untuk beberapa worker (akun X) di disk yang sama.

Satu task hanya dikerjakan satu worker: sebelum mengerjakan, worker membuat file klaim secara atomik
(O_CREAT|O_EXCL). Worker lain melihat klaim itu dan lanjut ke task berikutnya. Selama task berjalan,
thread detak jantung menyentuh file klaim tiap HEARTBEAT_S detik; kalau worker mati, klaimnya basi
setelah STALE_S dan boleh diambil alih worker lain (dilanjutkan dari jendela terakhir yang tersimpan).

Struktur di <root>/queue/:
  claims/<label>.json  -> {"worker", "task", "since"}; mtime = detak jantung terakhir
  done/<label>         -> penanda task selesai (isi: worker & waktu)
  export.lock          -> worker yang membuat Excel akhir (sekali untuk seluruh job)
"""
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

HEARTBEAT_S = 60
STALE_S = int(os.environ.get("QUEUE_STALE_S", "600"))


def _label(task_id):
    return task_id.replace(":", "__")


def _now():
    return datetime.now(timezone.utc).isoformat()


class TaskQueue:
    def __init__(self, root, worker_id, stale_s=None):
        self.dir = Path(root) / "queue"
        self.claims, self.done_dir = self.dir / "claims", self.dir / "done"
        self.claims.mkdir(parents=True, exist_ok=True)
        self.done_dir.mkdir(parents=True, exist_ok=True)
        self.worker = worker_id
        self.stale_s = STALE_S if stale_s is None else stale_s
        self._beat_stop = None

    # ── status ─────────────────────────────────────────────────────────
    def is_done(self, task_id):
        return (self.done_dir / _label(task_id)).exists()

    def done_by(self, task_id):
        p = self.done_dir / _label(task_id)
        try:
            return json.loads(p.read_text()).get("worker", "")
        except (OSError, json.JSONDecodeError):
            return ""

    def claim_info(self, task_id):
        p = self.claims / f"{_label(task_id)}.json"
        try:
            info = json.loads(p.read_text())
            info["age_s"] = time.time() - p.stat().st_mtime
            return info
        except (OSError, json.JSONDecodeError):
            return None

    # ── klaim ──────────────────────────────────────────────────────────
    def claim(self, task_id):
        """True kalau task ini sekarang milik worker ini (baru, lanjutan klaim sendiri, atau ambil alih yang basi)."""
        if self.is_done(task_id):
            return False
        p = self.claims / f"{_label(task_id)}.json"
        body = json.dumps({"worker": self.worker, "task": task_id, "since": _now()})
        try:
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            with os.fdopen(fd, "w") as fh:
                fh.write(body)
            return True
        except FileExistsError:
            pass
        info = self.claim_info(task_id)
        if info is None:  # file klaim sedang ditulis worker lain / rusak: anggap dipegang orang lain
            return False
        if info.get("worker") == self.worker:  # klaim sendiri dari sebelum restart
            os.utime(p)
            return True
        if info["age_s"] < self.stale_s:
            return False
        # klaim basi (worker lain mati): ambil alih, lalu pastikan tidak bentrok dengan worker ketiga
        tmp = p.with_suffix(f".{self.worker}.tmp")
        tmp.write_text(body)
        os.replace(tmp, p)
        time.sleep(1)
        now = self.claim_info(task_id)
        return bool(now and now.get("worker") == self.worker)

    def release(self, task_id):
        p = self.claims / f"{_label(task_id)}.json"
        info = self.claim_info(task_id)
        if info and info.get("worker") == self.worker:
            p.unlink(missing_ok=True)

    def finish(self, task_id):
        tmp = self.done_dir / f".{_label(task_id)}.{self.worker}.tmp"
        tmp.write_text(json.dumps({"worker": self.worker, "at": _now()}))
        os.replace(tmp, self.done_dir / _label(task_id))
        self.release(task_id)

    def next_task(self, tasks):
        """Task berikutnya untuk worker ini: lanjutkan klaim sendiri dulu, lalu task bebas/basi pertama."""
        for t in tasks:  # klaim sendiri yang tertinggal (restart) didahulukan
            info = self.claim_info(t["id"])
            if info and info.get("worker") == self.worker and not self.is_done(t["id"]) and self.claim(t["id"]):
                return t
        for t in tasks:
            if not self.is_done(t["id"]) and self.claim(t["id"]):
                return t
        return None

    def remaining(self, tasks):
        return [t for t in tasks if not self.is_done(t["id"])]

    # ── detak jantung ──────────────────────────────────────────────────
    def heartbeat_start(self, task_id):
        """Sentuh file klaim tiap HEARTBEAT_S detik di thread terpisah (tetap jalan saat worker tidur
        menunggu rate limit/gangguan), supaya klaim tidak dianggap basi."""
        self.heartbeat_stop()
        stop = threading.Event()
        p = self.claims / f"{_label(task_id)}.json"

        def beat():
            while not stop.wait(HEARTBEAT_S):
                try:
                    os.utime(p)
                except OSError:
                    pass
        threading.Thread(target=beat, daemon=True).start()
        self._beat_stop = stop

    def heartbeat_stop(self):
        if self._beat_stop:
            self._beat_stop.set()
            self._beat_stop = None

    # ── ekspor sekali ──────────────────────────────────────────────────
    def take_export(self):
        """True untuk satu worker saja (yang pertama) — dia yang membuat & mengirim Excel akhir."""
        p = self.dir / "export.lock"
        try:
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            with os.fdopen(fd, "w") as fh:
                fh.write(json.dumps({"worker": self.worker, "at": _now()}))
            return True
        except FileExistsError:
            try:
                return json.loads(p.read_text()).get("worker") == self.worker
            except (OSError, json.JSONDecodeError):
                return False

    def export_owner(self):
        try:
            return json.loads((self.dir / "export.lock").read_text()).get("worker", "")
        except (OSError, json.JSONDecodeError):
            return ""
