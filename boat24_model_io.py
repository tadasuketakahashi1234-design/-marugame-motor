"""Atomic compressed model cache; prediction ledgers remain ordinary JSON."""
import gzip,json,os,tempfile
from pathlib import Path
from boat24_integrity import atomic_write

def read_json(path):
 path=Path(path)
 if path.suffix=='.gz':
  with gzip.open(path,'rt',encoding='utf-8') as f:return json.load(f)
 return json.loads(path.read_text())

def write_json(path,value):
 path=Path(path)
 if path.suffix!='.gz':return atomic_write(path,value)
 path.parent.mkdir(parents=True,exist_ok=True);name=None
 try:
  with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as raw:
   name=raw.name
   with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0,compresslevel=6) as zipped:
    zipped.write(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode())
   raw.flush();os.fsync(raw.fileno())
  os.replace(name,path);name=None
 finally:
  if name:os.unlink(name)
