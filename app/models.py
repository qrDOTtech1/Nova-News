from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class NewsItem(db.Model):
    __tablename__ = "news_item"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_region = db.Column(db.String(10), nullable=False)  # FR, PT, GLOBAL
    category = db.Column(db.String(50), nullable=False)  # AUTO, FINANCE, TECH, GENERAL
    raw_title = db.Column(db.Text, nullable=False)

    ai_summary = db.Column(db.JSON, nullable=True)  # ["Point 1", "Point 2"]
    illustration_url = db.Column(db.Text, nullable=True)
    trust_score = db.Column(db.Float, default=1.0)
    linked_apps = db.Column(db.JSON, default=[])  # ["NovaAuto", "NovaFact", "NovaContab"]

    full_text = db.Column(db.Text, nullable=True)
    source_url = db.Column(db.Text, unique=True, nullable=False)

    published_at = db.Column(db.DateTime, nullable=True)
    processed_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "source_region": self.source_region,
            "category": self.category,
            "raw_title": self.raw_title,
            "ai_summary": self.ai_summary or [],
            "illustration_url": self.illustration_url,
            "trust_score": self.trust_score,
            "linked_apps": self.linked_apps or [],
            "source_url": self.source_url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "processed_at": self.processed_at.isoformat(),
        }


class User(db.Model):
    __tablename__ = "nn_user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    onboarded = db.Column(db.Boolean, default=False)

    preferences = db.relationship("UserPreferences", backref="user", uselist=False, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class UserPreferences(db.Model):
    __tablename__ = "nn_user_prefs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("nn_user.id"), unique=True, nullable=False)
    topics = db.Column(db.JSON, default=list)     # ["TECH","FINANCE","SPORT","SCIENCE","AUTO","CRYPTO","POLITIQUE","CULTURE","SANTE","GAMING","IA"]
    regions = db.Column(db.JSON, default=list)    # ["FR","PT","GLOBAL"]
    bookmarks = db.Column(db.JSON, default=list)  # list of article IDs (strings)
