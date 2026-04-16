# PDCA Cricket Rules Agent — Admin Guide

**Agent name:** `pdca-cricket-rules-agent`  
**Purpose:** Answers cricket rules queries for Parramatta District Cricket Association (PDCA) competitions using PDCA by-laws and MCC Laws of Cricket as its knowledge base.  
**Model:** gpt-4o (deployed in Azure AI Foundry)  
**Last updated:** April 2026

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Azure Resources](#2-azure-resources)
3. [Local Files](#3-local-files)
4. [How the Agent Works](#4-how-the-agent-works)
5. [Updating the FAQ Document](#5-updating-the-faq-document)
6. [Rebuilding the Search Index](#6-rebuilding-the-search-index)
7. [Recreating the Agent](#7-recreating-the-agent)
8. [Adding New Source Documents](#8-adding-new-source-documents)
9. [Known Rules and Corrections](#9-known-rules-and-corrections)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Architecture Overview

```
User question
     │
     ▼
Azure AI Foundry Agent (pdca-cricket-rules-agent)
     │  gpt-4o + system instructions
     │
     ▼
Azure AI Search (pdca-cricket-rules index)
     ├── 169 chunks — 14 PDCA PDFs (by-laws, playing conditions)
     ├── 106 chunks — 44 MCC Law pages (lords.org)
     └──   1 chunk  — Curated FAQ document (hand-maintained)
     │
     ▼
Top 7 relevant chunks returned to gpt-4o
     │
     ▼
Answer with source citations
```

**Key principle:** PDCA by-laws override MCC Laws where they conflict. The agent is instructed to check PDCA rules first, then fall back to MCC Laws.

---

## 2. Azure Resources

| Resource | Name | Type | Region | Resource Group |
|---|---|---|---|---|
| AI Foundry Hub | `msfoundryclaudetest` | CognitiveServices | East US | rg-claudefoundryproject |
| AI Foundry Project | `proj-default-claude` | CognitiveServices/project | East US | rg-claudefoundryproject |
| Model Deployment | `gpt-4o` (2024-11-20) | GlobalStandard 225K | East US | rg-claudefoundryproject |
| AI Search Service | `pdca-cricket-search` | Basic SKU | East US | rg-claudefoundryproject |
| Search Connection | `pdca-cricket-search-conn` | CognitiveSearch | — | Hub-level connection |

**Portal:** https://ai.azure.com  
**Search endpoint:** https://pdca-cricket-search.search.windows.net  
**Search index:** `pdca-cricket-rules`

---

## 3. Local Files

All files are in `C:\aitraining\claude-foundry-test\`

| File | Purpose |
|---|---|
| `.env` | API keys and endpoints — **never share or commit** |
| `requirements.txt` | Python dependencies |
| `build_index.py` | Rebuilds the entire Azure AI Search index from source documents |
| `create_pdca_agent.py` | Deletes and recreates the agent in Azure AI Foundry |
| `chat_pdca_agent.py` | Test the agent via Python (bypasses playground) |
| `chat_agent.py` | Simple chat without search grounding (for testing model only) |
| `docs/pdca/` | Downloaded PDCA PDF source files (14 documents) |
| `docs/pdca_extracted.json` | Extracted plain text from all PDCA PDFs |
| `docs/mcc_laws.json` | Scraped text from all 44 MCC Law pages (lords.org) |

### .env file contents

```
AZURE_AI_ENDPOINT=https://msfoundryclaudetest.services.ai.azure.com/api/projects/proj-default-claude
AZURE_AI_API_KEY=<key from ai.azure.com>
AZURE_SEARCH_ENDPOINT=https://pdca-cricket-search.search.windows.net
AZURE_SEARCH_ADMIN_KEY=<key from Azure portal>
AZURE_SEARCH_INDEX=pdca-cricket-rules
```

---

## 4. How the Agent Works

### Knowledge sources (indexed in Azure AI Search)

| Document | Source | What it covers |
|---|---|---|
| PDCA By-Laws and Competition Rules | parradca.com | Main 55-page rulebook — most comprehensive |
| PDCA General Competition Rules | parradca.com | Registration, eligibility, grading |
| PDCA Senior Cricket Rules | parradca.com | Senior-specific playing conditions |
| PDCA Junior Cricket Rules | parradca.com | Junior-specific rules |
| PDCA Stage 1 / 2 / 3 Cricket | parradca.com | Junior stage competition rules |
| PDCA T20 Playing Conditions | parradca.com | T20-specific rules (free hits, powerplay, etc.) |
| PDCA Female Cricket Rules | parradca.com | Female competition rules |
| PDCA Codes of Conduct | parradca.com | Player/team conduct |
| PDCA Guide for Player Umpires | parradca.com | Umpiring guide |
| PDCA Constitution | parradca.com | Association governance |
| PDCA Child Protection Policy | parradca.com | Safeguarding policy |
| MCC Laws 1–42 + Preamble | lords.org | Universal laws of cricket |
| **PDCA FAQ (hand-maintained)** | This project | Curated Q&A for complex/ambiguous rules |

### How chunking works

PDCA PDFs are split on rule section boundaries (e.g. `46.1`, `47 LATE REGISTRATION`). Each chunk is prefixed with the document name and includes a `rule_numbers` field listing every rule number found in that chunk. This lets the search engine match queries like "Rule 13.1" directly.

### Search configuration

- Query type: **Semantic** with the `default` configuration
- Top N documents: **7** chunks per query
- Strictness: **2** (moderate — allows slightly broader retrieval)
- Scoring: title × 3, rule_numbers × 2, content × 1

---

## 5. Updating the FAQ Document

FAQ documents bridge the gap between natural language questions and formal rule text. They are uploaded directly to the search index (not derived from PDFs) and must be re-uploaded after every index rebuild.

### Current FAQ documents

| ID | File | Topics covered |
|---|---|---|
| `pdca_faq_001` | `upload_faq.py` | Player eligibility and registration (Rules 10.3, 10.6, 13.1, 66) |
| `pdca_faq_002` | `upload_faq.py` | Discipline, fines, penalties, swearing rule, knockout exception |

### Current FAQ entries

**pdca_faq_001 — Eligibility:**
- Can a junior (e.g. U15) for Club A play senior for Club B? → **YES** (Rule 13.1)
- Can a junior play junior and senior on the same day? → **YES** (Rule 10.3)
- Default senior registration for a junior player (Rule 10.6)
- Can a senior adult play for two clubs? → **NO** without Board permit (Rule 13.1)

**pdca_faq_002 — Discipline:**
- Swearing penalty: flat 5 points to team (regardless of player count) + ban via Judiciary
- Knockout matches: no points penalty; ban only (points irrelevant in knockouts)
- Unknown penalties: directed to PDCA Judiciary / pdca.executive@gmail.com
- MCC Law 41/42 does NOT apply for PDCA discipline matters

### To add or edit FAQ entries

1. Open `upload_faq.py` in your editor
2. Find `FAQ_001` or `FAQ_002` (whichever is relevant) and edit the `content` string
3. Add new Q&A pairs using the `Q: ... A: ...` format
4. For a new topic area, copy the `FAQ_001` structure and use a new ID (`pdca_faq_003`, etc.) — add it to the `all_faqs` list at the bottom of the file
5. Run the script:

```bash
cd C:\aitraining\claude-foundry-test
python upload_faq.py
```

**Tips:**
- Use the same `id` to overwrite an existing document — do not change existing IDs
- Update `rule_numbers` in the document dict to include any new rule numbers referenced
- The `@search.action: mergeOrUpload` means re-running is safe — it upserts, not duplicates

---

## 6. Rebuilding the Search Index

Run this when PDCA publishes updated by-laws or MCC Laws change.

```bash
cd C:\aitraining\claude-foundry-test

# Step 1: Download updated PDCA PDFs (edit URLs in build_index.py if they change)
# Re-run the download section or manually replace files in docs/pdca/

# Step 2: Re-extract PDF text
python -c "
import pdfplumber, os, json
docs_dir = 'docs/pdca'
output = []
for filename in sorted(os.listdir(docs_dir)):
    if not filename.endswith('.pdf'): continue
    with pdfplumber.open(f'{docs_dir}/{filename}') as pdf:
        text = '\n'.join(page.extract_text() or '' for page in pdf.pages)
        output.append({'id': filename.replace('.pdf','').replace('.','_'),
                       'filename': filename, 'content': text.strip(),
                       'word_count': len(text.split())})
with open('docs/pdca_extracted.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f'Extracted {len(output)} documents')
"

# Step 3: Rebuild and upload the index (this deletes and recreates the index)
python build_index.py

# Step 4: Re-upload the FAQ document (index rebuild wipes it)
python upload_faq.py   # or paste the FAQ upload script above
```

> **Important:** `build_index.py` deletes and recreates the index from scratch. Always re-upload the FAQ document after rebuilding.

---

## 7. Recreating the Agent

Run this when you need to update the agent's instructions, model, or tool configuration.

```bash
cd C:\aitraining\claude-foundry-test
python create_pdca_agent.py
```

This deletes the existing agent and creates a new one. After recreating:
1. Go to **ai.azure.com** → your project → **Agents** → `pdca-cricket-rules-agent`
2. Click the **Azure AI Search** tool → **Configure**
3. Re-select the `pdca-cricket-search` instance and `pdca-cricket-rules` index
4. Save — the playground warning will disappear

> **Note:** The agent configuration (instructions, tools) is set in `create_pdca_agent.py`. The PATCH API does not reliably update an existing agent — always delete and recreate via this script.

---

## 8. Adding New Source Documents

To add a new PDCA document (e.g. a new playing condition PDF):

1. Download the PDF to `docs/pdca/`
2. Add an entry to `DOC_META` in `build_index.py`:
   ```python
   "new_document_id": ("Full Document Title for Indexing", "Short Category Name"),
   ```
3. Re-extract PDFs and rebuild the index (see Section 6)

To add a custom Q&A / correction without a PDF source, add it to the FAQ document (see Section 5).

---

## 9. Known Rules and Corrections

This section documents cases where the agent initially gave wrong answers and what the correct rule says. Use this as a checklist when testing after any rebuild.

### Junior player dual-club eligibility (corrected April 2026)

**Wrong answer the agent gave:**
> "Players are required to be registered with a single club for all competitions within the PDCA during a season."

**Correct answer:**
> A junior-qualified player CAN play junior cricket for Club A and senior cricket for Club B in the same PDCA season.

**Rules that apply:**
- **Rule 10.3** — Junior players are exempt from the same-date restriction (can play both junior and senior fixtures on the same day)
- **Rule 10.6** — By default, juniors are auto-registered in senior with the same club in the lowest grade available
- **Rule 13.1** — Explicitly carves out an exception for junior-qualified players to play for more than one PDCA club. Adult senior players cannot do this without Board permit and original club clearance.

**Why it went wrong:** The semantic search returned registration/grading chunks instead of the eligibility chunk (Rules 10 + 13). Fixed by adding a curated FAQ entry (`pdca_faq_001`) and updating the agent's system instructions to explicitly reference Rules 10 and 13 for eligibility questions.

---

## 10. Troubleshooting

### Agent says "I don't have information about that" when it should

1. Test the search index directly:
   ```bash
   cd C:\aitraining\claude-foundry-test
   python -c "
   import requests, os, json
   from dotenv import load_dotenv; load_dotenv()
   r = requests.post(
       os.getenv('AZURE_SEARCH_ENDPOINT') + '/indexes/pdca-cricket-rules/docs/search?api-version=2024-05-01-preview',
       headers={'api-key': os.getenv('AZURE_SEARCH_ADMIN_KEY'), 'Content-Type': 'application/json'},
       json={'search': 'YOUR QUERY HERE', 'top': 5, 'select': 'title,rule_numbers,content',
             'queryType': 'semantic', 'semanticConfiguration': 'default'}
   )
   for d in r.json()['value']:
       print(d['title'], '|', d['rule_numbers'][:60])
       print(d['content'][:200]); print()
   "
   ```
2. If the right rule isn't returned → add a FAQ entry (Section 5)
3. If the right rule IS returned but the agent ignores it → update the system instructions in `create_pdca_agent.py` and recreate the agent

### Agent gives wrong answer confidently (hallucination)

1. Identify the correct rule from the PDCA PDFs in `docs/pdca/`
2. Add a FAQ entry with the correct Q&A and rule reference
3. Log the correction in Section 9 of this guide

### Playground shows "Tools not configured" warning

1. Go to ai.azure.com → Agents → `pdca-cricket-rules-agent`
2. Click the Azure AI Search tool → Configure
3. Re-select the search instance (`pdca-cricket-search`) and index (`pdca-cricket-rules`)
4. This step is always required after recreating the agent via script

### API key expired or rotated

1. Go to **ai.azure.com** → project → **Settings → Keys and Endpoints** → Regenerate
2. For Search key: **Azure Portal** → `pdca-cricket-search` → **Keys**
3. Update `.env` with both new keys
4. No other action needed — scripts read from `.env` at runtime

### Index is empty after a rebuild

`build_index.py` deletes and recreates the index. If it fails mid-upload, re-run it. Always re-upload the FAQ document after (`pdca_faq_001`) since it is not part of `build_index.py`.
