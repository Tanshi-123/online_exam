# Route to show all exams
@app.route('/admin/dashboard')
def admin_dashboard():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM exams')
    all_exams = cursor.fetchall()
    return render_template('admin_dash.html', exams=all_exams)

# Route to create a new exam
@app.route('/admin/add_exam', methods=['GET', 'POST'])
def add_exam():
    if request.method == 'POST':
        title = request.form['title']
        duration = request.form['duration']
        
        cursor = mysql.connection.cursor()
        cursor.execute('INSERT INTO exams (title, duration) VALUES (%s, %s)', (title, duration))
        mysql.connection.commit()
        flash('Exam created successfully!')
        return redirect(url_for('admin_dashboard'))
        
    return render_template('add_exam.html')