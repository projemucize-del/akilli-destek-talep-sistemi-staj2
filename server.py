#!/usr/bin/env python3
import csv
import io
import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from sensor_rules import evaluate_reading, normalize_reading


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "sensor_tests.db"
ALLOWED_STATUS = ("Kayıt", "Tamamlandı")
READING_ORIGINS = ("Örnek Üretici", "Manuel Test Girdisi")


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class SensorStore:
    def __init__(self, path=DB_PATH, seed=True):
        self.path = str(path)
        self.seed = seed
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def init_db(self):
        with self.connect() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL CHECK(length(name) BETWEEN 5 AND 80),
                    source TEXT NOT NULL DEFAULT 'Örnek Veri',
                    status TEXT NOT NULL DEFAULT 'Kayıt',
                    notes TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL,
                    ended_at TEXT
                );
                CREATE TABLE IF NOT EXISTS readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    emg REAL NOT NULL,
                    force REAL NOT NULL,
                    current REAL NOT NULL,
                    position REAL NOT NULL,
                    battery REAL NOT NULL,
                    alert_level TEXT NOT NULL,
                    alert_message TEXT NOT NULL,
                    reading_origin TEXT NOT NULL DEFAULT 'Örnek Üretici',
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
                CREATE INDEX IF NOT EXISTS idx_readings_session_time ON readings(session_id, recorded_at);
            """)
            columns = {row["name"] for row in con.execute("PRAGMA table_info(readings)")}
            if "reading_origin" not in columns:
                con.execute(
                    "ALTER TABLE readings ADD COLUMN reading_origin TEXT NOT NULL DEFAULT 'Örnek Üretici'"
                )
            if self.seed and con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0:
                session_id = self._insert_session(con, "Örnek kavrama testi", "Yerel örnek veri akışı")
                for index in range(18):
                    self._insert_reading(con, session_id, self.sample_values(index), "Örnek Üretici")

    def _insert_session(self, con, name, notes=""):
        cur = con.execute(
            "INSERT INTO sessions (name, source, status, notes, started_at) VALUES (?, 'Örnek Veri', 'Kayıt', ?, ?)",
            (name, notes, now_iso()),
        )
        return cur.lastrowid

    def create_session(self, data):
        if not isinstance(data, dict):
            return None, {"request": "JSON gövdesi bir nesne olmalıdır."}
        name = str(data.get("name", "")).strip()
        notes = str(data.get("notes", "")).strip()[:300]
        if not 5 <= len(name) <= 80:
            return None, {"name": "Test adı 5-80 karakter olmalıdır."}
        with self.connect() as con:
            session_id = self._insert_session(con, name, notes)
        return self.get_session(session_id), None

    def list_sessions(self, search="", status="", page=1, page_size=8):
        try:
            page = max(1, int(page))
            page_size = min(25, max(1, int(page_size)))
        except (TypeError, ValueError):
            page, page_size = 1, 8
        where, params = [], []
        if search:
            where.append("(s.name LIKE ? OR s.notes LIKE ?)")
            term = f"%{search[:60]}%"
            params.extend([term, term])
        if status in ALLOWED_STATUS:
            where.append("s.status = ?")
            params.append(status)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        base = """SELECT s.*, COUNT(r.id) reading_count,
                  COALESCE(SUM(CASE WHEN r.alert_level != 'Normal' THEN 1 ELSE 0 END), 0) alert_count
                  FROM sessions s LEFT JOIN readings r ON r.session_id = s.id"""
        with self.connect() as con:
            total = con.execute("SELECT COUNT(*) FROM sessions s" + clause, params).fetchone()[0]
            rows = con.execute(
                base + clause + " GROUP BY s.id ORDER BY s.id DESC LIMIT ? OFFSET ?",
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return {"items": [dict(row) for row in rows], "total": total, "page": page,
                "page_size": page_size, "pages": max(1, (total + page_size - 1) // page_size)}

    def get_session(self, session_id):
        with self.connect() as con:
            session = con.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not session:
                return None
            readings = con.execute(
                "SELECT * FROM readings WHERE session_id = ? ORDER BY id DESC LIMIT 240", (session_id,)
            ).fetchall()
        result = dict(session)
        result["readings"] = [dict(row) for row in readings]
        result["reading_count"] = len(result["readings"])
        result["alert_count"] = sum(row["alert_level"] != "Normal" for row in result["readings"])
        result["analytics"] = self.analyze_readings(result["readings"])
        return result

    @staticmethod
    def analyze_readings(readings):
        count = len(readings)
        if not count:
            return {
                "count": 0,
                "averages": {key: None for key in ("emg", "force", "current", "position", "battery")},
                "maximums": {"emg": None, "force": None, "current": None},
                "safe_count": 0,
                "safe_ratio": 0.0,
                "warning_count": 0,
                "critical_count": 0,
                "emg_force_correlation": None,
                "correlation_label": "Yetersiz veri",
            }

        sensor_keys = ("emg", "force", "current", "position", "battery")
        averages = {
            key: round(sum(float(row[key]) for row in readings) / count, 2)
            for key in sensor_keys
        }
        maximums = {
            key: round(max(float(row[key]) for row in readings), 3)
            for key in ("emg", "force", "current")
        }
        safe_count = sum(row["alert_level"] == "Normal" for row in readings)
        warning_count = sum(row["alert_level"] == "Uyarı" for row in readings)
        critical_count = sum(row["alert_level"] == "Kritik" for row in readings)
        correlation = SensorStore.pearson_correlation(
            [float(row["emg"]) for row in readings],
            [float(row["force"]) for row in readings],
        )
        return {
            "count": count,
            "averages": averages,
            "maximums": maximums,
            "safe_count": safe_count,
            "safe_ratio": round(safe_count / count * 100, 1),
            "warning_count": warning_count,
            "critical_count": critical_count,
            "emg_force_correlation": correlation,
            "correlation_label": SensorStore.correlation_label(correlation),
        }

    @staticmethod
    def pearson_correlation(first, second):
        if len(first) != len(second) or len(first) < 2:
            return None
        first_mean = sum(first) / len(first)
        second_mean = sum(second) / len(second)
        numerator = sum((x - first_mean) * (y - second_mean) for x, y in zip(first, second))
        first_spread = sum((x - first_mean) ** 2 for x in first)
        second_spread = sum((y - second_mean) ** 2 for y in second)
        denominator = math.sqrt(first_spread * second_spread)
        return round(numerator / denominator, 3) if denominator else None

    @staticmethod
    def correlation_label(value):
        if value is None:
            return "Yetersiz veri"
        strength = abs(value)
        direction = "pozitif" if value > 0 else "negatif" if value < 0 else "yönsüz"
        if strength >= 0.7:
            return f"Güçlü {direction}"
        if strength >= 0.4:
            return f"Orta {direction}"
        if strength >= 0.2:
            return f"Zayıf {direction}"
        return "Belirgin ilişki yok"

    def _insert_reading(self, con, session_id, reading, origin):
        evaluation = evaluate_reading(reading)
        con.execute("""INSERT INTO readings
            (session_id, emg, force, current, position, battery, alert_level, alert_message,
             reading_origin, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, reading["emg"], reading["force"], reading["current"], reading["position"],
             reading["battery"], evaluation["level"], evaluation["message"], origin, now_iso()))
        return evaluation

    def add_reading(self, session_id, data, origin="Manuel Test Girdisi"):
        if not isinstance(data, dict):
            return None, {"request": "JSON gövdesi bir nesne olmalıdır."}
        if origin not in READING_ORIGINS:
            return None, {"origin": "Geçersiz veri kaynağı."}
        clean, errors = normalize_reading(data)
        if errors:
            return None, errors
        with self.connect() as con:
            session = con.execute("SELECT status FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not session:
                return None, {"session": "Test oturumu bulunamadı."}
            if session["status"] != "Kayıt":
                return None, {"session": "Tamamlanan teste yeni veri eklenemez."}
            evaluation = self._insert_reading(con, session_id, clean, origin)
            row = con.execute("SELECT * FROM readings WHERE id = last_insert_rowid()").fetchone()
        result = dict(row)
        result["evaluation"] = evaluation
        return result, None

    @staticmethod
    def sample_values(index):
        return {
            "emg": round(42 + 24 * math.sin(index / 2.3), 2),
            "force": round(38 + 31 * math.sin(index / 3.1 + 0.4), 2),
            "current": round(0.8 + 0.75 * abs(math.sin(index / 2.0)), 3),
            "position": round(72 + 48 * math.sin(index / 3.4), 2),
            "battery": round(max(15, 94 - index * 0.7), 2),
        }

    def add_sample(self, session_id):
        current = self.get_session(session_id)
        if not current:
            return None, {"session": "Test oturumu bulunamadı."}
        return self.add_reading(
            session_id,
            self.sample_values(current["reading_count"]),
            origin="Örnek Üretici",
        )

    def complete_session(self, session_id):
        with self.connect() as con:
            row = con.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not row:
                return None, {"session": "Test oturumu bulunamadı."}
            con.execute("UPDATE sessions SET status = 'Tamamlandı', ended_at = ? WHERE id = ?", (now_iso(), session_id))
        return self.get_session(session_id), None

    def stats(self):
        with self.connect() as con:
            total_sessions = con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            active_sessions = con.execute("SELECT COUNT(*) FROM sessions WHERE status = 'Kayıt'").fetchone()[0]
            total_readings = con.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
            alerts = con.execute("SELECT COUNT(*) FROM readings WHERE alert_level != 'Normal'").fetchone()[0]
            latest = con.execute("SELECT * FROM readings ORDER BY id DESC LIMIT 1").fetchone()
        return {"sessions": total_sessions, "active": active_sessions, "readings": total_readings,
                "alerts": alerts, "latest": dict(latest) if latest else None}

    def export_csv(self):
        with self.connect() as con:
            rows = con.execute("""SELECT s.name, r.* FROM readings r
                                JOIN sessions s ON s.id = r.session_id ORDER BY r.id""").fetchall()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Test", "Oturum Kaynağı", "Okuma Kaynağı", "EMG (%)", "FSR (%)",
                         "Motor Akımı (A)", "Konum (°)", "Batarya (%)", "Uyarı", "Açıklama", "Zaman"])
        for row in rows:
            writer.writerow([row["name"], "Örnek Veri", row["reading_origin"], row["emg"],
                             row["force"], row["current"], row["position"],
                             row["battery"], row["alert_level"], row["alert_message"], row["recorded_at"]])
        return "\ufeff" + output.getvalue()


