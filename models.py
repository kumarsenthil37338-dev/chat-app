from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


db = SQLAlchemy()


def utc_now():
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    profile_picture = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    messages = db.relationship(
        "Message",
        foreign_keys="Message.user_id",
        back_populates="sender",
        lazy=True
    )

    received_messages = db.relationship(
        "Message",
        foreign_keys="Message.recipient_id",
        back_populates="recipient",
        lazy=True
    )

    files = db.relationship("SharedFile", back_populates="uploader", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_public_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "profile_picture": self.profile_picture,
        }


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    read_at = db.Column(db.DateTime(timezone=True), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

    sender = db.relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="messages"
    )

    recipient = db.relationship(
        "User",
        foreign_keys=[recipient_id],
        back_populates="received_messages"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "content": self.content,
            "timestamp": self.created_at.strftime("%Y-%m-%d %H:%M"),
            "read": self.read_at is not None,
            "sender": self.sender.to_public_dict(),
            "recipient": self.recipient.to_public_dict() if self.recipient else None,
            "file": None,
        }


class SharedFile(db.Model):
    __tablename__ = "files"

    id = db.Column(db.Integer, primary_key=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(80), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    uploaded_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    message_id = db.Column(db.Integer, db.ForeignKey("messages.id"), nullable=True)

    uploader = db.relationship("User", back_populates="files")
    message = db.relationship("Message", backref=db.backref("shared_file", uselist=False))

    def to_dict(self):
        return {
            "id": self.id,
            "original_filename": self.original_filename,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "download_url": f"/download/{self.id}",
            "preview_url": f"/uploads/{self.stored_filename}",
            "is_image": self.file_type.startswith("image/"),
        }
