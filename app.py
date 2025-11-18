import os
import traceback
from datetime import datetime
from flask import Flask, request, redirect, session, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message

# ----------------------------------------------------
# CONFIG
# ----------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "team_secret_key")

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///team_workspace.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', 'uploads')

# Email setup (Gmail App Password recommended)
app.config['MAIL_SERVER'] = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
app.config['MAIL_PORT'] = int(os.environ.get("MAIL_PORT", 587))
app.config['MAIL_USE_TLS'] = os.environ.get("MAIL_USE_TLS", "True").lower() in ("true", "1", "yes")
app.config['MAIL_USERNAME'] = os.environ.get("MAIL_USERNAME", "")
app.config['MAIL_PASSWORD'] = os.environ.get("MAIL_PASSWORD", "")
# ensure a sane default sender tuple (name, email)
app.config['MAIL_DEFAULT_SENDER'] = (
    os.environ.get("MAIL_SENDER_NAME", "Team Workspace"),
    os.environ.get("MAIL_SENDER_EMAIL", os.environ.get("MAIL_USERNAME", ""))
)

mail = Mail(app)
db = SQLAlchemy(app)

# ----------------------------------------------------
# SOCKETIO (gevent mode)
# ----------------------------------------------------
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="gevent",
    allow_upgrades=True,
    engineio_logger=False
)

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# ----------------------------------------------------
# STYLE + JS (common)
# ----------------------------------------------------
# top-right logout button class is .top-right-btn
STYLE = """
<link href='https://cdn.jsdelivr.net/npm/@sweetalert2/theme-dark@5/dark.css' rel='stylesheet'>
<script src='https://cdn.jsdelivr.net/npm/sweetalert2@11'></script>
<script src="https://cdn.socket.io/4.6.1/socket.io.min.js"></script>

<style>
body {
    font-family: Arial, sans-serif;
    background: linear-gradient(135deg,#9b5de5,#f15bb5,#00bbf9,#00f5d4);
    padding: 30px; margin: 0; background-attachment: fixed;
}
.container {
    background: #f5e9ff; padding:25px; border-radius:14px;
    max-width:920px; margin:auto; box-shadow:0 0 25px rgba(0,0,0,0.2);
    position: relative;
}
label { font-weight:bold; margin-top:12px; display:block; }
input, textarea {
    width:100%; padding:12px; margin-top:5px;
    border-radius:8px; border:1px solid #bbb;
    box-sizing: border-box;
}
button {
    width:100%; padding:12px; margin-top:12px;
    border-radius:10px; border:none; cursor:pointer;
    color:#fff; background:linear-gradient(45deg,#222,#444);
}
button.small { width:auto; padding:8px 14px; font-size:14px; }
.upload-item { padding:10px; border-bottom:1px solid #ddd; }
.meta { font-size:13px; color:#555; margin-top:6px; }
.top-right-btn {
    position:absolute; top:15px; right:15px;
    background: linear-gradient(45deg,#222,#444);
    color: #fff; border-radius:8px; padding:8px 12px;
    text-decoration: none;
    display:inline-block;
    font-weight:600;
}
a.top-right-btn { color: #fff; }
ul.project-list { padding-left: 18px; }
.container .card-title { margin-top:0; }
</style>

<script>
var socket = io();
window.currentProjectId = null;

socket.on('project_completed', function(data) {
  Swal.fire('Project Completed', 'Project \"' + data.name + '\" is completed!', 'success')
  .then(()=>{ 
    if (window.currentProjectId == data.pid) {
      window.location = '/project_completed/' + data.pid;
    }
  });
});
</script>
"""

# Helper to create logout button HTML (only visible when user logged in)
def logout_button_html():
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

class ProjectWeek(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer)
    week_number = db.Column(db.Integer)
    go_next_members = db.Column(db.Text, default="")

class Upload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer)
    week_number = db.Column(db.Integer)
    file_name = db.Column(db.String(300))
    uploaded_by = db.Column(db.String(200))
    description = db.Column(db.Text)
    uploaded_time = db.Column(db.DateTime, default=datetime.utcnow)

# ----------------------------------------------------
# DB Init
# ----------------------------------------------------
with app.app_context():
    db.create_all()

# ----------------------------------------------------
# EMAIL HELPER
# ----------------------------------------------------
def send_email_to_all(subject, body):
    """
    Send a simple plain-text email to all users with email addresses.
    Returns True on success, False on failure or no recipients.
    """
    try:
        with app.app_context():
            emails = [u.email for u in User.query.all() if u.email]
            if not emails:
                app.logger.info("send_email_to_all: no recipients found.")
                return False

            # Build message with explicit sender (tuple or string)
            sender = app.config.get("MAIL_DEFAULT_SENDER")
            msg = Message(subject=subject, recipients=emails, body=body, sender=sender)

            mail.send(msg)
            app.logger.info(f"send_email_to_all: sent '{subject}' to {len(emails)} recipients.")
            return True
    except Exception as e:
        # Print full stack trace to logs (Render will capture this)
        traceback.print_exc()
        app.logger.error(f"send_email_to_all: failed to send mail: {e}")
        return False

