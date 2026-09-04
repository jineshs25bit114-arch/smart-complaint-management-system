import os
import sqlite3
import hashlib
import csv
import io
from datetime import datetime, date
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, make_response, send_from_directory
)

app = Flask(__name__)
app.secret_key = 'scms_secret_key_2024_secure_xK9mP2'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'database.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def generate_complaint_id():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM complaints")
    count = cur.fetchone()[0] + 1
    conn.close()
    return f"CMP-{datetime.now().year}-{count:04d}"


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        full_name TEXT NOT NULL,
        student_id TEXT,
        department TEXT,
        phone TEXT,
        role TEXT DEFAULT 'student',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        code TEXT UNIQUE NOT NULL,
        head TEXT,
        email TEXT,
        phone TEXT,
        status TEXT DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complaint_id TEXT UNIQUE NOT NULL,
        user_id INTEGER NOT NULL,
        student_name TEXT NOT NULL,
        student_id_number TEXT,
        department TEXT,
        category TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        location TEXT,
        priority TEXT DEFAULT 'Medium',
        status TEXT DEFAULT 'Pending',
        assigned_department TEXT,
        admin_remarks TEXT,
        resolution_details TEXT,
        file_attachment TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS complaint_updates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complaint_id TEXT NOT NULL,
        status TEXT NOT NULL,
        remarks TEXT,
        updated_by TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (complaint_id) REFERENCES complaints(complaint_id)
    )''')

    # Seed data only once
    c.execute("SELECT id FROM users WHERE username = 'admin'")
    if c.fetchone() is None:
        _seed(c)

    conn.commit()
    conn.close()


def _seed(c):
    """Insert sample users, departments and complaints."""
    pw_admin = hashlib.sha256('admin123'.encode()).hexdigest()
    pw_student = hashlib.sha256('student123'.encode()).hexdigest()

    c.execute(
        "INSERT INTO users (username,email,password,full_name,role,department) VALUES (?,?,?,?,?,?)",
        ('admin', 'admin@college.edu', pw_admin, 'System Administrator', 'admin', 'Administration'))
    c.execute(
        "INSERT INTO users (username,email,password,full_name,student_id,department,role) VALUES (?,?,?,?,?,?,?)",
        ('student', 'student@college.edu', pw_student, 'John Doe', 'STU2024001',
         'Computer Science & Engineering', 'student'))
    c.execute(
        "INSERT INTO users (username,email,password,full_name,student_id,department,role) VALUES (?,?,?,?,?,?,?)",
        ('jane', 'jane@college.edu', pw_student, 'Jane Smith', 'STU2024002',
         'Information Technology', 'student'))

    depts = [
        ('Computer Science & Engineering', 'CSE', 'Dr. Rajesh Kumar', 'cse@college.edu', '044-2345-6701'),
        ('Information Technology', 'IT', 'Dr. Priya Sharma', 'it@college.edu', '044-2345-6702'),
        ('Electronics & Communication', 'ECE', 'Dr. Arun Patel', 'ece@college.edu', '044-2345-6703'),
        ('Mechanical Engineering', 'MECH', 'Dr. Suresh Reddy', 'mech@college.edu', '044-2345-6704'),
        ('Civil Engineering', 'CIVIL', 'Dr. Kavitha Nair', 'civil@college.edu', '044-2345-6705'),
        ('Administration', 'ADMIN', 'Mr. Venkat Rao', 'admin_dept@college.edu', '044-2345-6706'),
        ('Hostel Management', 'HOSTEL', 'Mr. Ramesh Babu', 'hostel@college.edu', '044-2345-6707'),
        ('Transport', 'TRANSPORT', 'Mr. Srinivas', 'transport@college.edu', '044-2345-6708'),
    ]
    for d in depts:
        c.execute("INSERT INTO departments (name,code,head,email,phone) VALUES (?,?,?,?,?)", d)

    # Sample complaints (user_id=2 is 'student', user_id=3 is 'jane')
    complaints = [
        ('CMP-2024-0001', 2, 'John Doe', 'STU2024001', 'Computer Science & Engineering',
         'Classroom', 'Projector Not Working in Room 301',
         'The projector in Room 301 of the CSE block has not been working for the past week. It flickers and shuts down after 5 minutes. This is affecting our lectures.',
         'Room 301, CSE Block', 'High', 'In Progress', 'IT', 'Technician has been assigned to inspect the projector.', None,
         None, '2024-08-15 09:30:00', '2024-08-18 14:20:00'),
        ('CMP-2024-0002', 2, 'John Doe', 'STU2024001', 'Computer Science & Engineering',
         'Hostel', 'Water Leakage in Hostel Block B',
         'There is continuous water leakage from the ceiling of Room 205 in Hostel Block B. The walls are getting damp and it is causing inconvenience.',
         'Room 205, Hostel Block B', 'Critical', 'Assigned', 'Hostel Management',
         'Maintenance team will visit tomorrow morning.', None,
         None, '2024-08-16 11:45:00', '2024-08-17 10:00:00'),
        ('CMP-2024-0003', 2, 'John Doe', 'STU2024001', 'Computer Science & Engineering',
         'Laboratory', 'Broken Computers in Lab 4',
         'Five computers in Lab 4 are not booting up. The hard drives seem to be failing. This is impacting our practical sessions.',
         'Lab 4, CSE Department', 'High', 'Resolved', 'IT',
         'All five computers have been repaired.', 'Hard drives were replaced and OS was reinstalled on all five machines. Lab 4 is now fully operational.',
         None, '2024-08-10 08:15:00', '2024-08-20 16:30:00'),
        ('CMP-2024-0004', 3, 'Jane Smith', 'STU2024002', 'Information Technology',
         'Canteen', 'Poor Food Quality in Main Canteen',
         'The food quality in the main canteen has declined significantly. Multiple students have complained about stale food and unhygienic preparation.',
         'Main Canteen', 'Medium', 'Under Review', None,
         'Complaint is being reviewed by the administration.', None,
         None, '2024-08-19 12:30:00', '2024-08-20 09:00:00'),
        ('CMP-2024-0005', 2, 'John Doe', 'STU2024001', 'Computer Science & Engineering',
         'Transport', 'Bus Route 5 Timing Issues',
         'Bus Route 5 has been arriving 20-30 minutes late consistently for the past two weeks. Students are missing their first period.',
         'Bus Route 5', 'Medium', 'Pending', None, None, None,
         None, '2024-08-21 07:00:00', '2024-08-21 07:00:00'),
        ('CMP-2024-0006', 3, 'Jane Smith', 'STU2024002', 'Information Technology',
         'Library', 'Insufficient Copies of Reference Books',
         'The library does not have enough copies of the DBMS reference textbook by Ramakrishnan. There are only 2 copies for 120 students.',
         'Central Library', 'Low', 'Resolved', 'Administration',
         'Additional copies have been ordered.', 'Ordered 15 new copies. Expected delivery within a week. Digital version also made available on the library portal.',
         None, '2024-08-05 14:00:00', '2024-08-12 11:00:00'),
        ('CMP-2024-0007', 2, 'John Doe', 'STU2024001', 'Computer Science & Engineering',
         'IT/Network', 'Wi-Fi Connectivity Issues in CSE Block',
         'The Wi-Fi in the CSE block drops frequently, especially during peak hours. Students are unable to access online resources during classes.',
         'CSE Block, All Floors', 'High', 'Pending', None, None, None,
         None, '2024-08-22 10:30:00', '2024-08-22 10:30:00'),
        ('CMP-2024-0008', 3, 'Jane Smith', 'STU2024002', 'Information Technology',
         'Infrastructure', 'Broken Chairs in IT Seminar Hall',
         'Around 15 chairs in the IT Seminar Hall are broken and unusable. This reduces the seating capacity during seminars and guest lectures.',
         'IT Seminar Hall', 'Medium', 'Rejected', 'Administration',
         'Chairs will be replaced during the next maintenance cycle. Not an urgent issue.', None,
         None, '2024-08-14 16:00:00', '2024-08-15 09:30:00'),
    ]

    for cmp in complaints:
        c.execute("""INSERT INTO complaints
            (complaint_id,user_id,student_name,student_id_number,department,
             category,title,description,location,priority,status,
             assigned_department,admin_remarks,resolution_details,
             file_attachment,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", cmp)

    # complaint_updates
    updates = [
        ('CMP-2024-0001', 'Pending', 'Complaint submitted.', 'John Doe', '2024-08-15 09:30:00'),
        ('CMP-2024-0001', 'Under Review', 'Reviewing the issue.', 'System Administrator', '2024-08-16 10:00:00'),
        ('CMP-2024-0001', 'In Progress', 'Technician has been assigned to inspect the projector.', 'System Administrator', '2024-08-18 14:20:00'),
        ('CMP-2024-0002', 'Pending', 'Complaint submitted.', 'John Doe', '2024-08-16 11:45:00'),
        ('CMP-2024-0002', 'Assigned', 'Assigned to Hostel Management.', 'System Administrator', '2024-08-17 10:00:00'),
        ('CMP-2024-0003', 'Pending', 'Complaint submitted.', 'John Doe', '2024-08-10 08:15:00'),
        ('CMP-2024-0003', 'In Progress', 'Repair work started.', 'System Administrator', '2024-08-14 09:00:00'),
        ('CMP-2024-0003', 'Resolved', 'All computers repaired and tested.', 'System Administrator', '2024-08-20 16:30:00'),
        ('CMP-2024-0004', 'Pending', 'Complaint submitted.', 'Jane Smith', '2024-08-19 12:30:00'),
        ('CMP-2024-0004', 'Under Review', 'Complaint is being reviewed.', 'System Administrator', '2024-08-20 09:00:00'),
        ('CMP-2024-0005', 'Pending', 'Complaint submitted.', 'John Doe', '2024-08-21 07:00:00'),
        ('CMP-2024-0006', 'Pending', 'Complaint submitted.', 'Jane Smith', '2024-08-05 14:00:00'),
        ('CMP-2024-0006', 'Resolved', 'Additional copies ordered and digital version made available.', 'System Administrator', '2024-08-12 11:00:00'),
        ('CMP-2024-0007', 'Pending', 'Complaint submitted.', 'John Doe', '2024-08-22 10:30:00'),
        ('CMP-2024-0008', 'Pending', 'Complaint submitted.', 'Jane Smith', '2024-08-14 16:00:00'),
        ('CMP-2024-0008', 'Rejected', 'Will be addressed in next maintenance cycle.', 'System Administrator', '2024-08-15 09:30:00'),
    ]
    for u in updates:
        c.execute("INSERT INTO complaint_updates (complaint_id,status,remarks,updated_by,created_at) VALUES (?,?,?,?,?)", u)


# ---------------------------------------------------------------------------
# Auth decorators
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Context processor
# ---------------------------------------------------------------------------

@app.context_processor
def inject_globals():
    return {'current_year': datetime.now().year}


# ---------------------------------------------------------------------------
# Routes – Auth
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('admin_dashboard') if session.get('role') == 'admin' else url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if not username or not password:
            flash('Please enter both username and password.', 'error')
            return render_template('login.html')

        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=? AND password=?", (username, pw_hash)).fetchone()
        conn.close()

        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            session['role'] = user['role']
            session['department'] = user['department']
            session['email'] = user['email']
            session['student_id'] = user['student_id'] or ''
            flash(f'Welcome back, {user["full_name"]}!', 'success')
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))


# ---------------------------------------------------------------------------
# Routes – Student
# ---------------------------------------------------------------------------

CATEGORIES = [
    'Classroom', 'Hostel', 'Laboratory', 'Library', 'Transport',
    'Canteen', 'Infrastructure', 'IT/Network', 'Faculty', 'Other'
]


@app.route('/dashboard')
@login_required
def dashboard():
    uid = session['user_id']
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM complaints WHERE user_id=?", (uid,)).fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM complaints WHERE user_id=? AND status IN ('Pending','Under Review')", (uid,)).fetchone()[0]
    in_progress = conn.execute("SELECT COUNT(*) FROM complaints WHERE user_id=? AND status IN ('Assigned','In Progress')", (uid,)).fetchone()[0]
    resolved = conn.execute("SELECT COUNT(*) FROM complaints WHERE user_id=? AND status='Resolved'", (uid,)).fetchone()[0]
    recent = conn.execute("SELECT * FROM complaints WHERE user_id=? ORDER BY created_at DESC LIMIT 5", (uid,)).fetchall()
    conn.close()
    stats = {'total': total, 'pending': pending, 'in_progress': in_progress, 'resolved': resolved}
    return render_template('dashboard.html', stats=stats, recent_complaints=recent, active_page='dashboard')


@app.route('/submit-complaint', methods=['GET', 'POST'])
@login_required
def submit_complaint():
    conn = get_db()
    departments = conn.execute("SELECT * FROM departments WHERE status='active' ORDER BY name").fetchall()

    if request.method == 'POST':
        cid = generate_complaint_id()
        student_name = request.form.get('student_name', session.get('full_name'))
        student_id_num = request.form.get('student_id', session.get('student_id', ''))
        department = request.form.get('department', '')
        category = request.form.get('category', '')
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        location = request.form.get('location', '').strip()
        priority = request.form.get('priority', 'Medium')

        if not title or not description or not category:
            flash('Please fill in all required fields.', 'error')
            conn.close()
            return render_template('submit_complaint.html', departments=departments,
                                   categories=CATEGORIES, active_page='submit_complaint')

        filename = None
        if 'attachment' in request.files:
            file = request.files['attachment']
            if file and file.filename:
                ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
                allowed = {'jpg', 'jpeg', 'png', 'gif', 'pdf', 'doc', 'docx'}
                if ext in allowed:
                    filename = f"{cid}_{file.filename}"
                    file.save(os.path.join(UPLOAD_FOLDER, filename))

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute("""INSERT INTO complaints
            (complaint_id,user_id,student_name,student_id_number,department,
             category,title,description,location,priority,status,
             file_attachment,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (cid, session['user_id'], student_name, student_id_num, department,
             category, title, description, location, priority, 'Pending',
             filename, now, now))
        conn.execute("INSERT INTO complaint_updates (complaint_id,status,remarks,updated_by,created_at) VALUES (?,?,?,?,?)",
                     (cid, 'Pending', 'Complaint submitted.', student_name, now))
        conn.commit()
        conn.close()
        flash(f'Complaint {cid} submitted successfully!', 'success')
        return redirect(url_for('my_complaints'))

    conn.close()
    return render_template('submit_complaint.html', departments=departments,
                           categories=CATEGORIES, active_page='submit_complaint')


@app.route('/my-complaints')
@login_required
def my_complaints():
    uid = session['user_id']
    f = request.args.get('filter', 'All')
    conn = get_db()
    if f == 'All':
        complaints = conn.execute("SELECT * FROM complaints WHERE user_id=? ORDER BY created_at DESC", (uid,)).fetchall()
    else:
        complaints = conn.execute("SELECT * FROM complaints WHERE user_id=? AND status=? ORDER BY created_at DESC", (uid, f)).fetchall()
    conn.close()
    return render_template('complaints.html', complaints=complaints, current_filter=f, active_page='my_complaints')


@app.route('/complaint/<complaint_id>')
@login_required
def complaint_details(complaint_id):
    conn = get_db()
    complaint = conn.execute("SELECT * FROM complaints WHERE complaint_id=?", (complaint_id,)).fetchone()
    if not complaint:
        conn.close()
        flash('Complaint not found.', 'error')
        return redirect(url_for('my_complaints'))
    if complaint['user_id'] != session['user_id'] and session.get('role') != 'admin':
        conn.close()
        flash('Access denied.', 'error')
        return redirect(url_for('my_complaints'))
    updates = conn.execute("SELECT * FROM complaint_updates WHERE complaint_id=? ORDER BY created_at ASC", (complaint_id,)).fetchall()
    conn.close()
    return render_template('complaint_details.html', complaint=complaint, updates=updates, active_page='my_complaints')


# ---------------------------------------------------------------------------
# Routes – Admin
# ---------------------------------------------------------------------------

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    conn = get_db()
    today = date.today().strftime('%Y-%m-%d')
    total = conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
    new_today = conn.execute("SELECT COUNT(*) FROM complaints WHERE DATE(created_at)=?", (today,)).fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM complaints WHERE status IN ('Pending','Under Review')").fetchone()[0]
    in_progress = conn.execute("SELECT COUNT(*) FROM complaints WHERE status IN ('Assigned','In Progress')").fetchone()[0]
    resolved = conn.execute("SELECT COUNT(*) FROM complaints WHERE status='Resolved'").fetchone()[0]
    high_priority = conn.execute("SELECT COUNT(*) FROM complaints WHERE priority IN ('High','Critical') AND status NOT IN ('Resolved','Rejected')").fetchone()[0]

    # Category data
    rows = conn.execute("SELECT category, COUNT(*) as cnt FROM complaints GROUP BY category").fetchall()
    category_data = {r['category']: r['cnt'] for r in rows}

    # Status data
    rows = conn.execute("SELECT status, COUNT(*) as cnt FROM complaints GROUP BY status").fetchall()
    status_data = {r['status']: r['cnt'] for r in rows}

    # Monthly data (current year)
    year = datetime.now().year
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    monthly_data = {}
    for i, m in enumerate(month_names, 1):
        cnt = conn.execute("SELECT COUNT(*) FROM complaints WHERE strftime('%%Y',created_at)=? AND strftime('%%m',created_at)=?",
                           (str(year), f'{i:02d}')).fetchone()[0]
        monthly_data[m] = cnt

    recent = conn.execute("SELECT * FROM complaints ORDER BY created_at DESC LIMIT 10").fetchall()
    conn.close()

    stats = {'total': total, 'new_today': new_today, 'pending': pending,
             'in_progress': in_progress, 'resolved': resolved, 'high_priority': high_priority}
    return render_template('admin_dashboard.html', stats=stats, category_data=category_data,
                           status_data=status_data, monthly_data=monthly_data,
                           recent_complaints=recent, active_page='admin_dashboard')


@app.route('/admin/complaints')
@admin_required
def admin_complaints():
    f = request.args.get('filter', 'All')
    cat = request.args.get('category', 'All')
    pri = request.args.get('priority', 'All')
    search = request.args.get('search', '').strip()

    conn = get_db()
    query = "SELECT * FROM complaints WHERE 1=1"
    params = []

    if f != 'All':
        query += " AND status=?"
        params.append(f)
    if cat != 'All':
        query += " AND category=?"
        params.append(cat)
    if pri != 'All':
        query += " AND priority=?"
        params.append(pri)
    if search:
        query += " AND (title LIKE ? OR complaint_id LIKE ? OR student_name LIKE ?)"
        s = f'%{search}%'
        params.extend([s, s, s])

    query += " ORDER BY created_at DESC"
    complaints = conn.execute(query, params).fetchall()
    conn.close()
    return render_template('admin_complaints.html', complaints=complaints,
                           current_filter=f, current_category=cat,
                           current_priority=pri, search_query=search,
                           active_page='admin_complaints')


@app.route('/admin/complaint/<complaint_id>', methods=['GET', 'POST'])
@admin_required
def admin_complaint_detail(complaint_id):
    conn = get_db()

    if request.method == 'POST':
        status = request.form.get('status', '')
        assigned = request.form.get('assigned_department', '')
        remarks = request.form.get('admin_remarks', '')
        resolution = request.form.get('resolution_details', '')
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        conn.execute("""UPDATE complaints SET status=?, assigned_department=?,
                        admin_remarks=?, resolution_details=?, updated_at=?
                        WHERE complaint_id=?""",
                     (status, assigned, remarks, resolution, now, complaint_id))
        conn.execute("INSERT INTO complaint_updates (complaint_id,status,remarks,updated_by,created_at) VALUES (?,?,?,?,?)",
                     (complaint_id, status, remarks, session.get('full_name', 'Admin'), now))
        conn.commit()
        flash('Complaint updated successfully!', 'success')

    complaint = conn.execute("SELECT * FROM complaints WHERE complaint_id=?", (complaint_id,)).fetchone()
    if not complaint:
        conn.close()
        flash('Complaint not found.', 'error')
        return redirect(url_for('admin_complaints'))

    departments = conn.execute("SELECT * FROM departments WHERE status='active' ORDER BY name").fetchall()
    updates = conn.execute("SELECT * FROM complaint_updates WHERE complaint_id=? ORDER BY created_at ASC", (complaint_id,)).fetchall()
    conn.close()
    return render_template('complaint_details.html', complaint=complaint, departments=departments,
                           updates=updates, is_admin=True, active_page='admin_complaints')


@app.route('/admin/delete-complaint/<complaint_id>')
@admin_required
def delete_complaint(complaint_id):
    conn = get_db()
    conn.execute("DELETE FROM complaint_updates WHERE complaint_id=?", (complaint_id,))
    conn.execute("DELETE FROM complaints WHERE complaint_id=?", (complaint_id,))
    conn.commit()
    conn.close()
    flash('Complaint deleted successfully.', 'success')
    return redirect(url_for('admin_complaints'))


# ---------------------------------------------------------------------------
# Routes – Departments
# ---------------------------------------------------------------------------

@app.route('/admin/departments')
@admin_required
def departments():
    conn = get_db()
    dept_list = conn.execute("SELECT * FROM departments ORDER BY name").fetchall()
    conn.close()
    return render_template('departments.html', departments=dept_list, active_page='departments')


@app.route('/admin/department/add', methods=['POST'])
@admin_required
def add_department():
    name = request.form.get('name', '').strip()
    code = request.form.get('code', '').strip().upper()
    head = request.form.get('head', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()

    if not name or not code:
        flash('Department name and code are required.', 'error')
        return redirect(url_for('departments'))

    conn = get_db()
    try:
        conn.execute("INSERT INTO departments (name,code,head,email,phone) VALUES (?,?,?,?,?)",
                     (name, code, head, email, phone))
        conn.commit()
        flash(f'Department "{name}" added successfully!', 'success')
    except sqlite3.IntegrityError:
        flash(f'Department code "{code}" already exists.', 'error')
    finally:
        conn.close()
    return redirect(url_for('departments'))


@app.route('/admin/department/delete/<int:dept_id>')
@admin_required
def delete_department(dept_id):
    conn = get_db()
    conn.execute("DELETE FROM departments WHERE id=?", (dept_id,))
    conn.commit()
    conn.close()
    flash('Department deleted successfully.', 'success')
    return redirect(url_for('departments'))


# ---------------------------------------------------------------------------
# Routes – Reports
# ---------------------------------------------------------------------------

@app.route('/admin/reports')
@admin_required
def reports():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
    resolved = conn.execute("SELECT COUNT(*) FROM complaints WHERE status='Resolved'").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM complaints WHERE status IN ('Pending','Under Review','Assigned','In Progress')").fetchone()[0]
    rejected = conn.execute("SELECT COUNT(*) FROM complaints WHERE status='Rejected'").fetchone()[0]
    resolution_rate = round((resolved / total * 100), 1) if total else 0

    rows = conn.execute("SELECT category, COUNT(*) as cnt FROM complaints GROUP BY category").fetchall()
    category_data = {r['category']: r['cnt'] for r in rows}

    rows = conn.execute("SELECT assigned_department, COUNT(*) as cnt FROM complaints WHERE assigned_department IS NOT NULL AND assigned_department != '' GROUP BY assigned_department").fetchall()
    department_data = {r['assigned_department']: r['cnt'] for r in rows}

    year = datetime.now().year
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    monthly_data = {}
    for i, m in enumerate(month_names, 1):
        cnt = conn.execute("SELECT COUNT(*) FROM complaints WHERE strftime('%%Y',created_at)=? AND strftime('%%m',created_at)=?",
                           (str(year), f'{i:02d}')).fetchone()[0]
        monthly_data[m] = cnt

    conn.close()
    stats = {'total': total, 'resolved': resolved, 'pending': pending,
             'rejected': rejected, 'resolution_rate': resolution_rate}
    return render_template('reports.html', stats=stats, category_data=category_data,
                           department_data=department_data, monthly_data=monthly_data,
                           active_page='reports')


# ---------------------------------------------------------------------------
# Routes – Profile
# ---------------------------------------------------------------------------

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    conn = get_db()
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()

        if full_name and email:
            try:
                conn.execute("UPDATE users SET full_name=?, email=?, phone=? WHERE id=?",
                             (full_name, email, phone, session['user_id']))
                conn.commit()
                session['full_name'] = full_name
                session['email'] = email
                flash('Profile updated successfully!', 'success')
            except sqlite3.IntegrityError:
                flash('Email already in use by another account.', 'error')

    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    conn.close()
    return render_template('profile.html', user=user, active_page='profile')


@app.route('/change-password', methods=['POST'])
@login_required
def change_password():
    current = request.form.get('current_password', '')
    new_pw = request.form.get('new_password', '')
    confirm = request.form.get('confirm_password', '')

    if not current or not new_pw or not confirm:
        flash('All password fields are required.', 'error')
        return redirect(url_for('profile'))
    if new_pw != confirm:
        flash('New passwords do not match.', 'error')
        return redirect(url_for('profile'))
    if len(new_pw) < 6:
        flash('Password must be at least 6 characters.', 'error')
        return redirect(url_for('profile'))

    conn = get_db()
    user = conn.execute("SELECT password FROM users WHERE id=?", (session['user_id'],)).fetchone()
    if hashlib.sha256(current.encode()).hexdigest() != user['password']:
        conn.close()
        flash('Current password is incorrect.', 'error')
        return redirect(url_for('profile'))

    conn.execute("UPDATE users SET password=? WHERE id=?",
                 (hashlib.sha256(new_pw.encode()).hexdigest(), session['user_id']))
    conn.commit()
    conn.close()
    flash('Password changed successfully!', 'success')
    return redirect(url_for('profile'))


# ---------------------------------------------------------------------------
# Routes – Export
# ---------------------------------------------------------------------------

@app.route('/admin/export-csv')
@admin_required
def export_csv():
    conn = get_db()
    rows = conn.execute("SELECT * FROM complaints ORDER BY created_at DESC").fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Complaint ID', 'Title', 'Category', 'Student Name', 'Department',
                     'Priority', 'Status', 'Assigned Department', 'Admin Remarks',
                     'Created Date', 'Updated Date'])
    for r in rows:
        writer.writerow([r['complaint_id'], r['title'], r['category'], r['student_name'],
                         r['department'], r['priority'], r['status'], r['assigned_department'] or '',
                         r['admin_remarks'] or '', r['created_at'], r['updated_at']])

    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=complaints_export_{date.today()}.csv'
    return response


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    init_db()
    print("\n" + "=" * 60)
    print("  SMART COMPLAINT MANAGEMENT SYSTEM")
    print("=" * 60)
    print("  Server running at: http://127.0.0.1:5000")
    print("  Admin login:   admin / admin123")
    print("  Student login:  student / student123")
    print("=" * 60 + "\n")
    app.run(debug=True, port=5000)
