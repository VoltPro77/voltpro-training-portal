"""'Ask the Regs' — answers staff questions from the extracted text of indexed regulation
documents (AS/NZS 3000, AS/NZS 3008, etc. — see scripts/extract_regulations.py), never
general training knowledge. Simple keyword-overlap retrieval (no vector DB) is plenty at
this corpus size (~600 page-chunks) — swap for embeddings-based search later if recall
quality becomes a problem as the corpus grows.
"""
import json
import math
import re

from . import config
from .models import RegulationChunk

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "of", "to", "in",
    "for", "on", "with", "as", "by", "at", "from", "and", "or", "what", "when",
    "where", "how", "does", "do", "i", "it", "this", "that", "there", "can", "if",
    "my", "you", "your",
}


def _tokenize(text):
    return [w for w in re.findall(r"[a-z0-9.]+", text.lower()) if w not in STOPWORDS and len(w) > 1]


def _load_index():
    """Tokenize every chunk once per call and compute document frequency per term.

    Without IDF weighting, generic words that saturate a whole section (e.g. "earth",
    "minimum", "conductor" appear on nearly every earthing page) drown out the specific
    terms that actually disambiguate a question (e.g. "depth", "electrode"), pushing the
    real answer page just outside the top-N cutoff. IDF fixes that by discounting terms
    that appear in many chunks.
    """
    chunks = RegulationChunk.query.all()
    chunk_terms = {(c.source, c.printed_page): _tokenize(c.text) for c in chunks}
    doc_freq = {}
    for terms in chunk_terms.values():
        for term in set(terms):
            doc_freq[term] = doc_freq.get(term, 0) + 1
    return chunks, chunk_terms, doc_freq


def search_chunks(question, top_hits=8, neighbor_window=1, max_chunks=16):
    """TF-IDF-ish keyword search, then widen to neighboring pages (within the same source
    document) of each strong hit.

    Table/figure-heavy pages (mostly numbers, little repeated prose) score poorly on
    keyword overlap even when they're the actual answer — e.g. Table 5.1 itself barely
    matches "earth conductor size" as text, while the clause pages either side of it that
    introduce/reference the table score highly. Pulling in neighbors catches this without
    needing real semantic search.
    """
    terms = _tokenize(question)
    if not terms:
        return []

    chunks, chunk_terms, doc_freq = _load_index()
    n_chunks = len(chunks)
    all_chunks = {(c.source, c.printed_page): c for c in chunks}

    idf = {
        term: math.log((n_chunks + 1) / (doc_freq.get(term, 0) + 1)) + 1 for term in set(terms)
    }

    scored = []
    for key, page_terms in chunk_terms.items():
        if not page_terms:
            continue
        term_counts = {}
        for t in page_terms:
            term_counts[t] = term_counts.get(t, 0) + 1
        score = sum(term_counts.get(term, 0) * idf[term] for term in terms)
        if score > 0:
            scored.append((score, key))

    scored.sort(key=lambda pair: pair[0], reverse=True)

    keys_to_include = []
    for _, (source, page) in scored[:top_hits]:
        for p in range(page - neighbor_window, page + neighbor_window + 1):
            key = (source, p)
            if key in all_chunks and key not in keys_to_include:
                keys_to_include.append(key)
            if len(keys_to_include) >= max_chunks:
                break
        if len(keys_to_include) >= max_chunks:
            break

    keys_to_include.sort()
    return [all_chunks[k] for k in keys_to_include]


ANSWER_PROMPT = """You are answering a question from an electrical apprentice/tradesperson \
about Australian electrical standards, for VoltPro, an Australian electrical contractor.

Answer ONLY using the excerpts below — they are the only source of truth you have. If the \
excerpts don't clearly answer the question, say so plainly rather than guessing or using \
general knowledge. Be concise and practical. Reference which document and page(s) your \
answer draws from.

Respond with ONLY valid JSON, no other text, in this exact shape:
{{"answer": "...", "citations": [{{"source": "AS/NZS 3000:2018", "page": 278}}], "found_clear_answer": true}}

Excerpts:
{excerpts}

Question: {question}
"""


def answer_question(question):
    """Returns {answer, citations, found_clear_answer}. Raises on API/config failure."""
    api_key = config.anthropic_api_key()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set — add it to .env to enable Ask the Regs.")

    chunks = search_chunks(question)
    if not chunks:
        return {
            "answer": "I couldn't find anything in the indexed standards matching that question. Try rephrasing, or ask a supervisor.",
            "citations": [],
            "found_clear_answer": False,
        }

    excerpts = "\n\n".join(
        f"--- {c.source}, page {c.printed_page} ---\n{c.text}" for c in chunks
    )

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1000,
        messages=[{"role": "user", "content": ANSWER_PROMPT.format(excerpts=excerpts, question=question)}],
    )
    raw_text = "".join(block.text for block in response.content if block.type == "text").strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    return json.loads(raw_text)
