"""AI-generated comprehension quizzes from a video transcript, via the Claude API."""
import json

from . import config

QUIZ_PROMPT = """You are writing a short comprehension quiz for an electrical trade apprentice \
who just watched a training video. Base every question ONLY on the transcript below \
(do not invent facts not present in it). Cover practical steps, safety points, and any \
regulations/standards mentioned.

Write exactly {n} multiple-choice questions. Each question has exactly 4 options, only one correct.

Respond with ONLY valid JSON, no other text, in this exact shape:
[
  {{"question": "...", "choices": ["...", "...", "...", "..."], "correct_index": 0}}
]

Transcript:
{transcript}
"""


def generate_quiz(transcript_text, n=5):
    """Returns a list of {question, choices, correct_index} dicts, or raises on failure."""
    api_key = config.anthropic_api_key()
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set — add it to .env to enable quiz generation."
        )

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    prompt = QUIZ_PROMPT.format(n=n, transcript=transcript_text[:20000])

    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw_text = "".join(block.text for block in response.content if block.type == "text").strip()

    # Model may wrap in a code fence despite instructions; strip if present.
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    questions = json.loads(raw_text)
    for q in questions:
        if len(q["choices"]) != 4 or not (0 <= q["correct_index"] < 4):
            raise ValueError(f"Malformed question from model: {q}")
    return questions
