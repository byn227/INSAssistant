## Installation rapide

### Installer Python dependencies

```bash
pip install -r requirements_embedding.txt
```

### Démarrer Qdrant

```bash
docker run -d -p 6333:6333 \
    -v $(pwd)/qdrant_storage:/qdrant/storage:z \
    --name qdrant \
    qdrant/qdrant
```

**Vérifier :**
```bash
curl http://localhost:6333/health
```

## Utilisation

### Test rapide (10 fichiers)

```bash
python3 embed_to_qdrant.py --limit 10
```

### Indexer tous les fichiers

```bash
python3 embed_to_qdrant.py
```

### Options utiles

```bash
# Changer la taille des chunks
python3 embed_to_qdrant.py --chunk-size 1000

# Utiliser un modèle différent
python3 embed_to_qdrant.py --model sentence-transformers/paraphrase-multilingual-mpnet-base-v2

# Nom de collection personnalisé
python3 embed_to_qdrant.py --collection mes_documents
```

## Vérifier les résultats

### Web Dashboard (recommandé)
```bash
firefox http://localhost:6333/dashboard
```

### Commande rapide
```bash
curl http://localhost:6333/collections | jq
```

### Test de recherche
```bash
python3 ../Mini_test_rag.py
```

## Configuration

### Taille des chunks

| Taille | Utilisation | Avantages | Inconvénients |
|--------|-------------|-----------|---------------|
| 256-512 (défaut) | Documents généraux | Précis | Plus de chunks |
| 1000-2000 | Longs articles | Moins de chunks | Peut perdre contexte |

### Modèles disponibles

| Modèle | Dimensions | Langues | Vitesse |
|--------|-----------|---------|---------|
| `paraphrase-multilingual-mpnet-base-v2` (défaut) | 768 | Multilingue | Moyen |
| `dangvantuan/sentence-camembert-large` | 1024 | Français | Lent |
| `all-MiniLM-L6-v2` | 384 | Anglais | Rapide |

##  Workflow complet

```bash
# Démarrer Qdrant
docker start qdrant

# Convertir les documents (si pas déjà fait)
python3 Convert_all_to_json.py

# Créer les embeddings
python3 embed_to_qdrant.py

# Vérifier
firefox http://localhost:6333/dashboard

# Tester
python3 ../Mini_test_rag.py
```

## Comment ça marche

```
Documents (PDF/DOCX/Code)
    ↓
JSON (Data_json/)
    ↓
Chunks de texte (512 caractères)
    ↓
Embeddings (vecteurs 768-d)
    ↓
Qdrant (recherche similarité)
```

## Problèmes courants

**Qdrant ne démarre pas :**
```bash
docker ps                # Vérifier
docker logs qdrant       # Voir erreurs
docker restart qdrant    # Redémarrer
```

**Collection existe déjà :**
```bash
curl -X DELETE http://localhost:6333/collections/insa_docs
python3 embed_to_qdrant.py
```

**Trop lent :**
```bash
# Utiliser modèle plus léger
python3 embed_to_qdrant.py --model all-MiniLM-L6-v2
```

