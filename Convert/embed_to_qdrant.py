import json
import os
from pathlib import Path
from typing import List, Dict, Optional
from tqdm import tqdm
import numpy as np

# Sentence Transformers cho embedding
from sentence_transformers import SentenceTransformer

# Qdrant client
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct


class TextChunker:
    
    def __init__(self, chunk_size: int = 512, overlap: int = 50):

        self.chunk_size = chunk_size
        self.overlap = overlap
    
    def chunk_text(self, text: str, metadata: Dict = None) -> List[Dict]:

        if not text or len(text.strip()) == 0:
            return []
        
        chunks = []
        start = 0
        text_len = len(text)
        chunk_id = 0
        
        while start < text_len:
       
            end = start + self.chunk_size
            chunk_text = text[start:end]
            

            if end < text_len:

                for sep in ['\n\n', '. ', '.\n', '! ', '? ', '\n']:
                    last_sep = chunk_text.rfind(sep)
                    if last_sep > self.chunk_size * 0.7: 
                        chunk_text = text[start:start + last_sep + len(sep)]
                        end = start + last_sep + len(sep)
                        break
            

            if len(chunk_text.strip()) > 50:
                chunk_meta = {
                    **(metadata or {}),
                    'chunk_id': chunk_id,
                    'chunk_start': start,
                    'chunk_end': end,
                }
                
                chunks.append({
                    'text': chunk_text.strip(),
                    'metadata': chunk_meta
                })
                chunk_id += 1
            

            start = end - self.overlap
            if start >= text_len:
                break
        
        return chunks
    
    def chunk_pdf_pages(self, pages: List[Dict], base_metadata: Dict = None) -> List[Dict]:

        all_chunks = []
        
        for page_info in pages:
            page_num = page_info.get('page', 0)
            page_text = page_info.get('text', '')
            
            if not page_text or len(page_text.strip()) == 0:
                continue
            

            page_meta = {
                **(base_metadata or {}),
                'page': page_num,
            }
            

            chunks = self.chunk_text(page_text, page_meta)
            all_chunks.extend(chunks)
        
        return all_chunks


class QdrantEmbedder:
    
    def __init__(
        self,
        collection_name: str = "insa_documents",
        model_name: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
    ):
        """
        Args:
            collection_name: Collection name in Qdrant
            model_name: Embedding model (supports French/Vietnamese)
            qdrant_host: Qdrant server host
            qdrant_port: Qdrant server port
        """
        print(f"🔧 Initializing embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)
        self.embedding_dim = self.model.get_sentence_embedding_dimension()
        
        print(f"🔧 Connecting to Qdrant: {qdrant_host}:{qdrant_port}")
        self.client = QdrantClient(host=qdrant_host, port=qdrant_port)
        self.collection_name = collection_name
        
        self._init_collection()
    
    def _init_collection(self):
        """Create collection if it doesn't exist"""
        collections = self.client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if self.collection_name not in collection_names:
            print(f" Creating new collection: {self.collection_name}")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.embedding_dim,
                    distance=Distance.COSINE
                )
            )
        else:
            print(f" Collection already exists: {self.collection_name}")
    
    def embed_texts(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """Create embeddings for list of texts"""
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=True,
            convert_to_numpy=True
        )
        return embeddings
    
    def add_chunks(self, chunks: List[Dict], batch_size: int = 100):
        """
        Add chunks to Qdrant
        
        Args:
            chunks: List of dicts with 'text' and 'metadata'
            batch_size: Number of chunks per batch
        """
        if not chunks:
            return
        
        # Get starting ID
        try:
            collection_info = self.client.get_collection(self.collection_name)
            start_id = collection_info.points_count
        except:
            start_id = 0
        
        # Embed in batches
        print(f" Embedding {len(chunks)} chunks...")
        texts = [chunk['text'] for chunk in chunks]
        embeddings = self.embed_texts(texts, batch_size=32)
        
        # Upload to Qdrant in batches
        print(f"📤 Uploading to Qdrant...")
        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_embeddings = embeddings[i:i + batch_size]
            
            points = []
            for j, (chunk, embedding) in enumerate(zip(batch_chunks, batch_embeddings)):
                point_id = start_id + i + j
                
                points.append(PointStruct(
                    id=point_id,
                    vector=embedding.tolist(),
                    payload={
                        'text': chunk['text'],
                        **chunk['metadata']
                    }
                ))
            
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
        
        print(f" Added {len(chunks)} chunks to Qdrant")


