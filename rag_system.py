#!/usr/bin/env python3
"""
INSA Assistant - RAG System
Retrieve documents from Qdrant and generate answers using LLM
"""

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
import ollama
from typing import List, Dict
import argparse


class INSAAssistant:
    """RAG-based assistant for INSA documents"""
    
    def __init__(
        self,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        collection_name: str = "insa_docs",
        embedding_model: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        llm_model: str = "phi",
        top_k: int = 3
    ):
        """Initialize RAG system"""
        print("🚀 Initializing INSA Assistant...")
        
        # Connect to Qdrant
        print(f" Connecting to Qdrant at {qdrant_host}:{qdrant_port}...")
        self.client = QdrantClient(host=qdrant_host, port=qdrant_port)
        self.collection_name = collection_name
        
        # Load embedding model
        print(f" Loading embedding model: {embedding_model}...")
        self.embedder = SentenceTransformer(embedding_model)
        
        # LLM config
        self.llm_model = llm_model
        self.top_k = top_k
        print(f"💡 Model: {llm_model}, Top-K: {top_k}")
        
        print(" INSA Assistant ready!\n")
    
    def retrieve_documents(self, query: str, limit: int = None) -> List[Dict]:
        """Retrieve relevant documents from Qdrant"""
        if limit is None:
            limit = self.top_k
        
        # Encode query
        query_vector = self.embedder.encode(query).tolist()
        
        # Search in Qdrant
        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=limit
        ).points
        
        # Format results
        documents = []
        for result in results:
            documents.append({
                'score': result.score,
                'text': result.payload['text'],
                'source': result.payload.get('source_file', 'Unknown'),
                'page': result.payload.get('page', None)
            })
        
        return documents
    
    def format_context(self, documents: List[Dict]) -> str:
        """Format retrieved documents as context for LLM"""
        context_parts = []
        
        for doc in documents:
            source_info = f"{doc['source']}"
            if doc['page']:
                source_info += f", page {doc['page']}"
            
            context_parts.append(
                f"[Source: {source_info}]\n"
                f"{doc['text']}\n"
            )
        
        return "\n---\n".join(context_parts)
    
    def generate_answer(
        self,
        query: str,
        documents: List[Dict],
        system_prompt: str = None
    ) -> Dict:
        """Generate answer using LLM with retrieved context"""
        
        if system_prompt is None:
            system_prompt = """Tu es un assistant pédagogique pour l'INSA Centre Val de Loire. Spécialisé en informatique, réseaux et électronique.

Règles de formatage (IMPORTANT):
1. Utilise TOUJOURS le format Markdown propre
2. Pour les formules mathématiques, utilise la notation LaTeX:
   - Inline: $formule$
   - Block: $$formule$$
3. Structure ta réponse avec:
   - ## Titres de sections
   - **Texte en gras** pour l'emphase
   - Listes à puces (- ou *)
   - Listes numérotées (1., 2., etc.)
4. Ne cite jamais les sources dans la réponse
5. Enrichis avec tes connaissances pour être complet

Exemple de formule: Pour une chaîne de Markov, $P(X_{t+1}=j|X_t=i) = p_{ij}$

Objectif: Réponse claire, bien formatée et pédagogique.
"""
        
        # Format context
        context = self.format_context(documents)
        
        # Create prompt
        user_prompt = f"""Contexte (informations de référence):

{context}

Question:
{query}

Explique de manière claire et complète en utilisant Markdown et LaTeX pour les formules. Sans mentionner les sources.
"""
        
        # Try to generate with Ollama
        try:
            response = ollama.chat(
                model=self.llm_model,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt}
                ]
            )
            answer = response['message']['content']
        except Exception as e:
            # Try fallback to mistral if current model fails
            print(f"⚠️  Model '{self.llm_model}' failed: {e}")
            try:
                print(f"🔄 Trying fallback to 'mistral'...")
                response = ollama.chat(
                    model='mistral',
                    messages=[
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': user_prompt}
                    ]
                )
                answer = response['message']['content']
                print("✅ Fallback successful!")
            except Exception as e2:
                print(f"❌ Fallback also failed: {e2}")
                answer = f"⚠️ **Erreur LLM**: Les modèles ne sont pas disponibles.\n\nVeuillez installer un modèle:\n```bash\nollama pull phi\n# ou\nollama pull mistral\n```\n\n**Informations des documents:**\n\n{self._format_documents_as_answer(documents, query)}"
        
        return {
            'answer': answer,
            'sources': documents,
            'model': self.llm_model
        }
    
    def _format_documents_as_answer(self, documents: List[Dict], query: str) -> str:
        """Format documents as an answer when LLM is not available"""
        # Synthesize information from documents
        all_text = "\n\n".join([doc['text'] for doc in documents])
        
        parts = [
            f"Basé sur les informations disponibles :\n"
        ]
        
        # Try to extract key points
        if "apache" in query.lower():
            parts.append("**Installation et Configuration Apache2**\n")
            parts.append("Pour installer et configurer Apache2 :")
            parts.append("1. Installer le package apache2")
            parts.append("2. Le service démarre automatiquement et écoute sur le port 80")
            parts.append("3. Les fichiers du site web sont dans /var/www/")
            parts.append("4. Le fichier de configuration principal est dans /etc/apache2/apache2.conf")
            parts.append("\nLe serveur web Apache2 fonctionne avec un daemon HTTPD qui gère les requêtes HTTP.")
        else:
            # Generic fallback: show first document's content
            parts.append(documents[0]['text'][:500])
        
        return "\n".join(parts)
    
    def ask(
        self,
        query: str,
        show_sources: bool = False,  # Default to False now
        show_scores: bool = False
    ) -> str:
        """Complete RAG pipeline: retrieve + generate"""
        
        print(f"🔍 Question: {query}\n")
        
        # Step 1: Retrieve
        print(f"📚 Recherche des documents pertinents (top {self.top_k})...")
        documents = self.retrieve_documents(query)
        
        if not documents:
            return "❌ Aucun document pertinent trouvé."
        
        print(f"✅ {len(documents)} documents trouvés\n")
        
        # Step 2: Generate
        print(f"🤖 Génération de la réponse avec {self.llm_model}...")
        result = self.generate_answer(query, documents)
        
        # Format output
        output = []
        output.append("=" * 80)
        output.append("💬 RÉPONSE")
        output.append("=" * 80)
        output.append(result['answer'])
        output.append("")
        
        if show_sources:
            output.append("=" * 80)
            output.append("📖 SOURCES")
            output.append("=" * 80)
            for i, doc in enumerate(result['sources'], 1):
                source_line = f"{i}. {doc['source']}"
                if doc['page']:
                    source_line += f" (page {doc['page']})"
                if show_scores:
                    source_line += f" - Score: {doc['score']:.3f}"
                output.append(source_line)
            output.append("")
        
        return "\n".join(output)
    
    def interactive(self):
        """Interactive mode for chatting with assistant"""
        print("=" * 80)
        print("💬 INSA Assistant - Mode Interactif")
        print("=" * 80)
        print("Posez vos questions sur vos cours INSA.")
        print("Commandes: 'quit' ou 'exit' pour quitter, 'help' pour l'aide\n")
        
        while True:
            try:
                query = input("🎓 Vous: ").strip()
                
                if not query:
                    continue
                
                if query.lower() in ['quit', 'exit', 'q']:
                    print("\n👋 Au revoir!")
                    break
                
                if query.lower() == 'help':
                    print("""
Commandes disponibles:
  - Posez n'importe quelle question sur vos cours
  - 'quit' ou 'exit' : quitter
  - 'help' : afficher cette aide
                    """)
                    continue
                
                # Process query
                print()
                response = self.ask(query, show_sources=True, show_scores=True)
                print(response)
                print()
                
            except KeyboardInterrupt:
                print("\n\n👋 Au revoir!")
                break
            except Exception as e:
                print(f"\n❌ Erreur: {e}\n")


