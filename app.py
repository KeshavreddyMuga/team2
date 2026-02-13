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
# STYLE
# ---------------------------
STYLE = """
<style>
body{
  font-family: Arial, sans-serif;
  margin:0;
  padding:40px;
  background: linear-gradient(135deg,#9b5de5,#f15bb5,#00bbf9,#00f5d4);
}
.container{
  max-width:1000px;
  margin:auto;
  background: rgba(255,255,255,0.2);
  padding:25px;
  border-radius:15px;
}
.input-field{
  width:100%;
  padding:12px;
  border-radius:10px;
  border:1px solid #ccc;
  margin-top:8px;
}
button.black{
  background:#000;
  color:#fff;
  padding:10px 16px;
  border:none;
  border-radius:10px;
  cursor:pointer;
}
.file-box{
  background:#fff;
  padding:10px;
  border-radius:8px;
  margin-bottom:8px;
}
.badge{
  background:#fff;
  padding:6px 10px;
  border-radius:6px;
  font-weight:bold;
  margin-right:6px;
}
</style>
"""

# ---------------------------
# MODELS
# ---------------------------
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
# AUTH
# ---------------------------
@app.route("/")
def home():
    return STYLE + """
    <div class='container'>
      <h1>Team Workspace</h1>
      <a href='/login'><button class='black'>Login</button></a>
      <a href='/register'><button class='black'>Register</button></a>
    </div>
    """

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"].lower()
        password = request.form["password"]

        if User.query.filter_by(email=email).first():
            return "Email already exists"

        db.session.add(User(name=name, email=email, password=password))
        db.session.commit()
        return redirect("/login")

    return STYLE + """
    <div class='container'>
      <h2>Register</h2>
      <form method='POST'>
        <input class='input-field' name='name' placeholder='Name'>
        <input class='input-field' name='email' placeholder='Email'>
        <input class='input-field' type='password' name='password' placeholder='Password'>
        <button class='black'>Register</button>
      </form>
    </div>
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
        return redirect("/dashboard")

    return STYLE + """
    <div class='container'>
      <h2>Login</h2>
      <form method='POST'>
        <input class='input-field' name='email' placeholder='Email'>
        <input class='input-field' type='password' name='password' placeholder='Password'>
        <button class='black'>Login</button>
      </form>
    </div>
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
    project_list = "".join(
        f"<li><a href='/project/{p.id}'>{p.name} — Week {p.current_week}/{p.weeks}</a></li>"
        for p in projects
    )

    return STYLE + f"""
    <div class='container'>
      <h1>Welcome {session.get('user_name')}</h1>
      <form method='POST' action='/create_project'>
        <input class='input-field' name='name' placeholder='Project name'>
        <input class='input-field' type='number' name='weeks' placeholder='Total weeks'>
        <button class='black'>Create</button>
      </form>
      <h3>Projects</h3>
      <ul>{project_list}</ul>
      <a href='/logout'><button class='black'>Logout</button></a>
    </div>
    """

@app.route("/create_project", methods=["POST"])
def create_project():
    p = Project(
        name=request.form["name"],
        weeks=int(request.form["weeks"])
    )
    db.session.add(p)
    db.session.commit()
    return redirect("/dashboard")

# ---------------------------
# PROJECT PAGE
# ---------------------------
@app.route("/project/<int:pid>", methods=["GET","POST"])
def project_page(pid):
    if "user_id" not in session:
        return redirect("/login")

    p = Project.query.get(pid)
    if not p:
        return "Project not found"

    # LOCK IF COMPLETED
    if p.completed:
        all_uploads = Upload.query.filter_by(project_id=pid).order_by(Upload.week_number).all()

        upload_html = ""
        for u in all_uploads:
            upload_html += f"""
            <div class='file-box'>
                <b>Week {u.week_number}</b> — {u.original_name}
                — {u.uploaded_by}
                — <a href='/download/{u.file_name}'>Download</a>
            </div>
            """

        return STYLE + f"""
        <div class='container'>
            <h1>{p.name} — Completed 🎉</h1>
            <p>Completed on {p.completed_time}</p>
            <hr>
            <h3>All Week Details</h3>
            {upload_html or "No uploads found"}
            <br>
            <a href='/dashboard'><button class='black'>Back</button></a>
        </div>
        """

    # UPLOAD
    if request.method == "POST":
        f = request.files["file"]
        if f:
            safe = uuid4().hex + "_" + secure_filename(f.filename)
            f.save(os.path.join(app.config["UPLOAD_FOLDER"], safe))

            db.session.add(Upload(
                project_id=pid,
                week_number=p.current_week,
                file_name=safe,
                original_name=f.filename,
                uploaded_by=session.get("user_name")
            ))
            db.session.commit()

    uploads = Upload.query.filter_by(project_id=pid, week_number=p.current_week).all()
    file_list = "".join(
        f"<div class='file-box'>{u.original_name} — {u.uploaded_by} "
        f"<a href='/download/{u.file_name}'>Download</a></div>"
        for u in uploads
    )

    return STYLE + f"""
    <div class='container'>
        <h1>{p.name}</h1>
        <div>
            <span class='badge'>Week {p.current_week}/{p.weeks}</span>
        </div>
        <hr>
        {file_list or "No uploads yet"}
        <form method='POST' enctype='multipart/form-data'>
            <input type='file' name='file'>
            <button class='black'>Upload</button>
        </form>
        <br>
        <form method='POST' action='/project/{pid}/next'>
            <button class='black'>Next Week</button>
        </form>
        <form method='POST' action='/project/{pid}/finish'>
            <button class='black'>Finish Project</button>
        </form>
        <br>
        <a href='/dashboard'><button class='black'>Back</button></a>
    </div>
    """

# ---------------------------
# NEXT WEEK
# ---------------------------
@app.route("/project/<int:pid>/next", methods=["POST"])
def project_next(pid):
    p = Project.query.get(pid)
    if p and not p.completed and p.current_week < p.weeks:
        p.current_week += 1
        db.session.commit()
    return redirect(f"/project/{pid}")

# ---------------------------
# FINISH PROJECT
# ---------------------------
@app.route("/project/<int:pid>/finish", methods=["POST"])
def project_finish(pid):
    p = Project.query.get(pid)
    if p and not p.completed:
        p.completed = True
        p.completed_time = datetime.utcnow()
        db.session.commit()
    return redirect(f"/project/{pid}")

# ---------------------------
# DOWNLOAD
# ---------------------------
@app.route("/download/<path:fname>")
def download(fname):
    return send_from_directory(app.config["UPLOAD_FOLDER"], fname, as_attachment=True)

# ---------------------------
if __name__ == "__main__":
    app.run(debug=True)
