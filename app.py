import os
import re
import uuid
from datetime import timedelta
from functools import wraps

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_socketio import SocketIO, emit
from flask_socketio import join_room
from sqlalchemy import or_, text
from werkzeug.utils import secure_filename

from models import Message, SharedFile, User, db, utc_now


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "pdf", "txt", "doc", "docx"}
ALLOWED_MIME_PREFIXES = ("image/",)
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
MAX_CONTENT_LENGTH = 8 * 1024 * 1024


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-change-this-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "database.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*")

connected_users = {}
http_online_users = {}
typing_users = set()


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)


def valid_username(username):
    return bool(re.fullmatch(r"[A-Za-z0-9_]{3,30}", username or ""))


def allowed_file(filename, mimetype):
    if "." not in filename:
        return False
    extension = filename.rsplit(".", 1)[1].lower()
    type_allowed = mimetype in ALLOWED_MIME_TYPES or mimetype.startswith(ALLOWED_MIME_PREFIXES)
    return extension in ALLOWED_EXTENSIONS and type_allowed


def message_payload(message):
    payload = message.to_dict()
    if message.shared_file:
        payload["file"] = message.shared_file.to_dict()
    return payload


def private_room(user_id):
    return f"user:{user_id}"


def can_view_message(user, message):
    return message.user_id == user.id or message.recipient_id == user.id


def conversation_query(user_id, other_user_id):
    return Message.query.filter(
        or_(
            (Message.user_id == user_id) & (Message.recipient_id == other_user_id),
            (Message.user_id == other_user_id) & (Message.recipient_id == user_id),
        )
    )


def online_user_payload():
    cutoff = utc_now() - timedelta(seconds=30)
    stale_user_ids = [user_id for user_id, seen_at in http_online_users.items() if seen_at < cutoff]
    for user_id in stale_user_ids:
        http_online_users.pop(user_id, None)

    user_ids = set(connected_users.keys()) | set(http_online_users.keys())
    users = User.query.filter(User.id.in_(user_ids)).order_by(User.username.asc()).all() if user_ids else []
    return [user.to_public_dict() for user in users]


@app.before_request
def make_session_permanent():
    session.permanent = True


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("chat"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        profile_picture = request.files.get("profile_picture")

        if not valid_username(username):
            flash("Username must be 3-30 characters and use only letters, numbers, or underscores.", "danger")
            return render_template("register.html")
        if not email or "@" not in email:
            flash("Please enter a valid email address.", "danger")
            return render_template("register.html")
        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "danger")
            return render_template("register.html")
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")
        if User.query.filter(or_(User.username == username, User.email == email)).first():
            flash("That username or email is already registered.", "danger")
            return render_template("register.html")

        picture_name = None
        if profile_picture and profile_picture.filename:
            if not allowed_file(profile_picture.filename, profile_picture.mimetype) or not profile_picture.mimetype.startswith("image/"):
                flash("Profile picture must be a valid image file.", "danger")
                return render_template("register.html")
            safe_name = secure_filename(profile_picture.filename)
            picture_name = f"profile_{uuid.uuid4().hex}_{safe_name}"
            profile_picture.save(os.path.join(app.config["UPLOAD_FOLDER"], picture_name))

        user = User(username=username, email=email, profile_picture=picture_name)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identity = request.form.get("identity", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter(or_(User.username == identity, User.email == identity.lower())).first()

        if user and user.check_password(password):
            session.clear()
            session["user_id"] = user.id
            session["username"] = user.username
            return redirect(url_for("chat"))

        flash("Invalid username/email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    user = current_user()
    if user:
        connected_users.pop(user.id, None)
        http_online_users.pop(user.id, None)
        socketio.emit("online_users", online_user_payload())
        socketio.emit("system_message", {"message": f"{user.username} left the chat."})
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


@app.route("/chat")
@login_required
def chat():
    user = current_user()
    users = User.query.filter(User.id != user.id).order_by(User.username.asc()).all()
    return render_template(
        "chat.html",
        user=user,
        users=[chat_user.to_public_dict() for chat_user in users],
        messages=[],
    )


@app.route("/api/users")
@login_required
def api_users():
    user = current_user()
    users = User.query.filter(User.id != user.id).order_by(User.username.asc()).all()
    return jsonify([chat_user.to_public_dict() for chat_user in users])


@app.route("/api/online")
@login_required
def api_online_users():
    return jsonify(online_user_payload())


@app.route("/api/heartbeat", methods=["POST"])
@login_required
def api_heartbeat():
    user = current_user()
    http_online_users[user.id] = utc_now()
    return jsonify({"online_users": online_user_payload()})


@app.route("/api/messages", methods=["GET"])
@login_required
def api_get_messages():
    user = current_user()
    other_user_id = request.args.get("user_id", type=int)
    after_id = request.args.get("after_id", 0, type=int)
    if not other_user_id or other_user_id == user.id:
        return jsonify([])

    messages = (
        conversation_query(user.id, other_user_id)
        .filter(Message.id > after_id)
        .order_by(Message.created_at.asc())
        .limit(100)
        .all()
    )
    return jsonify([message_payload(message) for message in messages])


@app.route("/messages/search")
@login_required
def search_messages():
    user = current_user()
    query = request.args.get("q", "").strip()
    other_user_id = request.args.get("user_id", type=int)
    if not query:
        return jsonify([])
    if not other_user_id:
        return jsonify([])
    matches = (
        conversation_query(user.id, other_user_id)
        .join(User, Message.user_id == User.id)
        .filter(or_(Message.content.ilike(f"%{query}%"), User.username.ilike(f"%{query}%")))
        .order_by(Message.created_at.desc())
        .limit(30)
        .all()
    )
    return jsonify([message_payload(message) for message in matches])


@app.route("/upload", methods=["POST"])
@login_required
def upload_file():
    user = current_user()
    uploaded_file = request.files.get("file")
    caption = request.form.get("caption", "").strip()
    recipient_id = request.form.get("recipient_id", type=int)

    recipient = db.session.get(User, recipient_id) if recipient_id else None
    if not recipient or recipient.id == user.id:
        return jsonify({"error": "Please select a valid user before sharing a file."}), 400
    if not uploaded_file or not uploaded_file.filename:
        return jsonify({"error": "No file selected."}), 400
    if not allowed_file(uploaded_file.filename, uploaded_file.mimetype):
        return jsonify({"error": "Unsupported file type."}), 400

    safe_name = secure_filename(uploaded_file.filename)
    stored_name = f"{uuid.uuid4().hex}_{safe_name}"
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], stored_name)
    uploaded_file.save(file_path)

    content = caption or f"Shared a file: {safe_name}"
    message = Message(content=content, sender=user, recipient=recipient)
    db.session.add(message)
    db.session.flush()

    shared_file = SharedFile(
        original_filename=safe_name,
        stored_filename=stored_name,
        file_type=uploaded_file.mimetype,
        file_size=os.path.getsize(file_path),
        uploader=user,
        message=message,
    )
    db.session.add(shared_file)
    db.session.commit()

    payload = message_payload(message)
    socketio.emit("new_message", payload, to=private_room(user.id))
    socketio.emit("new_message", payload, to=private_room(recipient.id))
    return jsonify(payload), 201


