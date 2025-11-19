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
app = Flask(_name_)
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
.container { background:white; padding:20px; border-radius:12px;
             box-shadow:0 0 10px rgba(0,0,0,0.1); max-width:900px; margin:auto; }
button { padding:10px; background:black; color:white; border:none;
         border-radius:6px; cursor:pointer; margin-top:10px; }
input, textarea { width:100%; padding:10px; border:1px solid #ccc;
                  margin-top:5px; border-radius:6px; }
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

class Upload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer)
    week_number = db.Column(db.Integer)
    file_name = db.Column(db.String(300))
    uploaded_by = db.Column(db.String(200))
    description = db.Column(db.Text)
    uploaded_time = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# ----------------------------------------------------
# RESEND EMAIL FUNCTION
# ----------------------------------------------------
def send_email(to, subject, body):
    """Send Email via Resend API."""
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
        print("RESEND =", r.status_code, r.text)
        return r.status_code in (200, 201)

    except Exception as e:
        print("EMAIL ERROR:", e)
        traceback.print_exc()
        return False


def send_email_to_all(subject, body):
    users = User.query.all()
    for u in users:
        if u.email:
            send_email(u.email, subject, body)

# ----------------------------------------------------
# ROUTES
# ----------------------------------------------------
@app.route("/")
def home():
    return STYLE + logout_btn() + """
    <div class='container'>
        <h2>Team Workspace</h2>
        <a href='/login'><button>Login</button></a>
        <a href='/register'><button>Register</button></a>
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
    items = "".join(f"<li><a href='/project/{p.id}'>{p.name}</a></li>" for p in projects)

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
    name = request.form["name"]
    weeks = int(request.form["weeks"])

    p = Project(name=name, weeks=weeks)
    db.session.add(p)
    db.session.commit()
    return redirect("/dashboard")

@app.route("/download/<path:f>")
def download(f):
    return send_from_directory(app.config["UPLOAD_FOLDER"], f, as_attachment=True)

@app.route("/project/<int:pid>", methods=["GET","POST"])
def project(pid):
    if "user_id" not in session:
        return redirect("/login")

    p = Project.query.get(pid)
    if not p:
        return STYLE + "<div class='container'>Project not found</div>"

    if request.method == "POST":
        f = request.files["file"]
        desc = request.form.get("description", "")

        fname = datetime.utcnow().strftime("%Y%m%d%H%M%S") + "" + uuid4().hex[:5] + "" + secure_filename(f.filename)
        f.save(os.path.join(app.config["UPLOAD_FOLDER"], fname))

        db.session.add(Upload(
            project_id=pid,
            week_number=p.current_week,
            file_name=fname,
            uploaded_by=session["user_name"],
            description=desc
        ))
        db.session.commit()

        send_email_to_all(
            f"New upload in {p.name}",
            f"{session['user_name']} uploaded {f.filename}"
        )

        return redirect(f"/project/{pid}")

    uploads = Upload.query.filter_by(project_id=pid, week_number=p.current_week).all()
    files = "".join(
        f"<div>{u.file_name} — <a href='/download/{u.file_name}'>Download</a></div>"
        for u in uploads
    )

    return STYLE + logout_btn() + f"""
    <div class='container'>
        <h2>{p.name}</h2>
        {files}
        <form method='POST' enctype='multipart/form-data'>
            <input type='file' name='file'>
            <textarea name='description'></textarea>
            <button>Upload</button>
        </form>
    </div>
"""

@app.route("/test_email")
def test_email():
    ok = send_email("keshavareddymuga@gmail.com", "Test", "Resend email working!")
    return "OK" if ok else "FAILED"

# ----------------------------------------------------
# RUN SERVER
# ----------------------------------------------------
if _name_ == "_main_":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
