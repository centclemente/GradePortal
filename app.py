from flask import Flask, render_template, request, redirect, session, url_for, g, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your_secret_key_here_change_in_production'

from flask import Flask, render_template, request, redirect, session, url_for, g, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your_secret_key_here_change_in_production'

import os

# This finds the folder where app.py is currently sitting
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# This builds the path to students.db inside that same folder
DATABASE = os.path.join(BASE_DIR, 'students.db')

def get_db_connection():
    # This now works on ANY computer because it looks in the local folder
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

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

@app.template_filter('to_12hour')
def to_12hour(time_str):
    """Convert 24-hour time format to 12-hour format with AM/PM"""
    if not time_str:
        return time_str
    try:
        from datetime import datetime
        time_obj = datetime.strptime(time_str, '%H:%M')
        return time_obj.strftime('%I:%M %p')
    except:
        return time_str

def query(sql, params=(), one=False):
    """Execute a SELECT query and return results"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    if one:
        result = cursor.fetchone()
    else:
        result = cursor.fetchall()
    return result

def execute_db(sql, params=()):
    """Execute an INSERT/UPDATE/DELETE query"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    conn.commit()

def init_db():
    """Initialize the database with the new simplified schema"""
    conn = sqlite3.connect(DATABASE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Check if users table already exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    users_exists = cursor.fetchone() is not None
    
    if not users_exists:
        # Create users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('Admin', 'Teacher', 'Student')),
                first_name TEXT,
                middle_name TEXT,
                last_name TEXT,
                suffix TEXT,
                gender TEXT,
                student_no TEXT UNIQUE,
                teacher_id TEXT UNIQUE
            )
        ''')
        
        # Create classes table (NEW SCHEMA: teachers create classes with code, subject, section)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS classes (
                id INTEGER PRIMARY KEY,
                teacher_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                subject TEXT NOT NULL,
                section TEXT NOT NULL,
                days TEXT,
                start_time TEXT,
                end_time TEXT,
                room TEXT,
                FOREIGN KEY (teacher_id) REFERENCES users(id)
            )
        ''')
        
        # Create class_students table (Junction: students added to classes directly, no enrollment process)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS class_students (
                id INTEGER PRIMARY KEY,
                class_id INTEGER NOT NULL,
                student_no TEXT NOT NULL,
                first_name TEXT NOT NULL,
                middle_name TEXT,
                last_name TEXT NOT NULL,
                suffix TEXT,
                gender TEXT,
                FOREIGN KEY (class_id) REFERENCES classes(id),
                UNIQUE(class_id, student_no)
            )
        ''')
        
        # Create grades table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS grades (
                id INTEGER PRIMARY KEY,
                class_student_id INTEGER NOT NULL,
                prelims REAL DEFAULT 0,
                midterms REAL DEFAULT 0,
                finals REAL DEFAULT 0,
                final_grade REAL DEFAULT 0,
                remarks TEXT DEFAULT 'Pending',
                FOREIGN KEY (class_student_id) REFERENCES class_students(id),
                UNIQUE(class_student_id)
            )
        ''')
        
        # Create default admin account
        cursor.execute(
            'INSERT INTO users (username, password, role, first_name, last_name) VALUES (?, ?, ?, ?, ?)',
            ('admin', generate_password_hash('admin123'), 'Admin', 'System', 'Admin')
        )
        
    conn.commit()
    conn.close()

