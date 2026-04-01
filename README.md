# NovaNews

Le moteur d'ingestion et d'intelligence d'actualités centralisé de l'écosystème NovaVivo.

## 🔍 Rôle

NovaNews n'est pas une simple application de lecture RSS. C'est une **Base de Connaissance Partagée** qui alimente en temps réel le reste de vos applications (NovaAuto, NovaContab, NovaFact, NovaBets) via un système de "Bridge". 

## 🛠️ Architecture

1. **Ingestion** : Scrape des flux RSS multi-régionaux (FR, PT, GLOBAL) via `feedparser`.
2. **Extraction** : Nettoie le code HTML avec `trafilatura` pour en extraire le texte pur sans les menus/publicités.
3. **Enrichissement** : Utilise l'API `Tavily` pour vérifier le contexte de l'actualité et récupérer des images d'illustration.
4. **Intelligence** : Utilise le modèle IA de `NovaAdmin` (via requête interne API) pour générer un résumé synthétique (3 points), assigner des mots-clés (`tags`), et attribuer un `trust_score`.
5. **Routage (Nova-Bridge)** : En fonction des tags, l'information est envoyée vers d'autres instances (ex: les tags "IMPOTS" / "TVA" alimenteront *NovaContab*).

## 🚀 Lancement local

```bash
python -m venv venv
source venv/bin/activate # ou venv\Scripts\activate sous Windows
pip install -r requirements.txt
python run.py
```

- L'API est servie sur `http://localhost:5003/api/news`
- Vous pouvez déclencher l'ingestion (protégée par clé interne) via `POST /api/ingest`
