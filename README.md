README.md
Markdown

# 🚀 SmartExam AI: Next-Gen Examination Portal

SmartExam AI is a full-stack automated examination platform designed for the 2026 academic landscape. It combines the power of **Google Gemini 1.5 Flash AI** with a sophisticated **Glassmorphic UI** to provide a seamless experience for both administrators and students.



## 🌟 Core Features

### 🧠 AI-Powered Assessment
* **Automated Question Generation:** Admins can generate high-quality MCQs instantly by simply entering a subject title, powered by the Google Gemini API.
* **Intelligent Fallback:** Includes a "Manual Add" feature to bypass AI rate limits, ensuring 100% system uptime during demos.

### 🛡️ Secure Proctored Testing
* **Live Countdown Timer:** A persistent, sticky timer that tracks exam duration.
* **Auto-Submit Logic:** Intelligent JavaScript triggers that automatically save and submit student responses when time expires.
* **Integrity Focused:** Prevents students from accessing exams with zero questions.

### 📊 Admin Command Center
* **Student Analytics:** A centralized dashboard to track performance across different students.
* **Live Search:** Filter student results by name using a high-speed SQL LIKE-operator search bar.
* **Data Management:** Full CRUD (Create, Read, Update, Delete) for exams with automated relational cleanup (cascading deletes).

### 🎨 Premium UI/UX
* **Glassmorphism Design:** A modern Midnight & Electric Violet theme using frosted glass effects and neon accents.
* **Responsive Layout:** Fully optimized for both desktop and mobile viewing.

---

## 🛠️ Technology Stack

| Component | Technology |
| :--- | :--- |
| **Backend** | Python (Flask) |
| **Database** | MySQL (MariaDB) |
| **AI Engine** | Google Gemini 1.5 Flash |
| **Frontend** | HTML5, CSS3 (Advanced Gradients), Bootstrap 5 |
| **Auth** | Flask Session Management |

---

## 🚀 Quick Start Guide

### 1. Prerequisites
* Python 3.x
* MySQL Server (XAMPP/WAMP)
* Google AI Studio API Key

### 2. Installation
```bash
# Clone the repository
git clone [https://github.com/yourusername/SmartExam-AI.git](https://github.com/yourusername/SmartExam-AI.git)

# Install required packages
pip install flask flask-mysqldb google-genai
3. Database Configuration
Create a database named online_exam in phpMyAdmin.

Import the provided SQL structure.

Update app.config in app.py with your MySQL credentials.

4. API Setup
Replace the placeholder in app.py with your Gemini API key:

Python

client = genai.Client(api_key="YOUR_API_KEY_HERE")
📂 Project Structure
Plaintext

├── app.py              # Main Flask application logic
├── templates/          # Glassmorphic HTML views
│   ├── admin_dash.html
│   ├── student_dash.html
│   ├── take_exam.html
│   └── ...
├── static/
│   └── css/
│       └── style.css   # Custom "Prosperous" CSS theme
└── README.md           # Documentation
📝 License
Distributed under the MIT License. See LICENSE for more information.


---

### **How to Commit to GitHub (Step-by-Step)**

If you have never uploaded this code before, follow these steps in your terminal:

1.  **Initialize Git:**
    ```bash
    git init
    ```
2.  **Stage all files:**
    ```bash
    git add .
    ```
3.  **Commit the changes:**
    ```bash
    git commit -m "Final Release: AI Exam Portal with Glassmorphic UI and Student Search"
    ```
4.  **Create a Repository on GitHub:**
    * Go to [GitHub](https://github.com/) -> New Repository.
    * Name it `SmartExam-AI`.
5.  **Connect Local to Remote:**
    *(Replace `URL` with the link GitHub gives you)*
    ```bash
    git remote add origin https://github.com/yourusername/SmartExam-AI.git
    git branch -M main
    git push -u origin main
    ```

**Your project is now officially professional! Is there any specific part of the p