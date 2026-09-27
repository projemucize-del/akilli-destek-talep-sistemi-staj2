#!/usr/bin/env python3
import csv
import io
import json
import re
import sqlite3
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ai_model import MODEL


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "tickets.db"
ALLOWED_STATUS = ("Açık", "İşlemde", "Çözüldü")
ALLOWED_PRIORITY = ("Düşük", "Normal", "Yüksek")
ALLOWED_CATEGORY = ("Ağ ve İnternet", "Yazılım", "Web Sayfası", "Hesap ve Yetki", "Donanım", "Diğer")


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class TicketStore:
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
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL CHECK(length(title) BETWEEN 5 AND 80),
                    category TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Açık',
                    description TEXT NOT NULL CHECK(length(description) BETWEEN 10 AND 500),
                    requester TEXT NOT NULL DEFAULT 'Anonim Test Kullanıcısı',
                    assigned_to TEXT,
                    ai_category TEXT,
                    ai_priority TEXT,
                    ai_confidence REAL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ticket_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id INTEGER NOT NULL,
                    old_status TEXT,
                    new_status TEXT NOT NULL,
                    note TEXT NOT NULL,
                    changed_at TEXT NOT NULL,
                    FOREIGN KEY(ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_tickets_status_category ON tickets(status, category);
                CREATE INDEX IF NOT EXISTS idx_tickets_created_at ON tickets(created_at);
                CREATE INDEX IF NOT EXISTS idx_history_ticket ON ticket_history(ticket_id);
            """)
            con.execute("PRAGMA optimize")
            if self.seed and con.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 0:
                seeds = [
                    ("Kablosuz ağ bağlantısı kesiliyor", "Ağ ve İnternet", "Normal", "Açık", "Test cihazında kablosuz bağlantı aralıklı olarak kopuyor."),
                    ("Form alanı doğrulama uyarısı", "Yazılım", "Yüksek", "İşlemde", "Boş bırakılan zorunlu alanda anlaşılır uyarı gösterilmiyor."),
                    ("Mobil görünüm menü testi", "Web Sayfası", "Düşük", "Çözüldü", "Dar ekranda menü taşması örnek cihazlarda kontrol edildi."),
                    ("Kullanıcı rolü erişim kontrolü", "Hesap ve Yetki", "Normal", "İşlemde", "Test kullanıcısının yalnızca yetkili işlevleri görmesi doğrulanacak."),
                    ("Yazıcı bağlantı kontrolü", "Donanım", "Normal", "Açık", "Test yazıcısı ağ üzerinde görünmesine rağmen çıktı alınamıyor."),
                    ("CSV rapor dışa aktarma", "Yazılım", "Düşük", "Çözüldü", "Filtrelenmiş test kayıtlarının CSV çıktısı doğrulandı."),
                ]
                for title, category, priority, status, description in seeds:
                    self._insert_seed(con, title, category, priority, status, description)

    def _insert_seed(self, con, title, category, priority, status, description):
        created = now_iso()
        ai = MODEL.predict(title, description)
        cur = con.execute("""INSERT INTO tickets
            (title, category, priority, status, description, ai_category, ai_priority, ai_confidence, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, category, priority, status, description, ai["category"], ai["priority"],
             min(ai["category_confidence"], ai["priority_confidence"]), created, created))
        con.execute("""INSERT INTO ticket_history
            (ticket_id, old_status, new_status, note, changed_at)
            VALUES (?, NULL, ?, ?, ?)""", (cur.lastrowid, status, "Örnek kayıt oluşturuldu.", created))

    def validate(self, data):
        errors = {}
        for key in ("title", "category", "priority", "description"):
            if not str(data.get(key, "")).strip():
                errors[key] = "Bu alan zorunludur."
        if "title" in data and not 5 <= len(str(data["title"]).strip()) <= 80:
            errors["title"] = "Başlık 5-80 karakter olmalıdır."
        if "description" in data and not 10 <= len(str(data["description"]).strip()) <= 500:
            errors["description"] = "Açıklama 10-500 karakter olmalıdır."
        if data.get("category") not in ALLOWED_CATEGORY:
            errors["category"] = "Geçersiz kategori."
        if data.get("priority") not in ALLOWED_PRIORITY:
            errors["priority"] = "Geçersiz öncelik."
        return errors

    def list(self, search="", status="", category="", page=1, page_size=8):
        page, page_size = max(1, int(page)), min(25, max(1, int(page_size)))
        where, params = [], []
        if search:
            where.append("(title LIKE ? OR category LIKE ? OR description LIKE ?)")
            term = f"%{search[:60]}%"
            params.extend([term, term, term])
        if status in ALLOWED_STATUS:
            where.append("status = ?"); params.append(status)
        if category in ALLOWED_CATEGORY:
            where.append("category = ?"); params.append(category)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        with self.connect() as con:
            total = con.execute("SELECT COUNT(*) FROM tickets" + clause, params).fetchone()[0]
            rows = con.execute("SELECT * FROM tickets" + clause + " ORDER BY id DESC LIMIT ? OFFSET ?",
                               (*params, page_size, (page - 1) * page_size)).fetchall()
        return {"items": [dict(r) for r in rows], "total": total, "page": page,
                "page_size": page_size, "pages": max(1, (total + page_size - 1) // page_size)}

    def get(self, ticket_id):
        with self.connect() as con:
            row = con.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            if not row:
                return None
            history = con.execute("SELECT * FROM ticket_history WHERE ticket_id = ? ORDER BY id DESC", (ticket_id,)).fetchall()
        item = dict(row)
        item["history"] = [dict(x) for x in history]
        return item

    def create(self, data):
        clean = {key: str(data.get(key, "")).strip() for key in ("title", "category", "priority", "description")}
        errors = self.validate(clean)
        if errors:
            return None, errors
        ai = MODEL.predict(clean["title"], clean["description"])
        created = now_iso()
        with self.connect() as con:
            cur = con.execute("""INSERT INTO tickets
                (title, category, priority, status, description, ai_category, ai_priority, ai_confidence, created_at, updated_at)
                VALUES (?, ?, ?, 'Açık', ?, ?, ?, ?, ?, ?)""",
                (clean["title"], clean["category"], clean["priority"], clean["description"],
                 ai["category"], ai["priority"], min(ai["category_confidence"], ai["priority_confidence"]),
                 created, created))
            con.execute("""INSERT INTO ticket_history
                (ticket_id, old_status, new_status, note, changed_at)
                VALUES (?, NULL, 'Açık', ?, ?)""", (cur.lastrowid, "Talep test arayüzünden oluşturuldu.", created))
        return self.get(cur.lastrowid), None

    def update_status(self, ticket_id, status, note=""):
        if status not in ALLOWED_STATUS:
            return None, {"status": "Geçersiz durum."}
        note = str(note).strip()[:240] or "Durum güncellendi."
        with self.connect() as con:
            row = con.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            if not row:
                return None, {"ticket": "Kayıt bulunamadı."}
            changed = now_iso()
            con.execute("UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?", (status, changed, ticket_id))
            con.execute("""INSERT INTO ticket_history
                (ticket_id, old_status, new_status, note, changed_at)
                VALUES (?, ?, ?, ?, ?)""", (ticket_id, row["status"], status, note, changed))
        return self.get(ticket_id), None

    def stats(self):
        with self.connect() as con:
            total = con.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
            by_status = {r["status"]: r["count"] for r in con.execute("SELECT status, COUNT(*) count FROM tickets GROUP BY status")}
            by_category = [dict(r) for r in con.execute("SELECT category label, COUNT(*) value FROM tickets GROUP BY category ORDER BY value DESC")]
        return {"total": total, "by_status": {s: by_status.get(s, 0) for s in ALLOWED_STATUS}, "by_category": by_category}

    def export_csv(self):
        with self.connect() as con:
            rows = [dict(r) for r in con.execute("SELECT * FROM tickets ORDER BY id DESC")]
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["No", "Başlık", "Kategori", "Öncelik", "Durum", "AI Kategori", "AI Öncelik", "Oluşturma Tarihi"])
        for row in rows:
            writer.writerow([row["id"], row["title"], row["category"], row["priority"], row["status"],
                             row["ai_category"], row["ai_priority"], row["created_at"]])
        return "\ufeff" + output.getvalue()


STORE = TicketStore()


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
            return self.send_json({"status": "ok", "database": "SQLite", "ai_model": MODEL.name})
        if parsed.path == "/api/stats":
            return self.send_json(STORE.stats())
        if parsed.path == "/api/ai/metrics":
            return self.send_json(MODEL.metrics())
        if parsed.path == "/api/tickets":
            return self.send_json(STORE.list(qs.get("search", [""])[0], qs.get("status", [""])[0],
                                             qs.get("category", [""])[0], qs.get("page", ["1"])[0],
                                             qs.get("page_size", ["8"])[0]))
        match = re.fullmatch(r"/api/tickets/(\d+)", parsed.path)
        if match:
            item = STORE.get(int(match.group(1)))
            return self.send_json(item if item else {"error": "Kayıt bulunamadı."}, 200 if item else 404)
        if parsed.path == "/api/export.csv":
            body = STORE.export_csv().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="test-talepleri.csv"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return self.send_json({"error": "Uç nokta bulunamadı."}, 404)

    def do_POST(self):
        if self.path == "/api/ai/predict":
            data = self.read_json()
            if data is None:
                return self.send_json({"error": "Geçersiz JSON."}, 400)
            try:
                return self.send_json(MODEL.predict(data.get("title", ""), data.get("description", "")))
            except ValueError as exc:
                return self.send_json({"error": str(exc)}, 422)
        if self.path == "/api/tickets":
            data = self.read_json()
            if data is None:
                return self.send_json({"error": "Geçersiz JSON."}, 400)
            item, errors = STORE.create(data)
            return self.send_json(item if item else {"errors": errors}, 201 if item else 422)
        return self.send_json({"error": "Uç nokta bulunamadı."}, 404)

    def do_PATCH(self):
        match = re.fullmatch(r"/api/tickets/(\d+)/status", urlparse(self.path).path)
        if not match:
            return self.send_json({"error": "Uç nokta bulunamadı."}, 404)
        data = self.read_json()
        if data is None:
            return self.send_json({"error": "Geçersiz JSON."}, 400)
        item, errors = STORE.update_status(int(match.group(1)), data.get("status", ""), data.get("note", ""))
        return self.send_json(item if item else {"errors": errors}, 200 if item else 422)

    def log_message(self, fmt, *args):
        print(f"[{now_iso()}] {self.address_string()} {fmt % args}")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("TEST ORTAMI: http://127.0.0.1:8765")
    server.serve_forever()
