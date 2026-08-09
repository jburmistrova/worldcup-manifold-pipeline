"""Shared generation module for semantic cross-platform market matching
(ADR-0014): the "AG" half of RAG, an LLM reasoning over retrieved
candidates rather than just trusting the raw similarity score. Same
"worth extracting" reasoning as market_embeddings.py: explain_top_candidate_matches.py
and evaluate_candidate_matches.py both need the identical prompt/parsing
logic, or the evaluation numbers stop describing what the real deliverable
script actually produces.

Local Ollama, not an API: no credential plumbing anywhere in this project,
still true after this feature (see ADR-0014 for why, and why that's a
bigger reason than just avoiding cost). Requires `ollama serve` running
(`brew install ollama`) and the model already pulled
(`ollama pull qwen2.5:7b`, ~4.7GB, one-time), see requirements.md.

Prompt fields are passed in as (question, answer_text) pairs, not a single
pre-formatted string, on purpose. Two earlier, worse versions were tried
and rejected empirically, not assumed: a bare team name alone ("Spain")
gave the model no context and it refused to confirm even an exact,
correct match; a "question (answer)" parenthetical string made the model
read the appended team name as literally redundant, suspicious text and
again refused an exact match ("this includes '(Spain)' which is
redundant"). Two clearly labeled fields, "Market question: ..." and
"Specific answer: ...", fixed both failures on the identical test case,
confirmed by testing the same candidates all three ways before settling
on this format, not guessed.

MODEL_NAME is qwen2.5:7b, not the smaller 3b. Found necessary on the one
market this feature is actually evaluated against: the real outright-winner
market's own title is "2026 FIFA World Cup ⚽ | 🏆 Winner", a terse,
emoji-decorated label, not a full sentence, and qwen2.5:3b consistently
answered NONE on this exact, correct match even with an explicit prompt
instruction about terse/stylized titles added specifically to address it.
qwen2.5:7b got the identical case right immediately, correct reasoning,
~10-20s per call locally, confirmed by testing both models against the
identical prompt before choosing, not assumed a bigger model would help.

Not a clean fix, worth being honest about: at the default sampling
temperature, qwen2.5:7b answered this specific Spain case correctly 2 of 3
identical, back-to-back runs, and wrong once, real non-determinism found
by actually repeating the call, not assumed stable after one success. At
temperature=0 (see explain_match below) the model becomes fully
reproducible, but reproducibly picks the wrong answer on this one case,
every time. Reproducible-but-sometimes-wrong was chosen over
nondeterministic-but-more-often-right, because an eval harness whose
reported precision changes between two runs of the identical code isn't
one worth trusting, and evaluate_candidate_matches.py's real, full run
across all 46 positive/4 negative pairs (not just this one hand-picked
hard case) is what actually says whether this is representative or an
outlier, see docs/results.md's addendum for the real number.

The prompt explicitly allows "none of these candidates are a real match"
as a valid answer. Without that, this couldn't be evaluated for false
positives at all: the 4 known Polymarket-only teams in the outright-winner
group (Bosnia-Herzegovina, Peru, Qatar, Saudi Arabia) have no correct
Manifold match by construction, and a prompt that always forces a pick
would have no way to get those right, making the negative side of
evaluate_candidate_matches.py's eval meaningless by design, not just hard.
"""
import json
import re
import urllib.error
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:7b"

_ANSWER_RE = re.compile(r"ANSWER:\s*(NONE|\d+)", re.IGNORECASE)

PROMPT_TEMPLATE = """Two prediction-market platforms each have many yes/no \
markets about the 2026 World Cup. I need to find which market on Platform B \
refers to the exact same real-world question as this one on Platform A. \
Market titles are often terse and stylized (may include emoji, \
abbreviations, or a title-case label rather than a full sentence) rather \
than fully-formed questions, e.g. a market titled "World Cup Winner" \
means "who wins the tournament outright", not any other kind of \
advancement.

Platform A market question: {query_question}
Platform A specific answer/outcome being evaluated: {query_answer}

Here are {n} candidate markets from Platform B, each with a semantic \
similarity score (higher means more textually similar, not necessarily \
correct):

{candidates_block}

A high similarity score does not guarantee a correct match (e.g. a market \
about a team winning the tournament outright is a different question from \
one about the same team merely advancing past the group stage, even \
though the text looks similar). It is possible that NONE of the \
candidates ask the exact same question. If so, say so.

Give 1-3 sentences of reasoning, explicitly naming why you ruled out any \
close-but-wrong candidates. Then end your response with exactly one final \
line in this format, no other text on that line:
ANSWER: <candidate number, or NONE>
"""


def _format_candidate(question, answer_text):
    if answer_text is None:
        return question
    return f"{question} [{answer_text}]"


def _format_candidates(candidates):
    lines = []
    for i, (question, answer_text, score) in enumerate(candidates, start=1):
        lines.append(f"{i}. {_format_candidate(question, answer_text)} (score {score:.3f})")
    return "\n".join(lines)


def explain_match(query_question, query_answer_text, candidates):
    """candidates: list of (question, answer_text, cosine_similarity)
    tuples, already sorted by the caller (highest similarity first),
    typically top-5 from market_embeddings.top_k_similar. Returns
    {"pick_index": int | None, "reasoning": str}. pick_index is a 0-based
    index into `candidates`, or None when the model judges no candidate is
    a real match.

    Raises RuntimeError with a clear, actionable message on a connection
    failure (Ollama not running) or an unparseable response (the model
    didn't end with the required ANSWER: line) rather than silently
    guessing a pick or returning a partial result a caller might trust by
    accident.
    """
    prompt = PROMPT_TEMPLATE.format(
        query_question=query_question,
        query_answer=query_answer_text if query_answer_text is not None else query_question,
        n=len(candidates),
        candidates_block=_format_candidates(candidates),
    )

    # temperature=0 (greedy decoding): found necessary after the default
    # sampling temperature produced genuinely different ANSWER lines
    # across identical, back-to-back calls on the same hard case (2 of 3
    # runs correct, 1 of 3 wrong, same exact prompt), which would make
    # evaluate_candidate_matches.py's reported numbers unreproducible run
    # to run, not something worth trusting or defending. temperature=0
    # doesn't make the model *right*; it makes it consistently whatever it
    # is, which is the more honest and more useful property for an eval
    # harness. See this module's header docstring for the specific known
    # case (the outright-winner market's own terse, emoji-decorated title)
    # this doesn't fix even at temperature=0.
    payload = json.dumps(
        {"model": MODEL_NAME, "prompt": prompt, "stream": False, "options": {"temperature": 0}}
    ).encode()
    request = urllib.request.Request(
        OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read())
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not reach Ollama at {OLLAMA_URL} ({exc}). "
            "Is it running? Start it with `ollama serve` "
            f"and confirm `{MODEL_NAME}` is pulled with `ollama pull {MODEL_NAME}`."
        ) from exc

    text = body["response"].strip()
    match = _ANSWER_RE.search(text)
    if not match:
        raise RuntimeError(
            f"Could not parse an ANSWER: line out of the model's response for "
            f"{query_question!r} / {query_answer_text!r}. Full response:\n{text}"
        )

    raw_answer = match.group(1).upper()
    pick_index = None if raw_answer == "NONE" else int(raw_answer) - 1
    if pick_index is not None and not (0 <= pick_index < len(candidates)):
        raise RuntimeError(
            f"Model picked candidate {raw_answer} for {query_question!r}, "
            f"out of range for {len(candidates)} candidates. Full response:\n{text}"
        )

    return {"pick_index": pick_index, "reasoning": text}
