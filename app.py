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
    os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
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
            "SELECT teacher_id FROM users WHERE role='Teacher' ORDER BY teacher_id DESC LIMIT 1",
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


@app.route("/teacher/grades/<int:class_id>", methods=["GET", "POST"])
@role_required("Teacher")
def teacher_grades(class_id):
    class_info = query("SELECT * FROM classes WHERE id=? AND teacher_id=?", (class_id, session["user_id"]), one=True)
    
    if not class_info:
        return redirect(url_for("teacher_classes"))
    
    if request.method == "POST":
        class_student_id = request.form.get("class_student_id")
        prelims = request.form.get("prelims")
        midterms = request.form.get("midterms")
        finals = request.form.get("finals")
        
        if class_student_id:
            prelims = float(prelims) if prelims else 0
            midterms = float(midterms) if midterms else 0
            finals = float(finals) if finals else 0
            final_grade = (prelims + midterms + finals) / 3
            remarks = "Passed" if final_grade >= 60 else "Failed"
            
            execute("""
                INSERT OR REPLACE INTO grades (class_student_id, prelims, midterms, finals, final_grade, remarks)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (class_student_id, prelims, midterms, finals, final_grade, remarks))
    
    students = query("""
        SELECT cs.id as class_student_id, cs.student_no, cs.first_name, cs.middle_name, cs.last_name, cs.suffix,
               g.prelims, g.midterms, g.finals, g.final_grade, g.remarks
        FROM class_students cs
        LEFT JOIN grades g ON cs.id = g.class_student_id
        WHERE cs.class_id=?
    """, (class_id,))
    
    return render_template("teacher/grade_entry.html", class_info=class_info, students=students)


@app.route("/teacher/add_student/<int:class_id>", methods=["POST"])
@role_required("Teacher")
def add_student_to_class(class_id):
    class_info = query("SELECT * FROM classes WHERE id=? AND teacher_id=?", (class_id, session["user_id"]), one=True)
    
    if not class_info:
        return redirect(url_for("teacher_classes"))
    
    student_no = request.form.get("student_no")
    first_name = request.form.get("first_name")
    middle_name = request.form.get("middle_name")
    last_name = request.form.get("last_name")
    suffix = request.form.get("suffix")
    gender = request.form.get("gender")
    
    if student_no and first_name and last_name:
        # Check if student already exists in users table
        existing_user = query("SELECT * FROM users WHERE username=?", (student_no,), one=True)
        
        if not existing_user:
            # Create user account
            execute("""
                INSERT INTO users (username, password, role, first_name, middle_name, last_name, suffix, gender, student_no)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (student_no, generate_password_hash(student_no), "Student", first_name, middle_name, last_name, suffix, gender, student_no))
        
        # Add student to class
        execute("""
            INSERT INTO class_students (class_id, student_no, first_name, middle_name, last_name, suffix, gender)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (class_id, student_no, first_name, middle_name, last_name, suffix, gender))
    
    return redirect(url_for("teacher_grades", class_id=class_id))


# ================= STUDENT =================
@app.route("/student/grades")
@role_required("Student")
def student_grades():
    student_no = session.get("student_no")

    data = query("""
        SELECT c.id, c.code, c.subject, c.section, u.first_name, u.last_name, g.final_grade, g.remarks
        FROM class_students cs
        JOIN classes c ON cs.class_id = c.id
        JOIN users u ON c.teacher_id = u.id
        LEFT JOIN grades g ON cs.id = g.class_student_id
        WHERE cs.student_no=?
    """, (student_no,))

    return render_template("student/grades.html", enrolled_classes=data)


@app.route("/student/course_grades/<int:class_id>")
@role_required("Student")
def student_course_grades(class_id):
    student_no = session.get("student_no")

    course = query("""
        SELECT c.*, u.first_name, u.last_name, g.prelims, g.midterms, g.finals, g.final_grade, g.remarks
        FROM classes c
        JOIN users u ON c.teacher_id = u.id
        JOIN class_students cs ON c.id = cs.class_id
        LEFT JOIN grades g ON cs.id = g.class_student_id
        WHERE c.id=? AND cs.student_no=?
    """, (class_id, student_no), one=True)

    return render_template("student/course_grades.html", course=course)


# ================= RUN APP =================
if __name__ == "__main__":
    with app.app_context():
        init_db()

    app.run(debug=True)
