from flask import Flask, render_template, request, redirect, session, url_for, g, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os

app = Flask(__name__)

# ================= DATABASE =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.makedirs(BASE_DIR, exist_ok=True)
DATABASE = os.path.join(BASE_DIR, 'students.db')

def get_db_connection():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE, timeout=30.0)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_db(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query(sql, params=(), one=False):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchone() if one else cur.fetchall()

def execute_db(sql, params=()):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()

# ================= INIT DB =================
def init_db():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
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
        id INTEGER PRIMARY KEY,
        teacher_id INTEGER,
        code TEXT,
        subject TEXT,
        section TEXT,
        FOREIGN KEY (teacher_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS class_students (
        id INTEGER PRIMARY KEY,
        class_id INTEGER,
        student_no TEXT,
        first_name TEXT,
        middle_name TEXT,
        last_name TEXT,
        FOREIGN KEY (class_id) REFERENCES classes(id),
        UNIQUE(class_id, student_no)
    );

    CREATE TABLE IF NOT EXISTS grades (
        id INTEGER PRIMARY KEY,
        class_student_id INTEGER,
        prelims REAL DEFAULT 0,
        midterms REAL DEFAULT 0,
        finals REAL DEFAULT 0,
        final_grade REAL DEFAULT 0,
        remarks TEXT DEFAULT 'Pending',
        FOREIGN KEY (class_student_id) REFERENCES class_students(id),
        UNIQUE(class_student_id)
    );
    """)

    # default admin
    cur.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (username, password, role, first_name, last_name) VALUES (?, ?, ?, ?, ?)",
            ('admin', generate_password_hash('admin123'), 'Admin', 'System', 'Admin')
        )

    conn.commit()
    conn.close()

# ================= AUTH =================
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

def role_required(role):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if 'user_id' not in session or session.get('role') != role:
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return wrapper
    return decorator

# ================= ROUTES =================
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        user = query('SELECT * FROM users WHERE username = ?', (request.form['username'],), one=True)
        if user and check_password_hash(user['password'], request.form['password']):
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['student_no'] = user['student_no']
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Invalid credentials")
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    if session['role'] == 'Admin':
        return redirect(url_for('admin_dashboard'))
    elif session['role'] == 'Teacher':
        return redirect(url_for('teacher_classes'))
    return redirect(url_for('student_grades'))

# ================= ADMIN =================
@app.route('/admin/dashboard', methods=['GET','POST'])
@role_required('Admin')
def admin_dashboard():
    if request.method == 'POST':
        teacher_id = "T" + str(len(query("SELECT * FROM users WHERE role='Teacher'")) + 1).zfill(4)
        execute_db(
            "INSERT INTO users (username,password,role,teacher_id) VALUES (?,?,?,?)",
            (teacher_id, generate_password_hash(teacher_id), 'Teacher', teacher_id)
        )
    teachers = query("SELECT * FROM users WHERE role='Teacher'")
    return render_template('admin/dashboard.html', teachers=teachers)

# ================= TEACHER =================
@app.route('/teacher/classes', methods=['GET','POST'])
@role_required('Teacher')
def teacher_classes():
    if request.method == 'POST':
        execute_db(
            "INSERT INTO classes (teacher_id,code,subject,section) VALUES (?,?,?,?)",
            (session['user_id'], request.form['code'], request.form['subject'], request.form['section'])
        )
    classes = query("SELECT * FROM classes WHERE teacher_id=?", (session['user_id'],))
    return render_template('teacher/classes.html', classes=classes)

# ================= STUDENT =================
@app.route('/student/grades')
@role_required('Student')
def student_grades():
    data = query("""
        SELECT c.code,c.subject,g.final_grade,g.remarks
        FROM class_students cs
        JOIN classes c ON cs.class_id=c.id
        LEFT JOIN grades g ON cs.id=g.class_student_id
        WHERE cs.student_no=?
    """,(session['student_no'],))
    return render_template('student/grades.html', enrolled_classes=data)

# ================= RUN =================
if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        print("Creating database...")
        init_db()

    app.run(debug=True)
