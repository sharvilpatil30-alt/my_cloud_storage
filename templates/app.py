import os
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = 'sharvil-cloud-secret-2025'

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── Users (username: hashed password) ───────────────────────────
USERS = {
    'sharvil': generate_password_hash('sharvil123'),
    'friend1': generate_password_hash('friend123'),
}

# ── Database ─────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            filename    TEXT NOT NULL,
            size        INTEGER NOT NULL,
            file_type   TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            uploaded_by TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ── Login required decorator ─────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ── Auth routes ──────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username in USERS and check_password_hash(USERS[username], password):
            session['username'] = username
            return redirect(url_for('home'))
        error = 'Wrong username or password'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

# ── Main routes ──────────────────────────────────────────────────
@app.route('/')
@login_required
def home():
    return render_template('index.html', username=session['username'])

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(file_path)

    size = os.path.getsize(file_path)
    file_type = file.filename.rsplit('.', 1)[-1].upper() if '.' in file.filename else 'UNKNOWN'
    uploaded_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    uploaded_by = session['username']

    conn = get_db()
    conn.execute(
        'INSERT INTO files (filename, size, file_type, uploaded_at, uploaded_by) VALUES (?, ?, ?, ?, ?)',
        (file.filename, size, file_type, uploaded_at, uploaded_by)
    )
    conn.commit()
    conn.close()

    return jsonify({
        'message': 'Uploaded!',
        'filename': file.filename,
        'size': size,
        'file_type': file_type,
        'uploaded_at': uploaded_at,
        'uploaded_by': uploaded_by
    }), 200

@app.route('/files', methods=['GET'])
@login_required
def list_files():
    conn = get_db()
    rows = conn.execute('SELECT * FROM files ORDER BY uploaded_at DESC').fetchall()
    conn.close()
    files = []
    for row in rows:
        path = os.path.join(app.config['UPLOAD_FOLDER'], row['filename'])
        if os.path.exists(path):
            files.append({
                'id': row['id'],
                'filename': row['filename'],
                'size': row['size'],
                'file_type': row['file_type'],
                'uploaded_at': row['uploaded_at'],
                'uploaded_by': row['uploaded_by']
            })
    return jsonify({'files': files}), 200

@app.route('/download/<filename>', methods=['GET'])
@login_required
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/delete/<filename>', methods=['DELETE'])
@login_required
def delete_file(filename):
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(path):
        return jsonify({'error': 'File not found'}), 404
    os.remove(path)
    conn = get_db()
    conn.execute('DELETE FROM files WHERE filename = ?', (filename,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Deleted!', 'filename': filename}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
