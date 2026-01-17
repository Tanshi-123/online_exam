from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mysqldb import MySQL
import MySQLdb.cursors
from google import genai

app = Flask(__name__)
app.secret_key = 'smart_exam_2026_final'

# --- Database Config ---
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = '' 
app.config['MYSQL_DB'] = 'online_exam'
mysql = MySQL(app)

# --- Gemini AI Config ---
client = genai.Client(api_key="AIzaSyApw71xyMw6QKIvRJomMk0rET8f5wJqCCs")

# --- AUTH ROUTES (Fixed for Blank Fields) ---
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE username = %s AND password = %s', (username, password))
        user = cursor.fetchone()
        if user:
            session.update({'loggedin': True, 'id': user['id'], 'username': user['username'], 'role': user['role']})
            return redirect(url_for('admin_dashboard' if user['role'] == 'admin' else 'student_dashboard'))
        flash('Invalid Credentials!', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        cursor = mysql.connection.cursor()
        cursor.execute('INSERT INTO users (username, password, role) VALUES (%s, %s, "student")', (username, password))
        mysql.connection.commit()
        flash('Account created! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

# --- ADMIN ROUTES (Fixed for IntegrityError) ---
@app.route('/admin/dashboard')
def admin_dashboard():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    search = request.args.get('search', '')
    cursor.execute('SELECT * FROM exams')
    exams = cursor.fetchall()
    
    query = '''SELECT results.score, results.total_marks, results.exam_date, users.username, exams.title 
               FROM results JOIN users ON results.user_id = users.id 
               JOIN exams ON results.exam_id = exams.id'''
    if search:
        cursor.execute(query + " WHERE users.username LIKE %s ORDER BY results.exam_date DESC", ("%" + search + "%",))
    else:
        cursor.execute(query + " ORDER BY results.exam_date DESC")
    return render_template('admin_dash.html', exams=exams, results=cursor.fetchall(), search_query=search)

@app.route('/admin/add_exam', methods=['GET', 'POST'])
def add_exam():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    if request.method == 'POST':
        title = request.form['title']
        duration = request.form['duration']
        cursor = mysql.connection.cursor()
        cursor.execute('INSERT INTO exams (title, duration) VALUES (%s, %s)', (title, duration))
        mysql.connection.commit()
        flash('Exam created successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('add_exam.html')

@app.route('/admin/delete_exam/<int:exam_id>')
def delete_exam(exam_id):
    if session.get('role') == 'admin':
        cursor = mysql.connection.cursor()
        # FIX: Delete child records first to satisfy Foreign Key constraints
        cursor.execute('DELETE FROM results WHERE exam_id = %s', (exam_id,))
        cursor.execute('DELETE FROM questions WHERE exam_id = %s', (exam_id,))
        cursor.execute('DELETE FROM exams WHERE id = %s', (exam_id,))
        mysql.connection.commit()
        flash('Exam and history deleted successfully.', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/add_question/<int:exam_id>', methods=['GET', 'POST'])
def add_question_manual(exam_id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    if request.method == 'POST':
        cursor = mysql.connection.cursor()
        cursor.execute('''INSERT INTO questions (exam_id, question_text, option_a, option_b, option_c, option_d, correct_option) 
                          VALUES (%s, %s, %s, %s, %s, %s, %s)''', 
                       (exam_id, request.form['question_text'], request.form['option_a'], 
                        request.form['option_b'], request.form['option_c'], request.form['option_d'], 
                        request.form['correct_option']))
        mysql.connection.commit()
        flash('Question added manually!', 'success')
        return redirect(url_for('add_question_manual', exam_id=exam_id))
    return render_template('add_question.html', exam_id=exam_id)

@app.route('/admin/generate_questions/<int:exam_id>')
def generate_ai_questions(exam_id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT title FROM exams WHERE id = %s', (exam_id,))
    exam = cursor.fetchone()
    try:
        prompt = f"Generate 5 MCQ for '{exam['title']}'. Format: Question|A|B|C|D|CorrectLetter."
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        for line in response.text.strip().split('\n'):
            p = line.split('|')
            if len(p) == 6:
                cursor.execute('INSERT INTO questions (exam_id, question_text, option_a, option_b, option_c, option_d, correct_option) VALUES (%s, %s, %s, %s, %s, %s, %s)', 
                               (exam_id, p[0], p[1], p[2], p[3], p[4], p[5].strip().upper()))
        mysql.connection.commit()
        flash('AI Questions Generated!', 'success')
    except Exception:
        flash('AI Limit Reached. Use "Manual Add" or wait 60s.', 'danger')
    return redirect(url_for('admin_dashboard'))

# --- STUDENT ROUTES ---
@app.route('/student/dashboard')
def student_dashboard():
    if session.get('role') == 'student':
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM exams')
        return render_template('student_dash.html', exams=cursor.fetchall())
    return redirect(url_for('login'))

@app.route('/take_exam/<int:exam_id>')
def take_exam(exam_id):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM questions WHERE exam_id = %s', (exam_id,))
    questions = cursor.fetchall()
    if not questions:
        flash('Exam not ready yet!', 'warning')
        return redirect(url_for('student_dashboard'))
    cursor.execute('SELECT * FROM exams WHERE id = %s', (exam_id,))
    return render_template('take_exam.html', exam=cursor.fetchone(), questions=questions)

@app.route('/submit_exam/<int:exam_id>', methods=['POST'])
def submit_exam(exam_id):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT id, correct_option FROM questions WHERE exam_id = %s', (exam_id,))
    questions = cursor.fetchall()
    score = sum(1 for q in questions if request.form.get(str(q['id'])) == q['correct_option'])
    cursor.execute('INSERT INTO results (user_id, exam_id, score, total_marks) VALUES (%s, %s, %s, %s)', 
                   (session['id'], exam_id, score, len(questions)))
    mysql.connection.commit()
    return redirect(url_for('student_results'))

@app.route('/student/results')
def student_results():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('''SELECT results.score, results.total_marks, results.exam_date, exams.title 
                      FROM results JOIN exams ON results.exam_id = exams.id 
                      WHERE results.user_id = %s ORDER BY results.exam_date DESC''', (session['id'],))
    return render_template('student_results.html', results=cursor.fetchall())

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)