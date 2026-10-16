"""Licensed Healthcare NLP inference, running only in the existing Spark venv."""
import json
import os
from pathlib import Path
import sys

PIPELINE_NAME = 'clinical_notes_qa_base_onnx_pipeline'
MAX_ANSWER_TOKENS = 128


class SetupError(RuntimeError):
    pass


def cached_pipeline_path():
    override = os.environ.get('ONCONOTE_QA_MODEL')
    candidates = ([Path(override).expanduser()] if override else
                  sorted((Path.home() / 'cache_pretrained').glob(PIPELINE_NAME + '_en_*')))
    valid = [p for p in candidates if p.is_dir() and (p / 'metadata').is_dir() and (p / 'stages').is_dir()]
    if not valid:
        raise SetupError('The local clinical notes QA pipeline is missing or incomplete. Set ONCONOTE_QA_MODEL to its existing cached directory. Downloads are disabled.')
    if len(valid) != 1:
        raise SetupError('Multiple cached QA pipelines were found. Set ONCONOTE_QA_MODEL to the intended local pipeline directory.')
    return valid[0]


class HealthcareQA:
    def __init__(self):
        self.pipeline = None
        self.spark = None
        self.load_count = 0

    def load(self):
        model_path = cached_pipeline_path()
        from importlib.metadata import version
        for package, expected in [('pyspark', '3.5.0'), ('spark-nlp', '7.0.0'), ('spark-nlp-jsl', '7.0.0')]:
            if version(package) != expected:
                raise SetupError(f'The licensed environment requires {package} {expected}. Use the existing notebook environment; do not install it in the Streamlit environment.')
        from johnsnowlabs import nlp
        # Prevent the JSL installer from filling missing dependencies via downloads.
        java_dir = Path(nlp.settings.java_dir)
        for name in ('spark-nlp-assembly-7.0.0.jar', 'spark-nlp-jsl-7.0.0.jar'):
            if not (java_dir / name).is_file():
                raise SetupError('The locally installed Healthcare NLP JARs are incomplete. Restore the licensed notebook installation; no download was attempted.')
        if not Path(nlp.settings.root_info_file).is_file():
            raise SetupError('The local John Snow Labs installation is missing. Restore the existing licensed installation.')
        tmp = Path.home() / 'spark-tmp' / 'onconote'
        tmp.mkdir(parents=True, exist_ok=True)
        os.environ.update(TMPDIR=str(tmp), SPARK_LOCAL_DIRS=str(tmp),
                          JAVA_TOOL_OPTIONS=f'-Djava.io.tmpdir={tmp}')
        self.spark = nlp.start(
            master_url='local[2]', create_jsl_home_if_missing=False,
            spark_conf={'spark.driver.memory': '3g', 'spark.default.parallelism': '2',
                        'spark.sql.shuffle.partitions': '2', 'spark.ui.enabled': 'false',
                        'spark.driver.bindAddress': '127.0.0.1', 'spark.driver.host': '127.0.0.1'})
        from sparknlp.pretrained import PretrainedPipeline
        self.pipeline = PretrainedPipeline.from_disk(str(model_path))
        qa_stages = [stage for stage in self.pipeline.model.stages
                     if type(stage).__name__ == 'MedicalQuestionAnswering']
        if len(qa_stages) != 1:
            self.pipeline = None
            raise SetupError('The local pipeline must contain exactly one Healthcare NLP MedicalQuestionAnswering stage.')
        # The cached model limits output to 30 subword tokens, cutting some answers
        # mid-word. Keep the same model, prompt and EOS behavior; allow longer output.
        qa_stages[0].setMaxNewTokens(MAX_ANSWER_TOKENS)
        from sparknlp.base import LightPipeline
        self.pipeline.light_model = LightPipeline(self.pipeline.model)
        self.load_count += 1

    def ask(self, question, context):
        if not isinstance(question, str) or not question.strip():
            raise SetupError('Enter an English question before submitting.')
        if not isinstance(context, str) or not context.strip():
            raise SetupError('The selected note is empty. Select another note.')
        if self.pipeline is None:
            try:
                self.load()
            except SetupError:
                raise
            except Exception as exc:
                raise SetupError(f'Healthcare NLP could not start ({type(exc).__name__}). Check the existing local license, Java, and notebook environment. No fallback model is used.') from None
        try:
            annotations = self.pipeline.fullAnnotate([question], [context])[0].get('answer', [])
        except Exception as exc:
            raise SetupError(f'Healthcare NLP inference failed ({type(exc).__name__}). Check the local license and available memory, then retry. No fallback answer is provided.') from None
        if not annotations or not annotations[0].result.strip():
            raise SetupError('Healthcare NLP returned no answer for this note and question.')
        return dict(answer=annotations[0].result, pipeline=PIPELINE_NAME,
                    worker_pid=os.getpid(), model_load_count=self.load_count)


def main():
    # Reserve stdout for JSON; redirect Python and JVM diagnostic output away from it.
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), 'w', buffering=1, encoding='utf-8')
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    qa = HealthcareQA()
    try:
        for line in sys.stdin:
            request_id = None
            try:
                request = json.loads(line)
                request_id = request.get('id')
                result = qa.ask(request.get('question'), request.get('context'))
                result.update(id=request_id, error=None)
            except SetupError as exc:
                result = dict(id=request_id, error=str(exc))
            except Exception:
                result = dict(id=request_id, error='The QA worker received an invalid request or encountered an internal error.')
            protocol.write(json.dumps(result) + '\n')
            protocol.flush()
    finally:
        if qa.spark is not None:
            qa.spark.stop()


if __name__ == '__main__':
    main()
