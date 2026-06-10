from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().with_name('run_fbbp_formal_case.py')), run_name='__main__')