from flask import Flask, render_template, request, redirect, url_for, session, flash

from dotenv import load_dotenv
load_dotenv()

from flask_mysqldb import MySQL

import MySQLdb.cursors

import urllib.request
import urllib.parse
import json
import os
import re
import socket
# This is the "Magic Fix" for the infinite loading issue
_old_getaddrinfo = socket.getaddrinfo
def new_getaddrinfo(*args, **kwargs):
    responses = _old_getaddrinfo(*args, **kwargs)
    return [r for r in responses if r[0] == socket.AF_INET]
socket.getaddrinfo = new_getaddrinfo


app = Flask(__name__)

app.secret_key = os.environ.get('SECRET_KEY', 'smart_exam_2026_final')



# --- Database Config ---

app.config['MYSQL_HOST'] = os.environ.get('MYSQL_HOST', 'localhost')

app.config['MYSQL_USER'] = os.environ.get('MYSQL_USER', 'root')

app.config['MYSQL_PASSWORD'] = os.environ.get('MYSQL_PASSWORD', '')

app.config['MYSQL_DB'] = os.environ.get('MYSQL_DB', 'online_exam')

mysql = MySQL(app)



# --- AI Config ---
# We use a 100% free open-source endpoint (pollinations.ai) to bypass Google/OpenAI restrictions.

# --- Ensure num_questions column exists ---
with app.app_context():
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("ALTER TABLE exams ADD COLUMN num_questions INT DEFAULT 10")
        mysql.connection.commit()
    except Exception as e:
        print("\n!!! DETAILED LOCAL DATABASE ERROR !!!:", e, "\n")  # Column already exists


MAX_AI_QUESTIONS = 50
GENERIC_QUESTION_PATTERNS = (
    r'\bgood first step when learning\b',
    r'\bhabit improves performance\b',
    r'\bafter making a mistake\b',
    r'\bpurpose of revision\b',
    r'\bbefore submitting\b',
    r'\bdifficult .* questions be handled\b',
    r'\blong-term learning\b',
    r'\bstudy tips?\b',
    r'\bexam-taking\b',
)
TOPIC_STOPWORDS = {
    'basic', 'basics', 'intro', 'introduction', 'advanced', 'chapter', 'unit',
    'exam', 'test', 'assessment', 'question', 'questions', 'quiz', 'mcq', 'mcqs'
}


def clamp_question_count(value, default=10):
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = default
    return max(1, min(MAX_AI_QUESTIONS, count))


def clean_ai_output(text):
    if not text:
        return ''
    return str(text).replace('```json', '').replace('```', '').strip()


def strip_question_prefix(text):
    text = str(text or '').strip().strip('*')
    return re.sub(
        r'^\s*(?:[-*]\s*)?(?:question\s*[:\-]?\s*|q\d*\s*[:.)\-]\s*|\d+\s*[:.)\-]\s*)',
        '',
        text,
        flags=re.IGNORECASE
    ).strip()


def strip_option_prefix(letter, text):
    text = str(text or '').strip()
    return re.sub(
        rf'^\s*(?:option\s*)?{letter}\s*[:.)\-]\s*',
        '',
        text,
        flags=re.IGNORECASE
    ).strip()


def normalize_correct_option(value):
    if value is None:
        return None
    text = str(value).strip().upper()
    match = re.search(r'\b([ABCD])\b', text)
    if match:
        return match.group(1)
    if text[:1] in 'ABCD':
        return text[:1]
    return None


def make_question(question_text, option_a, option_b, option_c, option_d, correct_option):
    answer = normalize_correct_option(correct_option)
    if not answer:
        return None

    question = strip_question_prefix(question_text)
    options = {
        'A': strip_option_prefix('A', option_a),
        'B': strip_option_prefix('B', option_b),
        'C': strip_option_prefix('C', option_c),
        'D': strip_option_prefix('D', option_d),
    }

    if not question or any(not value for value in options.values()):
        return None

    return {
        'question_text': question,
        'option_a': options['A'],
        'option_b': options['B'],
        'option_c': options['C'],
        'option_d': options['D'],
        'correct_option': answer
    }


def topic_keywords(title):
    words = re.findall(r'[a-zA-Z0-9+#.]+', str(title or '').lower())
    return [
        word for word in words
        if len(word) >= 3 and word not in TOPIC_STOPWORDS
    ]


