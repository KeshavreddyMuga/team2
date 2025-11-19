import os
os.environ["GEVENT_SUPPORT"] = "False"   # 🔥 IMPORTANT FIX FOR RESEND + RENDER

import traceback
import requests
from datetime import datetime
from uuid import uuid4
from flask import Flask, request, redirect, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
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

# Force threading only (NO GEvent)
socketio = SocketIO(
    app,
    async_mode="threading",
    cors_allowed_origins="*",
    engineio_logger=False,
)

# ----------------------------------------------------
# EMAIL SENDER (RESEND)
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
            "Content-Type": "application/json"
        }

        r = requests.post(url, json=payload, headers=headers, timeout=10)
        print("RESEND STATUS:", r.status_code, r.text)

        return r.status_code in (200, 201)

    except Exception as e:
        print("RESEND ERROR:", e)
        traceback.print_exc()
        return False


def send_email_to_all(subject, body):
    try:
        users = User.query.all()
        for u in users:
            send_email(u.email, subject, body)
    except:
        traceback.print_exc()

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
# ROUTES
# ----------------------------------------------------
@app.route("/")
def home():
    return """
        <h2>Team Workspace Organizer</h2>
        <a href='/login'>Login</a> | 
        <a href='/register'>Register</a>
    """

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"].strip().lower()
        pwd = request.form["password"]

        if User.query.filter_by(email=email).first():
            return "Email already registered"

        db.session.add(User(name=name, email=email, password=pwd))
        db.session.commit()
        return redirect("/login")

    return """
        <h2>Register</h2>
        <form method='POST'>
            <input name='name'>
            <input name='email'>
            <input name='password'>
            <button>Register</button>
        </form>
    """

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        pwd = request.form["password"]

        user = User.query.filter_by(email=email).first()
        if not user or user.password != pwd:
            return "Invalid login"

        session["user_id"] = user.id
        session["user_name"] = user.name
        return redirect("/dashboard")

    return """
        <h2>Login</h2>
        <form method='POST'>
            <input name='email'>
            <input name='password'>
            <button>Login</button>
        </form>
    """

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/dashboard")
def dashboard():
    projects = Project.query.all()
    html = "".join(f"<li><a href='/project/{p.id}'>{p.name}</a></li>" for p in projects)

    return f"""
        <h2>Welcome</h2>
        <form method='POST' action='/create_project'>
            <input name='name' placeholder='Project name'>
            <input name='weeks' placeholder='Weeks'>
            <button>Create</button>
        </form>
        <ul>{html}</ul>
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
def project_page(pid):
    project = Project.query.get(pid)
    if not project:
        return "Project not found"

    if request.method == "POST":
        f = request.files["file"]
        desc = request.form.get("description", "")

        original = secure_filename(f.filename)
        uid = uuid4().hex[:6]
        fname = f"{uid}_{original}"

        f.save(os.path.join(app.config["UPLOAD_FOLDER"], fname))

        db.session.add(Upload(
            project_id=pid,
            week_number=project.current_week,
            file_name=fname,
            uploaded_by=session["user_name"],
            description=desc
        ))
        db.session.commit()

        send_email_to_all(
            f"New Upload for {project.name}",
            f"{session['user_name']} uploaded {original}"
        )

        return redirect(f"/project/{pid}")

    uploads = Upload.query.filter_by(project_id=pid).all()

    items = "".join(f"<p>{u.file_name}</p>" for u in uploads)

    return f"""
        <h2>{project.name}</h2>
        {items}
        <form method='POST' enctype='multipart/form-data'>
            <input type='file' name='file'>
            <textarea name='description'></textarea>
            <button>Upload</button>
        </form>
    """

@app.route("/test_email")
def test_email():
    ok = send_email("keshavareddymuga@gmail.com", "Test Email", "Resend Works!")
    return "OK" if ok else "FAIL"

# ----------------------------------------------------
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
