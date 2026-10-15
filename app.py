"""Compatibility entry point for the real Healthcare NLP Streamlit application."""
from pathlib import Path
import runpy
import sys

demo = Path(__file__).resolve().parent / 'streamlit_demo'
sys.path.insert(0, str(demo))
runpy.run_path(str(demo / 'app.py'), run_name='__main__')
