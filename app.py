# app.py
import os
import traceback
import requests
from datetime import datetime
from uuid import uuid4
from flask import Flask, request, redirect, session, send_from_directory, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

# ---------------------------
# FLASK CONFIG
# ---------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "team_secret_key")

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///team_workspace.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.environ.get("UPLOAD_FOLDER", "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
SENDER_EMAIL = os.environ.get("EMAIL_FROM", "Team Workspace <onboarding@resend.dev>")

db = SQLAlchemy(app)

# ---------------------------
# MODELS
# ---------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    email = db.Column(db.String(200), unique=True)
    password = db.Column(db.String(200))
    role = db.Column(db.String(20), default="member")  # 🔥 NEW FIELD


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    weeks = db.Column(db.Integer)
    current_week = db.Column(db.Integer, default=1)
    completed = db.Column(db.Boolean, default=False)
    completed_time = db.Column(db.DateTime, nullable=True)


class Upload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer)
    week_number = db.Column(db.Integer)
    file_name = db.Column(db.String(300))
    original_name = db.Column(db.String(300))
    uploaded_by = db.Column(db.String(200))
    description = db.Column(db.Text)
    uploaded_time = db.Column(db.DateTime, default=datetime.utcnow)


class WeekStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer)
    week_number = db.Column(db.Integer)
    user_id = db.Column(db.Integer)
    action = db.Column(db.String(20))
    clicked_time = db.Column(db.DateTime, default=datetime.utcnow)


with app.app_context():
    db.create_all()

# ---------------------------
# EMAIL (Resend)
# ---------------------------
def send_email(to, subject, body):
    if not RESEND_API_KEY:
        return False
    try:
        url = "https://api.resend.com/emails"
        payload = {"from": SENDER_EMAIL, "to": to, "subject": subject, "text": body}
        headers = {"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"}
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        return r.status_code in (200, 201)
    except:
        return False


def notify_all_users(subject, body):
    for u in User.query.all():
        if u.email:
            send_email(u.email, subject, body)


def notify_project_users(project_id, subject, body):
    notify_all_users(subject, body)


# ---------------------------
# AUTH ROUTES
# ---------------------------
@app.route("/")
def home():
    return """
    <h2>Team Workspace</h2>
    <a href="/login">Login</a><br>
    <a href="/register">Register</a>
    """


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        pwd = request.form.get("password", "")

        if not email or not pwd:
            return "Email and password required"

        if User.query.filter_by(email=email).first():
            return "Email already exists"

        # 🔥 FIRST USER = ADMIN
        if User.query.count() == 0:
            role = "admin"
        else:
            role = "member"

        new_user = User(
            name=name,
            email=email,
            password=pwd,
            role=role
        )

        db.session.add(new_user)
        db.session.commit()

        return redirect("/login")

    return """
    <h2>Register</h2>
    <form method="POST">
        Name:<br><input name="name"><br>
        Email:<br><input name="email"><br>
        Password:<br><input type="password" name="password"><br><br>
        <button type="submit">Register</button>
    </form>
    """


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pwd = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if not user or user.password != pwd:
            return "Invalid login"

        session["user_id"] = user.id
        session["user_name"] = user.name
        session["user_role"] = user.role  # 🔥 STORE ROLE IN SESSION

        return redirect("/dashboard")

    return """
    <h2>Login</h2>
    <form method="POST">
        Email:<br><input name="email"><br>
        Password:<br><input type="password" name="password"><br><br>
        <button type="submit">Login</button>
    </form>
    """


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ---------------------------
# DASHBOARD
# ---------------------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    projects = Project.query.all()

    html = f"<h2>Welcome {session.get('user_name')} ({session.get('user_role')})</h2>"

    html += """
    <form method="POST" action="/create_project">
        Project Name: <input name="name">
        Weeks: <input type="number" name="weeks">
        <button>Create Project</button>
    </form>
    """

    html += "<h3>Projects</h3>"
    for p in projects:
        html += f"<div><a href='/project/{p.id}'>{p.name}</a></div>"

    html += "<br><a href='/logout'>Logout</a>"

    return html


@app.route("/create_project", methods=["POST"])
def create_project():
    if "user_id" not in session:
        return redirect("/login")

    name = request.form.get("name", "Untitled")
    weeks = int(request.form.get("weeks") or 1)

    p = Project(name=name, weeks=weeks)
    db.session.add(p)
    db.session.commit()

    return redirect("/dashboard")


# ---------------------------
# RUN
# ---------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
