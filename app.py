from flask import Flask, render_template, request, redirect, session, url_for, g, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os

app = Flask(__name__)
app.secret_key = "GRADES_PORTAL"

# ================= DATABASE CONFIG =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "students.db")


# ================= DB CONNECTION =================
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, timeout=30)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db:
        db.close()


def query(sql, params=(), one=False):
    cur = get_db().execute(sql, params)
    result = cur.fetchone() if one else cur.fetchall()
    cur.close()
    return result


def execute(sql, params=()):
    db = get_db()
    db.execute(sql, params)
    db.commit()


# ================= INIT DATABASE =================
def init_db():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT,
        first_name TEXT,
        middle_name TEXT,
        last_name TEXT,
        suffix TEXT,
        gender TEXT,
        student_no TEXT UNIQUE,
        teacher_id TEXT UNIQUE
    );

    CREATE TABLE IF NOT EXISTS classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_id INTEGER,
        code TEXT,
        subject TEXT,
        section TEXT,
        days TEXT,
        start_time TEXT,
        end_time TEXT,
        room TEXT
    );

    CREATE TABLE IF NOT EXISTS class_students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_id INTEGER,
        student_no TEXT,
        first_name TEXT,
        middle_name TEXT,
        last_name TEXT,
        suffix TEXT,
        gender TEXT,
        UNIQUE(class_id, student_no)
    );

    CREATE TABLE IF NOT EXISTS grades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_student_id INTEGER UNIQUE,
        prelims REAL DEFAULT 0,
        midterms REAL DEFAULT 0,
        finals REAL DEFAULT 0,
        final_grade REAL DEFAULT 0,
        remarks TEXT DEFAULT 'Pending'
    );
    """)

    # default admin
    cur.execute("SELECT * FROM users WHERE username='admin'")
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO users (username, password, role, first_name, last_name)
            VALUES (?, ?, ?, ?, ?)
        """, (
            "admin",
            generate_password_hash("admin123"),
            "Admin",
            "System",
            "Admin"
        ))

    conn.commit()
    conn.close()


# ================= AUTH DECORATORS =================
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def role_required(role):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if session.get("role") != role:
                return redirect(url_for("login"))
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ================= AUTH ROUTES =================
@app.route("/")
def index():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = query("SELECT * FROM users WHERE username=?", (username,), one=True)

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            session["student_no"] = user["student_no"]

            if user["role"] == "Admin":
                return redirect(url_for("admin_dashboard"))
            elif user["role"] == "Teacher":
                return redirect(url_for("teacher_classes"))
            else:
                return redirect(url_for("student_grades"))

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    role = session.get("role")

    if role == "Admin":
        return redirect(url_for("admin_dashboard"))
    elif role == "Teacher":
        return redirect(url_for("teacher_classes"))
    return redirect(url_for("student_grades"))


# ================= ADMIN =================
@app.route("/admin/dashboard", methods=["GET", "POST"])
@role_required("Admin")
def admin_dashboard():
    if request.method == "POST":
        first = request.form.get("first_name")
        last = request.form.get("last_name")

        last_teacher = query(
            "SELECT teacher_id FROM users WHERE role='Teacher' ORDER BY id DESC LIMIT 1",
            one=True
        )

        if last_teacher and last_teacher["teacher_id"]:
            num = int(last_teacher["teacher_id"][1:]) + 1
        else:
            num = 1

        teacher_id = f"T{num:04d}"

        execute("""
            INSERT INTO users (username, password, role, first_name, last_name, teacher_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            teacher_id,
            generate_password_hash(teacher_id),
            "Teacher",
            first,
            last,
            teacher_id
        ))

    teachers = query("SELECT * FROM users WHERE role='Teacher'")
    return render_template("admin/dashboard.html", teachers=teachers)


# ================= TEACHER =================
@app.route("/teacher/classes", methods=["GET", "POST"])
@role_required("Teacher")
def teacher_classes():
    if request.method == "POST":
        execute("""
            INSERT INTO classes (teacher_id, code, subject, section)
            VALUES (?, ?, ?, ?)
        """, (
            session["user_id"],
            request.form["code"],
            request.form["subject"],
            request.form["section"]
        ))

    classes = query("SELECT * FROM classes WHERE teacher_id=?", (session["user_id"],))
    return render_template("teacher/classes.html", classes=classes)


# ================= STUDENT =================
@app.route("/student/grades")
@role_required("Student")
def student_grades():
    student_no = session.get("student_no")

    data = query("""
        SELECT c.code, c.subject, g.final_grade, g.remarks
        FROM class_students cs
        JOIN classes c ON cs.class_id = c.id
        LEFT JOIN grades g ON cs.id = g.class_student_id
        WHERE cs.student_no=?
    """, (student_no,))

    return render_template("student/grades.html", enrolled_classes=data)


# ================= RUN APP =================
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
