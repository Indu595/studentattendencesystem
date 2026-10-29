from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import os
import re
import secrets
import sqlite3
from datetime import date, datetime, time
from functools import wraps
from typing import Any, Callable

from flask import Flask, g, jsonify, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("APP_SECRET_KEY") or secrets.token_hex(32),
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
)
DATABASE = os.environ.get("ATTENDANCE_DATABASE", "attendance.db")
ATTENDANCE_STATUSES = {"present", "absent", "late", "excused"}
FACE_DESCRIPTOR_SIZE = 128
MAX_FACE_IMAGE_BYTES = 1024 * 1024
FACE_MATCH_THRESHOLD = 0.43
ROLL_NUMBER_PATTERN = re.compile(r"^RQ\d+$")
ACADEMIC_YEAR_PATTERN = re.compile(r"^(\d{4})-(\d{4})$")


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(error: Any) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def json_payload() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def string_field(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    return value.strip() if isinstance(value, str) else ""


def current_academic_year() -> str:
    today = date.today()
    start_year = today.year if today.month >= 7 else today.year - 1
    return f"{start_year}-{start_year + 1}"


def valid_academic_year(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    match = ACADEMIC_YEAR_PATTERN.fullmatch(value)
    return bool(match and int(match.group(2)) == int(match.group(1)) + 1)


def student_checkin_window_open(now: datetime | None = None) -> bool:
    current_time = (now or datetime.now()).time()
    return time(9, 0) <= current_time < time(11, 0)


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            roll_number TEXT NOT NULL UNIQUE,
            class_name TEXT NOT NULL,
            study_year TEXT NOT NULL DEFAULT '',
            semester TEXT NOT NULL DEFAULT '',
            phone TEXT,
            branch TEXT NOT NULL DEFAULT 'General',
            academic_year TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_DATE
        );
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL,
            notes TEXT DEFAULT '',
            branch TEXT NOT NULL DEFAULT '',
            academic_year TEXT NOT NULL DEFAULT '',
            marked_by INTEGER,
            source TEXT NOT NULL DEFAULT 'manual',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id, date),
            FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
            FOREIGN KEY(marked_by) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'faculty')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS face_profiles (
            student_id INTEGER PRIMARY KEY,
            descriptor_json TEXT NOT NULL,
            enrolled_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS student_face_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            image_data BLOB NOT NULL,
            content_type TEXT NOT NULL DEFAULT 'image/jpeg',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS student_checkin_attempts (
            attempt_key TEXT PRIMARY KEY,
            failures INTEGER NOT NULL DEFAULT 0,
            window_started_at TEXT NOT NULL
        );
        """
    )
    student_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(students)").fetchall()
    }
    if "branch" not in student_columns:
        db.execute("ALTER TABLE students ADD COLUMN branch TEXT NOT NULL DEFAULT 'General'")
    if "academic_year" not in student_columns:
        db.execute("ALTER TABLE students ADD COLUMN academic_year TEXT NOT NULL DEFAULT ''")
    if "study_year" not in student_columns:
        db.execute("ALTER TABLE students ADD COLUMN study_year TEXT NOT NULL DEFAULT ''")
    if "semester" not in student_columns:
        db.execute("ALTER TABLE students ADD COLUMN semester TEXT NOT NULL DEFAULT ''")
    db.execute("UPDATE students SET study_year = class_name WHERE study_year = ''")
    db.execute(
        "UPDATE students SET academic_year = ? WHERE academic_year = ''",
        (current_academic_year(),),
    )
    existing_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(attendance)").fetchall()
    }
    if "branch" not in existing_columns:
        db.execute("ALTER TABLE attendance ADD COLUMN branch TEXT NOT NULL DEFAULT ''")
    if "academic_year" not in existing_columns:
        db.execute("ALTER TABLE attendance ADD COLUMN academic_year TEXT NOT NULL DEFAULT ''")
    if "marked_by" not in existing_columns:
        db.execute("ALTER TABLE attendance ADD COLUMN marked_by INTEGER REFERENCES users(id)")
    if "source" not in existing_columns:
        db.execute("ALTER TABLE attendance ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'")
    if "updated_at" not in existing_columns:
        db.execute("ALTER TABLE attendance ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
        db.execute(
            "UPDATE attendance SET updated_at = CURRENT_TIMESTAMP WHERE updated_at = ''"
        )
    db.execute(
        """
        UPDATE attendance SET
            branch = (SELECT branch FROM students WHERE students.id = attendance.student_id),
            academic_year = (SELECT academic_year FROM students WHERE students.id = attendance.student_id)
        WHERE branch = '' OR academic_year = ''
        """
    )
    db.commit()

    existing_count = db.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    if existing_count == 0:
        sample_students = [
            ("Aisha Karim", "STD-101", "Year 1", "Semester 1", "+1234567890", "General", current_academic_year()),
            ("Daniel Moyo", "STD-102", "Year 1", "Semester 1", "+1234567891", "General", current_academic_year()),
            ("Grace Ndlovu", "STD-103", "Year 1", "Semester 1", "+1234567892", "General", current_academic_year()),
            ("Liam Patel", "STD-104", "Year 2", "Semester 1", "+1234567893", "General", current_academic_year()),
            ("Noah Sibiya", "STD-105", "Year 2", "Semester 1", "+1234567894", "General", current_academic_year()),
            ("Sofia Khumalo", "STD-106", "Year 2", "Semester 1", "+1234567895", "General", current_academic_year()),
        ]
        db.executemany(
            """
            INSERT INTO students
                (name, roll_number, class_name, study_year, semester, phone, branch, academic_year)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (name, roll_number, study_year, study_year, semester, phone, branch, academic_year)
                for name, roll_number, study_year, semester, phone, branch, academic_year in sample_students
            ],
        )
        db.commit()


