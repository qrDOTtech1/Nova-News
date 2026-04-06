import os
import time
import logging
import feedparser
from datetime import datetime
from email.utils import parsedate_to_datetime

from trafilatura import fetch_url, extract
from tavily import TavilyClient

from app.models import db, NewsItem
from app.ai_processor import process_news_ai
from app.nova_bridge import route_news_to_apps

logger = logging.getLogger(__name__)

SOURCES = {
    "FR": [
        {"url": "https://www.lemonde.fr/rss/une.xml", "category": "GENERAL"},
        {"url": "https://www.lemonde.fr/sciences/rss_full.xml", "category": "SCIENCE"},
        {"url": "https://www.lefigaro.fr/rss/figaro_actualites.xml", "category": "GENERAL"},
        {"url": "https://investir.lesechos.fr/rss/les-plus-lus.xml", "category": "FINANCE"},
        {"url": "https://www.capital.fr/feed", "category": "FINANCE"},
        {"url": "https://www.numerama.com/feed/", "category": "TECH"},
        {"url": "https://www.lequipe.fr/rss/actu_rss.xml", "category": "SPORT"},
        {"url": "https://www.autoplus.fr/feed", "category": "AUTO"},
        {"url": "https://www.lefigaro.fr/sante/rss_actualites.xml", "category": "SANTE"},
    ],
    "PT": [
        {"url": "https://feeds.feedburner.com/PublicoRSS", "category": "GENERAL"},
        {"url": "https://eco.sapo.pt/feed/", "category": "FINANCE"},
        {"url": "https://shifter.pt/feed/", "category": "TECH"},
        {"url": "https://www.razaoautomovel.com/feed/", "category": "AUTO"},
    ],
    "GLOBAL": [
        {"url": "https://techcrunch.com/feed/", "category": "TECH"},
        {"url": "https://feeds.bbci.co.uk/news/world/rss.xml", "category": "GENERAL"},
        {"url": "https://feeds.bbci.co.uk/sport/rss.xml", "category": "SPORT"},
        {"url": "https://coindesk.com/arc/outboundfeeds/rss/", "category": "CRYPTO"},
        {"url": "https://decrypt.co/feed", "category": "CRYPTO"},
        {"url": "https://www.nasa.gov/feed/", "category": "SCIENCE"},
        {"url": "https://feeds.ign.com/ign/all", "category": "GAMING"},
        {"url": "https://www.theverge.com/rss/index.xml", "category": "TECH"},
        {"url": "https://www.wired.com/feed/rss", "category": "TECH"},
    ],
}


def ingest_and_enrich():
    """Moteur principal d'ingestion des flux RSS."""
    logger.info("Lancement de l'ingestion NovaNews...")

    tavily_api_key = os.environ.get("TAVILY_API_KEY", "")
    tavily = TavilyClient(api_key=tavily_api_key) if tavily_api_key else None

    if not tavily:
        logger.warning("[Ingestion] Clé API Tavily absente, enrichissement désactivé.")

    for region, feeds in SOURCES.items():
        for source in feeds:
            feed_url = source["url"]
            category = source["category"]

            logger.info(f"Lecture flux [{region}] {feed_url}...")
            try:
                parsed_feed = feedparser.parse(feed_url)
            except Exception as e:
                logger.error(f"[Ingestion] Erreur parsing flux {feed_url}: {e}")
                continue

            # Limite à 5 articles par flux (performance)
            for entry in parsed_feed.entries[:5]:
                # Vérifier si l'article existe déjà en DB
                existing = NewsItem.query.filter_by(source_url=entry.link).first()
                if existing:
                    continue

                logger.info(f"-> Traitement : {entry.title}")

                # 1. Extraction du texte brut (SOTA Cleaning)
                try:
                    downloaded = fetch_url(entry.link)
                    clean_content = extract(downloaded) if downloaded else ""
                except Exception as e:
                    logger.warning(f"[Trafilatura] Erreur extraction {entry.link}: {e}")
                    clean_content = ""

                if not clean_content:
                    logger.warning(f"Impossible d'extraire le contenu pour {entry.link}")
                    clean_content = entry.get("summary", "Contenu indisponible.")

                # 2. Enrichissement via Tavily (Recherche de contexte + IMAGES)
                context_snippets = []
                illustration_url = None
                if tavily:
                    try:
                        search_query = f"{entry.title} {region}"
                        context = tavily.search(
                            query=search_query,
                            search_depth="advanced",
                            include_images=True,
                            max_results=3,
                        )
                        context_snippets = [r["content"] for r in context.get("results", [])]
                        if context.get("images"):
                            illustration_url = context["images"][0]
                    except Exception as e:
                        logger.error(f"[Tavily] Erreur lors de la recherche : {e}")

                # 3. Analyse via le LLM de NovaAdmin (Orchestrateur)
                ai_data = process_news_ai(clean_content, context_snippets)
                ai_summary = ai_data.get("ai_summary", ["Résumé en cours..."])
                tags = ai_data.get("tags", [])
                trust_score = ai_data.get("trust_score", 0.5)

                # Date publication
                pub_date = datetime.utcnow()
                if hasattr(entry, "published"):
                    try:
                        pub_date = parsedate_to_datetime(entry.published)
                    except Exception:
                        pass

                # Création de l'objet temporaire pour le bridge
                news_data_temp = {
                    "source_region": region,
                    "category": category,
                    "raw_title": entry.title,
                    "trust_score": trust_score,
                }

                # 4. Synergy avec l'écosystème (Nova-Bridge)
                linked_apps = route_news_to_apps(news_data_temp, tags)

                # 5. Enregistrement DB
                news_item = NewsItem(
                    source_region=region,
                    category=category,
                    raw_title=entry.title,
                    ai_summary=ai_summary,
                    illustration_url=illustration_url,
                    trust_score=trust_score,
                    linked_apps=linked_apps,
                    full_text=clean_content,
                    source_url=entry.link,
                    published_at=pub_date,
                )

                db.session.add(news_item)
                try:
                    db.session.commit()
                    logger.info(f"News ajoutée : {entry.title[:50]}...")
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"[DB] Erreur commit: {e}")

                # Attente pour ne pas spammer les API
                time.sleep(2)

    logger.info("Ingestion NovaNews terminée.")