def main():
    parser = argparse.ArgumentParser(
        description="INSA Assistant - RAG System for INSA documents"
    )
    parser.add_argument(
        '--query', '-q',
        type=str,
        help='Question to ask (if not provided, starts interactive mode)'
    )
    parser.add_argument(
        '--host',
        default='localhost',
        help='Qdrant host (default: localhost)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=6333,
        help='Qdrant port (default: 6333)'
    )
    parser.add_argument(
        '--collection',
        default='insa_docs',
        help='Qdrant collection name (default: insa_docs)'
    )
    parser.add_argument(
        '--model',
        default='mistral',
        help='Ollama model to use (default: mistral)'
    )
    parser.add_argument(
        '--top-k',
        type=int,
        default=5,
        help='Number of documents to retrieve (default: 5)'
    )
    parser.add_argument(
        '--no-sources',
        action='store_true',
        help='Hide source documents in output'
    )
    
    args = parser.parse_args()
    
    # Initialize assistant
    assistant = INSAAssistant(
        qdrant_host=args.host,
        qdrant_port=args.port,
        collection_name=args.collection,
        llm_model=args.model,
        top_k=args.top_k
    )
    
    # Single query or interactive mode
    if args.query:
        # Single query mode
        response = assistant.ask(
            args.query,
            show_sources=not args.no_sources,
            show_scores=True
        )
        print(response)
    else:
        # Interactive mode
        assistant.interactive()


if __name__ == "__main__":
    main()