def require_auth(view: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Please log in to continue."}), 401
        user = get_db().execute(
            "SELECT id, username, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if user is None:
            session.clear()
            return jsonify({"error": "Your session has expired. Please log in again."}), 401
        g.current_user = user
        return view(*args, **kwargs)

    return wrapped


def require_admin(view: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(view)
    @require_auth
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        if g.current_user["role"] != "admin":
            return jsonify({"error": "Administrator access is required."}), 403
        return view(*args, **kwargs)

    return wrapped


def valid_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def valid_face_descriptor(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == FACE_DESCRIPTOR_SIZE
        and all(
            isinstance(item, (int, float))
            and not isinstance(item, bool)
            and math.isfinite(item)
            for item in value
        )
    )


def decode_face_images(values: Any) -> list[bytes] | None:
    if not isinstance(values, list) or len(values) != 3:
        return None
    decoded: list[bytes] = []
    total_bytes = 0
    for value in values:
        if not isinstance(value, str) or not value.startswith("data:image/jpeg;base64,"):
            return None
        try:
            image_bytes = base64.b64decode(value.partition(",")[2], validate=True)
        except (binascii.Error, ValueError):
            return None
        if (
            not image_bytes.startswith(b"\xff\xd8\xff")
            or len(image_bytes) > MAX_FACE_IMAGE_BYTES
        ):
            return None
        total_bytes += len(image_bytes)
        decoded.append(image_bytes)
    if total_bytes > 3 * MAX_FACE_IMAGE_BYTES:
        return None
    return decoded


def attendance_summary(
    selected_date: str,
    academic_year: str | None = None,
    branch: str | None = None,
) -> dict[str, Any]:
    db = get_db()
    filters = ["date = ?"]
    parameters: list[Any] = [selected_date]
    if academic_year:
        filters.append("academic_year = ?")
        parameters.append(academic_year)
    if branch:
        filters.append("branch = ?")
        parameters.append(branch)
    where_clause = " AND ".join(filters)
    counts = db.execute(
        f"""
        SELECT
            COUNT(*) AS marked,
            SUM(CASE WHEN status = 'present' THEN 1 ELSE 0 END) AS present,
            SUM(CASE WHEN status = 'late' THEN 1 ELSE 0 END) AS late,
            SUM(CASE WHEN status = 'excused' THEN 1 ELSE 0 END) AS excused,
            SUM(CASE WHEN status = 'absent' THEN 1 ELSE 0 END) AS absent
        FROM attendance WHERE {where_clause}
        """,
        parameters,
    ).fetchone()
    student_filters: list[str] = []
    student_parameters: list[Any] = []
    if academic_year:
        student_filters.append("academic_year = ?")
        student_parameters.append(academic_year)
    if branch:
        student_filters.append("branch = ?")
        student_parameters.append(branch)
    student_where = f"WHERE {' AND '.join(student_filters)}" if student_filters else ""
    total_students = db.execute(
        f"SELECT COUNT(*) FROM students {student_where}", student_parameters
    ).fetchone()[0]
    marked = counts["marked"] or 0
    present = counts["present"] or 0
    late = counts["late"] or 0
    return {
        "date": selected_date,
        "academic_year": academic_year or "all",
        "branch": branch or "all",
        "total_students": total_students,
        "marked": marked,
        "unmarked": max(total_students - marked, 0),
        "present": present,
        "late": late,
        "excused": counts["excused"] or 0,
        "absent": counts["absent"] or 0,
        "percentage": round((present + late) / total_students * 100, 2) if total_students else 0,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/auth/status", methods=["GET"])
def auth_status():
    db = get_db()
    setup_required = db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    user = None
    user_id = session.get("user_id")
    if user_id:
        user_row = db.execute(
            "SELECT id, username, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if user_row:
            user = dict(user_row)
        else:
            session.clear()
    return jsonify({"setup_required": setup_required, "user": user})


@app.route("/api/auth/setup", methods=["POST"])
def setup_admin():
    payload = json_payload()
    username = string_field(payload, "username")
    password = payload.get("password")
    if not isinstance(password, str):
        password = ""
    if len(username) < 3 or len(username) > 80:
        return jsonify({"error": "Username must be between 3 and 80 characters."}), 400
    if len(password) < 12:
        return jsonify({"error": "Admin password must be at least 12 characters."}), 400

    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            db.rollback()
            return jsonify({"error": "Initial administrator setup has already been completed."}), 409
        cursor = db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
            (username, generate_password_hash(password)),
        )
        db.commit()
        session.clear()
        session["user_id"] = cursor.lastrowid
        return jsonify({"id": cursor.lastrowid, "username": username, "role": "admin"}), 201
    except sqlite3.IntegrityError:
        db.rollback()
        return jsonify({"error": "That username is already in use."}), 409


@app.route("/api/auth/login", methods=["POST"])
def login():
    payload = json_payload()
    username = string_field(payload, "username")
    password = payload.get("password")
    if not isinstance(password, str):
        password = ""
    user = get_db().execute(
        "SELECT id, username, password_hash, role FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid username or password."}), 401
    session.clear()
    session["user_id"] = user["id"]
    return jsonify({"id": user["id"], "username": user["username"], "role": user["role"]})


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out."})


@app.route("/api/users", methods=["GET", "POST"])
@require_admin
def users():
    db = get_db()
    if request.method == "GET":
        rows = db.execute(
            "SELECT id, username, role, created_at FROM users ORDER BY username"
        ).fetchall()
        return jsonify([dict(row) for row in rows])

    payload = json_payload()
    username = string_field(payload, "username")
    password = payload.get("password")
    if not isinstance(password, str):
        password = ""
    role = payload.get("role") or "faculty"
    if len(username) < 3 or len(username) > 80:
        return jsonify({"error": "Username must be between 3 and 80 characters."}), 400
    if len(password) < 12:
        return jsonify({"error": "Password must be at least 12 characters."}), 400
    if role != "faculty":
        return jsonify({"error": "Only faculty accounts can be created here."}), 400
    try:
        cursor = db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'faculty')",
            (username, generate_password_hash(password)),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "That username is already in use."}), 409
    return jsonify({"id": cursor.lastrowid, "username": username, "role": "faculty"}), 201


