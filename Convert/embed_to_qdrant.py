import json
from pathlib import Path
from typing import List, Dict
import numpy as np
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
class Chunker:
    """Découpe texte en français"""
    
    def __init__(self, size: int = 512, overlap: int = 80):
        self.size = size
        self.overlap = overlap
        self.seps = ['\n\n', '.\n', '. ', ' ! ', ' ? ', ' ; ', ' : ', '\n', ', ']
    
    def chunk(self, text: str, meta: Dict = None) -> List[Dict]:
        """Découpe texte avec overlap"""
        if not text or not text.strip():
            return []
        
        chunks, start, tid = [], 0, 0
        while start < len(text):
            end = start + self.size
            chunk_txt = text[start:end]
        
            # Chercher bon séparateur (70%+ du chunk)
            if end < len(text):
                for sep in self.seps:
                    pos = chunk_txt.rfind(sep)
                    if pos > self.size * 0.7:
                        chunk_txt = text[start:start + pos + len(sep)]
                        end = start + pos + len(sep)
                        break
            
            # Garder que chunks > 50 chars
            if len(chunk_txt.strip()) > 50:
                chunks.append({
                    'text': chunk_txt.strip(),
                    'metadata': {**(meta or {}), 'chunk_id': tid}
                })
                tid += 1
            
            start = end - self.overlap
            if start >= len(text):
                break
        
        return chunks
    
    def chunk_pages(self, pages: List[Dict], meta: Dict = None) -> List[Dict]:
        """Découpe pages PDF"""
        all_chunks = []
        for p in pages:
            if txt := p.get('text', '').strip():
                page_meta = {**(meta or {}), 'page': p.get('page', 0)}
                all_chunks.extend(self.chunk(txt, page_meta))
        return all_chunks


class Embedder:
    """Embedder + Qdrant"""
    
    def __init__(
        self,
        collection: str = "insa_docs",
        model: str = "dangvantuan/sentence-camembert-large",
        host: str = "localhost",
        port: int = 6333
    ):
        print(f" Model: {model}")
        
        # Charger model avec fallback
        try:
            self.model = SentenceTransformer(model)
            print("    Loaded")
        except Exception as e:
            print(f"    Failed: {e}")
            fallback = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
            print(f"   → Fallback: {fallback}")
            self.model = SentenceTransformer(fallback)
        
        self.dim = self.model.get_sentence_embedding_dimension()
        self.client = QdrantClient(host=host, port=port)
        self.collection = collection
        
        # Créer collection si besoin
        colls = [c.name for c in self.client.get_collections().collections]
        if collection not in colls:
            print(f" Création collection: {collection}")
            self.client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=self.dim, distance=Distance.COSINE)
            )
        else:
            print(f" Collection existe: {collection}")
    
    def embed(self, texts: List[str]) -> np.ndarray:
        """Textes → vecteurs"""
        print(f" Encoding {len(texts)} chunks...")
        return self.model.encode(
            texts,
            batch_size=32,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True  # Important pour cosine!
        )
    
    def add(self, chunks: List[Dict], batch: int = 100):
        """Upload chunks vers Qdrant"""
        if not chunks:
            return
        
        # ID de départ
        try:
            info = self.client.get_collection(self.collection)
            start_id = info.points_count
        except:
            start_id = 0
        
        # Embed
        texts = [c['text'] for c in chunks]
        vecs = self.embed(texts)
        
        # Upload par batch
        print(f" Uploading...")
        for i in range(0, len(chunks), batch):
            points = []
            for j, (chunk, vec) in enumerate(zip(chunks[i:i+batch], vecs[i:i+batch])):
                points.append(PointStruct(
                    id=start_id + i + j,
                    vector=vec.tolist(),
                    payload={'text': chunk['text'], **chunk['metadata']}
                ))
            
            self.client.upsert(collection_name=self.collection, points=points)
        
        print(f" {len(chunks)} chunks added")


def process_json(path: Path, chunker: Chunker, embedder: Embedder) -> int:
    """Traite 1 fichier JSON"""
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        ftype = data.get('filetype', 'unknown')
        
        # Metadata commune
        meta = {
            'source_file': data.get('filename', path.name),
            'source_path': data.get('filepath', str(path)),
            'filetype': ftype
        }
        
        chunks = []
        
        # PDF: chunk par pages
        if ftype == 'pdf':
            m = data.get('metadata', {})
            meta.update({
                'title': m.get('title', ''),
                'author': m.get('author', ''),
                'num_pages': m.get('num_pages', 0)
            })
            chunks = chunker.chunk_pages(data.get('pages', []), meta)
        
        # Code/Text: chunk direct
        elif ftype in ('code', 'text'):
            if ftype == 'code':
                meta['language'] = data.get('language', '')
            chunks = chunker.chunk(data.get('content', ''), meta)
        
        else:
            print(f"  Type inconnu: {ftype}")
            return 0
        
        # Upload
        if chunks:
            embedder.add(chunks)
        
        return len(chunks)
    
    except Exception as e:
        print(f" Error [{path.name}]: {e}")
        return 0


def main():
    import argparse
    
    p = argparse.ArgumentParser(description="JSON → Qdrant Embedder")
    p.add_argument('--source', default='../Data_json')
    p.add_argument('--collection', default='insa_docs')
    p.add_argument('--model', default='dangvantuan/sentence-camembert-large')
    p.add_argument('--chunk-size', type=int, default=512)
    p.add_argument('--overlap', type=int, default=80)
    p.add_argument('--host', default='localhost')
    p.add_argument('--port', type=int, default=6333)
    p.add_argument('--limit', type=int, help='Limit nb files')
    
    args = p.parse_args()
    
    print("=" * 70)
    print("🇫🇷 JSON → Qdrant Embedder")
    print("=" * 70)
    print(f"Source: {args.source}")
    print(f"Collection: {args.collection}")
    print(f"Model: {args.model}")
    print(f"Chunk: {args.chunk_size} chars, overlap: {args.overlap}")
    print(f"Qdrant: {args.host}:{args.port}")
    print("=" * 70)
    
    # Init
    chunker = Chunker(args.chunk_size, args.overlap)
    embedder = Embedder(args.collection, args.model, args.host, args.port)
    
    # Scan JSON files
    src = Path(args.source)
    if not src.exists():
        # Auto-detect from script location
        alt = Path(__file__).parent.parent / args.source.lstrip('./')
        if alt.exists():
            src = alt
    
    if not src.exists():
        print(f" Source not found: {src}")
        return
    
    files = list(src.rglob("*.json"))
    if args.limit:
        files = files[:args.limit]
    
    print(f"\n Found {len(files)} JSON files")
    print("-" * 70)
    
    # Process
    total_chunks = 0
    success = 0
    
    for i, f in enumerate(files, 1):
        print(f"\n[{i}/{len(files)}] {f.name}")
        n = process_json(f, chunker, embedder)
        if n > 0:
            total_chunks += n
            success += 1
        print(f"  → {n} chunks")
    
    # Stats
    print("\n" + "=" * 70)
    print(" TERMINÉ")
    print("=" * 70)
    print(f"Files: {success}/{len(files)}")
    print(f"Chunks: {total_chunks}")
    print(f"Collection: {args.collection}")
    print("=" * 70)


if __name__ == "__main__":
    main()