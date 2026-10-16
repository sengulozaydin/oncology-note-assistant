"""Conservative source evidence adapted from the notebook; not model citations."""
import re
import html

TOKEN = re.compile(r"\d+(?:\.\d+)?|[a-z]+", re.I)
STOP = set("a an the was were is are be been being with of and or in on at to for by from it this that as had has have patient what which how did does do because".split())
NEGATION = {"no", "not", "without", "denies", "denied", "never"}
FUTURE = re.compile(r'\b(will|would|should|may|might|recommend\w*|plan\w*|scheduled|consider\w*|proposed|tomorrow)\b', re.I)

HEADINGS = re.compile(r"(?m)^[A-Za-z][A-Za-z0-9 /_()&-]{1,79}:[ \t]*")

# Bounded inflection families, not fuzzy matching or clinical synonym expansion.
# Avoid generic suffix stripping: drug names, masses, and diagnoses must not be
# conflated accidentally. Unlisted words, negation markers, and numbers stay exact.
INFLECTION_FAMILIES = (
    ('need', 'needs', 'needed', 'needing'),
    ('require', 'requires', 'required', 'requiring'),
    ('receive', 'receives', 'received', 'receiving'),
    ('administer', 'administers', 'administered', 'administering'),
    ('inject', 'injects', 'injected', 'injecting'),
    ('perform', 'performs', 'performed', 'performing'),
    ('treat', 'treats', 'treated', 'treating'),
    ('place', 'places', 'placed', 'placing'),
    ('remove', 'removes', 'removed', 'removing'),
    ('condition', 'conditions'),
    ('medication', 'medications'),
    ('tumor', 'tumors'),
    ('lesion', 'lesions'),
    ('procedure', 'procedures'),
    ('symptom', 'symptoms'),
    ('allergy', 'allergies', 'allergic'),
)
WORD_FORMS = {form: family[0] for family in INFLECTION_FAMILIES for form in family}


def normalize_word(word):
    word = word.lower()
    return WORD_FORMS.get(word, word)


def terms(text):
    return [normalize_word(m.group()) for m in TOKEN.finditer(text)]

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
    empty = dict(evidence_matches=[], evidence_status='unverified', evidence_section=None,
                 evidence_text=None, evidence_start=None, evidence_end=None,
                 surrounding_text=None, context_start=None, context_end=None)
    # Reject visibly incomplete generated text rather than supporting a partial claim.
    if any(answer.count(left) != answer.count(right) for left, right in [('(', ')'), ('[', ']')]):
        return dict(empty, evidence_reason='Generated answer appears incomplete; no evidence selected.')
    answer_terms = terms(answer)
    question_terms = set(terms(question)) - NEGATION
    required = [t for t in answer_terms if t not in STOP and t not in question_terms]
    if not required or re.search(r"\b(unknown|unspecified|not (?:mentioned|specified|provided)|cannot determine)\b", answer, re.I):
        return dict(empty, evidence_reason='Answer has insufficient specific source information.')
    candidates = []
    for heading, start, end in source_sentences(text):
        # A plan can support a question about planned care, never a completed event.
        source_future = {m.lower() for m in FUTURE.findall(text[start:end])}
        if source_future and (not FUTURE.search(question) or
                              source_future != {m.lower() for m in FUTURE.findall(answer)}):
            continue
        sentence_terms = terms(text[start:end])
        if len(required) == 1:
            # Short field values need both a relevant section and the entire field
            # value to match. A lone word inside a longer sentence is insufficient.
            heading_terms = set(terms(heading)) - STOP
            if (not heading_terms.intersection(question_terms - STOP) or
                    set(sentence_terms) - STOP != set(required) or
                    not required[0].isalpha() or len(required[0]) < 4):
                continue
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
    matches = []
    answer_content = set(answer_terms) - STOP
    list_question = re.search(r'\b(?:which|what)\b.*\b(?:conditions|diagnoses)\b|\blist\b', question, re.I)
    for _, heading, start, end in best:
        sentence = text[start:end]
        # Highlight only answer-related source words, retaining unmatched list items
        # as plain text. Merge adjacent words across punctuation/function words.
        spans = []
        for token in TOKEN.finditer(sentence):
            if normalize_word(token.group()) not in answer_content:
                continue
            token_start, token_end = start + token.start(), start + token.end()
            if spans and not (set(terms(text[spans[-1][1]:token_start])) - STOP):
                spans[-1][1] = token_end
            else:
                spans.append([token_start, token_end])
        items = [set(terms(item)) - STOP for item in re.split(r'[,;]', sentence)]
        items = [item for item in items if item]
        covered = [item <= set(answer_terms) for item in items]
        partial = bool(list_question and len(items) >= 3 and any(covered) and not all(covered))
        matches.append(dict(evidence_section=heading, evidence_text=sentence,
                            evidence_start=start, evidence_end=end,
                            highlight_spans=spans, partial_list=partial))
    partial = any(match['partial_list'] for match in matches)
    status = ('partial_match_review_required' if partial else
              'multiple_matches_review_required' if len(matches) > 1 else
              'lexical_match_review_required')
    reason = (f'{len(matches)} equally ranked source matches are shown; no single occurrence was chosen. '
              if len(matches) > 1 else 'One lexical source match is shown. ')
    if partial:
        reason += 'The source list contains unmatched items; the answer may be incomplete. '
    reason += 'Source selection and highlighting are heuristic, not pipeline-validated evidence.'
    result = dict(empty, evidence_status=status, evidence_reason=reason, evidence_matches=matches)
    # Keep the existing single-match fields for callers that inspect a unique result.
    # Multiple matches deliberately have no arbitrarily selected primary evidence.
    if len(matches) == 1:
        match = matches[0]
        result.update({k: match[k] for k in ('evidence_section', 'evidence_text', 'evidence_start', 'evidence_end')})
        result.update(surrounding_text=match['evidence_text'],
                      context_start=match['evidence_start'], context_end=match['evidence_end'])
    return result


def highlighted_context(source, record):
    """Show every equally ranked source sentence, with validated local offsets."""
    blocks = []
    for match in record.get('evidence_matches', []):
        start, end = match['evidence_start'], match['evidence_end']
        if not (0 <= start < end <= len(source)) or source[start:end] != match['evidence_text']:
            raise ValueError('Evidence does not belong to the selected note.')
        cursor = start
        fragments = []
        for left, right in match['highlight_spans']:
            if not (cursor <= left < right <= end):
                raise ValueError('Invalid or overlapping highlight offsets.')
            fragments.append(html.escape(source[cursor:left]))
            fragments.append('<mark style="background-color:#ffe066;color:#111;padding:2px">'
                             + html.escape(source[left:right]) + '</mark>')
            cursor = right
        fragments.append(html.escape(source[cursor:end]))
        blocks.append('<div class="evidence-match"><p><strong>Evidence section: '
                      + html.escape(match['evidence_section']) + '</strong></p>'
                      + '<div class="source-context">' + ''.join(fragments) + '</div></div>')
    return ''.join(blocks)