def question_combined_text(question):
    return ' '.join([
        question.get('question_text', ''),
        question.get('option_a', ''),
        question.get('option_b', ''),
        question.get('option_c', ''),
        question.get('option_d', ''),
    ]).lower()


def is_subject_question(question, title):
    combined = question_combined_text(question)
    if not combined or '...' in combined:
        return False

    if any(re.search(pattern, combined) for pattern in GENERIC_QUESTION_PATTERNS):
        return False

    keywords = topic_keywords(title)
    if not keywords:
        return True

    return any(keyword in combined for keyword in keywords)


def filter_subject_questions(questions, title, limit):
    filtered = []
    seen = set()

    for question in questions:
        if not is_subject_question(question, title):
            continue

        key = re.sub(r'[^a-z0-9]+', ' ', question['question_text'].lower()).strip()
        if key in seen:
            continue

        seen.add(key)
        filtered.append(question)
        if len(filtered) >= limit:
            break

    return filtered


def question_from_mapping(item):
    if not isinstance(item, dict):
        return None

    question = (
        item.get('question_text')
        or item.get('question')
        or item.get('prompt')
        or item.get('text')
    )
    options = item.get('options') or item.get('choices') or {}

    if isinstance(options, dict):
        option_a = options.get('A') or options.get('a') or options.get('option_a')
        option_b = options.get('B') or options.get('b') or options.get('option_b')
        option_c = options.get('C') or options.get('c') or options.get('option_c')
        option_d = options.get('D') or options.get('d') or options.get('option_d')
    elif isinstance(options, list) and len(options) >= 4:
        option_a, option_b, option_c, option_d = options[:4]
    else:
        option_a = item.get('option_a') or item.get('A') or item.get('a')
        option_b = item.get('option_b') or item.get('B') or item.get('b')
        option_c = item.get('option_c') or item.get('C') or item.get('c')
        option_d = item.get('option_d') or item.get('D') or item.get('d')

    correct = (
        item.get('correct_option')
        or item.get('correct')
        or item.get('answer')
        or item.get('correctAnswer')
        or item.get('correct_answer')
    )
    return make_question(question, option_a, option_b, option_c, option_d, correct)


def parse_json_questions(raw_output):
    text = clean_ai_output(raw_output)
    if not text:
        return []

    candidates = [text]
    if '[' in text and ']' in text:
        candidates.append(text[text.find('['):text.rfind(']') + 1])
    if '{' in text and '}' in text:
        candidates.append(text[text.find('{'):text.rfind('}') + 1])

    parsed = []
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue

        if isinstance(data, dict):
            data = data.get('questions') or data.get('items') or [data]
        if not isinstance(data, list):
            continue

        for item in data:
            question = question_from_mapping(item)
            if question:
                parsed.append(question)
        if parsed:
            break

    return parsed


def parse_pipe_questions(raw_output):
    parsed = []
    for raw_line in clean_ai_output(raw_output).splitlines():
        line = raw_line.strip().strip('-* ')
        if '|' not in line:
            continue

        parts = [part.strip() for part in line.split('|')]
        if len(parts) < 6:
            continue

        question_text = '|'.join(parts[:-5])
        option_a, option_b, option_c, option_d = parts[-5:-1]
        parsed_question = make_question(question_text, option_a, option_b, option_c, option_d, parts[-1])
        if parsed_question:
            parsed.append(parsed_question)

    return parsed


