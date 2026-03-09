#!/usr/bin/env python3
"""Run the Macro Dashboard without needing 'streamlit' on PATH."""
import subprocess
import sys

if __name__ == "__main__":
    subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py"], check=False)
