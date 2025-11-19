# app.py
import os
import traceback
import requests
from datetime import datetime
from uuid import uuid4
from flask import Flask, request, redirect, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

# ----------------------------------------------------
# FLASK CONFIG
# ----------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "team_secret_key")

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///team_workspace.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.environ.get("UPLOAD_FOLDER", "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# ----------------------------------------------------
# RESEND CONFIG
# ----------------------------------------------------
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
SENDER_EMAIL = os.environ.get("EMAIL_FROM", "Team Workspace <onboarding@resend.dev>")

db = SQLAlchemy(app)

# ----------------------------------------------------
# MODERN UI STYLE (Gradient + Glassmorphism + Black Buttons)
# ----------------------------------------------------
STYLE = """
<style>
body {
    font-family: 'Arial', sans-serif;
    background: linear-gradient(135deg, #9b5de5, #f15bb5, #00bbf9, #00f5d4);
    background-attachment: fixed;
    padding: 40px;
    margin: 0;
}

.container {
    background: rgba(255, 255, 255, 0.25);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-radius: 18px;
    padding: 30px;
    max-width: 900px;
    margin: auto;
    box-shadow: 0 8px 32px rgba(0,0,0,0.2);
}

input, textarea {
    width: 100%;
    padding: 12px;
    margin-top: 6px;
    border-radius: 10px;
    border: 1px solid #bbb;
    font-size: 15px;
}

button {
    background: black;
    color: white;
    padding: 12px 22px;
    border-radius: 10px;
    border: none;
    cursor: pointer;
    font-size: 15px;
    margin-top: 10px;
}

button:hover {
    opacity: 0.8;
}

.black-btn {
    background: #000;
    color: #fff;
    padding: 10px 18px;
    border-radius: 10px;
    margin-right: 8px;
}

.badge {
    display: inline-block;
    padding: 6px 10px;
    background: #fff;
    border-radius: 8px;
    margin-right: 8px;
    font-size: 14px;
}

.logout {
    float: right;
    background: #000;
    color: white;
    padding: 8px 16px;
    border-radius: 8px;
    text-decoration: none;
    font-weight: bold;
}

.file-box {
    margin-bottom: 12px;
    padding: 10px;
    background: rgba(255,255,255,0.4);
    border-radius: 10px;
}
</style>
"""

def logout_btn():
    return "<a class='logout' href='/logout'>Logout</a>" if session.get("user_id") else ""

# ----------------------------------------------------
# MODELS
# ----------------------------------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    email = db.Column(db.String(200), unique=True)
    password = db.Column(db.String(200))

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

# ----------------------------------------------------
# SEND EMAIL - RESEND API
# ----------------------------------------------------
def send_email(to, subject, body):
    try:
        url = "https://api.resend.com/emails"
        payload = {"from": SENDER_EMAIL, "to": to, "subject": subject, "text": body}
        headers = {
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        }
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        return r.status_code in (200, 201)
    except:
        return False

def notify_project_users(project_id, subject, body):
    for u in User.query.all():
        if u.email:
            send_email(u.email, subject, body)

# ----------------------------------------------------
# AUTH ROUTES
# ----------------------------------------------------
@app.route("/")
def home():
    return STYLE + logout_btn() + """
    <div class='container'>
        <h2>Team Workspace</h2>
        <a href='/login'><button class='black-btn'>Login</button></a>
        <a href='/register'><button class='black-btn'>Register</button></a>
    </div>
"""

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"].lower()
        pwd = request.form["password"]
        if User.query.filter_by(email=email).first():
            return STYLE + "<script>alert('Email exists');window.location='/register';</script>"
        db.session.add(User(name=name, email=email, password=pwd))
        db.session.commit()
        return redirect("/login")

    return STYLE + """
    <div class='container'>
        <h2>Register</h2>
        <form method='POST'>
            <input name='name' placeholder='Name'>
            <input name='email' placeholder='Email'>
            <input name='password' type='password' placeholder='Password'>
            <button>Register</button>
        </form>
        <a href='/login'><button class='black-btn'>Login</button></a>
    </div>
"""

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].lower()
        pwd = request.form["password"]
        user = User.query.filter_by(email=email).first()
        if not user or user.password != pwd:
            return STYLE + "<script>alert('Invalid login');window.location='/login';</script>"
        session["user_id"] = user.id
        session["user_name"] = user.name
        return redirect("/dashboard")

    return STYLE + """
    <div class='container'>
        <h2>Login</h2>
        <form method='POST'>
            <input name='email' placeholder='Email'>
            <input type='password' name='password' placeholder='Password'>
            <button>Login</button>
        </form>
        <a href='/register'><button class='black-btn'>Register</button></a>
    </div>
"""

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ----------------------------------------------------
# DASHBOARD
# ----------------------------------------------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    projects = Project.query.all()
    items = "".join(f"<li><a href='/project/{p.id}'>{p.name} (Week {p.current_week}/{p.weeks})</a></li>"
                    for p in projects)

    return STYLE + logout_btn() + f"""
    <div class='container'>
        <h2>Welcome {session['user_name']}</h2>

        <form method='POST' action='/create_project'>
            <input name='name' placeholder='Project Name'>
            <input name='weeks' type='number' placeholder='Weeks'>
            <button>Create</button>
        </form>

        <h3>Your Projects</h3>
        <ul>{items}</ul>
    </div>
"""