def login_required(f):
    """Decorator to protect routes that require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(role):
    """Decorator to check user role"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session or session.get('role') != role:
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        error = None
        
        user = query('SELECT * FROM users WHERE username = ?', (username,), one=True)
        
        if user is None:
            error = 'Invalid username.'
        elif not check_password_hash(user['password'], password):
            error = 'Invalid password.'
        
        if error is None:
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['first_name'] = user['first_name']
            session['role'] = user['role']
            session['student_no'] = user['student_no']
            
            # Redirect based on role
            if user['role'] == 'Admin':
                return redirect(url_for('admin_dashboard'))
            elif user['role'] == 'Teacher':
                return redirect(url_for('teacher_classes'))
            else:
                return redirect(url_for('student_grades'))
        
        return render_template('login.html', error=error)
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Redirect to role-specific dashboard"""
    if session['role'] == 'Admin':
        return redirect(url_for('admin_dashboard'))
    elif session['role'] == 'Teacher':
        return redirect(url_for('teacher_classes'))
    else:
        return redirect(url_for('student_grades'))

@app.route('/student/student_grades')
def student_grades_redirect():
    return redirect(url_for('student_grades'))

# ============ ADMIN ROUTES ============

@app.route('/admin/dashboard', methods=['GET', 'POST'])
@role_required('Admin')
def admin_dashboard():
    """Admin panel for creating teachers"""
    if request.method == 'POST':
        first_name = request.form.get('first_name')
        middle_name = request.form.get('middle_name')
        last_name = request.form.get('last_name')
        suffix = request.form.get('suffix')
        gender = request.form.get('gender')
        
        # Generate teacher ID (T0001, T0002, etc.)
        last_teacher = query('SELECT teacher_id FROM users WHERE role = "Teacher" ORDER BY teacher_id DESC LIMIT 1', one=True)
        if last_teacher and last_teacher['teacher_id']:
            last_num = int(last_teacher['teacher_id'][1:])
            teacher_id = f'T{last_num + 1:04d}'
        else:
            teacher_id = 'T0001'
        
        # Username and password are both the teacher_id
        hashed_password = generate_password_hash(teacher_id)
        
        try:
            execute_db('''
                INSERT INTO users (username, password, role, first_name, middle_name, last_name, suffix, gender, teacher_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (teacher_id, hashed_password, 'Teacher', first_name, middle_name, last_name, suffix, gender, teacher_id))
        except sqlite3.IntegrityError:
            pass
    
    # Get all teachers
    teachers = query('''
        SELECT username, teacher_id, first_name, middle_name, last_name, suffix
        FROM users WHERE role = 'Teacher'
        ORDER BY teacher_id
    ''')
    
    return render_template('admin/dashboard.html', teachers=teachers)

# ============ TEACHER ROUTES ============

@app.route('/teacher/classes', methods=['GET', 'POST'])
@role_required('Teacher')
def teacher_classes():
    """Display classes for logged-in teacher and handle class creation"""
    if request.method == 'POST':
        code = request.form.get('code')
        subject = request.form.get('subject')
        section = request.form.get('section')
        days = request.form.get('days')
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        room = request.form.get('room', '')
        
        if code and subject and section:
            try:
                execute_db('''
                    INSERT INTO classes (teacher_id, code, subject, section, days, start_time, end_time, room)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (session['user_id'], code, subject, section, days, start_time, end_time, room))
            except Exception as e:
                print(f"Error: {e}")
        else:
            print("Missing required fields")
    
    # Get all classes taught by this teacher
    classes = query('''
        SELECT id, code, subject, section
        FROM classes
        WHERE teacher_id = ?
        ORDER BY code
    ''', (session['user_id'],))
    
    return render_template('teacher/classes.html', classes=classes)

@app.route('/teacher/class/<int:class_id>/grades', methods=['GET', 'POST'])
@role_required('Teacher')
def teacher_grades(class_id):
    """Manage grades for a specific class"""
    # Verify teacher owns this class
    class_info = query('''
        SELECT id, code, subject, section, days, start_time, end_time FROM classes
        WHERE id = ? AND teacher_id = ?
    ''', (class_id, session['user_id']), one=True)
    
    if not class_info:
        return redirect(url_for('teacher_classes'))
    
    if request.method == 'POST':
        class_student_id = request.form.get('class_student_id')
        prelims = request.form.get('prelims', 0)
        midterms = request.form.get('midterms', 0)
        finals = request.form.get('finals', 0)
        
        print(f"DEBUG: Attempting to save grades for class_student_id={class_student_id}")
        print(f"DEBUG: Grades - Prelims={prelims}, Midterms={midterms}, Finals={finals}")
        
        try:
            # Calculate final grade (average of prelims, midterms, finals)
            final_grade = (float(prelims) + float(midterms) + float(finals)) / 3
            print(f"DEBUG: Calculated final_grade={final_grade}")
            
            # Determine remarks
            remarks = 'Passed' if final_grade >= 75 else 'Failed'
            
            # Check if grades already exist for this student
            existing = query('SELECT id FROM grades WHERE class_student_id = ?', (class_student_id,), one=True)
            if existing:
                # Update existing grades
                execute_db('''
                    UPDATE grades
                    SET prelims = ?, midterms = ?, finals = ?, final_grade = ?, remarks = ?
                    WHERE class_student_id = ?
                ''', (prelims, midterms, finals, final_grade, remarks, class_student_id))
                print(f"DEBUG: Grades updated for class_student_id={class_student_id}")
            else:
                # Insert new grades
                execute_db('''
                    INSERT INTO grades (class_student_id, prelims, midterms, finals, final_grade, remarks)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (class_student_id, prelims, midterms, finals, final_grade, remarks))
                print(f"DEBUG: Grades saved successfully for class_student_id={class_student_id}")
        except Exception as e:
            print(f"ERROR: Failed to save grades - {str(e)}")
        
        # Redirect to refresh the page and close modal
        return redirect(url_for('teacher_grades', class_id=class_id))
    
    # Get all students in this class with their grades
    students = query('''
        SELECT cs.id as class_student_id, cs.student_no, cs.first_name, cs.middle_name, cs.last_name,
               g.prelims, g.midterms, g.finals, g.final_grade, g.remarks
        FROM class_students cs
        LEFT JOIN grades g ON cs.id = g.class_student_id
        WHERE cs.class_id = ?
        ORDER BY cs.first_name, cs.last_name
    ''', (class_id,))
 
    return render_template('teacher/grade_entry.html', class_info=class_info, students=students)

@app.route('/teacher/class/<int:class_id>/search-students')
@role_required('Teacher')
def search_students(class_id):
    """API endpoint for searching students in a class"""
    search_query = request.args.get('q', '')
    
    students = query('''
        SELECT cs.id as class_student_id, cs.student_no, cs.first_name, cs.middle_name, cs.last_name,
               g.prelims, g.midterms, g.finals, g.final_grade, g.remarks
        FROM class_students cs
        LEFT JOIN grades g ON cs.id = g.class_student_id
        WHERE cs.class_id = ? AND (cs.student_no LIKE ? OR cs.first_name LIKE ? OR cs.last_name LIKE ?)
        ORDER BY cs.first_name, cs.last_name
        LIMIT 10
    ''', (class_id, f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'))
    
    return jsonify([{
        'id': s['class_student_id'],
        'student_no': s['student_no'],
        'name': f"{s['first_name']} {s['middle_name'] if s['middle_name'] else ''} {s['last_name']}",
        'prelims': s['prelims'],
        'midterms': s['midterms'],
        'finals': s['finals'],
        'final_grade': s['final_grade'],
        'remarks': s['remarks']
    } for s in students])

@app.route('/teacher/class/<int:class_id>/add-student', methods=['POST'])
@role_required('Teacher')
def add_student_to_class(class_id):
    """Add a student to a class"""
    # Verify teacher owns this class
    class_info = query('SELECT id FROM classes WHERE id = ? AND teacher_id = ?',
                      (class_id, session['user_id']), one=True)
    
    if not class_info:
        return redirect(url_for('teacher_classes'))
    
    student_no = request.form.get('student_no')
    first_name = request.form.get('first_name')
    middle_name = request.form.get('middle_name')
    last_name = request.form.get('last_name')
    suffix = request.form.get('suffix')
    gender = request.form.get('gender')
    
    try:
        # Check if student user account exists, if not create one
        existing_user = query('SELECT id FROM users WHERE username = ?', (student_no,), one=True)
        if not existing_user:
            hashed_password = generate_password_hash(student_no)
            execute_db('''
                INSERT INTO users (username, password, first_name, middle_name, last_name, role, student_no)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (student_no, hashed_password, first_name, middle_name, last_name, 'Student', student_no))
        
        # Add student to class
        execute_db('''
            INSERT INTO class_students (class_id, student_no, first_name, middle_name, last_name, suffix, gender)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (class_id, student_no, first_name, middle_name, last_name, suffix, gender))
        
        # Create grade record
        last_class_student = query('''
            SELECT id FROM class_students WHERE class_id = ? AND student_no = ?
        ''', (class_id, student_no), one=True)
        if last_class_student:
            execute_db('INSERT INTO grades (class_student_id) VALUES (?)', (last_class_student['id'],))
    except sqlite3.IntegrityError:
        pass
    
    return redirect(url_for('teacher_grades', class_id=class_id))

# ============ STUDENT ROUTES ============
@app.route('/student/grades')
@role_required('Student')
def student_grades():
    """Display all classes and grades for the student"""
    # Get enrolled classes with grades
    student_no = session.get('student_no')
    enrolled_classes = []
    if student_no:
        enrolled_classes = query('''
            SELECT c.id, c.code, c.subject,
                   u.first_name, u.middle_name, u.last_name,
                   g.prelims, g.midterms, g.finals, g.final_grade, g.remarks
            FROM class_students cs
            JOIN classes c ON cs.class_id = c.id
            JOIN users u ON c.teacher_id = u.id
            LEFT JOIN grades g ON cs.id = g.class_student_id
            WHERE cs.student_no = ?
            ORDER BY c.code
        ''', (student_no,))
    
    return render_template('student/grades.html', enrolled_classes=enrolled_classes)

@app.route('/student/course/<int:class_id>/grades')
@role_required('Student')
def student_course_grades(class_id):
    """Display grades for a specific course"""
    student_no = session.get('student_no')
    
    # Get the course details and grades
    course = query('''
        SELECT c.id, c.code, c.subject as name, c.section, c.days, c.start_time, c.end_time,
               u.first_name, u.middle_name, u.last_name,
               g.prelims, g.midterms, g.finals, g.final_grade, g.remarks
        FROM class_students cs
        JOIN classes c ON cs.class_id = c.id
        JOIN users u ON c.teacher_id = u.id
        LEFT JOIN grades g ON cs.id = g.class_student_id
        WHERE c.id = ? AND cs.student_no = ?
    ''', (class_id, student_no), one=True)
    
    if not course:
        return redirect(url_for('student_grades'))
    
    return render_template('student/course_grades.html', course=course)

@app.route('/teacher/profile')
@role_required('Teacher')
def teacher_profile():
    """Display teacher profile"""
    user_id = session.get('user_id')
    teacher = query('''
        SELECT id, username, first_name, middle_name, last_name, suffix, gender
        FROM users
        WHERE id = ? AND role = 'Teacher'
        LIMIT 1
    ''', (user_id,), one=True)
    
    if not teacher:
        return redirect(url_for('teacher_classes'))
    
    return render_template('teacher/profile.html', teacher=teacher)

@app.route('/teacher/profile/edit', methods=['GET', 'POST'])
@role_required('Teacher')
def edit_teacher_profile():
    """Edit teacher profile"""
    user_id = session.get('user_id')
    teacher = query('''
        SELECT id, username, first_name, middle_name, last_name, suffix, gender
        FROM users
        WHERE id = ? AND role = 'Teacher'
        LIMIT 1
    ''', (user_id,), one=True)
    
    if not teacher:
        return redirect(url_for('teacher_classes'))
    
    if request.method == 'POST':
        first_name = request.form.get('first_name')
        middle_name = request.form.get('middle_name')
        last_name = request.form.get('last_name')
        suffix = request.form.get('suffix')
        gender = request.form.get('gender')
        
        if first_name and last_name:
            execute_db('''
                UPDATE users
                SET first_name = ?, middle_name = ?, last_name = ?, suffix = ?, gender = ?
                WHERE id = ?
            ''', (first_name, middle_name or '', last_name, suffix or '', gender or '', user_id))
            
            return redirect(url_for('teacher_profile'))
    
    return render_template('teacher/edit_profile.html', teacher=teacher)

# ============ INITIALIZE DATABASE AND RUN APP ============

if __name__ == '__main__':
    init_db()
    app.run(debug=True)


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

@app.template_filter('to_12hour')
def to_12hour(time_str):
    """Convert 24-hour time format to 12-hour format with AM/PM"""
    if not time_str:
        return time_str
    try:
        from datetime import datetime
        time_obj = datetime.strptime(time_str, '%H:%M')
        return time_obj.strftime('%I:%M %p')
    except:
        return time_str

def query(sql, params=(), one=False):
    """Execute a SELECT query and return results"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    if one:
        result = cursor.fetchone()
    else:
        result = cursor.fetchall()
    return result

