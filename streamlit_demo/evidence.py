"""Conservative source evidence adapted from the notebook; not model citations."""
import re
import html

TOKEN = re.compile(r"\d+(?:\.\d+)?|[a-z]+", re.I)
STOP = set("a an the was were is are be been being with of and or in on at to for by from it this that as had has have patient what which how did does do".split())
NEGATION = {"no", "not", "without", "denies", "denied", "never"}
HEADINGS = re.compile(r"(?m)^[A-Za-z][A-Za-z0-9 /_()&-]{1,79}:[ \t]*")

def terms(text):
    return [m.group().lower() for m in TOKEN.finditer(text)]

def source_sentences(text):
    """Yield exact source offsets, including notes without recognizable headings."""
    headings = list(HEADINGS.finditer(text))
    sections = [("Unsectioned text", 0, headings[0].start() if headings else len(text))]
    sections += [(m.group().strip(), m.end(),
                  headings[i + 1].start() if i + 1 < len(headings) else len(text))
                 for i, m in enumerate(headings)]
    for heading, start, end in sections:
        if heading.lower().rstrip(':') in {'keywords', 'sample name', 'sample type / medical specialty'}:
            continue
        # A decimal point is not a sentence boundary.
        for match in re.finditer(r"\S[\s\S]*?(?:[.!?](?=\s|$)|\n|$)", text[start:end]):
            raw = match.group()
            body = raw.rstrip()
            if body:
                yield heading, start + match.start(), start + match.start() + len(body)

def select_evidence(text, question, answer):
    empty = dict(evidence_status='unverified', evidence_section=None,
                 evidence_text=None, evidence_start=None, evidence_end=None,
                 surrounding_text=None, context_start=None, context_end=None)
    # Reject visibly incomplete generated text rather than supporting a partial claim.
    if any(answer.count(left) != answer.count(right) for left, right in [('(', ')'), ('[', ']')]):
        return dict(empty, evidence_reason='Generated answer appears incomplete; no evidence selected.')
    answer_terms = terms(answer)
    question_terms = set(terms(question)) - NEGATION
    required = [t for t in answer_terms if t not in STOP and t not in question_terms]
    if len(required) < 2 or re.search(r"\b(unknown|unspecified|not (?:mentioned|specified|provided)|cannot determine)\b", answer, re.I):
        return dict(empty, evidence_reason='Answer has insufficient specific source information.')
    candidates = []
    for heading, start, end in source_sentences(text):
        # Planned or recommended care is not evidence that a procedure occurred.
        # Abstain conservatively even when some words also match a completed event.
        if re.search(r"\b(will|would|should|may|might|recommend\w*|plan\w*|scheduled|consider\w*|proposed|tomorrow)\b", text[start:end], re.I):
            continue
        sentence_terms = terms(text[start:end])
        if set(answer_terms) & NEGATION != set(sentence_terms) & NEGATION:
            continue
        # Require every answer-specific token in order, retaining numbers and negation.
        iterator = iter(sentence_terms)
        if not all(any(token == needed for token in iterator) for needed in required):
            continue
        relevance = len((set(terms(heading)) - STOP) & question_terms)
        candidates.append((relevance, heading, start, end))
    if not candidates:
        return dict(empty, evidence_reason='No conservative source match; answer is unverified.')
    best_score = max(c[0] for c in candidates)
    best = [c for c in candidates if c[0] == best_score]
    if len(best) != 1:
        return dict(empty, evidence_status='ambiguous',
                    evidence_reason='Multiple source occurrences match equally; no evidence selected.')
    _, heading, start, end = best[0]
    left, right = max(0, start - 350), min(len(text), end + 350)
    return dict(evidence_status='lexical_match_review_required',
                evidence_reason='Unique lexical source match, not validated clinical entailment.',
                evidence_section=heading, evidence_text=text[start:end],
                evidence_start=start, evidence_end=end, surrounding_text=text[left:right],
                context_start=left, context_end=right)


def highlighted_context(source, record):
    """Validate provenance and highlight one exact occurrence, never all text matches."""
    if record['evidence_text'] is None:
        return ''
    start, end = record['evidence_start'], record['evidence_end']
    left, right = record['context_start'], record['context_end']
    if not (0 <= left <= start < end <= right <= len(source)):
        raise ValueError('Evidence offsets are outside the selected note.')
    if source[start:end] != record['evidence_text'] or source[left:right] != record['surrounding_text']:
        raise ValueError('Evidence does not belong to the selected note.')
    marked = (html.escape(source[left:start])
              + '<mark style="background-color:#ffe066;color:#111;padding:2px">'
              + html.escape(source[start:end]) + '</mark>' + html.escape(source[end:right]))
    return '<div class="source-context">' + marked + '</div>'
