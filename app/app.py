import os
from pathlib import Path
from flask import Flask, jsonify, request
from threading import Thread
from functools import wraps

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

from app.models import db, NewsItem
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///novanews.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)


@app.before_request
def create_tables():
    app.before_request_funcs[None].remove(create_tables)
    db.create_all()


# Sécurité interne pour déclencher l'ingestion
INTERNAL_API_KEY = os.environ.get(
    "INTERNAL_API_KEY", "nova-internal-key-change-in-prod"
)


def require_internal_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-Internal-Key")
        if not key or key != INTERNAL_API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)

    return decorated


@app.route("/api/news", methods=["GET"])
def get_news():
    """
    API publique/interne pour récupérer les actualités.
    Filtres supportés: region (FR, PT), category (AUTO, FINANCE...), linked_app (NovaFact...)
    """
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

    # Filtre manuel pour le JSON (SQLite JSON est complexe à requêter nativement sans dialecte spécifique)
    results = [n.to_dict() for n in news_list]
    if linked_app:
        results = [n for n in results if linked_app in n.get("linked_apps", [])]

    return jsonify(results)


@app.route("/api/ingest", methods=["POST"])
@require_internal_key
def trigger_ingestion():
    """
    Déclenche le moteur d'ingestion en arrière-plan (feedparser -> trafilatura -> tavily -> AI -> BD).
    Peut être appelé par un cron externe (ex: Railway Cron).
    """
    from app.ingestion_engine import ingest_and_enrich

    def run_job(app_context):
        with app_context:
            try:
                ingest_and_enrich()
            except Exception as e:
                app.logger.error(f"Erreur fatale lors de l'ingestion: {e}")

    # Lancement dans un thread séparé pour ne pas bloquer la requête
    Thread(target=run_job, args=(app.app_context(),)).start()
    return jsonify({"status": "Ingestion démarrée en arrière-plan."})
