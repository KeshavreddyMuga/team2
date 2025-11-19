# app.py
import os
import traceback
import requests
from datetime import datetime
from uuid import uuid4
from flask import Flask, request, redirect, session, send_from_directory, url_for
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
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")

db = SQLAlchemy(app)

# ----------------------------------------------------
# STYLE
# ----------------------------------------------------
STYLE = """
<style>
body { font-family: Arial; background:#eef; padding:20px; }
.container { background:white; padding:20px; border-radius:12px; box-shadow:0 0 10px rgba(0,0,0,0.1); max-width:900px; margin:auto; }
button { padding:10px; background:black; color:white; border:none; border-radius:6px; cursor:pointer; margin-top:10px; }
input, textarea { width:100%; padding:10px; border:1px solid #ccc; margin-top:5px; border-radius:6px; }
.badge { display:inline-block; padding:6px 10px; background:#ddd; border-radius:6px; margin-right:6px; }
.success { color:green; font-weight:bold; }
</style>
"""

def logout_btn():
    return "<a href='/logout' style='float:right;padding:10px;'>Logout</a>" if session.get("user_id") else ""

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
    """
    Stores who clicked next/finish for which project & week.
    action: 'next' or 'finish'
    """
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer)
    week_number = db.Column(db.Integer)
    user_id = db.Column(db.Integer)
    action = db.Column(db.String(20))
    clicked_time = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# ----------------------------------------------------
# EMAIL HELPERS
# ----------------------------------------------------
def send_email(to, subject, body):
    try:
        url = "https://api.resend.com/emails"
        payload = {
            "from": SENDER_EMAIL,
            "to": to,
            "subject": subject,
            "text": body
        }
        headers = {
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        }
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        app.logger.info("RESEND %s %s", r.status_code, r.text)
        return r.status_code in (200, 201)
    except Exception as e:
        app.logger.exception("EMAIL ERROR")
        return False

def notify_all_users(subject, body):
    users = User.query.all()
    for u in users:
        if u.email:
            send_email(u.email, subject, body)

def notify_project_users(project_id, subject, body):
    # In Option A, project users == all registered users
    notify_all_users(subject, body)

# ----------------------------------------------------
# ROUTES (auth + basic)
# ----------------------------------------------------
@app.route("/")
def home():
    return STYLE + logout_btn() + """
    <div class='container'>
        <h2>Team Workspace (Option A)</h2>
        <a href='/login'><button>Login</button></a>
        <a href='/register'><button>Register</button></a>
        <p>All registered users form a single team in this mode.</p>
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
        <a href='/login'><button>Login</button></a>
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
            <input name='email'>
            <input type='password' name='password'>
            <button>Login</button>
        </form>
        <a href='/register'><button>Register</button></a>
    </div>
"""

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")
    projects = Project.query.all()
    items = "".join(f"<li><a href='/project/{p.id}'>{p.name} (Week {p.current_week}/{p.weeks})</a></li>" for p in projects)
    return STYLE + logout_btn() + f"""
    <div class='container'>
        <h2>Welcome {session['user_name']}</h2>
        <form method='POST' action='/create_project'>
            <input name='name' placeholder='Project Name'>
            <input name='weeks' type='number' placeholder='Weeks'>
            <button>Create</button>
        </form>
        <ul>{items}</ul>
    </div>
"""

@app.route("/create_project", methods=["POST"])
def create_project():
    if "user_id" not in session:
        return redirect("/login")
    name = request.form["name"]
    weeks = int(request.form["weeks"])
    p = Project(name=name, weeks=weeks)
    db.session.add(p)
    db.session.commit()
    return redirect("/dashboard")

@app.route("/download/<path:f>")
def download(f):
    return send_from_directory(app.config["UPLOAD_FOLDER"], f, as_attachment=True)

# ----------------------------------------------------
# NEW: Show all uploads up to current week (week-wise details)
@app.route("/project/<int:pid>/uploads_all")
def uploads_all(pid):
    if "user_id" not in session:
        return redirect("/login")

    p = Project.query.get(pid)
    if not p:
        return STYLE + "<div class='container'>Project not found</div>"

    file_list = ""

    # Loop all weeks up to current week
    for week in range(1, p.current_week + 1):
        uploads = Upload.query.filter_by(project_id=pid, week_number=week).all()
        file_list += f"<h3>Week {week}</h3>"

        if not uploads:
            file_list += "<p>No uploads this week.</p>"
            continue

        for u in uploads:
            ts = u.uploaded_time.strftime('%Y-%m-%d %H:%M:%S') if u.uploaded_time else 'N/A'
            file_list += f"<div><b>{u.file_name}</b> — uploaded by <i>{u.uploaded_by}</i> at {ts} — <a href='/download/{u.file_name}'>Download</a></div>"

        file_list += "<hr>"

    return STYLE + logout_btn() + f"""
    <div class='container'>
        <h2>{p.name} — All Uploads Until Week {p.current_week}</h2>
        {file_list}
        <br><a href='/project/{pid}'><button>Back</button></a>
    </div>
    """

