"""Quick test RAG without waiting"""
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

client = QdrantClient(host="localhost", port=6333)
model = SentenceTransformer("dangvantuan/sentence-camembert-large")

query = "Comment installer Apache2 ?"
query_vector = model.encode(query).tolist()

results = client.query_points(
    collection_name="insa_docs",
    query=query_vector,
    limit=3
).points

print(f"Question: {query}\n")
print("="*80)
print("CONTEXTE POUR LLM (sans citations):\n")

for doc in results:
    print(doc.payload['text'][:300])
    print("\n" + "-"*60 + "\n")

print("\n" + "="*80)
print("Avec ce format, LLM va générer réponse pure sans mentionner sources")