def parse_labeled_questions(raw_output):
    option_re = re.compile(r'^\s*(?:[-*]\s*)?(?:option\s*)?([A-D])\s*[:.)\-]\s*(.+)$', re.IGNORECASE)
    answer_re = re.compile(
        r'(?:correct\s*(?:answer|option)?|answer)\s*[:\-]?\s*(?:option\s*)?([A-D])\b',
        re.IGNORECASE
    )
    question_re = re.compile(
        r'^\s*(?:[-*]\s*)?(?:(?:question\s*)?\d+|q\d*)\s*[:.)\-]\s*(.+)$',
        re.IGNORECASE
    )

    parsed = []
    current = {'question': None, 'A': None, 'B': None, 'C': None, 'D': None, 'answer': None}

    def reset_current():
        return {'question': None, 'A': None, 'B': None, 'C': None, 'D': None, 'answer': None}

    def finalize_current():
        parsed_question = make_question(
            current['question'],
            current['A'],
            current['B'],
            current['C'],
            current['D'],
            current['answer']
        )
        if parsed_question:
            parsed.append(parsed_question)

    for raw_line in clean_ai_output(raw_output).splitlines():
        line = raw_line.strip().strip('*')
        if not line or '|' in line:
            continue

        answer_match = answer_re.search(line)
        if answer_match:
            current['answer'] = answer_match.group(1)
            finalize_current()
            current = reset_current()
            continue

        option_match = option_re.match(line)
        if option_match:
            letter = option_match.group(1).upper()
            value = option_match.group(2).strip()
            if re.search(r'\bcorrect\b', value, flags=re.IGNORECASE):
                current['answer'] = letter
                value = re.sub(r'\s*\(?\bcorrect\b\)?\s*', ' ', value, flags=re.IGNORECASE).strip()
            current[letter] = value
            continue

        question_match = question_re.match(line)
        if question_match:
            if current['question'] and any(current[key] for key in 'ABCD'):
                finalize_current()
            current = reset_current()
            current['question'] = question_match.group(1)
            continue

        if not current['question']:
            current['question'] = line
        elif not all(current[key] for key in 'ABCD'):
            current['question'] = f"{current['question']} {line}".strip()

    finalize_current()
    return parsed


def parse_ai_questions(raw_output, limit):
    questions = []
    seen = set()

    for parser in (parse_json_questions, parse_pipe_questions, parse_labeled_questions):
        for question in parser(raw_output):
            key = re.sub(r'[^a-z0-9]+', ' ', question['question_text'].lower()).strip()
            if key in seen:
                continue
            seen.add(key)
            questions.append(question)
            if len(questions) >= limit:
                return questions

    return questions


def build_question_prompt(title, count):
    topic = (title or '').strip()
    return (
        f"Create exactly {count} unique multiple-choice questions about this exact subject: {topic}. "
        f"Every question must test knowledge of {topic} itself or a specific subtopic inside {topic}. "
        "Do not create generic study tips, exam-taking advice, revision habits, learning habits, or motivational questions. "
        "Do not repeat the same question idea. Do not create multiple sets. "
        "Use realistic subject questions with one clearly correct answer and three plausible wrong answers. "
        "Return only valid JSON with this exact shape: "
        "[{\"question\":\"question text\",\"options\":{\"A\":\"option\",\"B\":\"option\",\"C\":\"option\",\"D\":\"option\"},\"answer\":\"A\"}]. "
        "No markdown, no numbering, no explanations, no extra text."
    )


def build_local_questions(title, count):
    topic = (title or 'this topic').strip()
    templates = [
        (
            "Which statement best describes {topic}?",
            "It focuses on the core ideas and practical use of {topic}",
            "It is unrelated to the exam subject",
            "It can only be learned by guessing",
            "It does not require examples or revision",
            "A"
        ),
        (
            "What is a good first step when learning {topic}?",
            "Skip the basics",
            "Memorize answers without understanding",
            "Understand the key terms and examples",
            "Avoid practice questions",
            "C"
        ),
        (
            "Why are examples useful in {topic}?",
            "They make concepts easier to apply",
            "They replace all theory",
            "They remove the need for revision",
            "They are never used in exams",
            "A"
        ),
        (
            "Which habit improves performance in {topic} exams?",
            "Reading questions carefully before answering",
            "Selecting the longest option every time",
            "Ignoring incorrect answers during review",
            "Starting without checking instructions",
            "A"
        ),
        (
            "What should a student do after making a mistake in {topic}?",
            "Forget the mistake immediately",
            "Review the concept and practice a similar question",
            "Stop studying the subject",
            "Choose answers randomly next time",
            "B"
        ),
        (
            "Which approach shows strong understanding of {topic}?",
            "Applying ideas to a new problem",
            "Only recognizing the chapter title",
            "Avoiding all definitions",
            "Depending on luck",
            "A"
        ),
        (
            "What is the purpose of revision in {topic}?",
            "To strengthen memory and clarify weak areas",
            "To make the exam longer",
            "To remove the need for practice",
            "To change the syllabus",
            "A"
        ),
        (
            "Which action is most helpful before submitting a {topic} exam?",
            "Review unanswered questions",
            "Close the browser immediately",
            "Ignore the timer",
            "Change every answer randomly",
            "A"
        ),
        (
            "How should difficult {topic} questions be handled?",
            "Break the problem into smaller parts",
            "Leave all questions blank",
            "Choose the first option without reading",
            "Assume every option is correct",
            "A"
        ),
        (
            "What best supports long-term learning in {topic}?",
            "Regular practice with feedback",
            "Studying only once",
            "Avoiding previous mistakes",
            "Reading without testing yourself",
            "A"
        ),
    ]

    questions = []
    for index in range(count):
        template = templates[index % len(templates)]
        cycle = index // len(templates)
        question_text = template[0].format(topic=topic)
        if cycle:
            question_text = f"{question_text} Practice set {cycle + 1}."

        questions.append(make_question(
            question_text,
            template[1].format(topic=topic),
            template[2].format(topic=topic),
            template[3].format(topic=topic),
            template[4].format(topic=topic),
            template[5]
        ))

    return [question for question in questions if question]


