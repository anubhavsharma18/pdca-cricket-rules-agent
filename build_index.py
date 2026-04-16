"""
Build Azure AI Search index with PDCA by-laws and MCC Laws of Cricket.

v2 improvements:
- Rule-aware chunking: splits on section numbers (46.1, 47.2 etc.)
- Each chunk prefixed with document name + rule context
- Separate searchable field for rule_numbers found in chunk
- MCC law chunks prefixed with law name for better grounding
"""

import os
import json
import re
from dotenv import load_dotenv
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SimpleField,
    SearchableField,
    SemanticConfiguration,
    SemanticSearch,
    SemanticPrioritizedFields,
    SemanticField,
    ScoringProfile,
    TextWeights,
)
from azure.core.credentials import AzureKeyCredential

load_dotenv()

SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
SEARCH_KEY = os.getenv("AZURE_SEARCH_ADMIN_KEY")
INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX")

credential = AzureKeyCredential(SEARCH_KEY)
index_client = SearchIndexClient(endpoint=SEARCH_ENDPOINT, credential=credential)


def create_index():
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name="en.lucene"),
        SearchableField(name="title", type=SearchFieldDataType.String, analyzer_name="en.lucene"),
        SearchableField(name="rule_numbers", type=SearchFieldDataType.String, analyzer_name="en.lucene"),
        SimpleField(name="source", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="category", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="url", type=SearchFieldDataType.String),
    ]

    semantic_config = SemanticConfiguration(
        name="default",
        prioritized_fields=SemanticPrioritizedFields(
            title_field=SemanticField(field_name="title"),
            keywords_fields=[SemanticField(field_name="rule_numbers")],
            content_fields=[SemanticField(field_name="content")],
        ),
    )

    # Boost title and rule_numbers fields in scoring
    scoring_profile = ScoringProfile(
        name="pdca-boost",
        text_weights=TextWeights(weights={"title": 3.0, "rule_numbers": 2.0, "content": 1.0}),
    )

    index = SearchIndex(
        name=INDEX_NAME,
        fields=fields,
        semantic_search=SemanticSearch(configurations=[semantic_config]),
        scoring_profiles=[scoring_profile],
        default_scoring_profile="pdca-boost",
    )

    try:
        index_client.delete_index(INDEX_NAME)
        print(f"Deleted existing index '{INDEX_NAME}'")
    except Exception:
        pass

    index_client.create_index(index)
    print(f"Created index '{INDEX_NAME}'")


