# Intégrer des documents dans Qdrant

## 📋 Vue d'ensemble

Script pour générer des embeddings à partir de fichiers JSON (issus de PDFs, code, texte) et les indexer dans la base vectorielle Qdrant pour effectuer des recherches sémantiques.

## 🔧 Installation

### 1. Installer les packages Python

```bash
pip install -r requirements_embedding.txt
```

Packages nécessaires :
- `sentence-transformers` : génération des embeddings
- `qdrant-client` : client pour la base Qdrant
- `torch` : backend pour sentence-transformers
- `tqdm` : barres de progression

### 2. Installer Qdrant

**Avec Docker (recommandé) :**

```bash
# Récupérer l'image
docker pull qdrant/qdrant

# Lancer le serveur Qdrant
docker run -p 6333:6333 -p 6334:6334 \
    -v $(pwd)/qdrant_storage:/qdrant/storage:z \
    qdrant/qdrant
```

## 🧪 Tester la stratégie de découpage (chunking)

Avant d'indexer, testez comment le texte est segmenté :

```bash
# Test avec un fichier JSON
python test_chunking.py ../Data_json/path/to/file.json

# Essayer d'autres tailles de chunk
python test_chunking.py ../Data_json/path/to/file.json --chunk-size 1000 --overlap 100
```

Le résultat affiche :
- Le nombre de chunks créés
- La taille de chaque chunk
- Un aperçu du contenu des chunks

## 🚀 Utilisation

### 1. Démarrer le serveur Qdrant

```bash
docker run -p 6333:6333 -p 6334:6334 \
    -v $(pwd)/qdrant_storage:/qdrant/storage:z \
    qdrant/qdrant
```

### 2. Tester d'abord sur quelques fichiers

```bash
# Test sur les 10 premiers fichiers
python embed_to_qdrant.py --limit 10
```

### 3. Indexer tous les fichiers

```bash
# Indexer tout avec la configuration par défaut
python embed_to_qdrant.py

# Personnaliser la taille et le recouvrement des chunks
python embed_to_qdrant.py --chunk-size 1000 --overlap 100

# Utiliser un autre modèle
python embed_to_qdrant.py --model "sentence-transformers/all-MiniLM-L6-v2"
```

## ⚙️ Configuration

### Chunk Size & Overlap

- **chunk_size** : nombre de caractères par chunk (par défaut : 512)
  - Plus petit (256-512) : plus précis mais plus de chunks
  - Plus grand (1000-2000) : moins de chunks mais risque de perdre du contexte

- **overlap** : nombre de caractères de recouvrement entre chunks (par défaut : 50)
  - Aide à conserver le contexte entre les chunks
  - Recommandé : 10-20% de chunk_size

### Modèles d'embedding

**Modèles multilingues (recommandés pour FR/VN) :**
- `paraphrase-multilingual-mpnet-base-v2` (par défaut) — 768 dims
- `distiluse-base-multilingual-cased-v2` — 512 dims (plus rapide)

**Modèles anglais (si corpus uniquement en anglais) :**
- `all-MiniLM-L6-v2` — 384 dims (très rapide)
- `all-mpnet-base-v2` — 768 dims (plus précis)

## 📊 Architecture

```
Fichiers JSON (Data_json/)
    ↓
Découpage du texte (512 caractères + 50 de recouvrement)
    ↓
Sentence Transformers (modèle multilingue)
    ↓
Embeddings (vecteurs 768-d)
    ↓
Base Qdrant (similarité cosinus)
```

### Métadonnées stockées

Chaque chunk stocke les métadonnées :
- `text` : contenu du chunk
- `source_file` : nom du fichier d'origine
- `source_path` : chemin du fichier
- `filetype` : pdf/code/text
- `chunk_id` : identifiant du chunk dans le fichier
- `page` : numéro de page (si PDF)
- `title`, `author` : métadonnées PDF
- `language` : langue (si code)

## 🎨 Interface Web Qdrant

Qdrant propose une interface Web intégrée pour suivre et gérer les collections :

**URLs :**
- **Dashboard** : http://localhost:6333/dashboard
- **API Docs** : http://localhost:6333/docs (Swagger)
- **ReDoc** : http://localhost:6333/redoc

**Accès rapide :**
```bash
# Ouvrir le dashboard
./check_qdrant.sh

# Ou monitorer en temps réel dans le terminal
python3 monitor_qdrant.py

# Afficher l'état une seule fois
python3 monitor_qdrant.py --once
```

**Fonctionnalités du Dashboard :**
- ✅ Voir toutes les collections et le nombre de vecteurs
- ✅ Inspecter la configuration des collections
- ✅ Rechercher des vecteurs avec des requêtes personnalisées
- ✅ Parcourir les points et leurs métadonnées
- ✅ Suivre l'état des collections

## 🔍 Exemple de requête

```python
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

# Connexion
client = QdrantClient(host="localhost", port=6333)
model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-mpnet-base-v2")

# Requête
query = "Comment configurer Apache ?"
query_vector = model.encode(query).tolist()

# Recherche
results = client.search(
    collection_name="insa_documents",
    query_vector=query_vector,
    limit=5
)

# Affichage des résultats
for result in results:
    print(f"Score : {result.score:.3f}")
    print(f"Fichier : {result.payload['source_file']}")
    print(f"Texte : {result.payload['text'][:200]}...")
    print("-" * 80)
```

## 📈 Performances

Pour 1157 fichiers (~1100 PDFs) :
- **Découpage** : ~5-10 minutes
- **Embedding** : ~30-60 minutes (selon GPU/CPU)
- **Upload vers Qdrant** : ~5-10 minutes

**Temps total** : ~1-2 heures

## 💡 Conseils

1. **Tester d'abord** : utilisez `--limit 10` pour un essai rapide
2. **Choisir une taille de chunk adaptée** : testez avec `test_chunking.py`
3. **GPU = plus rapide** : si disponible, l'embedding sera bien plus rapide
4. **Sauvegarde** : Qdrant stocke les données dans `qdrant_storage/`
5. **Suivi** : utilisez `monitor_qdrant.py` ou l'interface Web
6. **Web UI** : ouvrez http://localhost:6333/dashboard pour une vue d'ensemble

## 🐛 Dépannage

**Problème de connexion à Qdrant :**
```bash
# Vérifier que Qdrant fonctionne
curl http://localhost:6333/health

# Redémarrer Qdrant
docker restart <container_id>
```

**Mémoire insuffisante (Out of memory) :**
- Réduire la taille de batch dans le code
- Utiliser un modèle plus léger (distiluse)
- Traiter les fichiers par lots

**Embedding lent :**
- Vérifier le GPU : `nvidia-smi`
- Utiliser un modèle plus petit
- Réduire le nombre de fichiers avec `--limit`