def collect_text_values(value):
    if isinstance(value, str):
        return [value] if value.strip() else []

    if isinstance(value, list):
        chunks = []
        for item in value:
            chunks.extend(collect_text_values(item))
        return chunks

    if isinstance(value, dict):
        chunks = []
        for key, nested in value.items():
            if key in {'input', 'user_input', 'userInput', 'prompt', 'request'}:
                continue
            if key in {'text', 'content', 'output_text', 'outputText'}:
                chunks.extend(collect_text_values(nested))
            elif isinstance(nested, (dict, list)):
                chunks.extend(collect_text_values(nested))
        return chunks

    return []


def extract_text_from_gemini_interaction(result):
    if isinstance(result, dict):
        output_text = result.get('output_text') or result.get('outputText')
        if isinstance(output_text, str) and output_text.strip():
            return output_text

        model_chunks = []
        for step in result.get('steps', []):
            if not isinstance(step, dict):
                continue
            model_output = step.get('model_output') or step.get('modelOutput')
            if model_output:
                model_chunks.extend(collect_text_values(model_output))
        if model_chunks:
            return '\n'.join(model_chunks)

        model_output = result.get('model_output') or result.get('modelOutput')
        if model_output:
            model_chunks = collect_text_values(model_output)
            if model_chunks:
                return '\n'.join(model_chunks)

        chunks = []
        for key, value in result.items():
            if key in {'input', 'user_input', 'userInput', 'prompt', 'request'}:
                continue
            if key in {'text', 'content'} and isinstance(value, str) and value.strip():
                chunks.append(value)
            elif isinstance(value, (dict, list)):
                nested = extract_text_from_gemini_interaction(value)
                if nested:
                    chunks.append(nested)
        return '\n'.join(chunks)

    if isinstance(result, list):
        chunks = []
        for item in result:
            nested = extract_text_from_gemini_interaction(item)
            if nested:
                chunks.append(nested)
        return '\n'.join(chunks)

    return ''