def clean_text(text):
    text = re.sub(r'[^\x20-\x7E\n]', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


def extract_rule_numbers(text):
    """Extract PDCA rule numbers (e.g. 46.1, 47.2) and MCC law refs from text."""
    patterns = [
        r'\b(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)\b',   # 46.1, 46.1.2
        r'\bRule\s+(\d+(?:\.\d+)?)\b',               # Rule 46.1
        r'\bLaw\s+(\d+(?:\.\d+)?)\b',                # Law 24.1
        r'\b(Law\s+\d+)\b',                           # Law 24
    ]
    numbers = []
    for p in patterns:
        numbers.extend(re.findall(p, text, re.IGNORECASE))
    return ' '.join(sorted(set(numbers)))


def rule_aware_chunk(text, doc_title, max_words=500):
    """
    Split text on rule section boundaries (e.g. '46.1', '47 LATE REGISTRATION').
    Each chunk is prefixed with the document title and leading rule number.
    Falls back to word-count chunking if no rule numbers found.
    """
    # Detect rule section starts: lines beginning with a number like "46.1" or "47 TITLE"
    section_pattern = re.compile(
        r'(?:^|\n)(\d{1,2}(?:\.\d{1,2})?\s+[A-Z][^\n]{3,}|\d{1,2}\.\d{1,2}[^\n]*)',
        re.MULTILINE
    )

    splits = [(m.start(), m.group().strip()) for m in section_pattern.finditer(text)]

    if len(splits) < 3:
        # Fallback: word-count chunks with overlap
        words = text.split()
        chunks = []
        step = max_words - 60
        for i in range(0, len(words), step):
            chunk_words = words[i:i + max_words]
            chunk = ' '.join(chunk_words)
            if len(chunk.strip()) > 80:
                chunks.append(f"[{doc_title}]\n{chunk}")
            if i + max_words >= len(words):
                break
        return chunks

    # Build chunks from section splits, merging small sections
    chunks = []
    current_parts = []
    current_words = 0
    current_header = doc_title

    def flush(parts, header):
        combined = '\n'.join(parts).strip()
        if len(combined.split()) > 40:
            return f"[{doc_title}]\n{combined}"
        return None

    for idx, (pos, header) in enumerate(splits):
        next_pos = splits[idx + 1][0] if idx + 1 < len(splits) else len(text)
        section_text = text[pos:next_pos].strip()
        section_words = len(section_text.split())

        if current_words + section_words > max_words and current_parts:
            chunk = flush(current_parts, current_header)
            if chunk:
                chunks.append(chunk)
            current_parts = [section_text]
            current_words = section_words
            current_header = header
        else:
            current_parts.append(section_text)
            current_words += section_words
            if not current_header or current_header == doc_title:
                current_header = header

    if current_parts:
        chunk = flush(current_parts, current_header)
        if chunk:
            chunks.append(chunk)

    return chunks if chunks else [f"[{doc_title}]\n{text}"]


def load_pdca_docs():
    with open("C:/aitraining/claude-foundry-test/docs/pdca_extracted.json", encoding="utf-8") as f:
        return json.load(f)


def load_mcc_laws():
    with open("C:/aitraining/claude-foundry-test/docs/mcc_laws.json", encoding="utf-8") as f:
        return json.load(f)


DOC_META = {
    "pdca_rules":               ("PDCA By-Laws and Competition Rules", "PDCA By-Laws"),
    "pdca_constitution":        ("PDCA Constitution", "PDCA Constitution"),
    "guide_player_umpires":     ("PDCA Guide for Player Umpires Captains and Managers", "PDCA Umpires Guide"),
    "codes_of_conduct":         ("PDCA Codes of Conduct", "PDCA Code of Conduct"),
    "junior_cricket":           ("PDCA Junior Cricket Rules", "PDCA Junior Cricket"),
    "stage1_cricket":           ("PDCA Stage 1 Cricket Rules", "PDCA Stage 1 Cricket"),
    "stage2_cricket":           ("PDCA Stage 2 Cricket Rules", "PDCA Stage 2 Cricket"),
    "stage3_cricket":           ("PDCA Stage 3 Cricket Rules", "PDCA Stage 3 Cricket"),
    "general_competition_rules":("PDCA General Competition Rules", "PDCA General Competition"),
    "t20_playing_conditions":   ("PDCA T20 Playing Conditions", "PDCA T20"),
    "senior_cricket":           ("PDCA Senior Cricket Competition Rules", "PDCA Senior Cricket"),
    "female_cricket":           ("PDCA Female Cricket Rules", "PDCA Female Cricket"),
    "association_child_protection": ("PDCA Child Protection and Safeguarding Policy", "PDCA Child Protection"),
    "member_protection_declaration": ("PDCA Member Protection Declaration", "PDCA Member Protection"),
}

MCC_LAW_TITLES = {
    "preamble": "MCC Preamble - Spirit of Cricket",
    "law1": "MCC Law 1 - The Players",
    "law2": "MCC Law 2 - The Umpires",
    "law3": "MCC Law 3 - The Scorers",
    "law4": "MCC Law 4 - The Ball",
    "law5": "MCC Law 5 - The Bat",
    "law6": "MCC Law 6 - The Pitch",
    "law7": "MCC Law 7 - The Creases",
    "law8": "MCC Law 8 - The Wickets",
    "law9": "MCC Law 9 - Preparation and Maintenance of Playing Area",
    "law10": "MCC Law 10 - Covering the Pitch",
    "law11": "MCC Law 11 - Intervals",
    "law12": "MCC Law 12 - Start and Cessation of Play",
    "law13": "MCC Law 13 - Innings",
    "law14": "MCC Law 14 - The Follow-On",
    "law15": "MCC Law 15 - Declaration and Forfeiture",
    "law16": "MCC Law 16 - The Result",
    "law17": "MCC Law 17 - The Over",
    "law18": "MCC Law 18 - Scoring Runs",
    "law19": "MCC Law 19 - Boundaries",
    "law20": "MCC Law 20 - Dead Ball",
    "law21": "MCC Law 21 - No Ball",
    "law22": "MCC Law 22 - Wide Ball",
    "law23": "MCC Law 23 - Bye and Leg Bye",
    "law24": "MCC Law 24 - Fielders Absence and Substitutes",
    "law25": "MCC Law 25 - Batters Innings and Runners",
    "law26": "MCC Law 26 - Practice on the Field",
    "law27": "MCC Law 27 - The Wicket-Keeper",
    "law28": "MCC Law 28 - The Fielder",
    "law29": "MCC Law 29 - The Wicket is Down",
    "law30": "MCC Law 30 - Batter Out of Ground",
    "law31": "MCC Law 31 - Appeals",
    "law32": "MCC Law 32 - Bowled",
    "law33": "MCC Law 33 - Caught",
    "law34": "MCC Law 34 - Hit the Ball Twice",
    "law35": "MCC Law 35 - Hit Wicket",
    "law36": "MCC Law 36 - Leg Before Wicket",
    "law37": "MCC Law 37 - Obstructing the Field",
    "law38": "MCC Law 38 - Run Out",
    "law39": "MCC Law 39 - Stumped",
    "law40": "MCC Law 40 - Timed Out",
    "law41": "MCC Law 41 - Unfair Play",
    "law42": "MCC Law 42 - Players Conduct",
    "appendices": "MCC Laws Appendices",
}


def build_documents():
    docs = []

    # --- PDCA Documents ---
    for doc in load_pdca_docs():
        doc_id = doc["id"]
        full_title, short_title = DOC_META.get(doc_id, (doc["filename"], doc["filename"]))
        text = clean_text(doc["content"])
        chunks = rule_aware_chunk(text, full_title, max_words=500)

        for i, chunk in enumerate(chunks):
            rule_nums = extract_rule_numbers(chunk)
            docs.append({
                "id": f"pdca_{doc_id}_{i:03d}",
                "title": f"{full_title} — section {i+1}",
                "content": chunk,
                "rule_numbers": rule_nums,
                "source": "PDCA",
                "category": short_title,
                "url": "https://www.parradca.com/pdca-rules-policies",
            })

    # --- MCC Laws ---
    for law in load_mcc_laws():
        law_id = law["id"]
        title = MCC_LAW_TITLES.get(law_id, law_id)
        text = clean_text(law["content"])

        # Strip nav/boilerplate from MCC pages (common repeated text)
        text = re.sub(r'MCC\s+Laws\s+of\s+Cricket.*?(?=\d+\.\d+|\Z)', '', text, flags=re.DOTALL | re.IGNORECASE)

        chunks = rule_aware_chunk(text, title, max_words=500)
        for i, chunk in enumerate(chunks):
            rule_nums = extract_rule_numbers(chunk)
            docs.append({
                "id": f"mcc_{law_id}_{i:03d}",
                "title": f"{title} — section {i+1}",
                "content": chunk,
                "rule_numbers": rule_nums,
                "source": "MCC",
                "category": title,
                "url": f"https://www.lords.org/mcc/the-laws/{law['slug']}",
            })

    return docs


def upload_documents(docs, batch_size=100):
    search_client = SearchClient(
        endpoint=SEARCH_ENDPOINT,
        index_name=INDEX_NAME,
        credential=credential,
    )
    total = 0
    for i in range(0, len(docs), batch_size):
        batch = docs[i: i + batch_size]
        result = search_client.upload_documents(documents=batch)
        succeeded = sum(1 for r in result if r.succeeded)
        total += succeeded
        print(f"  Batch {i // batch_size + 1}: {succeeded}/{len(batch)} uploaded")
    return total


if __name__ == "__main__":
    print("=== Rebuilding PDCA Cricket Rules Search Index (v2) ===\n")

    print("1. Creating index...")
    create_index()

    print("\n2. Building documents...")
    docs = build_documents()
    pdca_count = sum(1 for d in docs if d["source"] == "PDCA")
    mcc_count = sum(1 for d in docs if d["source"] == "MCC")
    print(f"   PDCA chunks : {pdca_count}")
    print(f"   MCC chunks  : {mcc_count}")
    print(f"   Total       : {len(docs)}")

    # Show sample to verify quality
    print("\nSample chunks:")
    for d in docs[:2]:
        print(f"  [{d['category']}] {d['title']}")
        print(f"  Rules: {d['rule_numbers'][:80]}")
        print(f"  Content: {d['content'][:200]}")
        print()

    print("3. Uploading...")
    total = upload_documents(docs)
    print(f"\nDone. {total} chunks indexed in '{INDEX_NAME}'")
