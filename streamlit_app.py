"""
PDCA Cricket Rules Agent — Streamlit web UI.

Deploy to Streamlit Community Cloud (free):
  https://streamlit.io/cloud

Set these secrets in the Streamlit Cloud dashboard (Settings → Secrets):
  AZURE_AI_API_KEY = "..."
  AZURE_SEARCH_ENDPOINT = "..."
  AZURE_SEARCH_ADMIN_KEY = "..."
  AZURE_SEARCH_INDEX = "pdca-cricket-rules"
"""

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Config — reads from Streamlit secrets (cloud) or .env (local)
# ---------------------------------------------------------------------------
try:
    # Streamlit Cloud: secrets set in dashboard
    API_KEY = st.secrets["AZURE_AI_API_KEY"]
    SEARCH_ENDPOINT = st.secrets["AZURE_SEARCH_ENDPOINT"]
    SEARCH_KEY = st.secrets["AZURE_SEARCH_ADMIN_KEY"]
    INDEX_NAME = st.secrets["AZURE_SEARCH_INDEX"]
except (KeyError, FileNotFoundError):
    # Local dev: fall back to .env
    from dotenv import load_dotenv
    import os
    load_dotenv()
    API_KEY = os.getenv("AZURE_AI_API_KEY")
    SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
    SEARCH_KEY = os.getenv("AZURE_SEARCH_ADMIN_KEY")
    INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX")

HUB_BASE = "https://msfoundryclaudetest.services.ai.azure.com"
PROJECT_PATH = "/api/projects/proj-default-claude"
AGENT_NAME = "pdca-cricket-rules-agent"
API_VERSION_MGMT = "2025-11-15-preview"
API_VERSION_OPENAI = "2024-10-21"
HEADERS = {"api-key": API_KEY, "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Agent helpers
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_agent_instructions():
    r = requests.get(
        f"{HUB_BASE}{PROJECT_PATH}/agents/{AGENT_NAME}?api-version={API_VERSION_MGMT}",
        headers=HEADERS, timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    defn = data["versions"]["latest"]["definition"]
    return defn["instructions"], defn["model"]


def ask_agent(messages, model="gpt-4o"):
    payload = {
        "messages": messages,
        "data_sources": [
            {
                "type": "azure_search",
                "parameters": {
                    "endpoint": SEARCH_ENDPOINT,
                    "index_name": INDEX_NAME,
                    "authentication": {"type": "api_key", "key": SEARCH_KEY},
                    "query_type": "semantic",
                    "semantic_configuration": "default",
                    "top_n_documents": 7,
                    "in_scope": True,
                    "strictness": 2,
                },
            }
        ],
    }
    r = requests.post(
        f"{HUB_BASE}/openai/deployments/{model}/chat/completions?api-version={API_VERSION_OPENAI}",
        headers=HEADERS, json=payload, timeout=45,
    )
    r.raise_for_status()
    data = r.json()
    message = data["choices"][0]["message"]
    citations = message.get("context", {}).get("citations", [])
    return message["content"], citations


# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="PDCA Cricket Rules Assistant",
    page_icon="🏏",
    layout="centered",
)

st.title("🏏 PDCA Cricket Rules Assistant")
st.caption(
    "Ask anything about cricket rules for **Parramatta District Cricket Association (PDCA)** competitions. "
    "PDCA by-laws take precedence over MCC Laws where they conflict."
)

# Disclaimer
with st.expander("ℹ️ About this assistant"):
    st.markdown(
        """
        This assistant answers questions about cricket rules and regulations for **PDCA competitions only**.

        **Knowledge sources:**
        - PDCA By-Laws and Playing Conditions (parradca.com)
        - MCC Laws of Cricket (lords.org)

        **Scope:** Rules, playing conditions, eligibility, conduct, and regulations.
        **Out of scope:** Scores, fixtures, player stats, coaching advice.

        For official rulings contact PDCA: [pdca.executive@gmail.com](mailto:pdca.executive@gmail.com) | [parradca.com](https://parradca.com)
        """
    )

# Suggested questions
SUGGESTIONS = [
    "Can a junior U15 player for Club A also play senior cricket for Club B?",
    "What happens if a player swears at an umpire?",
    "How many overs in a senior PDCA one-day match?",
    "What is the free hit rule in PDCA T20?",
    "Can a player bat with a runner in PDCA cricket?",
]

st.markdown("**Try asking:**")
cols = st.columns(len(SUGGESTIONS))
for col, suggestion in zip(cols, SUGGESTIONS):
    if col.button(suggestion, use_container_width=True, key=suggestion):
        st.session_state.pending_question = suggestion

# ---------------------------------------------------------------------------
# Chat state
# ---------------------------------------------------------------------------
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []   # list of {"role": ..., "content": ...}

if "system_instructions" not in st.session_state:
    with st.spinner("Loading agent…"):
        instructions, model = load_agent_instructions()
    st.session_state.system_instructions = instructions
    st.session_state.model = model

# Render existing messages
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Handle suggestion button clicks
if "pending_question" in st.session_state:
    user_input = st.session_state.pop("pending_question")
else:
    user_input = st.chat_input("Ask a PDCA cricket rules question…")

# ---------------------------------------------------------------------------
# Handle new message
# ---------------------------------------------------------------------------
if user_input:
    # Show user message immediately
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Build message list for API (system + history)
    messages = [{"role": "system", "content": st.session_state.system_instructions}]
    messages.extend(st.session_state.chat_history)

    with st.chat_message("assistant"):
        with st.spinner("Looking up the rules…"):
            try:
                reply, citations = ask_agent(messages, model=st.session_state.model)
            except Exception as e:
                reply = f"Sorry, I encountered an error: {e}"
                citations = []

        st.markdown(reply)

        if citations:
            with st.expander(f"Sources ({len(citations)} documents retrieved)"):
                for i, c in enumerate(citations[:5], 1):
                    title = c.get("title", "Unknown document")
                    url = c.get("url", "")
                    st.markdown(f"**{i}.** {title}" + (f" — [{url}]({url})" if url else ""))

    st.session_state.chat_history.append({"role": "assistant", "content": reply})

# Clear chat button
if st.session_state.chat_history:
    if st.button("Clear chat", type="secondary"):
        st.session_state.chat_history = []
        st.rerun()
