"""Run PDF parsing separately with memory/CPU limits on the Linux API host."""
import json
import sys
from pathlib import Path
try:
    import resource
    resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU,(15,15))
except ImportError:
    pass
from app.services.resume_parser import extract_pdf
print(json.dumps(extract_pdf(Path(sys.argv[1]).read_bytes()),ensure_ascii=False))
