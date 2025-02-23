import streamlit as st
from utils.settings_utils import load_settings, save_settings
from utils.db_utils import save_history
from datetime import datetime
import os
from embedding import Embeddings
from langchain_chroma import Chroma
from langchain_openai import AzureChatOpenAI
from langchain.chains import RetrievalQA
from langchain.prompts import ChatPromptTemplate
from dotenv import load_dotenv

load_dotenv()

azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")
azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
azure_api_version = os.getenv("AZURE_OPENAI_API_VERSION")
azure_deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")


def question_page(user_path, username):
    settings = load_settings(user_path)
    st.title("RAG Question Page")

    # --- Sidebar Settings ---
    st.sidebar.header("Settings")

    k = st.sidebar.slider("Documents to retrieve (k)", 1,
                          20, settings["k"], key="k_slider")

    st.sidebar.write("Score threshold")
    score_threshold = st.sidebar.slider(
        " ", 0.0, 1.0, settings["score_threshold"], step=0.01, key="score_slider")

    # Embedding model
    embedding_model = st.sidebar.text_input(
        "Embedding model name", settings["embedding_model"], key="embedding_model_q")

    # HuggingFace token
    hf_token = st.sidebar.text_input(
        "HuggingFace API token", settings["hf_token"], type="password", key="hf_token_q")

    # Save Settings Button
    if st.sidebar.button("Save Settings"):
        settings.update({
            "k": k,
            "score_threshold": score_threshold,
            "embedding_model": embedding_model,
            "hf_token": hf_token
        })
        save_settings(user_path, settings)
        st.success("Settings saved successfully!")

    # --- Main Content ---
    st.header("System Prompt")
    system_prompt = st.text_area(
        "Define system instructions", value=settings["system_prompt"], key="system_prompt")

    query = st.text_input("Enter your query", "")

    if st.button("Submit") and query:
        # Vector DB Initialization
        vector_db = Chroma(
            persist_directory=settings["db_dir"],
            embedding_function=Embeddings(
                model_name=embedding_model, hf_token=hf_token)
        )

        retriever = vector_db.as_retriever(search_type="similarity_score_threshold", search_kwargs={
            "score_threshold": score_threshold, "k": k
        })

        # Azure LLM
        llm = AzureChatOpenAI(
            azure_endpoint=azure_endpoint,
            api_version=azure_api_version,
            azure_deployment=azure_deployment_name,
            api_key=azure_api_key,
            model="gpt-4o"
        )

        # Prompt Template
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "質問: {question}\n\n関連する情報: {context}\n\n回答:")
        ])

        qa_chain = RetrievalQA.from_chain_type(
            llm,
            retriever=retriever,
            return_source_documents=True,
            chain_type="stuff",
            chain_type_kwargs={"prompt": prompt_template,
                               "document_variable_name": "context"}
        )

        # Query Execution
        response = qa_chain.invoke({"query": query})
        answer = response.get("result", "No valid response found.")

        # Display Response
        st.subheader("Response")
        st.markdown(
            f"<div style='border:1px solid #d3d3d3; padding: 10px; border-radius: 5px;'>{answer}</div>",
            unsafe_allow_html=True
        )

        # Display Retrieved Documents
        with st.expander("Retrieved Documents with Scores", expanded=False):
            retrieved_docs = retriever.invoke(query)
            for i, doc in enumerate(retrieved_docs):
                document_name = doc.metadata.get('source', 'Unknown Document')
                chunk_number = doc.metadata.get('chunk_number', 'N/A')
                st.write(f"**Document {i + 1}:**")
                st.write(
                    f"**Source:** {document_name} | **Chunk:** {chunk_number}")
                st.write(doc.page_content)
                st.write(
                    f"Relevance score: {doc.metadata.get('relevance_score', 'N/A')}")

        # Save Query History
        history_entry = {
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "system_prompt": system_prompt,
            "settings": {
                "k": k,
                "score_threshold": score_threshold,
                "embedding_model": embedding_model
            },
            "response": answer,
            "username": username,
            "retrieved_docs": [
                {
                    "content": str(doc.page_content),
                    "score": doc.metadata.get(
                        'relevance_score', 'N/A'),
                    "document_name": doc.metadata.get('source', 'Unknown Document'),
                    "chunk_number": doc.metadata.get('chunk_number', 'N/A')
                }
                for doc in retrieved_docs
            ]
        }
        save_history(user_path, history_entry)

        st.success("Query executed and history saved successfully.")
