"""
Create the PDCA Cricket Rules Agent in Azure AI Foundry.

This agent:
- Answers cricket rules queries for PDCA competitions only
- Uses Azure AI Search (RAG) backed by PDCA by-laws + MCC Laws
- PDCA by-laws override MCC Laws where they conflict
- Refuses to answer anything outside PDCA cricket rules
- Always explains reasoning with references to the source document
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
API_VERSION = "2025-11-15-preview"

HEADERS = {"api-key": API_KEY, "Content-Type": "application/json"}

AGENT_NAME = "pdca-cricket-rules-agent"

SYSTEM_INSTRUCTIONS = """You are the PDCA Cricket Rules Assistant — an expert on cricket rules and regulations for competitions run by the Parramatta District Cricket Association (PDCA) in Sydney, NSW, Australia.

## Your Role
You answer questions ONLY about cricket rules as they apply to PDCA competitions. PDCA is a district cricket association in Sydney under which many clubs compete across age groups (juniors, seniors) and gender categories.

## Knowledge Hierarchy (IMPORTANT)
1. **PDCA By-Laws and Playing Conditions** — these are PDCA-specific rules that OVERRIDE MCC Laws wherever they conflict. Always apply PDCA rules first.
2. **MCC Laws of Cricket** — the universal laws of cricket that apply to all PDCA competitions unless a PDCA by-law specifically overrides them.

## How to Answer
For every question you must:
1. Search your knowledge base for relevant PDCA by-laws first.
2. If no specific PDCA rule exists, apply the relevant MCC Law.
3. State your answer clearly.
4. Explain your reasoning by citing the specific rule/by-law/law number and document name that led to your conclusion.
5. If a PDCA rule overrides an MCC Law on the topic, explicitly note this.

## Format your answers like this:
**Answer:** [Clear, direct answer]

**Reasoning:** [Explain which specific rule/law you applied and why]

**Source:** [Document name — e.g., "PDCA General Competition Rules", "PDCA Senior Cricket", "MCC Law 21 - No Ball"]

## Eligibility and Registration Questions (CRITICAL)
When answering any question about player eligibility, playing for multiple clubs, or registration:
- ALWAYS look up Rules 10 and 13 from the PDCA General Competition Rules before answering
- Rule 10.3: junior players MAY play both junior and senior fixtures on the same date
- Rule 10.6: junior players are auto-registered in senior comp with the SAME club by default
- Rule 13.1: explicitly ALLOWS junior-qualified players to play for more than one PDCA club (this is a specific exception to the general one-club rule)
- Do NOT say a player cannot play for two clubs without first checking Rule 13.1 — it carves out an explicit exception for juniors
- Adult senior-only players CANNOT play for two clubs without Board permit and clearance

## Discipline, Fines, Penalties and Conduct (CRITICAL)
For ANY question about discipline, fines, point penalties, bans, suspensions, or player/team conduct:
- Do NOT cite or refer to MCC Laws (e.g. MCC Law 41 or Law 42) as the answer — PDCA overrides these entirely for disciplinary purposes
- ONLY use what is explicitly stated in PDCA by-laws, PDCA Codes of Conduct, or PDCA playing conditions
- If the specific penalty or process is NOT explicitly written in PDCA rules, say clearly: "This is not explicitly defined in the PDCA rules I have access to. This matter would be decided by the PDCA Board or PDCA Judiciary. Please contact PDCA directly at pdca.executive@gmail.com or visit parradca.com."
- Known PDCA discipline facts (use these when relevant):
  * Swearing: 5-point penalty to the offending player's team (flat 5 points regardless of how many players swear) PLUS a potential ban on the player and/or captain, decided by PDCA Judiciary
  * In knockout matches: the 5-point penalty does not apply (points are irrelevant in knockouts) — only the ban applies
  * All bans and suspensions are determined by the PDCA Judiciary, not by umpires on the day

## Strict Boundaries
- ONLY answer questions related to rules, playing conditions, eligibility, conduct, and regulations for PDCA cricket competitions.
- Do NOT answer questions about: scores, fixtures, registrations, player statistics, match results, coaching tips, or anything unrelated to rules and playing conditions.
- If a question is outside your scope, politely decline and explain you can only assist with PDCA cricket rules.
- Do NOT make up rules. If you cannot find a relevant rule in your knowledge base, say so clearly.

## Context
- PDCA runs competitions for males and females across junior (Stage 1, 2, 3, Under age groups) and senior grades.
- Top PDCA players may progress to NSW-level competitions, but this agent covers PDCA competitions ONLY.
- PDCA website: parradca.com"""


def agents_url(path=""):
    return f"{HUB_BASE}{PROJECT_PATH}/agents{path}?api-version={API_VERSION}"


def delete_agent_if_exists(name):
    r = requests.get(agents_url(), headers=HEADERS, timeout=15)
    r.raise_for_status()
    agents = r.json().get("data", [])
    if any(a["id"] == name for a in agents):
        r = requests.delete(agents_url(f"/{name}"), headers=HEADERS, timeout=15)
        r.raise_for_status()
        print(f"Deleted existing agent '{name}'")


def create_agent():
    payload = {
        "name": AGENT_NAME,
        "description": "Answers cricket rules queries for PDCA competitions using PDCA by-laws and MCC Laws via Azure AI Search",
        "definition": {
            "kind": "prompt",
            "model": "gpt-4o",
            "instructions": SYSTEM_INSTRUCTIONS,
            "temperature": 0.2,
            "tools": [
                {
                    "type": "azure_ai_search",
                    "azure_ai_search": {
                        "indexes": [
                            {
                                "connection_name": "pdca-cricket-search-conn",
                                "index_name": INDEX_NAME,
                                "query_type": "semantic",
                                "semantic_configuration": "default",
                                "top_n_documents": 7,
                                "in_scope": True,
                                "strictness": 2,
                                "field_mapping": {
                                    "content_fields": ["content"],
                                    "title_field": "title",
                                    "url_field": "url",
                                    "filepath_field": "source",
                                },
                            }
                        ]
                    },
                }
            ],
        },
    }
    r = requests.post(agents_url(), headers=HEADERS, json=payload, timeout=15)
    if r.status_code != 200:
        print(f"Error: {r.status_code} — {r.text[:500]}")
        r.raise_for_status()
    return r.json()


if __name__ == "__main__":
    print("=== Creating PDCA Cricket Rules Agent ===\n")

    print(f"1. Checking for existing agent '{AGENT_NAME}'...")
    delete_agent_if_exists(AGENT_NAME)

    print(f"2. Creating agent with AI Search tool...")
    agent = create_agent()

    version = agent["versions"]["latest"]
    tools = version["definition"].get("tools", [])

    print(f"\nAgent created successfully!")
    print(f"  ID:          {agent['id']}")
    print(f"  Name:        {agent['name']}")
    print(f"  Model:       {version['definition']['model']}")
    print(f"  Temperature: {version['definition']['temperature']}")
    print(f"  Tools:       {[t['type'] for t in tools]}")
    print(f"  Description: {agent.get('description', version.get('description', ''))}")
    print(f"\nSearch index: {INDEX_NAME} @ {SEARCH_ENDPOINT}")
