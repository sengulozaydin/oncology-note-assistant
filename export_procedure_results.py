"""Export saved QA results without starting Spark or loading a model."""

import argparse
from collections import Counter
import csv
import html
import json
from pathlib import Path

CSV_FIELDS = ['file_name', 'question', 'answer', 'evidence_status',
              'evidence_section', 'evidence_text']
STATUS_LABELS = {
    'lexical_match_review_required': 'Lexical match — review required',
    'ambiguous': 'Ambiguous — no evidence selected',
    'unverified': 'Unverified — no evidence selected',
    'qa_error': 'QA error',
}


def validate_records(records, notes_dir):
    """Check provenance before writing either deliverable."""
    if not records:
        raise ValueError('No saved results to export.')
    keys = [(r['file_name'], r['question']) for r in records]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate file/question records.')
    for record in records:
        name = record['file_name']
        if Path(name).name != name:
            raise ValueError('Expected a source filename, not a path.')
        source = (notes_dir / name).read_text(encoding='utf-8')
        if record['evidence_text'] is not None:
            start, end = record['evidence_start'], record['evidence_end']
            left, right = record['context_start'], record['context_end']
            if not (0 <= left <= start < end <= right <= len(source)):
                raise ValueError(f'Invalid evidence offsets: {name}')
            if source[start:end] != record['evidence_text']:
                raise ValueError(f'Evidence differs from source: {name}')
            if source[left:right] != record['surrounding_text']:
                raise ValueError(f'Context differs from source: {name}')
            if record['evidence_status'] != 'lexical_match_review_required':
                raise ValueError(f'Unexpected evidence status: {name}')


def render_card(record):
    """Escape source text and highlight only its saved evidence occurrence."""
    esc = lambda value: html.escape(str(value))
    status = STATUS_LABELS.get(record['evidence_status'], record['evidence_status'])
    fields = [('Question', record['question']), ('Model answer', record['answer'] or 'No answer'),
              ('Evidence status', status), ('Selection note', record['evidence_reason']),
              ('Evidence section', record['evidence_section'] or 'Not selected')]
    body = ''.join(f'<p><strong>{label}:</strong> {esc(value)}</p>' for label, value in fields)
    if record['evidence_text'] is not None:
        text = record['surrounding_text']
        start = record['evidence_start'] - record['context_start']
        end = record['evidence_end'] - record['context_start']
        marked = (esc(text[:start]) + '<mark style="background:#ffe066;color:#111">'
                  + esc(text[start:end]) + '</mark>' + esc(text[end:]))
        body += '<p><strong>Source-note evidence and surrounding text:</strong></p>'
        body += f'<div class="source" style="white-space:pre-wrap;overflow-wrap:anywhere">{marked}</div>'
    else:
        body += '<p class="notice">No reliable evidence selected. No source text is highlighted.</p>'
    if record.get('error'):
        body += f'<p><strong>Error:</strong> {esc(record["error"])}</p>'
    return f'<article><h2>{esc(record["file_name"])}</h2>{body}</article>'


def preview_records(records):
    """Show up to three examples, covering different evidence statuses."""
    selected = []
    for status in ('lexical_match_review_required', 'ambiguous', 'unverified'):
        match = next((r for r in records if r['evidence_status'] == status), None)
        if match is not None:
            selected.append(match)
    return selected[:3]


def export_results(records, output_dir=Path('results'), notes_dir=Path('mt_onc_50')):
    validate_records(records, notes_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / 'procedure_qa_results.csv'
    report_path = output_dir / 'procedure_qa_report.html'
    with csv_path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)
    counts = Counter(r['evidence_status'] for r in records)
    summary = ''.join(f'<li><strong>{count}</strong> {html.escape(STATUS_LABELS.get(status, status))}</li>'
                      for status, count in sorted(counts.items()))
    cards = '\n'.join(render_card(r) for r in records)
    report = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Procedure QA Results</title><style>
body{margin:0;background:#f3f5f7;color:#182331;font:16px/1.65 system-ui,Arial,sans-serif}
main{max-width:980px;margin:36px auto;padding:0 20px}header,article{background:white;padding:28px;border:1px solid #d9e0e7;border-radius:10px;margin-bottom:20px}
h1{font-size:30px;margin:0 0 12px}h2{font-size:20px;margin:0 0 18px;overflow-wrap:anywhere}p{margin:10px 0;overflow-wrap:anywhere}
ul{padding-left:24px}.source{background:#fafbfc;padding:18px;border-left:3px solid #8b9cb0}.notice{color:#5b4650}mark{background:#ffe066;color:#111;padding:1px 0}
a{color:#1554a0}@media print{body{background:white}main{margin:0;max-width:none}article{break-inside:avoid}mark{print-color-adjust:exact;-webkit-print-color-adjust:exact}}
</style></head><body><main><header><h1>Procedure QA Results</h1>
'''
    report += f'<p>{len(records)} saved results. Answers and evidence selection are unchanged; no model inference was run for this export.</p>'
    report += '<p>Yellow highlighting identifies source-note text offered as support for the answer. Lexical matches require review and do not establish clinical entailment or reveal the model’s reasoning. Ambiguous and unverified answers have no highlighted evidence.</p>'
    report += f'<ul>{summary}</ul><p><a href="procedure_qa_results.csv" download>Download all results as CSV</a></p></header>'
    report += cards + '</main></body></html>\n'
    report_path.write_text(report, encoding='utf-8')
    return csv_path, report_path


if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=root / '.ipynb_checkpoints/qa_batch_results.json')
    parser.add_argument('--output-dir', type=Path, default=root / 'results')
    args = parser.parse_args()
    records = json.loads(args.input.read_text(encoding='utf-8'))
    export_results(records, args.output_dir, root / 'mt_onc_50')
    print(f'Exported {len(records)} saved results.')
    print('Evidence status counts:', dict(Counter(r['evidence_status'] for r in records)))