# ----------------------------------------------------
# ROUTES
# ----------------------------------------------------
@app.route("/")
def home():
    html = STYLE + logout_button_html() + """
    <div class='container'>
        <h2 class='card-title'>Team Workspace Organizer</h2>
        <a href='/login'><button class='small'>Login</button></a>
        <a href='/register'><button class='small'>Register</button></a>
    </div>
    """
    return html

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        pwd = request.form.get("password", "")

        if not email or not pwd:
            return STYLE + logout_button_html() + "<div class='container'><script>alert('Please provide email & password');window.location='/register';</script></div>"

        if User.query.filter_by(email=email).first():
            return STYLE + logout_button_html() + "<div class='container'><script>alert('Email already registered');window.location='/register';</script></div>"

        db.session.add(User(name=name, email=email, password=pwd))
        db.session.commit()
        return redirect("/login")

    return STYLE + logout_button_html() + """
    <div class='container'>
        <h2>Register</h2>
        <form method='POST'>
            <label>Name</label><input name='name'>
            <label>Email</label><input name='email'>
            <label>Password</label><input type='password' name='password'>
            <button>Register</button>
        </form>
    </div>
    """

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pwd = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()
        if not user or user.password != pwd:
            return STYLE + logout_button_html() + "<div class='container'><script>alert('Invalid login');window.location='/login';</script></div>"

        session["user_id"] = user.id
        session["user_name"] = user.name
        return redirect("/dashboard")

    return STYLE + logout_button_html() + """
    <div class='container'>
        <h2>Login</h2>
        <form method='POST'>
            <label>Email</label><input name='email'>
            <label>Password</label><input type='password' name='password'>
            <button>Login</button>
        </form>
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
    html_list = "".join(f"<li><a href='/project/{p.id}'>{p.name}</a></li>" for p in projects)

    return STYLE + logout_button_html() + f"""
    <div class='container'>
        <h2>Welcome {session['user_name']}</h2>
        <form method='POST' action='/create_project'>
            <label>Project Name</label><input name='name'>
            <label>Weeks</label><input type='number' name='weeks' min='1'>
            <button>Create Project</button>
        </form>
        <h3>Projects</h3>
        <ul class='project-list'>{html_list}</ul>
    </div>
    """

@app.route("/create_project", methods=["POST"])
def create_project():
    if "user_id" not in session:
        return redirect("/login")

    name = request.form.get("name", "").strip()
    weeks = int(request.form.get("weeks", 1) or 1)

    p = Project(name=name, weeks=weeks)
    db.session.add(p)
    db.session.commit()

    for w in range(1, weeks + 1):
        db.session.add(ProjectWeek(project_id=p.id, week_number=w))
    db.session.commit()

    return redirect("/dashboard")

@app.route("/download/<path:filename>")
def download(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=True)

@app.route("/project/<int:pid>", methods=["GET","POST"])
def project_page(pid):
    if "user_id" not in session:
        return redirect("/login")

    p = Project.query.get(pid)
    if p is None:
        return redirect("/dashboard")

    # current project week row (may be None)
    pw = ProjectWeek.query.filter_by(project_id=pid, week_number=p.current_week).first()

    if request.method == "POST":
        # file upload
        if 'file' not in request.files:
            return STYLE + logout_button_html() + "<div class='container'><script>alert('No file provided');window.location='/project/%s';</script></div>" % pid

        f = request.files["file"]
        desc = request.form.get("description", "")

        if not f or f.filename == "":
            return STYLE + logout_button_html() + "<div class='container'><script>alert('No file selected');window.location='/project/%s';</script></div>" % pid

        fname = secure_filename(f.filename)
        dest_path = os.path.join(app.config["UPLOAD_FOLDER"], fname)
        f.save(dest_path)

        db.session.add(Upload(
            project_id=pid,
            week_number=p.current_week,
            file_name=fname,
            uploaded_by=session.get("user_name", "Unknown"),
            description=desc
        ))
        db.session.commit()

        # Send email notification; log if fails
        subject = f"New File Uploaded - {p.name}"
        body = f"{session.get('user_name','Someone')} uploaded {fname} for project {p.name} (Week {p.current_week})."
        ok = send_email_to_all(subject, body)
        if not ok:
            # show a gentle alert to user but continue
            return STYLE + logout_button_html() + "<div class='container'><script>alert('Uploaded OK, but email notifications failed. Check logs.');window.location='/project/%s';</script></div>" % pid

        return redirect(f"/project/{pid}")

    uploads = Upload.query.filter_by(project_id=pid, week_number=p.current_week).all()

    items = "".join(
        f"<div class='upload-item'><b>{u.file_name}</b> — <a href='/download/{u.file_name}'>Download</a>"
        f"<div class='meta'>Uploaded by {u.uploaded_by} at {u.uploaded_time.strftime('%Y-%m-%d %H:%M:%S')}</div></div>"
        for u in uploads
    ) or "<p>No files yet</p>"

    return STYLE + logout_button_html() + f"""
    <script>window.currentProjectId = {pid};</script>
    <div class='container'>
        <h2>{p.name} — Week {p.current_week}</h2>
        {items}
        <form method='POST' enctype='multipart/form-data'>
            <label>Select File</label><input type='file' name='file'>
            <label>Description</label><textarea name='description'></textarea>
            <button>Upload</button>
        </form>
    </div>
    """

@app.route("/project_completed/<int:pid>")
def project_completed(pid):
    return STYLE + logout_button_html() + f"""
    <div class='container'>
        <h2>Project Completed</h2>
        <a href='/dashboard'><button>Back</button></a>
    </div>
    """

# ----------------------------------------------------
# RUN (for local/dev)
# ----------------------------------------------------
if __name__ == "__main__":
    # Debug is False for production; when developing you can set debug=True
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
