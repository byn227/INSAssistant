# 🎓 INSA Assistant

Un assistant intelligent basé sur RAG (Retrieval-Augmented Generation) pour les étudiants de l'INSA Centre Val de Loire. Ce système permet de poser des questions sur les cours et d'obtenir des réponses précises basées sur les documents pédagogiques.

![INSA Logo](assets/insa_logo.png)

## ✨ Fonctionnalités

- 🔍 **Scraping automatique** : Télécharge les documents depuis Celene
- 📄 **Conversion intelligente** : Transforme PDF, DOCX et autres formats en JSON
- 🧠 **Embeddings vectoriels** : Indexation sémantique avec Qdrant
- 💬 **Chat interactif** : Interface web moderne avec Streamlit
- 🤖 **Génération de réponses** : Utilise Ollama (Mistral, Phi, Llama2, etc.)
- 📚 **Sources citées** : Affiche les documents utilisés pour chaque réponse
- 🎨 **Interface sombre** : Design moderne et confortable

## 🏗️ Architecture

```
Documents Celene
    ↓
Scraper (celene_scraper.py)
    ↓
Documents locaux (Data/)
    ↓
Conversion (Convert/)
    ↓
JSON structuré (Data_json/)
    ↓
Embeddings (embed_to_qdrant.py)
    ↓
Qdrant Vector DB
    ↓
RAG System (rag_system.py)
    ↓
Web Interface (web_app.py)
```

## 📋 Prérequis

- Python 3.8+
- Docker (pour Qdrant)
- Ollama (pour les LLM)
- Compte Celene INSA

## 🚀 Installation rapide

### 1. Cloner le projet

```bash
git clone <repository-url>
cd INSAssistant
```

### 2. Installer les dépendances Python

```bash
# Pour le scraping et conversion
pip install -r Convert/requirements_embedding.txt

# Pour l'interface web
pip install -r requirements_web.txt
```

### 3. Lancer Qdrant (base vectorielle)

```bash
docker run -d -p 6333:6333 \
    -v $(pwd)/qdrant_storage:/qdrant/storage:z \
    --name qdrant \
    qdrant/qdrant
```

Vérifier que Qdrant fonctionne :
```bash
curl http://localhost:6333/health
```

### 4. Installer Ollama et télécharger un modèle

```bash
# Installer Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Télécharger un modèle (au choix)
ollama pull phi          # Rapide et léger (recommandé)
ollama pull mistral      # Équilibré qualité/vitesse
ollama pull llama2       # Haute qualité mais plus lent
```

## 📖 Utilisation

### Étape 1 : Scraper les documents depuis Celene

1. Configurer vos identifiants :

```bash
cp celene.conf.sample celene.conf
# Éditer celene.conf avec vos identifiants
```

2. Lancer le scraper :

```bash
python3 celene_scraper.py
```

Les documents seront téléchargés dans `Data/`

### Étape 2 : Convertir les documents en JSON

```bash
cd Convert
python3 Convert_all_to_json.py
```

Les fichiers JSON seront dans `Data_json/`

### Étape 3 : Créer les embeddings et indexer dans Qdrant

```bash
cd Convert
python3 embed_to_qdrant.py
```

Options utiles :
```bash
# Test avec 10 fichiers seulement
python3 embed_to_qdrant.py --limit 10

# Changer la taille des chunks
python3 embed_to_qdrant.py --chunk-size 1000

# Utiliser un modèle d'embedding différent
python3 embed_to_qdrant.py --model sentence-transformers/paraphrase-multilingual-mpnet-base-v2
```

### Étape 4 : Lancer l'interface web

```bash
streamlit run web_app.py
```

L'application sera accessible sur : **http://localhost:8501**

## 💡 Utilisation de l'interface web

### Poser des questions

Exemples de questions :
- "Qu'est-ce que la cryptographie ?"
- "Comment fonctionne le protocole TCP/IP ?"
- "Explique-moi les chaînes de Markov"
- "Comment installer Apache2 ?"

### Configuration (Sidebar)

- **Modèle LLM** : Choisir entre phi (rapide), mistral (équilibré), llama2 (qualité)
- **Nombre de documents** : 1-10 documents à récupérer (moins = plus rapide)
- **Afficher les sources** : Voir les documents utilisés pour la réponse
- **Connexion Qdrant** : Modifier host/port si nécessaire

### Raccourcis

- **🔄 Réinitialiser** : Efface le cache et redémarre
- **🗑️ Effacer l'historique** : Nettoie la conversation
- **💡 Exemples de questions** : Questions pré-remplies

## 📁 Structure du projet

