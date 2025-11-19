# app.py
import os
import traceback
import requests
from datetime import datetime
from uuid import uuid4
from flask import Flask, request, redirect, session, send_from_directory, url_for, render_template_string
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
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")  # e.g. Keshava Reddy <onboarding@resend.dev>

db = SQLAlchemy(app)

# ----------------------------------------------------
# STYLE
# ----------------------------------------------------
STYLE = """
<style>
body { font-family: Arial; background:#eef; padding:20px; }
.container { background:white; padding:20px; border-radius:12px; box-shadow:0 0 10px rgba(0,0,0,0.1); max-width:900px; margin:auto; }
button { padding:10px; background:black; color:white; border:none; border-radius:6px; cursor:pointer; margin-top:10px; }
input, textarea, select { width:100%; padding:10px; border:1px solid #ccc; margin-top:5px; border-radius:6px; }
.badge { display:inline-block; padding:6px 10px; background:#ddd; border-radius:6px; margin-right:6px; }
.success { color:green; font-weight:bold; }
.small { font-size:0.9em; color:#555; }
.msg { padding:10px; border-radius:8px; background:#f3f3f3; margin-bottom:10px; }
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

class ProjectMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer)
    user_id = db.Column(db.Integer)

class WeekStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer)
    week_number = db.Column(db.Integer)
    user_id = db.Column(db.Integer)
    action = db.Column(db.String(20))  # 'next' or 'finish'
    clicked_time = db.Column(db.DateTime, default=datetime.utcnow)

class ProjectInvite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer)
    invited_email = db.Column(db.String(200))
    token = db.Column(db.String(64), unique=True)
    created_time = db.Column(db.DateTime, default=datetime.utcnow)
    used = db.Column(db.Boolean, default=False)

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

def notify_members(project_id, subject, body):
    member_rows = ProjectMember.query.filter_by(project_id=project_id).all()
    for m in member_rows:
        u = User.query.get(m.user_id)
        if u and u.email:
            send_email(u.email, subject, body)

# ----------------------------------------------------
# SMALL HELPERS
# ----------------------------------------------------
def project_member_count(pid):
    return ProjectMember.query.filter_by(project_id=pid).count()

def is_project_member(pid, uid):
    return ProjectMember.query.filter_by(project_id=pid, user_id=uid).first() is not None

def add_member_to_project(pid, user_id):
    if not ProjectMember.query.filter_by(project_id=pid, user_id=user_id).first():
        db.session.add(ProjectMember(project_id=pid, user_id=user_id))
        db.session.commit()
        u = User.query.get(user_id)
        if u and u.email:
            send_email(u.email, f"You were added to project", f"Hi {u.name},\n\nYou were added to project (ID: {pid}).")
        # notify existing members
        notify_members(pid, f"New member joined project {pid}", f"{u.name} ({u.email}) joined the project.")
        return True
    return False

# ----------------------------------------------------
# ROUTES (auth + basic)
# ----------------------------------------------------
@app.route("/")
def home():
    return STYLE + logout_btn() + """
    <div class='container'>
        <h2>Team Workspace (Option B + Invites)</h2>
        <a href='/login'><button>Login</button></a>
        <a href='/register'><button>Register</button></a>
        <p>Each project can have its own members. Invite people by email — they can accept via the email link even if not registered yet.</p>
    </div>
