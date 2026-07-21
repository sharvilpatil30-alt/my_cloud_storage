import os
import sqlite3
from datetime import datetime
from flask import (Flask, request, jsonify, render_template,
                   send_from_directory, redirect, url_for, session)
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'sharvil-cloud-secret-2025')

UPLOAD_FOLDER = 'uploads'
MAX_EXTRA_USERS = 5

app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024

CATEGORY_LIMITS = {
    'images':    50  * 1024 * 1024,
    'videos':    2   * 1024 * 1024 * 1024,
    'audio':     100 * 1024 * 1024,
    'documents': 100 * 1024 * 1024,
    'others':    100 * 1024 * 1024,
}

CATEGORY_LIMIT_LABELS = {
    'images':    '50 MB',
    'videos':    '2 GB',
    'audio':     '100 MB',
    'documents': '100 MB',
    'others':    '100 MB',
}

CATEGORY_MAP = {
    'images':    ['jpg','jpeg','png','gif','webp','svg'],
    'documents': ['pdf','doc','docx','txt','xlsx','xls','csv','pptx'],
    'videos':    ['mp4','mov','avi','mkv','wmv'],
    'audio':     ['mp3','wav','aac','flac','ogg'],
}

for cat in ['images','documents','videos','audio','others']:
    os.makedirs(os.path.join(UPLOAD_FOLDER, cat), exist_ok=True)

def get_category(filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    for category, exts in CATEGORY_MAP.items():
        if ext in exts:
            return category
    return 'others'

def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        size INTEGER NOT NULL,
        file_type TEXT NOT NULL,
        category TEXT NOT NULL,
        uploaded_at TEXT NOT NULL,
        uploaded_by TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        created_at TEXT NOT NULL)''')
    conn.commit()
    existing = conn.execute("SELECT * FROM users WHERE username='sharvil'").fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO users (username, password_hash, is_admin, created_at) VALUES (?,?,?,?)",
            ('sharvil', generate_password_hash('sharvil123'), 1, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        conn.commit()
    conn.close()

def sync_files_to_db():
    conn = get_db()
    for cat in ['images','documents','videos','audio','others']:
        folder = os.path.join(UPLOAD_FOLDER, cat)
        if not os.path.exists(folder):
            continue
        for filename in os.listdir(folder):
            filepath = os.path.join(folder, filename)
            if not os.path.isfile(filepath):
                continue
            existing = conn.execute(
                "SELECT id FROM files WHERE filename=? AND category=?",
                (filename, cat)).fetchone()
            if not existing:
                size = os.path.getsize(filepath)
                file_type = filename.rsplit('.', 1)[-1].upper() if '.' in filename else 'UNKNOWN'
                conn.execute(
                    "INSERT INTO files (filename, size, file_type, category, uploaded_at, uploaded_by) VALUES (?,?,?,?,?,?)",
                    (filename, size, file_type, cat, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'sharvil'))
    conn.commit()
    conn.close()

init_db()
sync_files_to_db()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/login', methods=['GET','POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','')
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], password):
            session['username'] = username
            return redirect(url_for('home'))
        error = 'Wrong username or password'
    return render_template('login.html', error=error)

@app.route('/register', methods=['GET','POST'])
def register():
    conn = get_db()
    extra_count = conn.execute("SELECT COUNT(*) FROM users WHERE is_admin=0").fetchone()[0]
    if extra_count >= MAX_EXTRA_USERS:
        conn.close()
        return render_template('register.html', error='Registration is closed.', disabled=True)
    error = None
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','')
        confirm  = request.form.get('confirm','')
        if not username or not password:
            error = 'Username and password are required'
        elif len(username) < 3:
            error = 'Username must be at least 3 characters'
        elif len(password) < 6:
            error = 'Password must be at least 6 characters'
        elif password != confirm:
            error = 'Passwords do not match'
        else:
            existing = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            if existing:
                error = 'Username already taken'
            else:
                conn.execute(
                    "INSERT INTO users (username, password_hash, is_admin, created_at) VALUES (?,?,?,?)",
                    (username, generate_password_hash(password), 0, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit()
                conn.close()
                return redirect(url_for('login'))
    conn.close()
    slots_left = MAX_EXTRA_USERS - extra_count
    return render_template('register.html', error=error, disabled=False, slots_left=slots_left)

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def home():
    return render_template('index.html', username=session['username'])

@app.after_request
def add_ngrok_header(response):
    response.headers['ngrok-skip-browser-warning'] = 'true'
    return response

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    category    = get_category(file.filename)
    folder_path = os.path.join(UPLOAD_FOLDER, category)
    file_path   = os.path.join(folder_path, file.filename)
    file_data   = file.read()
    file_size   = len(file_data)
    limit = CATEGORY_LIMITS.get(category, 100 * 1024 * 1024)
    label = CATEGORY_LIMIT_LABELS.get(category, '100 MB')
    if file_size > limit:
        return jsonify({'error': f'{category.capitalize()} files are limited to {label}. Your file is {round(file_size/(1024*1024),1)} MB.'}), 413
    with open(file_path, 'wb') as f:
        f.write(file_data)
    file_type   = file.filename.rsplit('.', 1)[-1].upper() if '.' in file.filename else 'UNKNOWN'
    uploaded_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    uploaded_by = session['username']
    conn = get_db()
    conn.execute("DELETE FROM files WHERE filename=? AND category=?", (file.filename, category))
    conn.execute(
        "INSERT INTO files (filename, size, file_type, category, uploaded_at, uploaded_by) VALUES (?,?,?,?,?,?)",
        (file.filename, file_size, file_type, category, uploaded_at, uploaded_by))
    conn.commit()
    conn.close()
    return jsonify({'message':'Uploaded!','filename':file.filename,'size':file_size,'file_type':file_type,'category':category,'uploaded_at':uploaded_at,'uploaded_by':uploaded_by}), 200

@app.route('/files', methods=['GET'])
@login_required
def list_files():
    category = request.args.get('category', 'all')
    conn = get_db()
    if category == 'all':
        rows = conn.execute('SELECT * FROM files ORDER BY uploaded_at DESC').fetchall()
    else:
        rows = conn.execute('SELECT * FROM files WHERE category=? ORDER BY uploaded_at DESC', (category,)).fetchall()
    conn.close()
    files = []
    for row in rows:
        path = os.path.join(UPLOAD_FOLDER, row['category'], row['filename'])
        if os.path.exists(path):
            files.append({'id':row['id'],'filename':row['filename'],'size':row['size'],'file_type':row['file_type'],'category':row['category'],'uploaded_at':row['uploaded_at'],'uploaded_by':row['uploaded_by']})
    return jsonify({'files': files}), 200

@app.route('/preview/<category>/<filename>')
@login_required
def preview_file(category, filename):
    folder = os.path.join(os.getcwd(), UPLOAD_FOLDER, category)
    return send_from_directory(folder, filename)

@app.route('/download/<category>/<filename>')
@login_required
def download_file(category, filename):
    folder = os.path.join(os.getcwd(), UPLOAD_FOLDER, category)
    return send_from_directory(folder, filename, as_attachment=True)

@app.route('/delete/<category>/<filename>', methods=['DELETE'])
@login_required
def delete_file(category, filename):
    path = os.path.join(UPLOAD_FOLDER, category, filename)
    if not os.path.exists(path):
        return jsonify({'error': 'File not found'}), 404
    os.remove(path)
    conn = get_db()
    conn.execute('DELETE FROM files WHERE filename=? AND category=?', (filename, category))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Deleted!'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
