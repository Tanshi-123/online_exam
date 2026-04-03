from flask import Flask, render_template, request, redirect, url_for, session, flash

from flask_mysqldb import MySQL

import MySQLdb.cursors

import urllib.request
import urllib.parse
import socket
# This is the "Magic Fix" for the infinite loading issue
_old_getaddrinfo = socket.getaddrinfo
def new_getaddrinfo(*args, **kwargs):
    responses = _old_getaddrinfo(*args, **kwargs)
    return [r for r in responses if r[0] == socket.AF_INET]
socket.getaddrinfo = new_getaddrinfo


app = Flask(__name__)

app.secret_key = 'smart_exam_2026_final'



# --- Database Config ---

app.config['MYSQL_HOST'] = 'localhost'

app.config['MYSQL_USER'] = 'root'

app.config['MYSQL_PASSWORD'] = ''

app.config['MYSQL_DB'] = 'online_exam'

mysql = MySQL(app)



# --- AI Config ---
# We use a 100% free open-source endpoint (pollinations.ai) to bypass Google/OpenAI restrictions.

# --- Ensure num_questions column exists ---
with app.app_context():
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("ALTER TABLE exams ADD COLUMN num_questions INT DEFAULT 10")
        mysql.connection.commit()
    except:
        pass  # Column already exists



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

        num_questions = request.form.get('num_questions', 10)

        cursor = mysql.connection.cursor()

        cursor.execute('INSERT INTO exams (title, duration, num_questions) VALUES (%s, %s, %s)', (title, duration, num_questions))

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
    cursor.execute('SELECT title, num_questions FROM exams WHERE id = %s', (exam_id,))
    exam = cursor.fetchone()
    num_q = exam.get('num_questions', 10) or 10

    try:
        # We tell the AI EXACTLY what to do to prevent parsing errors
        prompt = (f"Generate {num_q} MCQs for '{exam['title']}'. "
                  "Format: Question|A|B|C|D|CorrectLetter. "
                  "Strictly NO intro text, NO markdown, NO backticks.")
        
        # Hit the free open API 
        safe_prompt = urllib.parse.quote(prompt)
        url = f"https://text.pollinations.ai/{safe_prompt}"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            raw_output = response.read().decode('utf-8').replace('```', '').strip()
        
        for line in raw_output.split('\n'):
            if '|' in line:
                p = line.split('|')
                if len(p) == 6:
                    cursor.execute('''INSERT INTO questions 
                        (exam_id, question_text, option_a, option_b, option_c, option_d, correct_option) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s)''', 
                        (exam_id, p[0].strip(), p[1].strip(), p[2].strip(), 
                         p[3].strip(), p[4].strip(), p[5].strip().upper()))
        
        mysql.connection.commit()
        flash('AI Questions Generated Successfully!', 'success')

    except Exception as e:
        print(f"AI ERROR LOG: {e}") # Look at your CMD/Terminal to see the real error!
        flash(f'AI Error: {str(e)[:100]}... Please check your API key.', 'danger')

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

    if not session.get('loggedin'): return redirect(url_for('login'))

   

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    cursor.execute('SELECT * FROM questions WHERE exam_id = %s', (exam_id,))

    questions = cursor.fetchall()

   

    review_data = []

    score = 0

    total = len(questions)



    for q in questions:

        user_ans = request.form.get(str(q['id']))

        is_correct = (user_ans == q['correct_option'])

        if is_correct:

            score += 1

       

        # Store detailed info for the review page

        review_data.append({

            'question': q['question_text'],

            'options': {'A': q['option_a'], 'B': q['option_b'], 'C': q['option_c'], 'D': q['option_d']},

            'user_ans': user_ans,

            'correct_ans': q['correct_option'],

            'is_correct': is_correct

        })



    # Save final score to database

    cursor.execute('INSERT INTO results (user_id, exam_id, score, total_marks) VALUES (%s, %s, %s, %s)',

                   (session['id'], exam_id, score, total))

    mysql.connection.commit()



    # Show the review page instead of redirecting to dashboard

    return render_template('review_results.html', score=score, total=total, review=review_data)

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