def execute_db(sql, params=()):
    """Execute an INSERT/UPDATE/DELETE query"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    conn.commit()

def init_db():
    """Initialize the database with the new simplified schema"""
    conn = sqlite3.connect(DATABASE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Check if users table already exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    users_exists = cursor.fetchone() is not None
    
    if not users_exists:
        # Create users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('Admin', 'Teacher', 'Student')),
                first_name TEXT,
                middle_name TEXT,
                last_name TEXT,
                suffix TEXT,
                gender TEXT,
                student_no TEXT UNIQUE,
                teacher_id TEXT UNIQUE
            )
        ''')
        
        # Create classes table (NEW SCHEMA: teachers create classes with code, subject, section)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS classes (
                id INTEGER PRIMARY KEY,
                teacher_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                subject TEXT NOT NULL,
                section TEXT NOT NULL,
                days TEXT,
                start_time TEXT,
                end_time TEXT,
                room TEXT,
                FOREIGN KEY (teacher_id) REFERENCES users(id)
            )
        ''')
        
        # Create class_students table (Junction: students added to classes directly, no enrollment process)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS class_students (
                id INTEGER PRIMARY KEY,
                class_id INTEGER NOT NULL,
                student_no TEXT NOT NULL,
                first_name TEXT NOT NULL,
                middle_name TEXT,
                last_name TEXT NOT NULL,
                suffix TEXT,
                gender TEXT,
                FOREIGN KEY (class_id) REFERENCES classes(id),
                UNIQUE(class_id, student_no)
            )
        ''')
        
        # Create grades table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS grades (
                id INTEGER PRIMARY KEY,
                class_student_id INTEGER NOT NULL,
                prelims REAL DEFAULT 0,
                midterms REAL DEFAULT 0,
                finals REAL DEFAULT 0,
                final_grade REAL DEFAULT 0,
                remarks TEXT DEFAULT 'Pending',
                FOREIGN KEY (class_student_id) REFERENCES class_students(id),
                UNIQUE(class_student_id)
            )
        ''')
        
        # Create default admin account
        cursor.execute(
            'INSERT INTO users (username, password, role, first_name, last_name) VALUES (?, ?, ?, ?, ?)',
            ('admin', generate_password_hash('admin123'), 'Admin', 'System', 'Admin')
        )
        
    conn.commit()
    conn.close()

def login_required(f):
    """Decorator to protect routes that require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(role):
    """Decorator to check user role"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session or session.get('role') != role:
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        error = None
        
        user = query('SELECT * FROM users WHERE username = ?', (username,), one=True)
        
        if user is None:
            error = 'Invalid username.'
        elif not check_password_hash(user['password'], password):
            error = 'Invalid password.'
        
        if error is None:
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['first_name'] = user['first_name']
            session['role'] = user['role']
            session['student_no'] = user['student_no']
            
            # Redirect based on role
            if user['role'] == 'Admin':
                return redirect(url_for('admin_dashboard'))
            elif user['role'] == 'Teacher':
                return redirect(url_for('teacher_classes'))
            else:
                return redirect(url_for('student_grades'))
        
        return render_template('login.html', error=error)
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Redirect to role-specific dashboard"""
    if session['role'] == 'Admin':
        return redirect(url_for('admin_dashboard'))
    elif session['role'] == 'Teacher':
        return redirect(url_for('teacher_classes'))
    else:
        return redirect(url_for('student_grades'))

