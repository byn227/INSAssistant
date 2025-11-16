from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

# Connexion
client = QdrantClient(host="localhost", port=6333)
model = SentenceTransformer("dangvantuan/sentence-camembert-large")
# Requête
query = "Comment configurer Apache2 ?"
query_vector = model.encode(query).tolist()

# Recherche
results = client.query_points(
    collection_name="insa_docs",
    query=query_vector,
    limit=5
).points

# Affichage des résultats
for result in results:
    print(f"Score : {result.score:.3f}")
    print(f"Fichier : {result.payload['source_file']}")
    print(f"Texte : {result.payload['text'][:200]}...")
    print("-" * 80)