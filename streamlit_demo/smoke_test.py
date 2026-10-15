"""Run two real local model questions and verify worker reuse. No test doubles."""
from pathlib import Path
from qa_client import QAClient
from evidence import select_evidence

root = Path(__file__).resolve().parents[1]
context = (root / 'mt_onc_50/mt_oncology_1.txt').read_text(encoding='utf-8')
client = QAClient()
try:
    responses = []
    for question, expected in [
        ('What was the postoperative diagnosis?', 'POSTOPERATIVE DIAGNOSIS:'),
        ('What was injected beneath the conjunctiva and skin?', 'PROCEDURE:'),
    ]:
        response = client.ask(question, context)
        evidence = select_evidence(context, question, response['answer'])
        assert evidence['evidence_section'] == expected, evidence
        assert evidence['evidence_status'] == 'lexical_match_review_required'
        responses.append(response)
        print(question, '\nAnswer:', response['answer'], '\nSection:', expected, flush=True)
    assert responses[0]['worker_pid'] == responses[1]['worker_pid']
    assert all(r['model_load_count'] == 1 for r in responses)
    print('PASS: real Healthcare NLP answers; source evidence; one worker and one model load.', flush=True)
finally:
    client.close()