@app.route('/student/student_grades')
def student_grades_redirect():
    return redirect(url_for('student_grades'))

# ============ ADMIN ROUTES ============

@app.route('/admin/dashboard', methods=['GET', 'POST'])
@role_required('Admin')
def admin_dashboard():
    """Admin panel for creating teachers"""
    if request.method == 'POST':
        first_name = request.form.get('first_name')
        middle_name = request.form.get('middle_name')
        last_name = request.form.get('last_name')
        suffix = request.form.get('suffix')
        gender = request.form.get('gender')
        
        # Generate teacher ID (T0001, T0002, etc.)
        last_teacher = query('SELECT teacher_id FROM users WHERE role = "Teacher" ORDER BY teacher_id DESC LIMIT 1', one=True)
        if last_teacher and last_teacher['teacher_id']:
            last_num = int(last_teacher['teacher_id'][1:])
            teacher_id = f'T{last_num + 1:04d}'
        else:
            teacher_id = 'T0001'
        
        # Username and password are both the teacher_id
        hashed_password = generate_password_hash(teacher_id)
        
        try:
            execute_db('''
                INSERT INTO users (username, password, role, first_name, middle_name, last_name, suffix, gender, teacher_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (teacher_id, hashed_password, 'Teacher', first_name, middle_name, last_name, suffix, gender, teacher_id))
        except sqlite3.IntegrityError:
            pass
    
    # Get all teachers
    teachers = query('''
        SELECT username, teacher_id, first_name, middle_name, last_name, suffix
        FROM users WHERE role = 'Teacher'
        ORDER BY teacher_id
    ''')
    
    return render_template('admin/dashboard.html', teachers=teachers)

# ============ TEACHER ROUTES ============

@app.route('/teacher/classes', methods=['GET', 'POST'])
@role_required('Teacher')
def teacher_classes():
    """Display classes for logged-in teacher and handle class creation"""
    if request.method == 'POST':
        code = request.form.get('code')
        subject = request.form.get('subject')
        section = request.form.get('section')
        days = request.form.get('days')
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        room = request.form.get('room', '')
        
        if code and subject and section:
            try:
                execute_db('''
                    INSERT INTO classes (teacher_id, code, subject, section, days, start_time, end_time, room)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (session['user_id'], code, subject, section, days, start_time, end_time, room))
            except Exception as e:
                print(f"Error: {e}")
        else:
            print("Missing required fields")
    
    # Get all classes taught by this teacher
    classes = query('''
        SELECT id, code, subject, section
        FROM classes
        WHERE teacher_id = ?
        ORDER BY code
    ''', (session['user_id'],))
    
    return render_template('teacher/classes.html', classes=classes)