@app.route("/api/students", methods=["GET", "POST"])
@require_auth
def students():
    db = get_db()
    if request.method == "GET":
        rows = db.execute(
            """
            SELECT s.*, EXISTS(
                SELECT 1 FROM face_profiles fp WHERE fp.student_id = s.id
            ) AS has_face_profile
            FROM students s ORDER BY s.academic_year DESC, s.branch, s.study_year, s.semester, s.name
            """
        ).fetchall()
        return jsonify([dict(row) for row in rows])

    payload = json_payload()
    name = string_field(payload, "name")
    roll_number = string_field(payload, "roll_number").upper()
    study_year = string_field(payload, "study_year")
    semester = string_field(payload, "semester")
    phone = string_field(payload, "phone")
    branch = string_field(payload, "branch")
    academic_year = string_field(payload, "academic_year")
    if not name or not roll_number or not study_year or not semester or not branch:
        return jsonify({"error": "Name, roll number, year of study, semester, and branch are required."}), 400
    if not ROLL_NUMBER_PATTERN.fullmatch(roll_number):
        return jsonify({"error": "Roll number must be 2-40 letters, digits, or . _ / - characters."}), 400
    if len(branch) > 100:
        return jsonify({"error": "Branch name must be 100 characters or fewer."}), 400
    if len(study_year) > 50 or len(semester) > 50:
        return jsonify({"error": "Year of study and semester must be 50 characters or fewer."}), 400
    if not valid_academic_year(academic_year):
        return jsonify({"error": "Academic year must be consecutive years in YYYY-YYYY format."}), 400
    try:
        if db.execute(
            "SELECT 1 FROM students WHERE UPPER(roll_number) = ?", (roll_number,)
        ).fetchone():
            return jsonify({"error": "A student with that roll number already exists."}), 409
        cursor = db.execute(
            """
            INSERT INTO students
                (name, roll_number, class_name, study_year, semester, phone, branch, academic_year)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, roll_number, study_year, study_year, semester, phone, branch, academic_year),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "A student with that roll number already exists."}), 409
    created = db.execute("SELECT * FROM students WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return jsonify(dict(created)), 201


@app.route("/api/student/check-in", methods=["POST"])
def student_check_in():
    if not student_checkin_window_open():
        return jsonify({"error": "Student attendance check-in is available only between 9:00 AM and 11:00 AM."}), 403

    payload = json_payload()
    roll_number = string_field(payload, "roll_number").upper()
    descriptor = payload.get("descriptor")
    if not ROLL_NUMBER_PATTERN.fullmatch(roll_number):
        return jsonify({"error": "Enter a valid roll number and try again."}), 400
    if not valid_face_descriptor(descriptor):
        return jsonify({"error": "A valid live face scan is required."}), 400

    db = get_db()
    attempt_key = hashlib.sha256(
        f"{request.remote_addr or 'unknown'}:{roll_number}".encode("utf-8")
    ).hexdigest()
    now = datetime.utcnow()
    attempt = db.execute(
        "SELECT failures, window_started_at FROM student_checkin_attempts WHERE attempt_key = ?",
        (attempt_key,),
    ).fetchone()
    if attempt:
        try:
            window_started = datetime.strptime(attempt["window_started_at"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            window_started = now
        if (now - window_started).total_seconds() < 600 and attempt["failures"] >= 5:
            return jsonify({"error": "Too many unsuccessful attempts. Wait 10 minutes and try again."}), 429

    student = db.execute(
        """
        SELECT s.id, s.name, s.roll_number, s.study_year, s.semester, s.branch, s.academic_year,
               fp.descriptor_json
        FROM students s JOIN face_profiles fp ON fp.student_id = s.id
        WHERE UPPER(s.roll_number) = ?
        """,
        (roll_number,),
    ).fetchone()
    matched = False
    if student:
        saved_descriptor = json.loads(student["descriptor_json"])
        if valid_face_descriptor(saved_descriptor):
            distance = math.sqrt(
                sum((float(observed) - float(saved)) ** 2 for observed, saved in zip(descriptor, saved_descriptor))
            )
            matched = distance <= FACE_MATCH_THRESHOLD

    if not matched:
        failures = 1
        window_started_at = now.strftime("%Y-%m-%d %H:%M:%S")
        if attempt:
            try:
                previous_start = datetime.strptime(attempt["window_started_at"], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                previous_start = now
            if (now - previous_start).total_seconds() < 600:
                failures = attempt["failures"] + 1
                window_started_at = attempt["window_started_at"]
        db.execute(
            """
            INSERT INTO student_checkin_attempts (attempt_key, failures, window_started_at)
            VALUES (?, ?, ?)
            ON CONFLICT(attempt_key) DO UPDATE SET
                failures = excluded.failures,
                window_started_at = excluded.window_started_at
            """,
            (attempt_key, failures, window_started_at),
        )
        db.commit()
        return jsonify({"error": "Roll number and face did not match an enrolled student. Try again or ask staff for help."}), 403

    db.execute("DELETE FROM student_checkin_attempts WHERE attempt_key = ?", (attempt_key,))
    cursor = db.execute(
        """
        INSERT OR IGNORE INTO attendance
            (student_id, date, status, notes, branch, academic_year, marked_by, source)
        VALUES (?, ?, 'present', 'Student self check-in with face verification', ?, ?, NULL, 'student-face')
        """,
        (student["id"], str(date.today()), student["branch"], student["academic_year"]),
    )
    db.commit()
    if cursor.rowcount == 0:
        return jsonify(
            {
                "message": "Attendance is already recorded for today.",
                "duplicate": True,
                "academic_year": student["academic_year"],
                "branch": student["branch"],
                "study_year": student["study_year"],
                "semester": student["semester"],
            }
        )
    return jsonify(
        {
            "message": "Face verified. Attendance has been marked.",
            "duplicate": False,
            "date": str(date.today()),
            "academic_year": student["academic_year"],
            "branch": student["branch"],
            "study_year": student["study_year"],
            "semester": student["semester"],
        }
    ), 201


@app.route("/api/face-profiles", methods=["GET"])
@require_auth
def get_face_profiles():
    profiles = get_db().execute(
        "SELECT student_id, descriptor_json FROM face_profiles"
    ).fetchall()
    return jsonify(
        [
            {"student_id": row["student_id"], "descriptor": json.loads(row["descriptor_json"])}
            for row in profiles
        ]
    )


@app.route("/api/face-profiles/<int:student_id>", methods=["POST", "DELETE"])
@require_auth
def face_profile(student_id: int):
    db = get_db()
    student = db.execute("SELECT id FROM students WHERE id = ?", (student_id,)).fetchone()
    if student is None:
        return jsonify({"error": "Student not found."}), 404

    if request.method == "DELETE":
        db.execute("DELETE FROM face_profiles WHERE student_id = ?", (student_id,))
        db.execute("DELETE FROM student_face_images WHERE student_id = ?", (student_id,))
        db.commit()
        return jsonify({"message": "Face photos and profile deleted."})

    payload = json_payload()
    descriptor = payload.get("descriptor")
    images = decode_face_images(payload.get("images"))
    if payload.get("consent") is not True:
        return jsonify({"error": "Student or guardian consent is required before face enrollment."}), 400
    if not valid_face_descriptor(descriptor):
        return jsonify({"error": "A valid face descriptor is required."}), 400
    if images is None:
        return jsonify({"error": "Three valid JPEG face images are required (up to 1 MB each)."}), 400

    try:
        db.execute("BEGIN")
        db.execute("DELETE FROM student_face_images WHERE student_id = ?", (student_id,))
        db.execute(
            """
            INSERT INTO face_profiles (student_id, descriptor_json, enrolled_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(student_id) DO UPDATE SET
                descriptor_json = excluded.descriptor_json,
                enrolled_at = CURRENT_TIMESTAMP
            """,
            (student_id, json.dumps(descriptor, separators=(",", ":"))),
        )
        db.executemany(
            "INSERT INTO student_face_images (student_id, image_data) VALUES (?, ?)",
            [(student_id, image) for image in images],
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return jsonify({"message": "Face images and recognition profile saved."}), 201


@app.route("/api/attendance", methods=["GET", "POST"])
@require_auth
def attendance():
    db = get_db()
    if request.method == "GET":
        selected_date = request.args.get("date") or str(date.today())
        academic_year = request.args.get("academic_year", "")
        branch = request.args.get("branch", "")
        if not valid_date(selected_date):
            return jsonify({"error": "Date must use YYYY-MM-DD format."}), 400
        if academic_year and not valid_academic_year(academic_year):
            return jsonify({"error": "Academic year must use YYYY-YYYY format."}), 400
        filters = ["a.date = ?"]
        parameters: list[Any] = [selected_date]
        if academic_year:
            filters.append("a.academic_year = ?")
            parameters.append(academic_year)
        if branch:
            filters.append("a.branch = ?")
            parameters.append(branch)
        rows = db.execute(
            f"""
            SELECT a.id, a.student_id, a.date, a.status, a.notes, a.source,
                   a.updated_at, a.branch, a.academic_year,
                   s.name AS student_name, s.roll_number, s.study_year, s.semester,
                   u.username AS marked_by
            FROM attendance a
            INNER JOIN students s ON s.id = a.student_id
            LEFT JOIN users u ON u.id = a.marked_by
            WHERE {" AND ".join(filters)}
            ORDER BY a.academic_year DESC, a.branch, s.study_year, s.semester, s.name
            """,
            parameters,
        ).fetchall()
        return jsonify([dict(row) for row in rows])

    payload = json_payload()
    selected_date = payload.get("date") or str(date.today())
    academic_year_filter = payload.get("academic_year") or ""
    branch_filter = payload.get("branch") or ""
    records = payload.get("records")
    if not valid_date(selected_date):
        return jsonify({"error": "Date must use YYYY-MM-DD format."}), 400
    if academic_year_filter and not valid_academic_year(academic_year_filter):
        return jsonify({"error": "Academic year must use YYYY-YYYY format."}), 400
    if not isinstance(academic_year_filter, str) or not isinstance(branch_filter, str):
        return jsonify({"error": "Invalid branch or academic year filter."}), 400
    if not isinstance(records, list) or not records:
        return jsonify({"error": "Attendance records are required."}), 400

    updates = []
    for item in records:
        if not isinstance(item, dict):
            return jsonify({"error": "Each attendance record must be an object."}), 400
        student_id = item.get("student_id")
        status = item.get("status")
        notes = item.get("notes") or ""
        if not isinstance(student_id, int) or isinstance(student_id, bool):
            return jsonify({"error": "Each record must include a valid student ID."}), 400
        if not isinstance(status, str) or status not in ATTENDANCE_STATUSES:
            return jsonify({"error": f"Unsupported attendance status: {status}"}), 400
        if not isinstance(notes, str) or len(notes) > 500:
            return jsonify({"error": "Attendance notes must be 500 characters or fewer."}), 400
        updates.append((student_id, status, notes.strip()))

    try:
        db.execute("BEGIN")
        for student_id, status, notes in updates:
            student = db.execute(
                "SELECT branch, academic_year FROM students WHERE id = ?",
                (student_id,),
            ).fetchone()
            if not student:
                db.rollback()
                return jsonify({"error": f"Student {student_id} does not exist."}), 400
            if (
                (academic_year_filter and academic_year_filter != student["academic_year"])
                or (branch_filter and branch_filter != student["branch"])
            ):
                db.rollback()
                return jsonify({"error": "A correction record is outside the selected branch or academic year."}), 400
            db.execute(
                """
                INSERT INTO attendance
                    (student_id, date, status, notes, branch, academic_year, marked_by, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'manual', CURRENT_TIMESTAMP)
                ON CONFLICT(student_id, date) DO UPDATE SET
                    status = excluded.status,
                    notes = excluded.notes,
                    branch = excluded.branch,
                    academic_year = excluded.academic_year,
                    marked_by = excluded.marked_by,
                    source = 'manual',
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    student_id,
                    selected_date,
                    status,
                    notes,
                    student["branch"],
                    student["academic_year"],
                    g.current_user["id"],
                ),
            )
        db.commit()
    except sqlite3.Error:
        db.rollback()
        raise
    return jsonify({"message": "Attendance saved. Manual corrections are recorded."})


