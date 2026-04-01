import logging

logger = logging.getLogger(__name__)


def route_news_to_apps(news_data: dict, tags: list) -> list:
    """
    Fonction "Nova-Bridge"
    Détermine quelles applications de l'écosystème doivent être notifiées de cette nouvelle,
    basé sur les tags et le score de confiance extraits par l'IA.
    Retourne la liste des noms d'applications.
    """
    linked_apps = []
    tags_upper = [t.upper() for t in tags]

    # 1. Alimentation de NovaContab (L'assistant business)
    compta_keywords = [
        "TVA",
        "IMPOTS",
        "LOI",
        "FINANCE",
        "TAXE",
        "SUBVENTION",
        "ENTREPRISE",
    ]
    if (
        any(k in tags_upper for k in compta_keywords)
        or news_data.get("category") == "FINANCE"
    ):
        linked_apps.append("NovaContab")
        # En production : requests.post("https://novacontab.../api/webhook/news", json=news_data)
        logger.info(f"[BRIDGE] ➡️ Push vers NovaContab: '{news_data.get('raw_title')}'")

    # 2. Alimentation de NovaAuto (Le futur)
    auto_keywords = [
        "RAPPEL",
        "MOTEUR",
        "CRASH-TEST",
        "VEHICULE",
        "VOITURE",
        "CARBURANT",
        "ELECTRIQUE",
    ]
    if (
        any(k in tags_upper for k in auto_keywords)
        or news_data.get("category") == "AUTO"
    ):
        linked_apps.append("NovaAuto")
        logger.info(f"[BRIDGE] ➡️ Push vers NovaAuto: '{news_data.get('raw_title')}'")

    # 3. Alimentation de NovaFact (Le vérificateur)
    if news_data.get("trust_score", 1.0) < 0.6:
        linked_apps.append("NovaFact")
        logger.info(
            f"[BRIDGE] ➡️ Marqué 'À vérifier' dans NovaFact: '{news_data.get('raw_title')}' (Score: {news_data.get('trust_score')})"
        )

    # 4. Alimentation de NovaBets (Le prédicteur)
    bets_keywords = [
        "BLESSURE",
        "METEO",
        "SPORT",
        "FOOTBALL",
        "MERCATO",
        "TRANSFERT",
        "MATCH",
    ]
    if any(k in tags_upper for k in bets_keywords):
        linked_apps.append("NovaBets")
        logger.info(f"[BRIDGE] ➡️ Push vers NovaBets: '{news_data.get('raw_title')}'")

    return list(set(linked_apps))