@app.route('/teacher/class/<int:class_id>/grades', methods=['GET', 'POST'])
@role_required('Teacher')
def teacher_grades(class_id):
    """Manage grades for a specific class"""
    # Verify teacher owns this class
    class_info = query('''
        SELECT id, code, subject, section, days, start_time, end_time FROM classes
        WHERE id = ? AND teacher_id = ?
    ''', (class_id, session['user_id']), one=True)
    
    if not class_info:
        return redirect(url_for('teacher_classes'))
    
    if request.method == 'POST':
        class_student_id = request.form.get('class_student_id')
        prelims = request.form.get('prelims', 0)
        midterms = request.form.get('midterms', 0)
        finals = request.form.get('finals', 0)
        
        print(f"DEBUG: Attempting to save grades for class_student_id={class_student_id}")
        print(f"DEBUG: Grades - Prelims={prelims}, Midterms={midterms}, Finals={finals}")
        
        try:
            # Calculate final grade (average of prelims, midterms, finals)
            final_grade = (float(prelims) + float(midterms) + float(finals)) / 3
            print(f"DEBUG: Calculated final_grade={final_grade}")
            
            # Determine remarks
            remarks = 'Passed' if final_grade >= 75 else 'Failed'
            
            # Check if grades already exist for this student
            existing = query('SELECT id FROM grades WHERE class_student_id = ?', (class_student_id,), one=True)
            if existing:
                # Update existing grades
                execute_db('''
                    UPDATE grades
                    SET prelims = ?, midterms = ?, finals = ?, final_grade = ?, remarks = ?
                    WHERE class_student_id = ?
                ''', (prelims, midterms, finals, final_grade, remarks, class_student_id))
                print(f"DEBUG: Grades updated for class_student_id={class_student_id}")
            else:
                # Insert new grades
                execute_db('''
                    INSERT INTO grades (class_student_id, prelims, midterms, finals, final_grade, remarks)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (class_student_id, prelims, midterms, finals, final_grade, remarks))
                print(f"DEBUG: Grades saved successfully for class_student_id={class_student_id}")
        except Exception as e:
            print(f"ERROR: Failed to save grades - {str(e)}")
        
        # Redirect to refresh the page and close modal
        return redirect(url_for('teacher_grades', class_id=class_id))
    
    # Get all students in this class with their grades
    students = query('''
        SELECT cs.id as class_student_id, cs.student_no, cs.first_name, cs.middle_name, cs.last_name,
               g.prelims, g.midterms, g.finals, g.final_grade, g.remarks
        FROM class_students cs
        LEFT JOIN grades g ON cs.id = g.class_student_id
        WHERE cs.class_id = ?
        ORDER BY cs.first_name, cs.last_name
    ''', (class_id,))
 
    return render_template('teacher/grade_entry.html', class_info=class_info, students=students)

@app.route('/teacher/class/<int:class_id>/search-students')
@role_required('Teacher')
def search_students(class_id):
    """API endpoint for searching students in a class"""
    search_query = request.args.get('q', '')
    
    students = query('''
        SELECT cs.id as class_student_id, cs.student_no, cs.first_name, cs.middle_name, cs.last_name,
               g.prelims, g.midterms, g.finals, g.final_grade, g.remarks
        FROM class_students cs
        LEFT JOIN grades g ON cs.id = g.class_student_id
        WHERE cs.class_id = ? AND (cs.student_no LIKE ? OR cs.first_name LIKE ? OR cs.last_name LIKE ?)
        ORDER BY cs.first_name, cs.last_name
        LIMIT 10
    ''', (class_id, f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'))
    
    return jsonify([{
        'id': s['class_student_id'],
        'student_no': s['student_no'],
        'name': f"{s['first_name']} {s['middle_name'] if s['middle_name'] else ''} {s['last_name']}",
        'prelims': s['prelims'],
        'midterms': s['midterms'],
        'finals': s['finals'],
        'final_grade': s['final_grade'],
        'remarks': s['remarks']
    } for s in students])

@app.route('/teacher/class/<int:class_id>/add-student', methods=['POST'])
@role_required('Teacher')
def add_student_to_class(class_id):
    """Add a student to a class"""
    # Verify teacher owns this class
    class_info = query('SELECT id FROM classes WHERE id = ? AND teacher_id = ?',
                      (class_id, session['user_id']), one=True)
    
    if not class_info:
        return redirect(url_for('teacher_classes'))
    
    student_no = request.form.get('student_no')
    first_name = request.form.get('first_name')
    middle_name = request.form.get('middle_name')
    last_name = request.form.get('last_name')
    suffix = request.form.get('suffix')
    gender = request.form.get('gender')
    
    try:
        # Check if student user account exists, if not create one
        existing_user = query('SELECT id FROM users WHERE username = ?', (student_no,), one=True)
        if not existing_user:
            hashed_password = generate_password_hash(student_no)
            execute_db('''
                INSERT INTO users (username, password, first_name, middle_name, last_name, role, student_no)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (student_no, hashed_password, first_name, middle_name, last_name, 'Student', student_no))
        
        # Add student to class
        execute_db('''
            INSERT INTO class_students (class_id, student_no, first_name, middle_name, last_name, suffix, gender)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (class_id, student_no, first_name, middle_name, last_name, suffix, gender))
        
        # Create grade record
        last_class_student = query('''
            SELECT id FROM class_students WHERE class_id = ? AND student_no = ?
        ''', (class_id, student_no), one=True)
        if last_class_student:
            execute_db('INSERT INTO grades (class_student_id) VALUES (?)', (last_class_student['id'],))
    except sqlite3.IntegrityError:
        pass
    
    return redirect(url_for('teacher_grades', class_id=class_id))

# ============ STUDENT ROUTES ============
@app.route('/student/grades')
@role_required('Student')
def student_grades():
    """Display all classes and grades for the student"""
    # Get enrolled classes with grades
    student_no = session.get('student_no')
    enrolled_classes = []
    if student_no:
        enrolled_classes = query('''
            SELECT c.id, c.code, c.subject,
                   u.first_name, u.middle_name, u.last_name,
                   g.prelims, g.midterms, g.finals, g.final_grade, g.remarks
            FROM class_students cs
            JOIN classes c ON cs.class_id = c.id
            JOIN users u ON c.teacher_id = u.id
            LEFT JOIN grades g ON cs.id = g.class_student_id
            WHERE cs.student_no = ?
            ORDER BY c.code
        ''', (student_no,))
    
    return render_template('student/grades.html', enrolled_classes=enrolled_classes)

@app.route('/student/course/<int:class_id>/grades')
@role_required('Student')
def student_course_grades(class_id):
    """Display grades for a specific course"""
    student_no = session.get('student_no')
    
    # Get the course details and grades
    course = query('''
        SELECT c.id, c.code, c.subject as name, c.section, c.days, c.start_time, c.end_time,
               u.first_name, u.middle_name, u.last_name,
               g.prelims, g.midterms, g.finals, g.final_grade, g.remarks
        FROM class_students cs
        JOIN classes c ON cs.class_id = c.id
        JOIN users u ON c.teacher_id = u.id
        LEFT JOIN grades g ON cs.id = g.class_student_id
        WHERE c.id = ? AND cs.student_no = ?
    ''', (class_id, student_no), one=True)
    
    if not course:
        return redirect(url_for('student_grades'))
    
    return render_template('student/course_grades.html', course=course)

@app.route('/teacher/profile')
@role_required('Teacher')
def teacher_profile():
    """Display teacher profile"""
    user_id = session.get('user_id')
    teacher = query('''
        SELECT id, username, first_name, middle_name, last_name, suffix, gender
        FROM users
        WHERE id = ? AND role = 'Teacher'
        LIMIT 1
    ''', (user_id,), one=True)
    
    if not teacher:
        return redirect(url_for('teacher_classes'))
    
    return render_template('teacher/profile.html', teacher=teacher)

@app.route('/teacher/profile/edit', methods=['GET', 'POST'])
@role_required('Teacher')
def edit_teacher_profile():
    """Edit teacher profile"""
    user_id = session.get('user_id')
    teacher = query('''
        SELECT id, username, first_name, middle_name, last_name, suffix, gender
        FROM users
        WHERE id = ? AND role = 'Teacher'
        LIMIT 1
    ''', (user_id,), one=True)
    
    if not teacher:
        return redirect(url_for('teacher_classes'))
    
    if request.method == 'POST':
        first_name = request.form.get('first_name')
        middle_name = request.form.get('middle_name')
        last_name = request.form.get('last_name')
        suffix = request.form.get('suffix')
        gender = request.form.get('gender')
        
        if first_name and last_name:
            execute_db('''
                UPDATE users
                SET first_name = ?, middle_name = ?, last_name = ?, suffix = ?, gender = ?
                WHERE id = ?
            ''', (first_name, middle_name or '', last_name, suffix or '', gender or '', user_id))
            
            return redirect(url_for('teacher_profile'))
    
    return render_template('teacher/edit_profile.html', teacher=teacher)

# ============ INITIALIZE DATABASE AND RUN APP ============

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
