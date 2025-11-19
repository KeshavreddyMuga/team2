# final app.py
import os
import traceback
import requests
from datetime import datetime
from uuid import uuid4
from flask import Flask, request, redirect, session, send_from_directory, url_for, abort

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
# STYLE (Gradient A + glass + black buttons)
# ----------------------------------------------------
STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
body{
  font-family: Inter, Arial, sans-serif;
  margin:0;
  padding:40px;
  background: linear-gradient(135deg,#9b5de5,#f15bb5,#00bbf9,#00f5d4);
  background-attachment: fixed;
}
.container{
  max-width:1000px;
  margin: auto;
  background: rgba(255,255,255,0.18);
  border-radius:16px;
  padding:28px;
  box-shadow: 0 20px 40px rgba(0,0,0,0.18);
  backdrop-filter: blur(8px);
}
.header-row{ display:flex; align-items:center; justify-content:space-between; }
h1{ margin:0 0 12px 0; font-size:26px; color:#0b0b0b; }
a.logout{
  display:inline-block;
  background:#000;
  color:#fff;
  padding:8px 14px;
  border-radius:10px;
  text-decoration:none;
  font-weight:600;
  margin-left:8px;
}
.badges{ margin:12px 0; }
.badge{
  display:inline-block;
  background:#fff;
  padding:6px 10px;
  border-radius:8px;
  margin-right:8px;
  font-weight:600;
}
.file-box{
  background: rgba(255,255,255,0.35);
  padding:10px;
  border-radius:10px;
  margin-bottom:12px;
  overflow:auto;
}
.form-row{ margin-top:16px; }
input[type=file] { background: rgba(255,255,255,0.1); padding:8px; border-radius:8px; }
textarea{ width:100%; height:90px; padding:12px; border-radius:10px; border:1px solid #ddd; margin-top:10px; resize:vertical; }
button.black{
  background:#000; color:#fff; border:none; padding:12px 18px; border-radius:12px; cursor:pointer; margin-top:12px;
  font-weight:600;
}
.button-small{ padding:8px 12px; border-radius:8px; background:#fff; border:none; font-weight:700; margin-right:8px; cursor:default; }
.card{
  background: rgba(255,255,255,0.22);
  padding:14px;
  border-radius:12px;
  margin-bottom:12px;
  box-shadow: 0 6px 18px rgba(0,0,0,0.06);
}
.meta{ color:#111; font-size:13px; margin-top:6px; }
.link{ color:#0056ff; text-decoration:underline; }
.small{ font-size:13px; color:#222; }
.footer-actions{ margin-top:18px; }
.week-list { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px; }
.week-card { padding:10px; background: rgba(255,255,255,0.18); border-radius:8px; }
.center { text-align:center; }
</style>
"""

# ----------------------------------------------------
# DATABASE MODELS
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
    original_name = db.Column(db.String(300))
    uploaded_by = db.Column(db.String(200))
    description = db.Column(db.Text)
    uploaded_time = db.Column(db.DateTime, default=datetime.utcnow)

class WeekStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer)
    week_number = db.Column(db.Integer)
    user_id = db.Column(db.Integer)
    action = db.Column(db.String(20))  # 'next' or 'finish'
    clicked_time = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# ----------------------------------------------------
# EMAIL: Resend API
# ----------------------------------------------------
def send_email(to, subject, body):
    if not RESEND_API_KEY:
        app.logger.error("Missing RESEND_API_KEY env var")
        return False
    try:
        url = "https://api.resend.com/emails"
        payload = {"from": SENDER_EMAIL, "to": to, "subject": subject, "text": body}
        headers = {"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"}
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        app.logger.info("Resend response: %s %s", r.status_code, r.text)
        return r.status_code in (200, 201)
    except Exception:
        app.logger.exception("send_email failed")
        return False

def notify_all_users(subject, body):
    for u in User.query.all():
        if u.email:
            send_email(u.email, subject, body)

def notify_project_users(project_id, subject, body):
    # currently not per-project membership — notify all users
    notify_all_users(subject, body)

# ----------------------------------------------------
# HELPERS
# ----------------------------------------------------
def logout_html():
    return "<a class='logout' href='/logout'>Logout</a>" if session.get("user_id") else ""

def build_file_detail_path(upload_id):
    return f"/file/{upload_id}"

# ----------------------------------------------------
# AUTH ROUTES
# ----------------------------------------------------
@app.route("/")
def home():
    return STYLE + logout_html() + """
    <div class="container">
      <div class="header-row"><h1>Team Workspace</h1></div>
      <p class="small">Simple team workspace with week-tracking and file uploads.</p>
      <div style="margin-top:14px;">
        <a href="/login"><button class="black">Login</button></a>
        <a href="/register"><button class="black">Register</button></a>
      </div>
    </div>
    """

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        email = request.form.get("email","").strip().lower()
        pwd = request.form.get("password","")
        if not email or not pwd:
            return STYLE + "<div class='container'><script>alert('Email and password required');window.location='/register';</script></div>"
        if User.query.filter_by(email=email).first():
            return STYLE + "<div class='container'><script>alert('Email already exists');window.location='/register';</script></div>"
        db.session.add(User(name=name, email=email, password=pwd))
        db.session.commit()
        return redirect("/login")
    return STYLE + logout_html() + """
    <div class="container">
      <h2>Register</h2>
      <form method="POST">
        <input name="name" placeholder="Name">
        <input name="email" placeholder="Email">
        <input name="password" placeholder="Password" type="password">
        <button class="black">Register</button>
      </form>
      <div style="margin-top:10px;"><a href="/login"><button class="black">Login</button></a></div>
    </div>
    """

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        pwd = request.form.get("password","")
        user = User.query.filter_by(email=email).first()
        if not user or user.password != pwd:
            return STYLE + "<div class='container'><script>alert('Invalid login');window.location='/login';</script></div>"
        session["user_id"] = user.id
        session["user_name"] = user.name
        return redirect("/dashboard")
    return STYLE + logout_html() + """
    <div class="container">
      <h2>Login</h2>
      <form method="POST">
        <input name="email" placeholder="Email">
        <input name="password" placeholder="Password" type="password">
        <button class="black">Login</button>
      </form>
      <div style="margin-top:10px;"><a href="/register"><button class="black">Register</button></a></div>
    </div>
    """

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ----------------------------------------------------
# DASHBOARD / PROJECT CRUD
# ----------------------------------------------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")
    projects = Project.query.all()
    project_list = "".join(f"<li><a href='/project/{p.id}'>{p.name} — Week {p.current_week}/{p.weeks}</a></li>" for p in projects)
    return STYLE + logout_html() + f"""
    <div class="container">
      <div class="header-row"><h1>Welcome {session.get('user_name')}</h1></div>
      <form method="POST" action="/create_project">
        <input name="name" placeholder="Project name">
        <input name="weeks" placeholder="Total weeks" type="number">
        <button class="black">Create Project</button>
      </form>
      <h3 style="margin-top:18px">Projects</h3>
      <ul>{project_list}</ul>
    </div>
    """

@app.route("/create_project", methods=["POST"])
def create_project():
    if "user_id" not in session:
        return redirect("/login")
    name = request.form.get("name","Untitled").strip()
    weeks = int(request.form.get("weeks") or 1)
    p = Project(name=name, weeks=weeks)
    db.session.add(p)
    db.session.commit()
    return redirect("/dashboard")

# ----------------------------------------------------
# DOWNLOAD
# ----------------------------------------------------
@app.route("/download/<path:fname>")
def download(fname):
    return send_from_directory(app.config["UPLOAD_FOLDER"], fname, as_attachment=True)

# ----------------------------------------------------
# FILE DETAIL (for links in emails)
# ----------------------------------------------------
@app.route("/file/<int:upload_id>")
def file_detail(upload_id):
    u = Upload.query.get(upload_id)
    if not u:
        return STYLE + "<div class='container'>File not found</div>"
    download_url = url_for('download', fname=u.file_name, _external=True)
    uploaded_at = u.uploaded_time.strftime("%Y-%m-%d %H:%M:%S") if u.uploaded_time else "N/A"
    return STYLE + logout_html() + f"""
    <div class='container'>
      <h2>File Details</h2>
      <div class='card'>
        <b>{u.original_name}</b>
        <div class='meta'>Uploaded by: {u.uploaded_by} — {uploaded_at}</div>
        <p style='margin-top:10px'>{(u.description or 'No description provided')}</p>
        <div style='margin-top:10px'>
          <a class='link' href='{download_url}'>Download file</a>
        </div>
      </div>
      <a href='/project/{u.project_id}'><button class='black'>Back to Project</button></a>
    </div>
    """

# ----------------------------------------------------
# PROJECT PAGE + UPLOAD + NEXT/FINISH
# ----------------------------------------------------
@app.route("/project/<int:pid>", methods=["GET","POST"])
def project_page(pid):
    if "user_id" not in session:
        return redirect("/login")
    p = Project.query.get(pid)
    if not p:
        return STYLE + "<div class='container'>Project not found</div>"

    # upload handling
    if request.method == "POST" and 'file' in request.files:
        f = request.files["file"]
        if not f or f.filename == "":
            return redirect(f"/project/{pid}")
        desc = request.form.get("description","").strip()
        original = f.filename
        safe = uuid4().hex + "_" + secure_filename(original)
        f.save(os.path.join(app.config["UPLOAD_FOLDER"], safe))
        up = Upload(project_id=pid, week_number=p.current_week, file_name=safe, original_name=original, uploaded_by=session.get("user_name"), description=desc)
        db.session.add(up)
        db.session.commit()

        # Build absolute links for email
        host = request.host_url.rstrip("/")
        download_link = f"{host}/download/{safe}"
        detail_link = f"{host}{build_file_detail_path(up.id)}"

        # Email body containing description + download link + details link
        email_body = (
            f"New file uploaded in project: {p.name}\n\n"
            f"Uploaded by: {session.get('user_name')}\n"
            f"Week: {p.current_week}\n"
            f"File: {original}\n"
            f"Description: {desc or 'No description provided'}\n\n"
            f"Download link: {download_link}\n"
            f"View details: {detail_link}\n"
        )
        notify_project_users(pid, f"New upload in {p.name}", email_body)
        return redirect(f"/project/{pid}")

    uploads = Upload.query.filter_by(project_id=pid, week_number=p.current_week).all()
    file_list = ""
    for u in uploads:
        file_list += f"<div class='file-box'><b>{u.original_name}</b> — {u.uploaded_by} — <a class='link' href='/download/{u.file_name}'>Download</a></div>"

    uid = session.get("user_id")
    total_users = User.query.count() or 1
    next_count = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, action='next').count()
    finish_count = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, action='finish').count()
    next_clicked = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, user_id=uid, action='next').first()
    finish_clicked = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, user_id=uid, action='finish').first()

    # week buttons 1..current_week
    week_buttons = "".join(f"<a href='/project/{pid}/week/{w}'><div class='week-card'>Week {w}</div></a>" for w in range(1, p.current_week+1))

    show_next_btn = (p.current_week < p.weeks) and (not next_clicked)
    show_finish_btn = (p.current_week == p.weeks) and (not finish_clicked) and (not p.completed)

    if p.completed:
        return STYLE + logout_html() + f"""
        <div class='container'>
          <h1>{p.name} — Completed 🎉</h1>
          <p class='small'>Project completed on {p.completed_time}</p>
          <a href='/dashboard'><button class='black'>Back</button></a>
        </div>
        """

    # Insert Week Details button beside logout (top-right)
    # We'll show Week Details (links to uploads_all) and Logout to the right before container
    week_details_button_html = f"<a class='logout' href='/project/{pid}/uploads_all'>Week Details</a>"
    logout_html_btn = "<a class='logout' href='/logout'>Logout</a>"

    return STYLE + week_details_button_html + logout_html_btn + f"""
    <div class='container'>
      <div class='header-row'><h1>{p.name}</h1></div>

      <div class='badges'>
        <span class='badge'>Week {p.current_week}/{p.weeks}</span>
        <span class='badge'>Next: {next_count}/{total_users}</span>
        <span class='badge'>Finish: {finish_count}/{total_users}</span>
      </div>

      <div class='week-list'>{week_buttons}</div>

      <hr/>
      {file_list or "<p class='small'>No uploads for this week</p>"}

      <form method='POST' enctype='multipart/form-data' class='form-row'>
        <input type='file' name='file'><br>
        <textarea name='description' placeholder='Description'></textarea><br>
        <button class='black'>Upload</button>
      </form>

      <div class='footer-actions'>
        {"<form method='POST' action='/project/"+str(pid)+"/next' style='display:inline-block;'><button class='black'>Go Next Week</button></form>" if show_next_btn else ""}
        {"<form method='POST' action='/project/"+str(pid)+"/finish' style='display:inline-block; margin-left:8px;'><button class='black'>Finish Project</button></form>" if show_finish_btn else ""}
        <a href='/project/{pid}/uploads_all' style='margin-left:10px;'><button class='black'>Week Details</button></a>
      </div>
    </div>
    """

# ----------------------------------------------------
# NEXT / FINISH actions
# ----------------------------------------------------
@app.route("/project/<int:pid>/next", methods=["POST"])
def project_next(pid):
    if "user_id" not in session:
        return redirect("/login")
    p = Project.query.get(pid)
    if not p or p.completed:
        return redirect(f"/project/{pid}")
    uid = session.get("user_id")
    exists = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, user_id=uid, action='next').first()
    if not exists:
        db.session.add(WeekStatus(project_id=pid, week_number=p.current_week, user_id=uid, action='next'))
        db.session.commit()
        notify_project_users(pid, f"{session.get('user_name')} clicked Next", f"{session.get('user_name')} clicked Next for {p.name} (Week {p.current_week}).")
    total = User.query.count() or 1
    done = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, action='next').count()
    if done >= total and p.current_week < p.weeks:
        p.current_week += 1
        db.session.commit()
        notify_project_users(pid, f"Project {p.name} moved to Week {p.current_week}", f"Project {p.name} advanced to Week {p.current_week}.")
    return redirect(f"/project/{pid}")

@app.route("/project/<int:pid>/finish", methods=["POST"])
def project_finish(pid):
    if "user_id" not in session:
        return redirect("/login")
    p = Project.query.get(pid)
    if not p or p.completed:
        return redirect(f"/project/{pid}")
    uid = session.get("user_id")
    exists = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, user_id=uid, action='finish').first()
    if not exists:
        db.session.add(WeekStatus(project_id=pid, week_number=p.current_week, user_id=uid, action='finish'))
        db.session.commit()
        notify_project_users(pid, f"{session.get('user_name')} clicked Finish", f"{session.get('user_name')} clicked Finish for {p.name} (Week {p.current_week}).")
    total = User.query.count() or 1
    done = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, action='finish').count()
    if done >= total:
        p.completed = True
        p.completed_time = datetime.utcnow()
        db.session.commit()
        notify_project_users(pid, f"Project {p.name} Completed", f"Project {p.name} has been completed by the whole team.")
    return redirect(f"/project/{pid}")

# ----------------------------------------------------
# WEEK DETAILS (shows weeks 1..current_week)
# ----------------------------------------------------
@app.route("/project/<int:pid>/uploads_all")
def uploads_all(pid):
    if "user_id" not in session:
        return redirect("/login")
    p = Project.query.get(pid)
    if not p:
        return STYLE + "<div class='container'>Project not found</div>"

    content = ""
    for week in range(1, p.current_week + 1):
        uploads = Upload.query.filter_by(project_id=pid, week_number=week).all()
        next_users = WeekStatus.query.filter_by(project_id=pid, week_number=week, action='next').all()
        finish_users = WeekStatus.query.filter_by(project_id=pid, week_number=week, action='finish').all()
        next_names = ", ".join([User.query.get(ws.user_id).name for ws in next_users if User.query.get(ws.user_id)])
        finish_names = ", ".join([User.query.get(ws.user_id).name for ws in finish_users if User.query.get(ws.user_id)])
        pending_list = [u.name for u in User.query.all() if u.name not in next_names.split(", ") and u.name not in finish_names.split(", ")]
        pending = ", ".join([n for n in pending_list if n])

        file_cards = ""
        if uploads:
            for u in uploads:
                file_cards += f"""
                <div class='card'>
                  <b>{u.original_name}</b>
                  <div class='meta'>Uploaded by: {u.uploaded_by} — {u.uploaded_time.strftime('%Y-%m-%d %H:%M:%S')}</div>
                  <div style='margin-top:8px'>{(u.description or 'No description')}</div>
                  <div style='margin-top:8px'><a class='link' href='/file/{u.id}'>View Details</a> — <a class='link' href='/download/{u.file_name}'>Download</a></div>
                </div>
                """
        else:
            file_cards = "<p class='small'>No uploads for this week.</p>"

        content += f"""
        <h3 style='margin-top:14px'>Week {week}</h3>
        <div class='card'>
          {file_cards}
          <div style='margin-top:8px'><b>Next clicked:</b> {next_names or '—'}</div>
          <div style='margin-top:4px'><b>Finish clicked:</b> {finish_names or '—'}</div>
          <div style='margin-top:4px'><b>Pending:</b> {pending or '—'}</div>
        </div>
        """

    return STYLE + logout_html() + f"""
    <div class='container'>
      <h2>{p.name} — Week details (1..{p.current_week})</h2>
      {content}
      <a href='/project/{pid}'><button class='black'>Back</button></a>
    </div>
    """

# ----------------------------------------------------
# TEST EMAIL
# ----------------------------------------------------
@app.route("/test_email")
def test_email():
    to = os.environ.get("TEST_TO", "")
    if not to:
        return "Set TEST_TO env var for a quick test."
    ok = send_email(to, "Test email", "This is a test from Resend API.")
    return "OK" if ok else "FAILED"

# ----------------------------------------------------
# RUN
# ----------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
