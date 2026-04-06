import os
import logging
from pathlib import Path
from datetime import datetime
from functools import wraps
from threading import Thread

from flask import (
    Flask, jsonify, request, session, render_template,
    redirect, url_for, flash
)
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

from app.models import db, NewsItem, User, UserPreferences

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = Flask(__name__)
_db_url = os.environ.get("DATABASE_URL", "sqlite:///novanews.db")
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = _db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "nova-dev-secret-change-in-prod")

db.init_app(app)

INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "nova-internal-key-change-in-prod")


# ─── DB Init ──────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()


# ─── Auth Helpers ─────────────────────────────────────────────────────────────

def current_user():
    user_id = session.get("user_id")
    if user_id:
        return User.query.get(user_id)
    return None


def require_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user():
            flash("Veuillez vous connecter pour accéder à cette page.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def require_internal_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-Internal-Key")
        if not key or key != INTERNAL_API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# ─── Public Routes ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    user = current_user()
    if user:
        if user.onboarded:
            return redirect(url_for("feed"))
        return redirect(url_for("onboarding"))
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user():
        return redirect(url_for("feed"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        error = None
        if not username or not email or not password:
            error = "Tous les champs sont requis."
        elif len(username) < 3:
            error = "Le nom d'utilisateur doit contenir au moins 3 caractères."
        elif len(password) < 6:
            error = "Le mot de passe doit contenir au moins 6 caractères."
        elif User.query.filter_by(username=username).first():
            error = "Ce nom d'utilisateur est déjà pris."
        elif User.query.filter_by(email=email).first():
            error = "Cet email est déjà utilisé."

        if error:
            flash(error, "danger")
            return render_template("register.html", username=username, email=email)

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        session["user_id"] = user.id
        flash(f"Bienvenue, {username} ! Personnalisez votre flux.", "success")
        return redirect(url_for("onboarding"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("feed"))

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter(
            (User.email == identifier.lower()) | (User.username == identifier)
        ).first()

        if not user or not user.check_password(password):
            flash("Identifiant ou mot de passe incorrect.", "danger")
            return render_template("login.html", identifier=identifier)

        session["user_id"] = user.id
        flash(f"Bon retour, {user.username} !", "success")

        if not user.onboarded:
            return redirect(url_for("onboarding"))
        return redirect(url_for("feed"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Vous avez été déconnecté.", "info")
    return redirect(url_for("index"))


# ─── Onboarding ───────────────────────────────────────────────────────────────

@app.route("/onboarding", methods=["GET", "POST"])
@require_login
def onboarding():
    user = current_user()

    if request.method == "POST":
        topics = request.form.getlist("topics")
        regions = request.form.getlist("regions")

        if not topics:
            flash("Sélectionnez au moins un sujet.", "warning")
            return render_template("onboarding.html", user=user)

        if not regions:
            regions = ["GLOBAL"]

        prefs = UserPreferences.query.filter_by(user_id=user.id).first()
        if not prefs:
            prefs = UserPreferences(user_id=user.id)
            db.session.add(prefs)

        prefs.topics = topics
        prefs.regions = regions
        if prefs.bookmarks is None:
            prefs.bookmarks = []

        user.onboarded = True
        db.session.commit()

        flash("Votre flux est prêt !", "success")
        return redirect(url_for("feed"))

    return render_template("onboarding.html", user=user)


# ─── Feed ─────────────────────────────────────────────────────────────────────

@app.route("/feed")
@require_login
def feed():
    user = current_user()
    prefs = UserPreferences.query.filter_by(user_id=user.id).first()
    topics = prefs.topics if prefs else []
    regions = prefs.regions if prefs else []
    bookmarks = prefs.bookmarks if prefs else []

    sections = {}
    for topic in topics:
        q = NewsItem.query
        if regions:
            q = q.filter(NewsItem.source_region.in_(regions + ["GLOBAL"]))
        q = q.filter_by(category=topic).order_by(NewsItem.published_at.desc()).limit(6)
        articles = q.all()
        if articles:
            sections[topic] = articles

    featured = (
        NewsItem.query
        .order_by(NewsItem.trust_score.desc(), NewsItem.published_at.desc())
        .first()
    )

    latest = (
        NewsItem.query
        .order_by(NewsItem.published_at.desc())
        .limit(6)
        .all()
    )

    must_read = (
        NewsItem.query
        .filter(NewsItem.trust_score >= 0.8)
        .order_by(NewsItem.trust_score.desc(), NewsItem.published_at.desc())
        .limit(5)
        .all()
    )

    now = datetime.utcnow()
    return render_template(
        "feed.html",
        user=user,
        sections=sections,
        featured=featured,
        latest=latest,
        must_read=must_read,
        bookmarks=bookmarks,
        now=now,
    )


# ─── Article Detail ───────────────────────────────────────────────────────────

@app.route("/article/<article_id>")
@require_login
def article(article_id):
    user = current_user()
    item = NewsItem.query.get_or_404(article_id)
    prefs = UserPreferences.query.filter_by(user_id=user.id).first()
    bookmarks = prefs.bookmarks if prefs else []
    now = datetime.utcnow()
    return render_template("article.html", user=user, article=item, bookmarks=bookmarks, now=now)


# ─── Bookmark ─────────────────────────────────────────────────────────────────

@app.route("/api/bookmark/<article_id>", methods=["POST"])
@require_login
def toggle_bookmark(article_id):
    user = current_user()
    prefs = UserPreferences.query.filter_by(user_id=user.id).first()
    if not prefs:
        prefs = UserPreferences(user_id=user.id, topics=[], regions=[], bookmarks=[])
        db.session.add(prefs)

    bookmarks = list(prefs.bookmarks or [])
    if article_id in bookmarks:
        bookmarks.remove(article_id)
        bookmarked = False
    else:
        bookmarks.append(article_id)
        bookmarked = True

    prefs.bookmarks = bookmarks
    db.session.commit()
    return jsonify({"bookmarked": bookmarked, "count": len(bookmarks)})


# ─── Search ───────────────────────────────────────────────────────────────────

@app.route("/search")
@require_login
def search():
    user = current_user()
    q = request.args.get("q", "").strip()
    results = []
    if q:
        like = f"%{q}%"
        results = (
            NewsItem.query
            .filter(
                db.or_(
                    NewsItem.raw_title.ilike(like),
                    NewsItem.full_text.ilike(like),
                )
            )
            .order_by(NewsItem.published_at.desc())
            .limit(30)
            .all()
        )
    prefs = UserPreferences.query.filter_by(user_id=user.id).first()
    bookmarks = prefs.bookmarks if prefs else []
    now = datetime.utcnow()
    return render_template("search.html", user=user, query=q, results=results, bookmarks=bookmarks, now=now)


# ─── Settings ─────────────────────────────────────────────────────────────────

@app.route("/settings", methods=["GET", "POST"])
@require_login
def settings():
    user = current_user()
    prefs = UserPreferences.query.filter_by(user_id=user.id).first()

    if request.method == "POST":
        topics = request.form.getlist("topics")
        regions = request.form.getlist("regions")

        if not topics:
            flash("Sélectionnez au moins un sujet.", "warning")
            return render_template("settings.html", user=user, prefs=prefs)

        if not regions:
            regions = ["GLOBAL"]

        if not prefs:
            prefs = UserPreferences(user_id=user.id)
            db.session.add(prefs)

        prefs.topics = topics
        prefs.regions = regions
        db.session.commit()

        flash("Préférences sauvegardées !", "success")
        return redirect(url_for("feed"))

    return render_template("settings.html", user=user, prefs=prefs)


# ─── API Routes (internal) ────────────────────────────────────────────────────

@app.route("/api/news", methods=["GET"])
def get_news():
    region = request.args.get("region")
    category = request.args.get("category")
    linked_app = request.args.get("linked_app")
    limit = int(request.args.get("limit", 20))

    query = NewsItem.query

    if region:
        query = query.filter_by(source_region=region.upper())
    if category:
        query = query.filter_by(category=category.upper())

    news_list = query.order_by(NewsItem.published_at.desc()).limit(limit).all()

    results = [n.to_dict() for n in news_list]
    if linked_app:
        results = [n for n in results if linked_app in n.get("linked_apps", [])]

    return jsonify(results)


@app.route("/api/ingest", methods=["POST"])
@require_internal_key
def trigger_ingestion():
    from app.ingestion_engine import ingest_and_enrich

    def run_job(app_context):
        with app_context:
            try:
                ingest_and_enrich()
            except Exception as e:
                app.logger.error(f"Erreur fatale lors de l'ingestion: {e}")

    Thread(target=run_job, args=(app.app_context(),)).start()
    return jsonify({"status": "Ingestion démarrée en arrière-plan."})


# ─── Background Auto-Ingestion ────────────────────────────────────────────────

def start_auto_ingestion():
    import time
    from app.ingestion_engine import ingest_and_enrich

    def loop():
        with app.app_context():
            while True:
                try:
                    app.logger.info("[AutoIngest] Lancement de l'ingestion automatique...")
                    ingest_and_enrich()
                except Exception as e:
                    app.logger.error(f"[AutoIngest] Erreur: {e}")
                time.sleep(1800)

    t = Thread(target=loop, daemon=True)
    t.start()
    app.logger.info("[AutoIngest] Thread démarré (intervalle: 30min).")


if os.environ.get("AUTO_INGEST", "false").lower() == "true":
    with app.app_context():
        start_auto_ingestion()