"""

@app.route("/register", methods=["GET","POST"])
def register():
    pending_token = session.get("pending_invite_token")
    message = ""
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"].lower()
        pwd = request.form["password"]
        if User.query.filter_by(email=email).first():
            return STYLE + "<script>alert('Email exists');window.location='/register';</script>"
        user = User(name=name, email=email, password=pwd)
        db.session.add(user)
        db.session.commit()
        session["user_id"] = user.id
        session["user_name"] = user.name

        # if there's a pending invite token in session, try to accept it
        token = session.pop("pending_invite_token", None)
        if token:
            inv = ProjectInvite.query.filter_by(token=token, used=False).first()
            if inv and inv.invited_email.lower() == email.lower():
                # add user to project and mark invite used
                add_member_to_project(inv.project_id, user.id)
                inv.used = True
                db.session.commit()
                message = f"Joined project (ID: {inv.project_id}) as part of invite."
        return redirect("/dashboard")

    # GET - show register page
    html = STYLE + logout_btn() + """
    <div class='container'>
        <h2>Register</h2>
        {message_block}
        <form method='POST'>
            <input name='name' placeholder='Name' required>
            <input name='email' placeholder='Email' required>
            <input name='password' type='password' placeholder='Password' required>
            <button>Register</button>
        </form>
        <a href='/login'><button>Login</button></a>
    </div>
    """.format(message_block=f"<div class='msg'>{pending_token and 'You are accepting an invite — after registering you will be added to the project.' or ''}</div>")
    return html

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
            <input name='email' placeholder='Email'>
            <input type='password' name='password' placeholder='Password'>
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
    items = ""
    for p in projects:
        member_count = project_member_count(p.id)
        items += f"<li><a href='/project/{p.id}'>{p.name} (Week {p.current_week}/{p.weeks}) - Members: {member_count}</a></li>"
    return STYLE + logout_btn() + f"""
    <div class='container'>
        <h2>Welcome {session['user_name']}</h2>
        <form method='POST' action='/create_project'>
            <input name='name' placeholder='Project Name' required>
            <input name='weeks' type='number' placeholder='Weeks' required>
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
    # add creator as member by default
    db.session.add(ProjectMember(project_id=p.id, user_id=session["user_id"]))
    db.session.commit()
    return redirect("/dashboard")

@app.route("/project/<int:pid>/add_member", methods=["POST"])
def add_member(pid):
    if "user_id" not in session:
        return redirect("/login")
    # this route is for direct add by email (sends invite)
    email = request.form.get("email","").lower()
    if not email:
        return redirect(f"/project/{pid}")
    # create invite
    token = uuid4().hex
    inv = ProjectInvite(project_id=pid, invited_email=email, token=token)
    db.session.add(inv)
    db.session.commit()

    # send invite email with link
    host = request.host_url.rstrip("/")  # e.g. https://team2-zr3v.onrender.com
    link = f"{host}/join/{token}"
    email_body = f"Hi,\n\nYou have been invited to join project (ID: {pid}). Click the link to accept the invite:\n\n{link}\n\nIf you don't have an account, register first using the same email and the invite will be attached automatically when you register."
    send_email(email, f"Invitation to join project {pid}", email_body)

    return redirect(f"/project/{pid}")

@app.route("/download/<path:f>")
def download(f):
    return send_from_directory(app.config["UPLOAD_FOLDER"], f, as_attachment=True)

# ----------------------------------------------------
# JOIN / INVITE ACCEPT
# ----------------------------------------------------
@app.route("/join/<token>")
def join_by_token(token):
    # token click handler
    inv = ProjectInvite.query.filter_by(token=token).first()
    if not inv:
        return STYLE + "<div class='container'><p>Invalid or expired invite token.</p><a href='/'>Home</a></div>"

    # if already used and user is logged in but not member, allow re-add? we'll treat used invites as still acceptable for adding if not used:
    # if invite already used, we still allow adding by matching email to user.
    # Find user by email
    u = User.query.filter_by(email=inv.invited_email.lower()).first()
    if u:
        # add them immediately if not member
        added = add_member_to_project(inv.project_id, u.id)
        inv.used = True
        db.session.commit()
        msg = "You have been added to the project." if added else "You are already a member."
        return STYLE + logout_btn() + f"<div class='container'><p>{msg}</p><a href='/project/{inv.project_id}'>Go to project</a></div>"

    # not registered - store token in session and redirect to register
    session["pending_invite_token"] = token
    return redirect("/register")