```
INSAssistant/
├── celene_scraper.py           # Scraper pour Celene
├── celene.conf                 # Configuration (à créer)
├── celene.conf.sample          # Exemple de configuration
├── rag_system.py               # Système RAG (retrieve + generate)
├── web_app.py                  # Interface web Streamlit
├── requirements_web.txt        # Dépendances web
├── assets/
│   └── insa_logo.png          # Logo INSA
├── Celene_parser/
│   ├── auth.py                # Authentification CAS
│   ├── models.py              # Modèles de données
│   ├── parser.py              # Parseur HTML Celene
│   └── utils.py               # Utilitaires
├── Convert/
│   ├── Convert_all_to_json.py # Conversion documents → JSON
│   ├── embed_to_qdrant.py     # Création embeddings + indexation
│   ├── clean_json_text.py     # Nettoyage du JSON
│   ├── requirements_embedding.txt
│   └── README_EMBEDDING.md    # Documentation embedding
├── Data/                       # Documents bruts (PDF, DOCX, etc.)
├── Data_json/                  # Documents convertis en JSON
├── qdrant_storage/            # Base de données Qdrant
└── Logs/                       # Logs du scraper
```

## ⚙️ Configuration avancée

### Performance

Pour améliorer la vitesse de réponse :

1. **Utiliser un modèle plus léger** : `phi` plutôt que `mistral`
2. **Réduire le nombre de documents** : 3 au lieu de 5
3. **Chunks plus petits** : `--chunk-size 512` (par défaut)
4. **GPU** : Configurer Ollama pour utiliser le GPU si disponible

### Modèles d'embedding disponibles

| Modèle | Dimensions | Langues | Vitesse |
|--------|-----------|---------|---------|
| `paraphrase-multilingual-mpnet-base-v2` (défaut) | 768 | Multi | Moyen |
| `dangvantuan/sentence-camembert-large` | 1024 | FR | Lent |
| `all-MiniLM-L6-v2` | 384 | EN | Rapide |

### Modèles LLM supportés

| Modèle | Taille | Vitesse | Qualité | Usage |
|--------|--------|---------|---------|-------|
| **phi** | 1.6 GB | ⚡⚡⚡ | ⭐⭐ | Rapide pour usage général |
| **mistral** | 4.4 GB | ⚡⚡ | ⭐⭐⭐ | Équilibré (recommandé) |
| **llama2** | 7 GB | ⚡ | ⭐⭐⭐⭐ | Haute qualité |
| **codellama** | 7 GB | ⚡ | ⭐⭐⭐⭐ | Questions code/programmation |
| **deepseek-coder** | 6.7 GB | ⚡⚡ | ⭐⭐⭐⭐ | Spécialisé programmation |

## 🔧 Dépannage

### Qdrant ne démarre pas

```bash
docker ps                # Vérifier le conteneur
docker logs qdrant       # Voir les erreurs
docker restart qdrant    # Redémarrer
```

### Ollama ne répond pas

```bash
ollama list              # Vérifier les modèles installés
ollama pull phi          # Télécharger un modèle
ollama serve             # Démarrer le service (si nécessaire)
```

### Collection Qdrant inexistante

```bash
cd Convert
python3 embed_to_qdrant.py
```

### Erreur de permission Docker

```bash
sudo usermod -aG docker $USER
# Puis se déconnecter/reconnecter
```

### Port 8501 déjà utilisé

```bash
streamlit run web_app.py --server.port 8502
```

## 🌐 Déploiement en production

### Sur un serveur

```bash
# Lancer sur toutes les interfaces réseau
streamlit run web_app.py --server.address 0.0.0.0 --server.port 8501
```

Accès depuis un autre PC : `http://<server-ip>:8501`

### Avec authentification

Modifier `.streamlit/config.toml` :

```toml
[server]
enableCORS = false
enableXsrfProtection = true

[browser]
gatherUsageStats = false
```

## 📊 Statistiques et monitoring

### Vérifier l'état de Qdrant

```bash
# Via API
curl http://localhost:6333/collections | jq

# Dashboard web
firefox http://localhost:6333/dashboard
```

### Logs de l'application

- Les logs du scraper sont dans `Logs/`
- Les logs de Streamlit s'affichent dans le terminal
- Les logs Ollama : `journalctl -u ollama` (si installé en service)

## 🤝 Contribution

Pour contribuer au projet :

1. Fork le repository
2. Créer une branche : `git checkout -b feature/ma-fonctionnalite`
3. Commit : `git commit -m "Ajout de ma fonctionnalité"`
4. Push : `git push origin feature/ma-fonctionnalite`
5. Créer une Pull Request

## 📄 Licence

Ce projet est développé pour un usage éducatif à l'INSA Centre Val de Loire.

## 🙏 Remerciements

- **INSA Centre Val de Loire** pour les ressources pédagogiques
- **Qdrant** pour la base de données vectorielle
- **Ollama** pour les modèles LLM
- **Streamlit** pour l'interface web
- **Sentence Transformers** pour les embeddings

## 📞 Contact & Support

Pour tout problème ou question :
- Créer une issue sur GitHub
- Consulter les README spécifiques :
  - [README_EMBEDDING.md](Convert/README_EMBEDDING.md) - Guide des embeddings
  - [README_WEB.md](README_WEB.md) - Guide de l'interface web

---
