import os
from datetime import datetime
from uuid import uuid4
from flask import Flask, request, redirect, session, send_from_directory, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

# ---------------------------
# APP CONFIG
# ---------------------------
app = Flask(__name__)
app.secret_key = "team_secret_key"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///team_workspace.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = "uploads"

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db = SQLAlchemy(app)

# ---------------------------
# MODELS
# ---------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    email = db.Column(db.String(200), unique=True)
    password = db.Column(db.String(200))
    role = db.Column(db.String(20), default="member")

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

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer)
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    assigned_to = db.Column(db.Integer)
    created_by = db.Column(db.Integer)
    created_time = db.Column(db.DateTime, default=datetime.utcnow)
    completed = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()

# ---------------------------
# AUTH
# ---------------------------
@app.route("/")
def home():
    return """
    <h1>Team Workspace</h1>
    <a href='/login'>Login</a> |
    <a href='/register'>Register</a>
    """

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        if User.query.filter_by(email=email).first():
            return "Email already exists"

        role = "admin" if User.query.count() == 0 else "member"

        user = User(name=name, email=email, password=password, role=role)
        db.session.add(user)
        db.session.commit()
        return redirect("/login")

    return """
    <h2>Register</h2>
    <form method='POST'>
        <input name='name' placeholder='Name'><br>
        <input name='email' placeholder='Email'><br>
        <input name='password' type='password' placeholder='Password'><br>
        <button>Register</button>
    </form>
    """

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()
        if not user or user.password != password:
            return "Invalid login"

        session["user_id"] = user.id
        session["user_name"] = user.name
        session["user_role"] = user.role

        return redirect("/dashboard")

    return """
    <h2>Login</h2>
    <form method='POST'>
        <input name='email' placeholder='Email'><br>
        <input name='password' type='password' placeholder='Password'><br>
        <button>Login</button>
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
    html = "<h2>Dashboard</h2>"

    if session["user_role"] == "admin":
        html += """
        <form method='POST' action='/create_project'>
            <input name='name' placeholder='Project name'>
            <input name='weeks' type='number' placeholder='Weeks'>
            <button>Create Project</button>
        </form>
        """

    for p in projects:
        html += f"<p><a href='/project/{p.id}'>{p.name}</a></p>"

    html += "<br><a href='/logout'>Logout</a>"
    return html

@app.route("/create_project", methods=["POST"])
def create_project():
    if session.get("user_role") != "admin":
        return redirect("/dashboard")

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

    if p.completed:
        return redirect(f"/project/{pid}/completed")

    # Upload
    if request.method == "POST" and "file" in request.files:
        file = request.files["file"]
        if file and not p.completed:
            fname = uuid4().hex + "_" + secure_filename(file.filename)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], fname))

            u = Upload(
                project_id=pid,
                week_number=p.current_week,
                file_name=fname,
                original_name=file.filename,
                uploaded_by=session["user_name"]
            )
            db.session.add(u)
            db.session.commit()

    uploads = Upload.query.filter_by(project_id=pid, week_number=p.current_week).all()
    tasks = Task.query.filter_by(project_id=pid).all()

    html = f"<h2>{p.name} - Week {p.current_week}/{p.weeks}</h2>"

    # TASKS DISPLAY
    html += "<h3>Tasks</h3>"
    for t in tasks:
        user = User.query.get(t.assigned_to)
        status = "✅ Done" if t.completed else "⏳ Pending"
        html += f"<p>{t.title} - {user.name if user else ''} - {status}</p>"

        if session["user_id"] == t.assigned_to and not t.completed:
            html += f"""
            <form method='POST' action='/task/{t.id}/complete'>
                <button>Mark Complete</button>
            </form>
            """

    # ADMIN CREATE TASK
    if session["user_role"] == "admin":
        users = User.query.filter(User.role=="member").all()
        html += f"""
        <h4>Create Task</h4>
        <form method='POST' action='/project/{pid}/create_task'>
            <input name='title' placeholder='Task title'><br>
            <textarea name='description'></textarea><br>
            <select name='assigned_to'>
        """
        for u in users:
            html += f"<option value='{u.id}'>{u.name}</option>"
        html += """
            </select><br>
            <button>Create</button>
        </form>
        """

    # UPLOAD SECTION
    html += """
    <h3>Uploads</h3>
    <form method='POST' enctype='multipart/form-data'>
        <input type='file' name='file'>
        <button>Upload</button>
    </form>
    """

    for u in uploads:
        html += f"<p>{u.original_name}</p>"

    html += f"""
    <br><a href='/project/{pid}/finish'>Finish Project</a>
    <br><a href='/dashboard'>Back</a>
    """
    return html

# ---------------------------
# TASK ROUTES
# ---------------------------
@app.route("/project/<int:pid>/create_task", methods=["POST"])
def create_task(pid):
    if session.get("user_role") != "admin":
        return redirect(f"/project/{pid}")

    p = Project.query.get(pid)
    if p.completed:
        return redirect(f"/project/{pid}")

    t = Task(
        project_id=pid,
        title=request.form["title"],
        description=request.form["description"],
        assigned_to=int(request.form["assigned_to"]),
        created_by=session["user_id"]
    )
    db.session.add(t)
    db.session.commit()
    return redirect(f"/project/{pid}")

@app.route("/task/<int:tid>/complete", methods=["POST"])
def complete_task(tid):
    t = Task.query.get(tid)
    if t and t.assigned_to == session["user_id"]:
        t.completed = True
        db.session.commit()
    return redirect(f"/project/{t.project_id}")

# ---------------------------
# FINISH PROJECT
# ---------------------------
@app.route("/project/<int:pid>/finish")
def finish_project(pid):
    p = Project.query.get(pid)
    p.completed = True
    p.completed_time = datetime.utcnow()
    db.session.commit()
    return redirect(f"/project/{pid}/completed")

# ---------------------------
# COMPLETED PAGE
# ---------------------------
@app.route("/project/<int:pid>/completed")
def completed_page(pid):
    p = Project.query.get(pid)
    html = f"<h2>🎉 Project Completed: {p.name}</h2>"

    for week in range(1, p.weeks+1):
        html += f"<h3>Week {week}</h3>"
        uploads = Upload.query.filter_by(project_id=pid, week_number=week).all()
        if uploads:
            for u in uploads:
                html += f"<p>{u.original_name} - {u.uploaded_by}</p>"
        else:
            html += "<p>No uploads</p>"

    html += "<br><a href='/dashboard'>Back to Dashboard</a>"
    return html

# ---------------------------
if __name__ == "__main__":
    app.run(debug=True)
