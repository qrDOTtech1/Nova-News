import os
import time
import json
import logging
import requests

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es l'Analyste Central de NovaNews.
Ta mission est de lire le texte brut d'une actualité (et son contexte additionnel), de la résumer, et d'en extraire des métadonnées essentielles pour l'écosystème NovaVivo.

Tu dois impérativement renvoyer UNIQUEMENT un objet JSON valide (pas de markdown autour).

Format attendu :
{
  "ai_summary": ["Point clé 1", "Point clé 2", "Point clé 3"],
  "tags": ["MOTCLE1", "MOTCLE2"],
  "trust_score": <float entre 0.0 et 1.0>
}

Règles pour le JSON :
- "ai_summary" : Doit contenir exactement 3 points courts et percutants résumant l'article (dans la langue de la région : FR ou PT).
- "tags" : Liste de 2 à 5 mots clés en MAJUSCULES (ex: "TVA", "IMPOTS", "RAPPEL", "MOTEUR", "SPORT").
- "trust_score" : Si l'article semble être du "clickbait", peu sourcé, ou sensationnaliste, mets un score entre 0.1 et 0.5. Si l'article vient d'une source neutre et présente des faits, mets entre 0.6 et 1.0.

L'article est fourni par l'utilisateur ci-dessous.
"""


def fetch_ai_config():
    """Récupère la configuration IA depuis NovaAdmin."""
    admin_url = os.environ.get("NOVA_ADMIN_URL", "https://novaxadmin.casa")
    internal_key = os.environ.get("INTERNAL_API_KEY", "")

    if not internal_key:
        logger.warning("[AI] Pas de INTERNAL_API_KEY définie.")
        return None

    try:
        resp = requests.get(
            f"{admin_url}/api/internal/config",
            headers={"X-Internal-Key": internal_key},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("ai_provider")
    except Exception as e:
        logger.error(f"[AI] Impossible de joindre NovaAdmin : {e}")
    return None


def _call_model(ai_config: dict, messages: list) -> str:
    base_url = ai_config["base_url"]
    api_key = ai_config.get("api_key", "")
    model = ai_config.get(
        "brain_model"
    )  # On utilise l'Orchestrateur (Brain) car tâche rapide/JSON
    provider_type = ai_config.get("provider_type", "groq")

    if provider_type == "ollama":
        if "api" not in base_url and "v1" not in base_url:
            url = f"{base_url.rstrip('/')}/api/chat"
        else:
            url = (
                f"{base_url.rstrip('/')}/chat"
                if "api" in base_url
                else f"{base_url.rstrip('/')}/chat/completions"
            )

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        if "completions" in url:
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": 500,
                "temperature": 0.1,
            }
        else:
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 500},
            }

        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        resp.raise_for_status()
        if "completions" in url:
            return resp.json()["choices"][0]["message"]["content"].strip()
        return resp.json()["message"]["content"].strip()

    # Format OpenAI standard
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 500,
        "temperature": 0.1,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=20)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def process_news_ai(text: str, context_snippets: list) -> dict:
    """Analyse un article avec l'IA et retourne le dictionnaire JSON parsé."""
    ai_config = fetch_ai_config()
    if not ai_config:
        # Fallback si l'IA n'est pas dispo
        return {
            "ai_summary": ["Analyse indisponible"],
            "tags": ["ERREUR_IA"],
            "trust_score": 0.5,
        }

    context_str = "\n".join(f"- {c}" for c in context_snippets)
    user_prompt = f"TEXTE BRUT:\n{text[:2000]}\n\nCONTEXTE TAVILY:\n{context_str}"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        raw_response = _call_model(ai_config, messages)
        # Nettoyage et parsing
        import re

        match = re.search(r"\{.*\}", raw_response, re.DOTALL)
        if match:
            return json.loads(match.group())
        return json.loads(raw_response)
    except Exception as e:
        logger.error(f"[AI] Erreur parsing ou requête : {e}")
        return {
            "ai_summary": ["Erreur de résumé IA"],
            "tags": ["ERREUR_IA"],
            "trust_score": 0.5,
        }
