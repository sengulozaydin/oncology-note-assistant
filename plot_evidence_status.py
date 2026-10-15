"""Plot saved evidence statuses without loading Spark, QA models, or a notebook.

Requires matplotlib. Run from any directory with:
    python plot_evidence_status.py
"""

from collections import Counter
import csv
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    root = Path(__file__).resolve().parent
    source = root / 'results/procedure_qa_results.csv'
    with source.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        reader.fieldnames = [name.strip() for name in reader.fieldnames or []]
        if 'evidence_status' not in reader.fieldnames:
            raise ValueError('CSV is missing the evidence_status column.')
        records = list(reader)
    if not records or any(None in row or row['evidence_status'] is None for row in records):
        raise ValueError('CSV contains no results or has malformed rows.')
    counts = Counter(row['evidence_status'].strip() for row in records)
    categories = [('lexical_match_review_required', 'Review required'),
                  ('ambiguous', 'Uncertain'), ('unverified', 'Unverified')]
    unknown = set(counts) - {key for key, _ in categories}
    if unknown:
        raise ValueError(f'Unrecognized evidence statuses: {sorted(unknown)}')
    values = [counts[key] for key, _ in categories]
    labels = [label for _, label in categories]
    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=180)
    fig.subplots_adjust(left=0.24, right=0.95, top=0.78, bottom=0.29)
    ax.barh(labels, values, height=0.55, color='#486d89')
    ax.invert_yaxis()
    ax.set_xlim(0, max(values) * 1.18)
    ax.set_xlabel('Number of notes', fontsize=11, labelpad=10)
    ax.tick_params(axis='y', length=0, labelsize=12, pad=12)
    ax.tick_params(axis='x', labelsize=10, colors='#52606d', length=0)
    ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True, nbins=6))
    ax.xaxis.grid(True, color='#e5e9ed', linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for index, value in enumerate(values):
        ax.text(value + max(values) * 0.025, index, str(value), va='center',
                fontsize=13, fontweight='bold', color='#263849')
    fig.text(0.06, 0.91, 'Evidence Matching Status', fontsize=21,
             fontweight='bold', color='#203347')
    fig.text(0.06, 0.10, 'Counts describe evidence matching status, not answer accuracy.',
             fontsize=11, color='#394b5b')
    fig.text(0.06, 0.045, f'Source: procedure_qa_results.csv | {len(records)} notes',
             fontsize=9, color='#657482')
    destination = root / 'results/evidence_matching_status.png'
    fig.savefig(destination, facecolor='white')
    plt.close(fig)
    print('Chart counts:', dict(zip(labels, values)))
    print('Saved:', destination)


if __name__ == '__main__':
    main()