@app.route("/api/attendance/automatic", methods=["POST"])
@require_auth
def automatic_attendance():
    payload = json_payload()
    student_id = payload.get("student_id")
    selected_date = payload.get("date") or str(date.today())
    if not isinstance(student_id, int) or isinstance(student_id, bool):
        return jsonify({"error": "A valid student ID is required."}), 400
    if not valid_date(selected_date):
        return jsonify({"error": "Date must use YYYY-MM-DD format."}), 400
    db = get_db()
    if not db.execute("SELECT 1 FROM students WHERE id = ?", (student_id,)).fetchone():
        return jsonify({"error": "Student not found."}), 404
    if not db.execute(
        "SELECT 1 FROM face_profiles WHERE student_id = ?", (student_id,)
    ).fetchone():
        return jsonify({"error": "Student does not have an enrolled face profile."}), 409
    student = db.execute(
        "SELECT branch, academic_year FROM students WHERE id = ?", (student_id,)
    ).fetchone()
    cursor = db.execute(
        """
        INSERT OR IGNORE INTO attendance
            (student_id, date, status, notes, branch, academic_year, marked_by, source)
        VALUES (?, ?, 'present', 'Recorded by webcam face match', ?, ?, ?, 'face')
        """,
        (student_id, selected_date, student["branch"], student["academic_year"], g.current_user["id"]),
    )
    db.commit()
    existing = db.execute(
        "SELECT status FROM attendance WHERE student_id = ? AND date = ?",
        (student_id, selected_date),
    ).fetchone()
    if cursor.rowcount == 0:
        return jsonify(
            {"message": "Attendance was already recorded for this date.", "status": existing["status"], "duplicate": True}
        )
    return jsonify({"message": "Attendance marked present.", "status": "present", "duplicate": False}), 201