# ----------------------------------------------------
# PROJECT PAGE + UPLOADS + NEXT/FINISH logic (Option A)
# ----------------------------------------------------
@app.route("/project/<int:pid>", methods=["GET","POST"])
def project(pid):
    if "user_id" not in session:
        return redirect("/login")
    p = Project.query.get(pid)
    if not p:
        return STYLE + "<div class='container'>Project not found</div>"

    # handle upload
    if request.method == "POST" and 'file' in request.files:
        f = request.files["file"]
        desc = request.form.get("description", "")
        fname = datetime.utcnow().strftime("%Y%m%d%H%M%S") + "_" + uuid4().hex[:5] + "_" + secure_filename(f.filename)
        f.save(os.path.join(app.config["UPLOAD_FOLDER"], fname))
        db.session.add(Upload(project_id=pid, week_number=p.current_week, file_name=fname, uploaded_by=session["user_name"], description=desc))
        db.session.commit()
        notify_project_users(pid, f"New upload in {p.name}", f"{session['user_name']} uploaded {f.filename}")
        return redirect(f"/project/{pid}")

    # list uploads (for current week)
    uploads = Upload.query.filter_by(project_id=pid, week_number=p.current_week).all()
    files = ""
    for u in uploads:
        ts = u.uploaded_time.strftime('%Y-%m-%d %H:%M:%S') if u.uploaded_time else 'N/A'
        files += f"<div>{u.file_name} — uploaded by <i>{u.uploaded_by}</i> at {ts} — <a href='/download/{u.file_name}'>Download</a></div>"

    # status for current user
    uid = session["user_id"]
    next_clicked = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, user_id=uid, action='next').first() is not None
    finish_clicked = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, user_id=uid, action='finish').first() is not None

    # counts
    total_users = User.query.count()
    next_count = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, action='next').count()
    finish_count = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, action='finish').count()

    # buttons visibility
    show_next_btn = (not p.completed) and (not next_clicked) and (p.current_week <= p.weeks)
    show_finish_btn = (not p.completed) and (p.current_week == p.weeks) and (not finish_clicked)

    # completion page if project completed
    if p.completed:
        return STYLE + logout_btn() + f"""
        <div class='container'>
            <h2>{p.name} — Completed</h2>
            <p class='success'>YOUR TEAM SUCCESSFULLY COMPLETED THE PROJECT 🎉</p>
        </div>
        """

    return STYLE + logout_btn() + f"""
    <div class='container'>
        <h2>{p.name}</h2>
        <div>
            <span class='badge'>Week {p.current_week} / {p.weeks}</span>
            <span class='badge'>Next clicked: {next_count}/{total_users}</span>
            <span class='badge'>Finish clicked: {finish_count}/{total_users}</span>
        </div>
        <hr/>
        {files}
        <a href='/project/{pid}/uploads_all'><button type='button'>Show All Week Uploads</button></a>
        <form method='POST' enctype='multipart/form-data'>
            <input type='file' name='file'>
            <textarea name='description' placeholder='Description'></textarea>
            <button>Upload</button>
        </form>
        <div style='margin-top:12px;'>
            {"<form method='POST' action='/project/"+str(pid)+"/click_next'><button>Go to Next Week</button></form>" if show_next_btn else "<div style='margin-top:8px;'>You already clicked Next or waiting for others.</div>"}
            {"<form method='POST' action='/project/"+str(pid)+"/click_finish'><button>Finish Project</button></form>" if show_finish_btn else ""}
        </div>
    </div>
    """

@app.route("/project/<int:pid>/click_next", methods=["POST"])
def click_next(pid):
    if "user_id" not in session:
        return redirect("/login")
    p = Project.query.get(pid)
    if not p or p.completed:
        return redirect(f"/project/{pid}")

    uid = session["user_id"]
    # prevent duplicate
    existing = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, user_id=uid, action='next').first()
    if existing:
        return redirect(f"/project/{pid}")

    ws = WeekStatus(project_id=pid, week_number=p.current_week, user_id=uid, action='next')
    db.session.add(ws)
    db.session.commit()

    # notify others that someone clicked
    notify_project_users(pid, f"{session['user_name']} clicked Go to Next Week", f"{session['user_name']} clicked Go to Next Week for project {p.name} (Week {p.current_week}).")

    # check if all users clicked
    total_users = User.query.count()
    next_count = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, action='next').count()
    if next_count >= total_users:
        # advance week
        if p.current_week < p.weeks:
            p.current_week += 1
            db.session.commit()
            # optional: clear next statuses for the new week (they are tied to week_number so it's fine)
            notify_project_users(pid, f"Project {p.name} advanced to Week {p.current_week}", f"All users clicked Next. Project {p.name} is now at Week {p.current_week}.")
        else:
            # if already at last week, do nothing here (finish flow handles completion)
            pass

    return redirect(f"/project/{pid}")

@app.route("/project/<int:pid>/click_finish", methods=["POST"])
def click_finish(pid):
    if "user_id" not in session:
        return redirect("/login")
    p = Project.query.get(pid)
    if not p or p.completed:
        return redirect(f"/project/{pid}")

    uid = session["user_id"]
    existing = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, user_id=uid, action='finish').first()
    if existing:
        return redirect(f"/project/{pid}")

    ws = WeekStatus(project_id=pid, week_number=p.current_week, user_id=uid, action='finish')
    db.session.add(ws)
    db.session.commit()

    notify_project_users(pid, f"{session['user_name']} clicked Finish", f"{session['user_name']} clicked Finish on project {p.name} (Week {p.current_week}).")

    total_users = User.query.count()
    finish_count = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, action='finish').count()
    if finish_count >= total_users:
        # mark project completed
        p.completed = True
        p.completed_time = datetime.utcnow()
        db.session.commit()
        notify_project_users(pid, f"Project {p.name} — Completed", f"Congratulations! Project {p.name} has been completed by all users.")
    return redirect(f"/project/{pid}")

@app.route("/test_email")
def test_email():
    ok = send_email("keshavareddymuga@gmail.com", "Test", "Resend email working!")
    return "OK" if ok else "FAILED"

# ----------------------------------------------------
# RUN SERVER
# ----------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
