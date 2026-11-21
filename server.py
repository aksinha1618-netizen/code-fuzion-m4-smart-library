"""Small, dependency-free backend for the Smart Library Seat Finder demo."""
from __future__ import annotations

import json
import os
import queue
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DATABASE_PATH", str(ROOT / "library.db")))
IST = timezone(timedelta(hours=5, minutes=30))
FLOORS = 3
SEATS_PER_FLOOR = 150
listeners: set[queue.Queue[str]] = set()
listeners_lock = threading.Lock()


def now_ist() -> datetime:
    return datetime.now(IST)


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=10000")
    return db


@contextmanager
def database():
    db = connect()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    with database() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS seats (
                id TEXT PRIMARY KEY,
                floor INTEGER NOT NULL CHECK(floor BETWEEN 1 AND 3),
                number INTEGER NOT NULL,
                UNIQUE(floor, number)
            );
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                seat_id TEXT NOT NULL REFERENCES seats(id),
                status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','cancelled','released')),
                checked_in INTEGER NOT NULL DEFAULT 0,
                on_break INTEGER NOT NULL DEFAULT 0,
                break_ends_at REAL,
                created_at TEXT NOT NULL,
                checked_in_at TEXT,
                ended_at TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_booking_per_seat
                ON bookings(seat_id) WHERE status='active';
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_booking_per_user
                ON bookings(user_id) WHERE status='active';
        """)
        for floor in range(1, FLOORS + 1):
            for number in range(1, SEATS_PER_FLOOR + 1):
                db.execute("INSERT OR IGNORE INTO seats(id,floor,number) VALUES(?,?,?)",
                           (f"F{floor}-S{number}", floor, number))


def publish() -> None:
    message = json.dumps({"type": "refresh"})
    with listeners_lock:
        dead = []
        for listener in listeners:
            try:
                listener.put_nowait(message)
            except queue.Full:
                dead.append(listener)
        for listener in dead:
            listeners.discard(listener)


def release_expired() -> bool:
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        cur = db.execute("""UPDATE bookings SET status='released',on_break=0,ended_at=?
            WHERE status='active' AND on_break=1 AND break_ends_at<=?""",
            (now_ist().isoformat(), time.time()))
        changed = cur.rowcount > 0
        db.execute("COMMIT")
    if changed:
        publish()
    return changed


def expiry_worker() -> None:
    while True:
        try:
            release_expired()
        except Exception:
            pass
        time.sleep(1)


def error(handler: SimpleHTTPRequestHandler, code: int, message: str) -> None:
    handler.send_json(code, {"error": message})


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def send_json(self, code: int, payload: object) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 16_384:
            raise ValueError("Request is too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self.send_json(200, {"ok": True})
        if path == "/api/state":
            release_expired()
            params = __import__("urllib.parse", fromlist=["parse_qs"]).parse_qs(urlparse(self.path).query)
            try:
                floor = int(params.get("floor", ["1"])[0])
            except ValueError:
                return error(self, 400, "Invalid floor")
            user_id = params.get("userId", [""])[0][:80]
            if floor not in range(1, FLOORS + 1):
                return error(self, 400, "Floor must be between 1 and 3")
            with database() as db:
                seats = db.execute("""SELECT s.id,s.floor,s.number,b.user_id,b.checked_in
                    FROM seats s LEFT JOIN bookings b ON b.seat_id=s.id AND b.status='active'
                    WHERE s.floor=? ORDER BY s.number""", (floor,)).fetchall()
                my = db.execute("""SELECT id,user_id,seat_id,checked_in,on_break,break_ends_at,created_at
                    FROM bookings WHERE user_id=? AND status='active'""", (user_id,)).fetchone() if user_id else None
            return self.send_json(200, {
                "floor": floor,
                "seats": [{"id": s["id"], "occupied": s["user_id"] is not None,
                           "checkedIn": bool(s["checked_in"])} for s in seats],
                "booking": dict(my) if my else None,
            })
        if path == "/api/admin/stats":
            with database() as db:
                hourly = db.execute("""SELECT substr(created_at,12,2) AS hour, count(*) AS bookings
                    FROM bookings GROUP BY hour ORDER BY bookings DESC,hour LIMIT 24""").fetchall()
                hogged = db.execute("""SELECT seat_id,count(*) AS bookings FROM bookings
                    GROUP BY seat_id ORDER BY bookings DESC,seat_id LIMIT 10""").fetchall()
                active = db.execute("SELECT count(*) FROM bookings WHERE status='active'").fetchone()[0]
                total = db.execute("SELECT count(*) FROM seats").fetchone()[0]
                counts = db.execute("""SELECT sum(CASE WHEN status='active' THEN 1 ELSE 0 END) AS active,
                    count(*) AS total FROM bookings""").fetchone()
            return self.send_json(200, {"totalSeats": total, "activeBookings": active,
                "bookingHistory": counts["total"], "peakHours": [dict(r) for r in hourly],
                "mostBookedSeats": [dict(r) for r in hogged]})
        if path == "/api/events":
            listener: queue.Queue[str] = queue.Queue(maxsize=8)
            with listeners_lock:
                listeners.add(listener)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            try:
                self.wfile.write(b"event: ready\ndata: {}\n\n")
                self.wfile.flush()
                while True:
                    try:
                        message = listener.get(timeout=15)
                        self.wfile.write(("data: " + message + "\n\n").encode())
                    except queue.Empty:
                        self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                with listeners_lock:
                    listeners.discard(listener)
            return
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self.read_json()
        except (ValueError, json.JSONDecodeError):
            return error(self, 400, "Invalid JSON request")
        user_id = str(data.get("userId", ""))[:80]
        if path in ("/api/book", "/api/cancel", "/api/checkin", "/api/break", "/api/break/cancel") and not user_id:
            return error(self, 400, "A browser user id is required")
        try:
            with database() as db:
                db.execute("BEGIN IMMEDIATE")
                if path == "/api/book":
                    seat_id = str(data.get("seatId", ""))[:20]
                    if not db.execute("SELECT 1 FROM seats WHERE id=?", (seat_id,)).fetchone():
                        db.execute("ROLLBACK")
                        return error(self, 404, "Seat not found")
                    if db.execute("SELECT 1 FROM bookings WHERE user_id=? AND status='active'", (user_id,)).fetchone():
                        db.execute("ROLLBACK")
                        return error(self, 409, "Cancel your current booking before booking another seat")
                    db.execute("INSERT INTO bookings(user_id,seat_id,created_at) VALUES(?,?,?)",
                               (user_id, seat_id, now_ist().isoformat()))
                elif path == "/api/cancel":
                    cur = db.execute("""UPDATE bookings SET status='cancelled',on_break=0,ended_at=?
                        WHERE user_id=? AND status='active'""", (now_ist().isoformat(), user_id))
                    if not cur.rowcount:
                        db.execute("ROLLBACK")
                        return error(self, 404, "No active booking found")
                elif path == "/api/checkin":
                    seat_id = str(data.get("seatId", ""))[:20]
                    cur = db.execute("""UPDATE bookings SET checked_in=1,checked_in_at=?
                        WHERE user_id=? AND seat_id=? AND status='active' AND checked_in=0""",
                        (now_ist().isoformat(), user_id, seat_id))
                    if not cur.rowcount:
                        db.execute("ROLLBACK")
                        return error(self, 409, "This seat QR does not match an unchecked active booking")
                elif path == "/api/break":
                    booking = db.execute("""SELECT checked_in,on_break FROM bookings
                        WHERE user_id=? AND status='active'""", (user_id,)).fetchone()
                    if not booking or not booking["checked_in"] or booking["on_break"]:
                        db.execute("ROLLBACK")
                        return error(self, 409, "Check in first; an active break timer may not already exist")
                    db.execute("""UPDATE bookings SET on_break=1,break_ends_at=?
                        WHERE user_id=? AND status='active'""", (time.time() + 20 * 60, user_id))
                elif path == "/api/break/cancel":
                    cur = db.execute("""UPDATE bookings SET on_break=0,break_ends_at=NULL
                        WHERE user_id=? AND status='active' AND on_break=1""", (user_id,))
                    if not cur.rowcount:
                        db.execute("ROLLBACK")
                        return error(self, 409, "No break timer is active")
                else:
                    db.execute("ROLLBACK")
                    return error(self, 404, "API route not found")
                db.execute("COMMIT")
        except sqlite3.IntegrityError:
            return error(self, 409, "This seat was just booked by someone else")
        except sqlite3.OperationalError as exc:
            return error(self, 503, "Database is busy; please try again")
        publish()
        return self.send_json(200, {"ok": True})


if __name__ == "__main__":
    init_db()
    threading.Thread(target=expiry_worker, daemon=True).start()
    port = int(os.environ.get("PORT", "8000"))
    print(f"Smart Library Seat Finder listening on port {port}; database: {DB_PATH}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