@app.route("/api/summary", methods=["GET"])
@require_auth
def get_summary():
    selected_date = request.args.get("date") or str(date.today())
    academic_year = request.args.get("academic_year", "")
    branch = request.args.get("branch", "")
    if not valid_date(selected_date):
        return jsonify({"error": "Date must use YYYY-MM-DD format."}), 400
    if academic_year and not valid_academic_year(academic_year):
        return jsonify({"error": "Academic year must use YYYY-YYYY format."}), 400
    return jsonify(attendance_summary(selected_date, academic_year or None, branch or None))


@app.route("/api/reports/overview", methods=["GET"])
@require_auth
def staff_overview():
    selected_date = request.args.get("date") or str(date.today())
    study_year = request.args.get("study_year", "")
    if not valid_date(selected_date):
        return jsonify({"error": "Date must use YYYY-MM-DD format."}), 400
    student_filters: list[str] = []
    parameters: list[Any] = [selected_date]
    if study_year:
        student_filters.append("s.study_year = ?")
        parameters.append(study_year)
    student_where = f"WHERE {' AND '.join(student_filters)}" if student_filters else ""
    rows = get_db().execute(
        f"""
        SELECT s.id, s.name, s.roll_number, s.study_year, s.semester, s.phone,
               s.branch, s.academic_year, a.status,
               (
                   SELECT COUNT(*) FROM attendance history
                   WHERE history.student_id = s.id
                     AND history.status IN ('present', 'late')
               ) AS attended_days
        FROM students s
        LEFT JOIN attendance a ON a.student_id = s.id AND a.date = ?
        {student_where}
        ORDER BY s.academic_year DESC, s.branch, s.study_year, s.semester, s.name
        """,
        parameters,
    ).fetchall()

    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["academic_year"], row["branch"], row["study_year"])
        group = groups.setdefault(
            key,
            {
                "academic_year": row["academic_year"],
                "branch": row["branch"],
                "study_year": row["study_year"],
                "present": 0,
                "absent": 0,
                "excused": 0,
                "unmarked": 0,
                "total": 0,
                "students": [],
            },
        )
        status = row["status"] or "unmarked"
        group["total"] += 1
        if status in {"present", "late"}:
            group["present"] += 1
        elif status == "absent":
            group["absent"] += 1
        elif status == "excused":
            group["excused"] += 1
        else:
            group["unmarked"] += 1
        student = dict(row)
        student["status"] = status
        group["students"].append(student)

    group_list = list(groups.values())
    return jsonify(
        {
            "date": selected_date,
            "study_year": study_year or "all",
            "summary": {
                "total_students": sum(group["total"] for group in group_list),
                "present": sum(group["present"] for group in group_list),
                "absent": sum(group["absent"] for group in group_list),
            },
            "groups": group_list,
        }
    )