# ----------------------------------------------------
# PROJECT PAGE + UPLOADS + NEXT/FINISH logic
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
        notify_members(pid, f"New upload in {p.name}", f"{session['user_name']} uploaded {f.filename}")
        return redirect(f"/project/{pid}")

    # lists
    uploads = Upload.query.filter_by(project_id=pid, week_number=p.current_week).all()
    files = "".join(f"<div>{u.file_name} — <a href='/download/{u.file_name}'>Download</a></div>" for u in uploads)

    uid = session["user_id"]
    is_member = is_project_member(pid, uid)
    members = ProjectMember.query.filter_by(project_id=pid).all()
    member_count = len(members)
    member_list_html = ""
    for m in members:
        u = User.query.get(m.user_id)
        member_list_html += f"<div>{u.name} — {u.email}</div>"

    next_clicked = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, user_id=uid, action='next').first() is not None
    finish_clicked = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, user_id=uid, action='finish').first() is not None

    next_count = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, action='next').count()
    finish_count = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, action='finish').count()

    show_join_ui = False
    if is_member:
        show_join_ui = True

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
            <span class='badge'>Next clicked: {next_count}/{member_count}</span>
            <span class='badge'>Finish clicked: {finish_count}/{member_count}</span>
        </div>
        <hr/>
        <h4>Members</h4>
        {member_list_html}
        {"<div style='margin-top:8px;'><form method='POST' action='/project/"+str(pid)+"/add_member'><input name='email' placeholder='Member email to invite' required><button>Invite Member</button></form></div>" if show_join_ui else "<p class='small'>Only project members can invite others.</p>"}
        <hr/>
        {files}
        <form method='POST' enctype='multipart/form-data'>
            <input type='file' name='file'>
            <textarea name='description' placeholder='Description'></textarea>
            <button>Upload</button>
        </form>
        <div style='margin-top:12px;'>
            {("<form method='POST' action='/project/"+str(pid)+"/click_next'><button>Go to Next Week</button></form>" if not next_clicked and is_member else "<div style='margin-top:8px;'>You already clicked Next or you are not a member.</div>")}
            {("<form method='POST' action='/project/"+str(pid)+"/click_finish'><button>Finish Project</button></form>" if (p.current_week==p.weeks and not finish_clicked and is_member) else "")}
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
    if not is_project_member(pid, uid):
        return redirect(f"/project/{pid}")
    existing = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, user_id=uid, action='next').first()
    if existing:
        return redirect(f"/project/{pid}")
    ws = WeekStatus(project_id=pid, week_number=p.current_week, user_id=uid, action='next')
    db.session.add(ws)
    db.session.commit()
    notify_members(pid, f"{session['user_name']} clicked Go to Next Week", f"{session['user_name']} clicked Go to Next Week for project {p.name} (Week {p.current_week}).")
    members = ProjectMember.query.filter_by(project_id=pid).all()
    member_count = len(members)
    next_count = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, action='next').count()
    if next_count >= member_count and member_count > 0:
        if p.current_week < p.weeks:
            p.current_week += 1
            db.session.commit()
            notify_members(pid, f"Project {p.name} advanced to Week {p.current_week}", f"All members clicked Next. Project {p.name} is now at Week {p.current_week}.")
    return redirect(f"/project/{pid}")

@app.route("/project/<int:pid>/click_finish", methods=["POST"])
def click_finish(pid):
    if "user_id" not in session:
        return redirect("/login")
    p = Project.query.get(pid)
    if not p or p.completed:
        return redirect(f"/project/{pid}")
    uid = session["user_id"]
    if not is_project_member(pid, uid):
        return redirect(f"/project/{pid}")
    existing = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, user_id=uid, action='finish').first()
    if existing:
        return redirect(f"/project/{pid}")
    ws = WeekStatus(project_id=pid, week_number=p.current_week, user_id=uid, action='finish')
    db.session.add(ws)
    db.session.commit()
    notify_members(pid, f"{session['user_name']} clicked Finish", f"{session['user_name']} clicked Finish on project {p.name} (Week {p.current_week}).")
    members = ProjectMember.query.filter_by(project_id=pid).all()
    member_count = len(members)
    finish_count = WeekStatus.query.filter_by(project_id=pid, week_number=p.current_week, action='finish').count()
    if finish_count >= member_count and member_count > 0:
        p.completed = True
        p.completed_time = datetime.utcnow()
        db.session.commit()
        notify_members(pid, f"Project {p.name} — Completed", f"Congratulations! Project {p.name} has been completed by all members.")
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
