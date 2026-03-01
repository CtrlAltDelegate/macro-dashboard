"""
Run the Streamlit app from the project root so 'Main module does not exist' is avoided.
Usage: python run_app.py  (or: streamlit run app.py  from the project root)
"""
import os
import subprocess
import sys
from pathlib import Path

def main():
    root = Path(__file__).resolve().parent
    os.chdir(root)
    app_path = root / "app.py"
    if not app_path.exists():
        print(f"app.py not found at {app_path}", file=sys.stderr)
        sys.exit(1)
    subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless", "true"], check=True)

if __name__ == "__main__":
    main()
