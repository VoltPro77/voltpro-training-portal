"""AI-generated comprehension quizzes from a video transcript, via the Claude API.

Optionally blends in AS/NZS regulation questions — grounded in real extracted document
text via regs.search_chunks() (the same retrieval Ask the Regs uses), never invented from
general knowledge. If nothing in the indexed standards clearly relates to a video's topic,
no regulation questions are added rather than guessing.
"""
import json

from . import config
from .regs import search_chunks

VIDEO_QUESTIONS_BLOCK = """You are writing a short comprehension quiz for an electrical trade apprentice \
who just watched a training video. Base every question ONLY on the transcript below \
(do not invent facts not present in it). Cover practical steps, safety points, and any \
regulations/standards mentioned in the video itself.

Write exactly {n} multiple-choice questions about the video content. Each question has \
exactly 4 options, only one correct.

Transcript:
{transcript}
"""

REG_QUESTIONS_BLOCK = """
You may also add up to {reg_n} further multiple-choice questions testing AS/NZS wiring \
rules relevant to this video's topic — but ONLY using the excerpts below as your source. \
Do not use outside knowledge and do not guess at any number, size, or value that isn't \
explicitly stated in the excerpts. If the excerpts don't clearly and specifically support \
a solid, unambiguous question about this video's topic, add zero regulation questions — \
a weak or speculative regulation question is worse than none.

Regulation excerpts:
{excerpts}
"""

RESPONSE_FORMAT_BLOCK = """
Respond with ONLY valid JSON, no other text, in this exact shape:
[
  {{"question": "...", "choices": ["...", "...", "...", "..."], "correct_index": 0, "source": "video"}}
]
Set "source" to "video" for questions based on the transcript, or "regulation" for questions \
based on the regulation excerpts.
"""


def _call_claude(prompt):
    api_key = config.anthropic_api_key()
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set — add it to .env to enable quiz generation."
        )

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw_text = "".join(block.text for block in response.content if block.type == "text").strip()

    # Model may wrap in a code fence despite instructions; strip if present.
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()
    return raw_text


def generate_quiz(transcript_text, video_title=None, n=5, reg_n=2):
    """Returns a list of {question, choices, correct_index, source} dicts, or raises on failure.

    When video_title is given, looks up relevant AS/NZS excerpts for that topic and asks the
    model to add a couple of regulation questions grounded strictly in that real text — the
    same retrieval Ask the Regs uses, so answers stay tied to what's actually indexed rather
    than the model's general knowledge.
    """
    prompt = VIDEO_QUESTIONS_BLOCK.format(n=n, transcript=transcript_text[:20000])

    if video_title:
        chunks = search_chunks(video_title, top_hits=5, neighbor_window=1, max_chunks=8)
        if chunks:
            excerpts = "\n\n".join(
                f"--- {c.source}, page {c.printed_page} ---\n{c.text}" for c in chunks
            )
            prompt += REG_QUESTIONS_BLOCK.format(reg_n=reg_n, excerpts=excerpts)

    prompt += RESPONSE_FORMAT_BLOCK

    raw_text = _call_claude(prompt)
    questions = json.loads(raw_text)
    for q in questions:
        if len(q["choices"]) != 4 or not (0 <= q["correct_index"] < 4):
            raise ValueError(f"Malformed question from model: {q}")
        q.setdefault("source", "video")
    return questions
