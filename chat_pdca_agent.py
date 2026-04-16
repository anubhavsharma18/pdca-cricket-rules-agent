"""
Chat with the PDCA Cricket Rules Agent.

Uses the OpenAI-compatible endpoint with the agent's system instructions
and Azure AI Search grounding via on_your_data configuration.
"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

HUB_BASE = "https://msfoundryclaudetest.services.ai.azure.com"
PROJECT_PATH = "/api/projects/proj-default-claude"
API_KEY = os.getenv("AZURE_AI_API_KEY")
SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
SEARCH_KEY = os.getenv("AZURE_SEARCH_ADMIN_KEY")
INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX")
API_VERSION_MGMT = "2025-11-15-preview"
API_VERSION_OPENAI = "2024-10-21"
AGENT_NAME = "pdca-cricket-rules-agent"

HEADERS = {"api-key": API_KEY, "Content-Type": "application/json"}


def get_agent_instructions(agent_name):
    r = requests.get(
        f"{HUB_BASE}{PROJECT_PATH}/agents/{agent_name}?api-version={API_VERSION_MGMT}",
        headers=HEADERS, timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    defn = data["versions"]["latest"]["definition"]
    return defn["instructions"], defn["model"]


def chat(messages, model="gpt-4o"):
    """
    Chat with grounding from Azure AI Search (PDCA + MCC rules index).
    Uses the on_your_data extension to inject search results as context.
    """
    payload = {
        "messages": messages,
        "data_sources": [
            {
                "type": "azure_search",
                "parameters": {
                    "endpoint": SEARCH_ENDPOINT,
                    "index_name": INDEX_NAME,
                    "authentication": {
                        "type": "api_key",
                        "key": SEARCH_KEY,
                    },
                    "query_type": "semantic",
                    "semantic_configuration": "default",
                    "top_n_documents": 5,
                    "in_scope": True,
                    "strictness": 3,
                },
            }
        ],
    }

    r = requests.post(
        f"{HUB_BASE}/openai/deployments/{model}/chat/completions?api-version={API_VERSION_OPENAI}",
        headers=HEADERS,
        json=payload,
        timeout=45,
    )
    r.raise_for_status()
    data = r.json()
    message = data["choices"][0]["message"]
    reply = message["content"]
    citations = message.get("context", {}).get("citations", [])
    usage = data.get("usage", {})
    return reply, citations, usage


if __name__ == "__main__":
    print(f"Loading agent '{AGENT_NAME}'...")
    instructions, model = get_agent_instructions(AGENT_NAME)
    print(f"  Model: {model}\n")
    print("=" * 70)

    history = [{"role": "system", "content": instructions}]

    test_questions = [
        "How many overs are bowled in a senior PDCA one-day match?",
        "What happens if a bowler bowls a no-ball in PDCA cricket? Is there a free hit?",
        "Can a PDCA team use a substitute fielder, and under what conditions?",
        "What is the PDCA rule if a match cannot be completed due to rain?",
    ]

    for question in test_questions:
        print(f"\nQ: {question}")
        print("-" * 70)
        history.append({"role": "user", "content": question})

        reply, citations, usage = chat(history, model=model)
        history.append({"role": "assistant", "content": reply})

        print(reply)

        if citations:
            print(f"\n  [Sources used: {len(citations)}]")
            for c in citations[:3]:
                print(f"    - {c.get('title', 'Unknown')} (score: {c.get('rerank_score', 'n/a')})")

        print(f"  (tokens: {usage.get('total_tokens', '?')})")
        print("=" * 70)
