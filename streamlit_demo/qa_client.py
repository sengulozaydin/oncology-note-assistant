"""A persistent local worker bridges the two existing Python environments."""
import atexit
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]


class QAError(RuntimeError):
    """An actionable, non-secret error suitable for the UI."""


class QAClient:
    def __init__(self, python_path=None, timeout=360):
        self.python_path = Path(python_path or os.environ.get(
            'ONCONOTE_QA_PYTHON', str(ROOT / 'spark/bin/python'))).expanduser()
        self.timeout = timeout
        self.process = None
        self.lock = threading.Lock()
        atexit.register(self.close)

    def _start(self):
        if not self.python_path.is_file():
            raise QAError('The licensed Python environment is missing. Set ONCONOTE_QA_PYTHON to its Python executable.')
        env = os.environ.copy()
        env.update(OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2',
                   PYSPARK_PYTHON=str(self.python_path),
                   PYSPARK_DRIVER_PYTHON=str(self.python_path),
                   SPARK_LOCAL_IP='127.0.0.1')
        try:
            self.process = subprocess.Popen(
                [str(self.python_path), '-u', str(Path(__file__).with_name('qa_worker.py'))],
                cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
                start_new_session=True, bufsize=1)
        except OSError as exc:
            raise QAError('Cannot start the licensed Python worker. Check ONCONOTE_QA_PYTHON and executable permissions.') from exc
        self.responses = queue.Queue()
        output, responses = self.process.stdout, self.responses

        def read_responses():
            try:
                for line in output:
                    responses.put(line)
            finally:
                responses.put(None)

        threading.Thread(target=read_responses, daemon=True).start()

    def _stop(self):
        process, self.process = self.process, None
        if process is None:
            return
        # Only terminate this client's worker and its own Spark descendants.
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        finally:
            if process.stdin:
                process.stdin.close()
            if process.stdout:
                process.stdout.close()

    def close(self):
        with self.lock:
            self._stop()

    def ask(self, question, context):
        if not question.strip():
            raise QAError('Enter an English question before submitting.')
        if not context.strip():
            raise QAError('The selected note is empty. Select another note.')
        with self.lock:
            if self.process is None or self.process.poll() is not None:
                self._stop()
                self._start()
            request_id = uuid.uuid4().hex
            try:
                self.process.stdin.write(json.dumps(dict(id=request_id, question=question.strip(), context=context)) + '\n')
                self.process.stdin.flush()
                line = self.responses.get(timeout=self.timeout)
                if line is None:
                    raise QAError('The Healthcare NLP worker stopped. Check the licensed environment, Java, and available memory, then retry.')
                response = json.loads(line)
                if response.get('id') != request_id:
                    raise QAError('The QA worker returned an invalid response. Please retry.')
                if response.get('error'):
                    raise QAError(response['error'])
                if not response.get('answer', '').strip():
                    raise QAError('Healthcare NLP returned no answer for this question.')
                return response
            except queue.Empty as exc:
                self._stop()
                raise QAError('Healthcare NLP timed out. Its worker was stopped; check memory and retry. No substitute answer was generated.') from exc
            except QAError:
                self._stop()
                raise
            except (OSError, ValueError, TypeError) as exc:
                self._stop()
                raise QAError('Communication with Healthcare NLP failed. Retry after checking the local environment.') from exc