def process_json_file(
    json_path: Path,
    chunker: TextChunker,
    embedder: QdrantEmbedder,
) -> int:
    """
    Process a JSON file
    
    Returns:
        Number of chunks created
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        filetype = data.get('filetype', 'unknown')
        filename = data.get('filename', json_path.name)
        filepath = data.get('filepath', str(json_path))
        
        # Common metadata
        base_metadata = {
            'source_file': filename,
            'source_path': filepath,
            'filetype': filetype,
        }
        
        chunks = []
        
        if filetype == 'pdf':
            # PDF: chunk by pages
            pages = data.get('pages', [])
            metadata = data.get('metadata', {})
            base_metadata.update({
                'title': metadata.get('title', ''),
                'author': metadata.get('author', ''),
                'num_pages': metadata.get('num_pages', 0),
            })
            chunks = chunker.chunk_pdf_pages(pages, base_metadata)
        
        elif filetype == 'code':
            # Code: chunk by lines
            content = data.get('content', '')
            language = data.get('language', '')
            base_metadata.update({
                'language': language,
            })
            chunks = chunker.chunk_text(content, base_metadata)
        
        elif filetype == 'text':
            # Text: chunk directly
            content = data.get('content', '')
            chunks = chunker.chunk_text(content, base_metadata)
        
        else:
            print(f"⚠️  Unknown filetype: {filetype} for {filename}")
            return 0
        
        # Add to Qdrant
        if chunks:
            embedder.add_chunks(chunks)
        
        return len(chunks)
    
    except Exception as e:
        print(f"❌ Error processing {json_path.name}: {e}")
        return 0


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Embed JSON files vào Qdrant database"
    )
    
    parser.add_argument(
        '--source', 
        default='../Data_json',
        help='Directory containing JSON files'
    )
    parser.add_argument(
        '--collection', 
        default='insa_documents',
        help='Collection name in Qdrant'
    )
    parser.add_argument(
        '--model',
        default='sentence-transformers/paraphrase-multilingual-mpnet-base-v2',
        help='Embedding model (multilingual support)'
    )
    parser.add_argument(
        '--chunk-size',
        type=int,
        default=512,
        help='Chunk size in characters'
    )
    parser.add_argument(
        '--overlap',
        type=int,
        default=50,
        help='Overlap between chunks in characters'
    )
    parser.add_argument(
        '--host',
        default='localhost',
        help='Qdrant host'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=6333,
        help='Qdrant port'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of files to process (for testing)'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print(" INSA Document Embedder for Qdrant")
    print("=" * 60)
    print(f"Source: {args.source}")
    print(f"Collection: {args.collection}")
    print(f"Model: {args.model}")
    print(f"Chunk size: {args.chunk_size} chars")
    print(f"Overlap: {args.overlap} chars")
    print("=" * 60)
    
    # Initialize
    chunker = TextChunker(chunk_size=args.chunk_size, overlap=args.overlap)
    embedder = QdrantEmbedder(
        collection_name=args.collection,
        model_name=args.model,
        qdrant_host=args.host,
        qdrant_port=args.port,
    )
    
    # Find all JSON files
    source_dir = Path(args.source)
    json_files = list(source_dir.rglob("*.json"))
    
    if args.limit:
        json_files = json_files[:args.limit]
    
    print(f"\n🔍 Found {len(json_files)} JSON files")
    print("-" * 60)
    
    # Process each file
    total_chunks = 0
    for i, json_path in enumerate(json_files, 1):
        print(f"\n[{i}/{len(json_files)}] Processing: {json_path.name}")
        num_chunks = process_json_file(json_path, chunker, embedder)
        total_chunks += num_chunks
        print(f"  → {num_chunks} chunks")
    
    print("\n" + "=" * 60)
    print("✅ COMPLETED!")
    print("=" * 60)
    print(f"Files processed: {len(json_files)}")
    print(f"Total chunks: {total_chunks}")
    print(f"Collection: {args.collection}")
    print("=" * 60)


if __name__ == "__main__":
    main()
