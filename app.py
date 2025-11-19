import os
import traceback
import requests
from datetime import datetime
from uuid import uuid4
from flask import Flask, request, redirect, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "team_secret_key")

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///team_workspace.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.environ.get("UPLOAD_FOLDER", "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# ---------- RESEND ----------
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")

db = SQLAlchemy(app)

# ******************** IMPORTANT FIX ********************
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",   # <---- FIXED!! no gevent, no recursion
    engineio_logger=False,
)
# *********************************************************

# ---------- UI STYLE ----------
STYLE = """
<link href='https://cdn.jsdelivr.net/npm/@sweetalert2/theme-dark@5/dark.css' rel='stylesheet'>
<script src='https://cdn.jsdelivr.net/npm/sweetalert2@11'></script>
"""

def logout_btn():
    return "<a class='top-right-btn' href='/logout'>Logout</a>" if session.get("user_id") else ""

# ---------- MODELS ----------
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

# ---------- RESEND EMAIL ----------
def send_email(to, subject, body):
    try:
        url = "https://api.resend.com/emails"

        data = {
            "from": SENDER_EMAIL,
            "to": to,
            "subject": subject,
            "text": body,
        }

        headers = {
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json"
        }

        r = requests.post(url, json=data, headers=headers)
        print("RESEND:", r.status_code, r.text)
        return r.status_code in (200, 201)

    except Exception as e:
        print("RESEND ERROR:", e)
        traceback.print_exc()
        return False

def send_email_to_all(subject, body):
    users = User.query.all()
    for u in users:
        if u.email:
            send_email(u.email, subject, body)

# ---------- ROUTES ----------
@app.route("/")
def home():
    return STYLE + """
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
        email = request.form["email"].strip().lower()
        pwd = request.form["password"]

        if User.query.filter_by(email=email).first():
            return STYLE + "<script>alert('Email already registered');window.location='/register';</script>"

        db.session.add(User(name=name, email=email, password=pwd))
        db.session.commit()
        return redirect("/login")

    return STYLE + """
    <div class='container'>
        <h2>Register</h2>
        <form method='POST'>
            <label>Name</label><input name='name'>
            <label>Email</label><input name='email'>
            <label>Password</label><input name='password' type='password'>
            <button>Register</button>
        </form>
        <a href='/login'><button>Login</button></a>
    </div>
"""

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
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
            <label>Email</label><input name='email'>
            <label>Password</label><input name='password' type='password'>
            <button>Login</button>
        </form>
        <a href='/register'><button>Register</button></a>
    </div>
"""

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    projects = Project.query.all()
    html = "".join(f"<li><a href='/project/{p.id}'>{p.name}</a></li>" for p in projects)

    return STYLE + f"""
    <div class='container'>
        <h2>Welcome {session['user_name']}</h2>

        <form action='/create_project' method='POST'>
            <label>Project Name</label><input name='name'>
            <label>Weeks</label><input name='weeks' type='number'>
            <button>Create Project</button>
        </form>

        <h3>Your Projects</h3>
        <ul>{html}</ul>
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

@app.route("/project/<int:pid>", methods=["GET","POST"])
def project(pid):
    if "user_id" not in session:
        return redirect("/login")

    p = Project.query.get(pid)
    if not p:
        return "<h2>Project not found</h2>"

    if request.method == "POST":
        f = request.files["file"]
        desc = request.form.get("description", "")

        fname = f"{datetime.utcnow().timestamp()}_{uuid4().hex}_{secure_filename(f.filename)}"
        f.save(os.path.join(app.config["UPLOAD_FOLDER"], fname))

        up = Upload(
            project_id=pid,
            week_number=p.current_week,
            file_name=fname,
            uploaded_by=session["user_name"],
            description=desc
        )

        db.session.add(up)
        db.session.commit()

        send_email_to_all(f"New upload in {p.name}", f"{session['user_name']} uploaded {f.filename}")

        return redirect(f"/project/{pid}")

    uploads = Upload.query.filter_by(project_id=pid).all()
    ul = "".join(f"<div>{u.file_name}</div>" for u in uploads)

    return f"""
    <h2>{p.name}</h2>
    {ul}
    <form method='POST' enctype='multipart/form-data'>
        <input type='file' name='file'>
        <textarea name='description'></textarea>
        <button>Upload</button>
    </form>
"""

@app.route("/test_email")
def test_email():
    send_email("keshavareddymuga@gmail.com", "Test Email", "Resend works!")
    return "Sent test email."

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