@app.route("/api/reports/daily", methods=["GET"])
@require_auth
def daily_report():
    selected_date = request.args.get("date") or str(date.today())
    academic_year = request.args.get("academic_year", "")
    branch = request.args.get("branch", "")
    if not valid_date(selected_date):
        return jsonify({"error": "Date must use YYYY-MM-DD format."}), 400
    if academic_year and not valid_academic_year(academic_year):
        return jsonify({"error": "Academic year must use YYYY-YYYY format."}), 400
    filters = ["a.date = ?"]
    parameters: list[Any] = [selected_date]
    if academic_year:
        filters.append("a.academic_year = ?")
        parameters.append(academic_year)
    if branch:
        filters.append("a.branch = ?")
        parameters.append(branch)
    records = get_db().execute(
        f"""
        SELECT a.student_id, s.name, s.roll_number, s.study_year, s.semester, a.status, a.notes,
               a.source, a.updated_at, a.branch, a.academic_year,
               u.username AS marked_by
        FROM attendance a
        JOIN students s ON s.id = a.student_id
        LEFT JOIN users u ON u.id = a.marked_by
        WHERE {" AND ".join(filters)}
        ORDER BY a.academic_year DESC, a.branch, s.study_year, s.semester, s.name
        """,
        parameters,
    ).fetchall()
    return jsonify(
        {
            "summary": attendance_summary(selected_date, academic_year or None, branch or None),
            "records": [dict(row) for row in records],
        }
    )


@app.route("/api/students/<int:student_id>/history", methods=["GET"])
@require_auth
def student_history(student_id: int):
    db = get_db()
    student = db.execute(
        "SELECT id, name, roll_number, study_year, semester FROM students WHERE id = ?",
        (student_id,),
    ).fetchone()
    if student is None:
        return jsonify({"error": "Student not found."}), 404
    records = db.execute(
        """
        SELECT date, status, notes, source, updated_at, branch, academic_year FROM attendance
        WHERE student_id = ? ORDER BY date DESC
        """,
        (student_id,),
    ).fetchall()
    total = len(records)
    eligible = sum(1 for record in records if record["status"] != "excused")
    attended = sum(1 for record in records if record["status"] in {"present", "late"})
    return jsonify(
        {
            "student": dict(student),
            "total_recorded_days": total,
            "eligible_days": eligible,
            "attended_days": attended,
            "percentage": round(attended / eligible * 100, 2) if eligible else 0,
            "records": [dict(record) for record in records],
        }
    )


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="127.0.0.1", port=5000)