@app.route("/create_project", methods=["POST"])
def create_project():
    name = request.form["name"]
    weeks = int(request.form["weeks"])
    p = Project(name=name, weeks=weeks)
    db.session.add(p)
    db.session.commit()
    return redirect("/dashboard")

# ----------------------------------------------------
# DOWNLOAD
# ----------------------------------------------------
@app.route("/download/<path:f>")
def download(f):
    return send_from_directory(app.config["UPLOAD_FOLDER"], f, as_attachment=True)

# ----------------------------------------------------
# PROJECT VIEW + UPLOADS + NEXT/FINISH BUTTONS
# ----------------------------------------------------
@app.route("/project/<int:pid>", methods=["GET","POST"])
def project(pid):
    if "user_id" not in session:
        return redirect("/login")

    p = Project.query.get(pid)

    if request.method == "POST" and "file" in request.files:
        f = request.files["file"]
        desc = request.form.get("description", "")
        fname = uuid4().hex + "_" + secure_filename(f.filename)
        f.save(os.path.join(app.config["UPLOAD_FOLDER"], fname))

        db.session.add(Upload(
            project_id=pid,
            week_number=p.current_week,
            file_name=fname,
            uploaded_by=session["user_name"],
            description=desc
        ))
        db.session.commit()

        notify_project_users(pid, "New Upload", f"{session['user_name']} uploaded {f.filename}")
        return redirect(f"/project/{pid}")

    uploads = Upload.query.filter_by(project_id=pid, week_number=p.current_week).all()
    file_list = "".join(
        f"<div class='file-box'><b>{u.file_name}</b> — {u.uploaded_by} — <a href='/download/{u.file_name}'>Download</a></div>"
        for u in uploads
    )

    uid = session["user_id"]
    total_users = User.query.count()

    next_count = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, action='next').count()
    finish_count = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, action='finish').count()

    next_clicked = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week,
                                              user_id=uid, action='next').first()

    finish_clicked = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week,
                                                user_id=uid, action='finish').first()

    show_next = (not next_clicked) and (p.current_week < p.weeks)
    show_finish = (p.current_week == p.weeks) and (not finish_clicked) and not p.completed

    if p.completed:
        return STYLE + logout_btn() + f"""
        <div class='container'>
            <h2>{p.name} — Completed 🎉</h2>
            <p>Project finished successfully!</p>
        </div>
        """

    return STYLE + logout_btn() + f"""
    <div class='container'>
        <h2>{p.name}</h2>

        <div class='badge'>Week {p.current_week}/{p.weeks}</div>
        <div class='badge'>Next: {next_count}/{total_users}</div>
        <div class='badge'>Finish: {finish_count}/{total_users}</div>

        <hr>

        {file_list}

        <form method='POST' enctype='multipart/form-data'>
            <input type='file' name='file'>
            <textarea name='description' placeholder='Description'></textarea>
            <button>Upload</button>
        </form>

        {"<form method='POST' action='/project/"+str(pid)+"/next'><button>Go Next Week</button></form>" if show_next else ""}
        {"<form method='POST' action='/project/"+str(pid)+"/finish'><button>Finish Project</button></form>" if show_finish else ""}
    </div>
"""

@app.route("/project/<int:pid>/next", methods=["POST"])
def next_week(pid):
    p = Project.query.get(pid)
    uid = session["user_id"]

    if not WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, user_id=uid, action='next').first():
        db.session.add(WeekStatus(project_id=pid, week_number=p.current_week, user_id=uid, action='next'))
        db.session.commit()

    total = User.query.count()
    done = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, action='next').count()

    if done >= total:
        p.current_week += 1
        db.session.commit()
        notify_project_users(pid, "Week Advanced", f"Project '{p.name}' moved to Week {p.current_week}")

    return redirect(f"/project/{pid}")

@app.route("/project/<int:pid>/finish", methods=["POST"])
def finish_project(pid):
    p = Project.query.get(pid)
    uid = session["user_id"]

    if not WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, user_id=uid, action='finish').first():
        db.session.add(WeekStatus(project_id=pid, week_number=p.current_week, user_id=uid, action='finish'))
        db.session.commit()

    total = User.query.count()
    done = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, action='finish').count()

    if done >= total:
        p.completed = True
        p.completed_time = datetime.utcnow()
        db.session.commit()
        notify_project_users(pid, "Project Completed", f"Project '{p.name}' is fully completed!")

    return redirect(f"/project/{pid}")

# ----------------------------------------------------
# RUN
# ----------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