STORE = SensorStore()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return None

    def do_GET(self):
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            return super().do_GET()
        qs = parse_qs(parsed.query)
        if parsed.path == "/api/health":
            return self.send_json({"status": "ok", "database": "SQLite", "mode": "Örnek Veri"})
        if parsed.path == "/api/stats":
            return self.send_json(STORE.stats())
        if parsed.path == "/api/sessions":
            return self.send_json(STORE.list_sessions(qs.get("search", [""])[0], qs.get("status", [""])[0],
                                                      qs.get("page", ["1"])[0], qs.get("page_size", ["8"])[0]))
        match = re.fullmatch(r"/api/sessions/(\d+)", parsed.path)
        if match:
            item = STORE.get_session(int(match.group(1)))
            return self.send_json(item if item else {"error": "Test oturumu bulunamadı."}, 200 if item else 404)
        if parsed.path == "/api/export.csv":
            body = STORE.export_csv().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="protez-sensor-testleri.csv"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return self.send_json({"error": "Uç nokta bulunamadı."}, 404)

    def do_POST(self):
        data = self.read_json()
        if data is None:
            return self.send_json({"error": "Geçersiz JSON."}, 400)
        if self.path == "/api/sessions":
            item, errors = STORE.create_session(data)
            return self.send_json(item if item else {"errors": errors}, 201 if item else 422)
        reading = re.fullmatch(r"/api/sessions/(\d+)/readings", self.path)
        sample = re.fullmatch(r"/api/sessions/(\d+)/sample", self.path)
        if reading:
            item, errors = STORE.add_reading(int(reading.group(1)), data)
            return self.send_json(item if item else {"errors": errors}, 201 if item else 422)
        if sample:
            item, errors = STORE.add_sample(int(sample.group(1)))
            return self.send_json(item if item else {"errors": errors}, 201 if item else 422)
        return self.send_json({"error": "Uç nokta bulunamadı."}, 404)

    def do_PATCH(self):
        match = re.fullmatch(r"/api/sessions/(\d+)/complete", urlparse(self.path).path)
        if not match:
            return self.send_json({"error": "Uç nokta bulunamadı."}, 404)
        item, errors = STORE.complete_session(int(match.group(1)))
        return self.send_json(item if item else {"errors": errors}, 200 if item else 422)

    def log_message(self, fmt, *args):
        print(f"[{now_iso()}] {self.address_string()} {fmt % args}")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("YEREL TEST ORTAMI: http://127.0.0.1:8765")
    server.serve_forever()