def fetch_ai_question_text(prompt):
    gemini_key = os.environ.get('GEMINI_API_KEY', '').strip()
    errors = []

    if gemini_key and gemini_key != app.secret_key and len(gemini_key) > 20:
        try:
            api_url = "https://generativelanguage.googleapis.com/v1beta/interactions"
            payload = json.dumps({
                "model": "gemini-3.5-flash",
                "input": prompt,
                "store": False
            }).encode('utf-8')
            req = urllib.request.Request(api_url, data=payload, headers={
                'Content-Type': 'application/json',
                'x-goog-api-key': gemini_key,
                'User-Agent': 'SmartExamAI/1.0'
            })
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
                output = extract_text_from_gemini_interaction(result)
                if output:
                    print(f"SUCCESS: Gemini Interactions API returned {len(output)} chars")
                    return clean_ai_output(output), 'Gemini', ''
                errors.append('Gemini returned no readable text')
        except Exception as e:
            errors.append(f"Gemini Interactions error: {e}")
            print(f"Gemini Interactions error: {e}")

        try:
            api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
            payload = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}]
            }).encode('utf-8')
            req = urllib.request.Request(api_url, data=payload, headers={
                'Content-Type': 'application/json',
                'x-goog-api-key': gemini_key,
                'User-Agent': 'SmartExamAI/1.0'
            })
            with urllib.request.urlopen(req, timeout=25) as response:
                result = json.loads(response.read().decode('utf-8'))
                output = result['candidates'][0]['content']['parts'][0]['text']
                print(f"SUCCESS: Gemini generateContent API returned {len(output)} chars")
                return clean_ai_output(output), 'Gemini', ''
        except Exception as e:
            errors.append(f"Gemini generateContent error: {e}")
            print(f"Gemini generateContent error: {e}")
    elif gemini_key:
        errors.append("Gemini key looks like a placeholder or matches SECRET_KEY")
        print("Skipping Gemini: GEMINI_API_KEY looks like a placeholder or matches SECRET_KEY.")
    else:
        errors.append("GEMINI_API_KEY is missing")

    try:
        payload = json.dumps({
            "model": "openai",
            "messages": [
                {
                    "role": "system",
                    "content": "Return only exam questions in the exact format requested. No markdown."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 2000,
            "stream": False
        }).encode('utf-8')
        req = urllib.request.Request(
            "https://text.pollinations.ai/openai",
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'SmartExamAI/1.0'
            }
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            output = result['choices'][0]['message']['content']
            print(f"SUCCESS: Pollinations OpenAI endpoint returned {len(output)} chars")
            return clean_ai_output(output), 'Pollinations', ''
    except Exception as e:
        errors.append(f"Pollinations OpenAI error: {e}")
        print(f"Pollinations OpenAI error: {e}")

    try:
        safe_prompt = urllib.parse.quote(prompt)
        query = urllib.parse.urlencode({
            'model': 'openai',
            'temperature': '0.7'
        })
        url = f"https://text.pollinations.ai/{safe_prompt}?{query}"
        req = urllib.request.Request(url, headers={'User-Agent': 'SmartExamAI/1.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            output = response.read().decode('utf-8')
            print(f"SUCCESS: Pollinations returned {len(output)} chars")
            return clean_ai_output(output), 'Pollinations', ''
    except Exception as e:
        errors.append(f"Pollinations GET error: {e}")
        print(f"Pollinations GET error: {e}")

    return '', '', '; '.join(errors[-3:])


def insert_generated_questions(cursor, exam_id, questions):
    cursor.execute('DELETE FROM questions WHERE exam_id = %s', (exam_id,))

    for question in questions:
        cursor.execute('''INSERT INTO questions
            (exam_id, question_text, option_a, option_b, option_c, option_d, correct_option)
            VALUES (%s, %s, %s, %s, %s, %s, %s)''',
            (
                exam_id,
                question['question_text'],
                question['option_a'],
                question['option_b'],
                question['option_c'],
                question['option_d'],
                question['correct_option']
            )
        )



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

        num_questions = clamp_question_count(request.form.get('num_questions', 10))

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
    if not exam:
        flash('Exam not found.', 'danger')
        return redirect(url_for('admin_dashboard'))

    num_q = clamp_question_count(exam.get('num_questions', 10))

    prompt = build_question_prompt(exam['title'], num_q)

    raw_output, source, error_message = fetch_ai_question_text(prompt)
    parsed_questions = parse_ai_questions(raw_output, num_q * 3)
    questions = filter_subject_questions(parsed_questions, exam['title'], num_q)

    if raw_output and parsed_questions and not questions:
        print(f"AI returned {len(parsed_questions)} parsed questions, but they were off-topic or duplicate.")
    elif raw_output and not questions:
        print(f"AI output could not be parsed:\n{raw_output[:1000]}")

    if questions:
        try:
            insert_generated_questions(cursor, exam_id, questions[:num_q])
            mysql.connection.commit()
            if len(questions) >= num_q:
                flash(f'{len(questions[:num_q])} questions generated online with {source}.', 'success')
            elif raw_output:
                flash(f'{len(questions[:num_q])} on-topic questions generated online with {source}. The AI returned fewer valid questions than requested.', 'warning')
            else:
                flash(f'{len(questions[:num_q])} questions generated online.', 'success')
        except Exception as e:
            mysql.connection.rollback()
            print(f"DB insert error: {e}")
            flash('Error saving generated questions. Please check the questions table and try again.', 'danger')
    elif raw_output:
        flash('The online service replied, but the app could not read enough valid on-topic MCQs from it. Check the terminal for details.', 'danger')
    else:
        flash(f'Online question generation failed. Check the VS Code terminal for details. Last error: {error_message[:180]}', 'danger')

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
