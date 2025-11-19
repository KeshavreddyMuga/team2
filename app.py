import os
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
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")  # Example: Keshava <onboarding@resend.dev>

db = SQLAlchemy(app)

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    engineio_logger=False,
)

# ----------------------------------------------------
# STYLE / UI
# ----------------------------------------------------
STYLE = """
<link href='https://cdn.jsdelivr.net/npm/@sweetalert2/theme-dark@5/dark.css' rel='stylesheet'>
<script src='https://cdn.jsdelivr.net/npm/sweetalert2@11'></script>
<style>
body { font-family: Arial; background: #f0f0ff; padding: 25px; }
.container { background: #fff; padding:20px; border-radius:14px; max-width:900px; margin:auto; box-shadow:0 0 15px rgba(0,0,0,0.15); position:relative; }
button { padding:10px; border:none; border-radius:8px; background:black; color:white; cursor:pointer; margin-top:10px; }
input, textarea { width:100%; padding:10px; border-radius:6px; border:1px solid #ccc; margin-top:5px; }
.top-right-btn { position:absolute; top:10px; right:10px; background:black; color:white; padding:8px 12px; border-radius:8px; text-decoration:none; }
.upload-item { padding:8px; border-bottom:1px solid #ddd; }
.meta { font-size:12px; color:#666; }
</style>
"""

def logout_btn():
    return "<a class='top-right-btn' href='/logout'>Logout</a>" if session.get("user_id") else ""

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
# RESEND EMAIL
# ----------------------------------------------------
def send_email(to, subject, body):
    """Send a single email using Resend API."""
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

        r = requests.post(url, json=payload, headers=headers)
        print("RESEND STATUS:", r.status_code, r.text)

        return r.status_code in (200, 201)

    except Exception as e:
        print("RESEND ERROR:", e)
        traceback.print_exc()
        return False


def send_email_to_all(subject, body):
    """Send email to every registered user."""
    try:
        users = User.query.all()
        for u in users:
            if u.email:
                send_email(u.email, subject, body)
        return True
    except:
        traceback.print_exc()
        return False

# ----------------------------------------------------
# ROUTES
# ----------------------------------------------------
@app.route("/")
def home():
    return STYLE + logout_btn() + """
    <div class='container'>
        <h2>Team Workspace Organizer</h2>
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

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    projects = Project.query.all()
    html = "".join(f"<li><a href='/project/{p.id}'>{p.name}</a></li>" for p in projects)

    return STYLE + logout_btn() + f"""
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
    if "user_id" not in session:
        return redirect("/login")

    name = request.form["name"]
    weeks = int(request.form["weeks"])

    p = Project(name=name, weeks=weeks)
    db.session.add(p)
    db.session.commit()

    return redirect("/dashboard")

@app.route("/download/<path:filename>")
def download(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=True)

@app.route("/project/<int:pid>", methods=["GET","POST"])
def project_page(pid):
    if "user_id" not in session:
        return redirect("/login")

    project = Project.query.get(pid)

    if not project:
        return STYLE + logout_btn() + "<div class='container'><h2>Project not found</h2></div>"

    if request.method == "POST":
        f = request.files["file"]
        desc = request.form.get("description", "")

        original = secure_filename(f.filename)
        unique = datetime.utcnow().strftime("%Y%m%d%H%M%S") + "_" + uuid4().hex[:6]
        fname = f"{unique}_{original}"

        path = os.path.join(app.config["UPLOAD_FOLDER"], fname)
        f.save(path)

        db.session.add(Upload(
            project_id=pid,
            week_number=project.current_week,
            file_name=fname,
            uploaded_by=session["user_name"],
            description=desc
        ))
        db.session.commit()

        send_email_to_all(
            f"New file in {project.name}",
            f"{session['user_name']} uploaded {original}"
        )

        return redirect(f"/project/{pid}")

    uploads = Upload.query.filter_by(
        project_id=pid,
        week_number=project.current_week
    ).order_by(Upload.uploaded_time.desc()).all()

    items = "".join(
        f"<div class='upload-item'><b>{u.file_name}</b> — <a href='/download/{u.file_name}'>Download</a>"
        f"<div class='meta'>Uploaded by {u.uploaded_by}</div></div>"
        for u in uploads
    ) or "<p>No files uploaded yet</p>"

    return STYLE + logout_btn() + f"""
    <div class='container'>
        <h2>{project.name} — Week {project.current_week}</h2>
        {items}
        <form method='POST' enctype='multipart/form-data'>
            <label>Select File</label><input type='file' name='file'>
            <label>Description</label><textarea name='description'></textarea>
            <button>Upload</button>
        </form>
        <a href='/dashboard'><button>Back</button></a>
    </div>
"""

@app.route("/test_email")
def test_email():
    ok = send_email("keshavareddymuga@gmail.com", "Test Email", "Resend is working!")
    return "Email sent!" if ok else "Email failed"

# ----------------------------------------------------
# RUN
# ----------------------------------------------------
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
