import os
import requests
from datetime import datetime
from uuid import uuid4
from flask import Flask, request, redirect, session, send_from_directory, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "team_secret_key"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///team_workspace.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = "uploads"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
SENDER_EMAIL = os.environ.get("EMAIL_FROM", "Team Workspace <onboarding@resend.dev>")

db = SQLAlchemy(app)

# ---------------- MODELS ----------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    email = db.Column(db.String(200), unique=True)
    password = db.Column(db.String(200))
    role = db.Column(db.String(20), default="member")  # admin/member

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    weeks = db.Column(db.Integer)
    current_week = db.Column(db.Integer, default=1)
    completed = db.Column(db.Boolean, default=False)
    completed_time = db.Column(db.DateTime)

class Upload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer)
    week_number = db.Column(db.Integer)
    file_name = db.Column(db.String(300))
    original_name = db.Column(db.String(300))
    uploaded_by = db.Column(db.String(200))
    description = db.Column(db.Text)
    uploaded_time = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# ---------------- EMAIL ----------------

def send_email(to, subject, body):
    if not RESEND_API_KEY:
        return False
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "from": SENDER_EMAIL,
        "to": to,
        "subject": subject,
        "text": body
    }
    r = requests.post(url, json=data, headers=headers)
    return r.status_code in (200, 201)

def notify_all_users(subject, body):
    for u in User.query.all():
        if u.email:
            send_email(u.email, subject, body)

# ---------------- AUTH ----------------

@app.route("/")
def home():
    return """
    <h1>Team Workspace</h1>
    <a href='/register'>Register</a> |
    <a href='/login'>Login</a>
    """

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"].lower()
        password = request.form["password"]

        if User.query.filter_by(email=email).first():
            return "Email already exists"

        role = "admin" if User.query.count() == 0 else "member"

        db.session.add(User(name=name, email=email, password=password, role=role))
        db.session.commit()
        return redirect("/login")

    return """
    <form method="POST">
        Name:<br><input name="name"><br>
        Email:<br><input name="email"><br>
        Password:<br><input type="password" name="password"><br>
        <button>Register</button>
    </form>
    """

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].lower()
        password = request.form["password"]
        user = User.query.filter_by(email=email).first()

        if not user or user.password != password:
            return "Invalid login"

        session["user_id"] = user.id
        session["user_name"] = user.name
        session["user_role"] = user.role
        return redirect("/dashboard")

    return """
    <form method="POST">
        Email:<br><input name="email"><br>
        Password:<br><input type="password" name="password"><br>
        <button>Login</button>
    </form>
    """

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    projects = Project.query.all()
    project_list = "".join(
        f"<li><a href='/project/{p.id}'>{p.name} - Week {p.current_week}/{p.weeks}</a></li>"
        for p in projects
    )

    return f"""
    <h2>Welcome {session.get('user_name')} ({session.get('user_role')})</h2>
    <form method="POST" action="/create_project">
        <input name="name" placeholder="Project name">
        <input name="weeks" type="number" placeholder="Weeks">
        <button>Create</button>
    </form>
    <ul>{project_list}</ul>
    <a href='/logout'>Logout</a>
    """

@app.route("/create_project", methods=["POST"])
def create_project():
    if "user_id" not in session:
        return redirect("/login")
    name = request.form["name"]
    weeks = int(request.form["weeks"])
    db.session.add(Project(name=name, weeks=weeks))
    db.session.commit()
    return redirect("/dashboard")

# ---------------- PROJECT PAGE ----------------

@app.route("/project/<int:pid>", methods=["GET","POST"])
def project_page(pid):
    if "user_id" not in session:
        return redirect("/login")

    p = Project.query.get(pid)
    if not p:
        return "Not found"

    if request.method == "POST":
        f = request.files["file"]
        desc = request.form.get("description")
        filename = uuid4().hex + "_" + secure_filename(f.filename)
        f.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        db.session.add(Upload(
            project_id=pid,
            week_number=p.current_week,
            file_name=filename,
            original_name=f.filename,
            uploaded_by=session["user_name"],
            description=desc
        ))
        db.session.commit()

        notify_all_users(
            f"New upload in {p.name}",
            f"{session['user_name']} uploaded file in Week {p.current_week}"
        )

        return redirect(f"/project/{pid}")

    uploads = Upload.query.filter_by(project_id=pid, week_number=p.current_week).all()
    files = "".join(
        f"<li>{u.original_name} - <a href='/download/{u.file_name}'>Download</a></li>"
        for u in uploads
    )

    next_button = ""
    finish_button = ""

    if session.get("user_role") == "admin" and not p.completed:
        if p.current_week < p.weeks:
            next_button = f"<form method='POST' action='/project/{pid}/next'><button>Next Week</button></form>"
        else:
            finish_button = f"<form method='POST' action='/project/{pid}/finish'><button>Finish Project</button></form>"

    return f"""
    <h2>{p.name}</h2>
    <p>Week {p.current_week}/{p.weeks}</p>
    <ul>{files or "No uploads"}</ul>

    <form method="POST" enctype="multipart/form-data">
        <input type="file" name="file">
        <textarea name="description"></textarea>
        <button>Upload</button>
    </form>

    {next_button}
    {finish_button}

    <a href="/dashboard">Back</a>
    """

# ---------------- NEXT WEEK ----------------

@app.route("/project/<int:pid>/next", methods=["POST"])
def project_next(pid):
    if session.get("user_role") != "admin":
        return redirect(f"/project/{pid}")

    p = Project.query.get(pid)
    if p.current_week < p.weeks:
        p.current_week += 1
        db.session.commit()

        notify_all_users(
            f"{p.name} moved to Week {p.current_week}",
            f"Admin moved project to Week {p.current_week}"
        )

    return redirect(f"/project/{pid}")

# ---------------- FINISH PROJECT ----------------

@app.route("/project/<int:pid>/finish", methods=["POST"])
def project_finish(pid):
    if session.get("user_role") != "admin":
        return redirect(f"/project/{pid}")

    p = Project.query.get(pid)
    p.completed = True
    p.completed_time = datetime.utcnow()
    db.session.commit()

    notify_all_users(
        f"{p.name} Completed 🎉",
        f"Project completed on {p.completed_time}"
    )

    return redirect(f"/project/{pid}/completed")

# ---------------- COMPLETED PAGE ----------------

@app.route("/project/<int:pid>/completed")
def project_completed(pid):
    p = Project.query.get(pid)
    content = ""

    for week in range(1, p.weeks + 1):
        uploads = Upload.query.filter_by(project_id=pid, week_number=week).all()
        if uploads:
            files = "".join(
                f"<li>{u.original_name} - <a href='/download/{u.file_name}'>Download</a></li>"
                for u in uploads
            )
        else:
            files = "No uploads"

        content += f"<h3>Week {week}</h3><ul>{files}</ul>"

    return f"""
    <h1>🎉 YOUR PROJECT IS SUCCESSFULLY COMPLETED 🎉</h1>
    <p>{p.name}</p>
    <p>Completed on: {p.completed_time}</p>
    {content}
    <a href="/dashboard">Back</a>
    """

# ---------------- DOWNLOAD ----------------

@app.route("/download/<path:fname>")
def download(fname):
    return send_from_directory(app.config["UPLOAD_FOLDER"], fname, as_attachment=True)

# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run(debug=True)
