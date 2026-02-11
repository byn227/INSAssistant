import streamlit as st
from rag_system import INSAAssistant
import time
from pathlib import Path

# Try to use INSA logo as favicon
logo_path = Path(__file__).parent / "assets" / "insa_logo.png"
page_icon = str(logo_path) if logo_path.exists() else "🎓"

# Page config
st.set_page_config(
    page_title="INSA Assistant",
    page_icon=page_icon,
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    * {
        font-family: 'Segoe UI', 'Arial Unicode MS', 'Helvetica Neue', Arial, sans-serif;
    }
    .main-header {
        text-align: center;
        padding: 1rem 0;
        background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 100%);
        color: white;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 1rem;
        border-left: 4px solid #3b82f6;
        font-family: 'Segoe UI', 'Arial Unicode MS', 'Helvetica Neue', Arial, sans-serif;
        line-height: 1.6;
        color: white;
    }
    .user-message {
        background-color: #1e293b;
        border-left-color: #3b82f6;
    }
    .assistant-message {
        background-color: #0f172a;
        border-left-color: #10b981;
    }
    .source-box {
        background-color: #422006;
        border-left: 4px solid #f59e0b;
        padding: 0.5rem;
        margin: 0.5rem 0;
        border-radius: 5px;
        font-size: 0.9rem;
        color: #fbbf24;
    }
    .stTextInput > div > div > input {
        background-color: #1e293b;
        color: white;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def initialize_assistant(host, port, collection, model, top_k):
    """Initialize and cache the assistant"""
    return INSAAssistant(
        qdrant_host=host,
        qdrant_port=port,
        collection_name=collection,
        llm_model=model,
        top_k=top_k
    )


def display_message(role, content, sources=None):
    """Display a chat message"""
    if role == "user":
        st.markdown(f"""
        <div class="chat-message user-message">
            <b>🎓 Vous:</b> {content}
        </div>
        """, unsafe_allow_html=True)
    else:
        # Assistant message with proper markdown rendering
        with st.container():
            st.markdown("""
            <div style="padding: 1rem; border-radius: 10px; margin-bottom: 1rem; 
                        background-color: #0f172a; border-left: 4px solid #10b981;">
                <b style="color: white;">🤖 Assistant:</b>
            </div>
            """, unsafe_allow_html=True)
            
            # Render content as markdown (supports LaTeX with $ and $$)
            st.markdown(content)
        
        # Display sources if available
        if sources and st.session_state.get('show_sources', False):
            with st.expander("📚 Sources utilisées", expanded=False):
                for i, doc in enumerate(sources, 1):
                    source_text = f"{doc['source']}"
                    if doc.get('page'):
                        source_text += f" (page {doc['page']})"
                    source_text += f" - Score: {doc['score']:.3f}"
                    
                    st.markdown(f"**{i}. {source_text}**")
                    with st.container():
                        st.text(doc['text'][:300] + "..." if len(doc['text']) > 300 else doc['text'])
                    st.divider()


def main():
    # Header
    st.markdown("""
    <div class="main-header">
        <h1>🎓 INSA Assistant</h1>
        <p>Votre assistant intelligent pour les cours de l'INSA Centre Val de Loire</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Connection settings
        with st.expander("🔗 Connexion Qdrant", expanded=False):
            host = st.text_input("Host", value="localhost")
            port = st.number_input("Port", value=6333, min_value=1, max_value=65535)
            collection = st.text_input("Collection", value="insa_docs")
        
        # Model settings
        with st.expander("🤖 Modèle LLM", expanded=False):
            llm_model = st.selectbox(
                "Modèle Ollama",
                ["phi", "mistral", "llama2", "codellama", "deepseek-coder"],
                index=0,
                help="phi est le plus rapide, mistral offre le meilleur équilibre"
            )
            top_k = st.slider("Nombre de documents", min_value=1, max_value=10, value=3,
                help="Moins de documents = réponse plus rapide")
        
        # Display settings
        st.subheader("🎨 Affichage")
        show_sources = st.checkbox("Afficher les sources", value=True)
        st.session_state['show_sources'] = show_sources
        
        # Initialize button
        if st.button("🔄 Réinitialiser", type="primary", use_container_width=True):
            st.cache_resource.clear()
            st.session_state.clear()
            st.rerun()
        
        # Info
        st.divider()
        st.info("""
        💡 **Astuce:**
        - Posez des questions sur vos cours
        - L'assistant utilise vos documents pour répondre
        - Les réponses sont basées sur le contenu indexé
        """)
        
        # Status
        st.divider()
        st.caption("📊 Statistiques")
        if 'messages' in st.session_state:
            st.metric("Questions posées", len([m for m in st.session_state.messages if m['role'] == 'user']))
    
    # Initialize session state
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    
    # Initialize assistant
    try:
        with st.spinner("🚀 Initialisation de l'assistant..."):
            assistant = initialize_assistant(
                host=host if 'host' in locals() else 'localhost',
                port=port if 'port' in locals() else 6333,
                collection=collection if 'collection' in locals() else 'insa_docs',
                model=llm_model if 'llm_model' in locals() else 'phi',
                top_k=top_k if 'top_k' in locals() else 3
            )
        
        # Display success message once
        if 'assistant_ready' not in st.session_state:
            st.success("✅ Assistant prêt!")
            st.session_state['assistant_ready'] = True
            time.sleep(1)
            st.rerun()
        
    except Exception as e:
        st.error(f"❌ Erreur d'initialisation: {e}")
        st.info("""
        **Vérifiez que:**
        1. Qdrant est démarré: `docker start qdrant`
        2. Les documents sont indexés: `python3 Convert/embed_to_qdrant.py`
        3. Ollama est installé et un modèle est téléchargé: `ollama pull mistral`
        """)
        st.stop()
    
    # Main chat area
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("💬 Conversation")
    
    with col2:
        if st.button("🗑️ Effacer l'historique", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
    
    # Display chat history
    chat_container = st.container()
    with chat_container:
        for message in st.session_state.messages:
            display_message(
                message['role'],
                message['content'],
                message.get('sources')
            )
    
    # Chat input
    st.divider()
    
    # Example questions
    with st.expander("💡 Exemples de questions", expanded=False):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🖥️ Qu'est-ce qu'Apache2 ?", use_container_width=True):
                st.session_state.example_query = "Qu'est-ce qu'Apache2 et comment l'installer ?"
        
        with col2:
            if st.button("🔐 Expliquer la cryptographie", use_container_width=True):
                st.session_state.example_query = "Explique-moi les bases de la cryptographie"
        
        with col3:
            if st.button("🌐 Les réseaux TCP/IP", use_container_width=True):
                st.session_state.example_query = "Comment fonctionne le protocole TCP/IP ?"
    
    # User input
    user_query = st.chat_input("Posez votre question ici...")
    
    # Handle example query
    if 'example_query' in st.session_state:
        user_query = st.session_state.example_query
        del st.session_state.example_query
    
    # Process query
    if user_query:
        # Add user message
        st.session_state.messages.append({
            'role': 'user',
            'content': user_query
        })
        
        # Display user message immediately
        display_message('user', user_query)
        
        # Get assistant response
        with st.spinner("🤔 Recherche et génération de la réponse..."):
            try:
                # Retrieve documents
                documents = assistant.retrieve_documents(user_query)
                
                if not documents:
                    response_text = "❌ Aucun document pertinent trouvé pour cette question."
                    sources = None
                else:
                    # Generate answer
                    result = assistant.generate_answer(user_query, documents)
                    response_text = result['answer']
                    sources = result['sources']
                
                # Add assistant message
                st.session_state.messages.append({
                    'role': 'assistant',
                    'content': response_text,
                    'sources': sources
                })
                
                # Rerun to display the new message
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ Erreur lors de la génération de la réponse: {e}")


if __name__ == "__main__":
    main()