@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/download/<int:file_id>")
@login_required
def download_file(file_id):
    shared_file = db.session.get(SharedFile, file_id)
    if not shared_file:
        abort(404)
    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        shared_file.stored_filename,
        as_attachment=True,
        download_name=shared_file.original_filename,
    )


@socketio.on("connect")
def handle_connect():
    user = current_user()
    if not user:
        return False
    connected_users.setdefault(user.id, set()).add(request.sid)
    join_room(private_room(user.id))
    emit("online_users", online_user_payload(), broadcast=True)
    emit("system_message", {"message": f"{user.username} joined the chat."}, broadcast=True)


@socketio.on("disconnect")
def handle_disconnect():
    user = current_user()
    if user:
        user_sids = connected_users.get(user.id, set())
        user_sids.discard(request.sid)
        if not user_sids:
            connected_users.pop(user.id, None)
        typing_users.discard(user.username)
        emit("online_users", online_user_payload(), broadcast=True)
        emit("typing_users", list(typing_users), broadcast=True)
        emit("system_message", {"message": f"{user.username} left the chat."}, broadcast=True)


@socketio.on("send_message")
def handle_send_message(data):
    user = current_user()
    if not user:
        return
    content = str(data.get("content", "")).strip()
    recipient_id = data.get("recipient_id")
    recipient = db.session.get(User, recipient_id) if recipient_id else None
    if not content or len(content) > 1000:
        emit("message_error", {"error": "Message must be between 1 and 1000 characters."})
        return
    if not recipient or recipient.id == user.id:
        emit("message_error", {"error": "Please select a valid user before sending."})
        return

    message = Message(content=content, sender=user, recipient=recipient)
    db.session.add(message)
    db.session.commit()
    payload = message_payload(message)
    emit("new_message", payload, to=private_room(user.id))
    emit("new_message", payload, to=private_room(recipient.id))


@app.route("/api/messages", methods=["POST"])
@login_required
def api_send_message():
    user = current_user()
    content = str(request.json.get("content", "") if request.is_json else "").strip()
    recipient_id = request.json.get("recipient_id") if request.is_json else None
    recipient = db.session.get(User, recipient_id) if recipient_id else None
    if not content or len(content) > 1000:
        return jsonify({"error": "Message must be between 1 and 1000 characters."}), 400
    if not recipient or recipient.id == user.id:
        return jsonify({"error": "Please select a valid user before sending."}), 400

    message = Message(content=content, sender=user, recipient=recipient)
    db.session.add(message)
    db.session.commit()
    payload = message_payload(message)
    socketio.emit("new_message", payload, to=private_room(user.id))
    socketio.emit("new_message", payload, to=private_room(recipient.id))
    return jsonify(payload), 201


@socketio.on("typing")
def handle_typing(data):
    user = current_user()
    if not user:
        return
    is_typing = bool(data.get("typing"))
    recipient_id = data.get("recipient_id")
    recipient = db.session.get(User, recipient_id) if recipient_id else None
    if not recipient or recipient.id == user.id:
        return
    emit(
        "typing_users",
        {"from_id": user.id, "typing": is_typing},
        to=private_room(recipient.id),
        include_self=False,
    )


@socketio.on("message_read")
def handle_message_read(data):
    user = current_user()
    message_id = data.get("message_id")
    message = db.session.get(Message, message_id)
    if user and message and can_view_message(user, message) and message.user_id != user.id and not message.read_at:
        message.read_at = utc_now()
        db.session.commit()
        emit("message_read", {"message_id": message.id}, to=private_room(message.user_id))


def migrate_database():
    with app.app_context():
        columns = [row[1] for row in db.session.execute(text("PRAGMA table_info(messages)")).all()]
        if "recipient_id" not in columns:
            db.session.execute(text("ALTER TABLE messages ADD COLUMN recipient_id INTEGER"))
            db.session.commit()


@app.errorhandler(413)
def file_too_large(_error):
    return jsonify({"error": "File is too large. Maximum size is 8 MB."}), 413


def initialize_database():
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    with app.app_context():
        db.create_all()
    migrate_database()


initialize_database()


if __name__ == "__main__":
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)