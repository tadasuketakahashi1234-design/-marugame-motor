"""Official byte-layout racer identity; sex is never inferred from names."""
import ctypes as C
import ctypes.util
import datetime as dt
import hashlib
from pathlib import Path
import tempfile
import urllib.request

def extract_lha(payload):
 lib=ctypes.util.find_library('archive')
 if not lib:raise RuntimeError('libarchive is required for the official racer registry')
 a=C.CDLL(lib);a.archive_read_new.restype=C.c_void_p
 for name in ('archive_read_support_filter_all','archive_read_support_format_all','archive_read_free'):
  getattr(a,name).argtypes=[C.c_void_p]
 a.archive_read_open_filename.argtypes=[C.c_void_p,C.c_char_p,C.c_size_t]
 a.archive_read_next_header.argtypes=[C.c_void_p,C.POINTER(C.c_void_p)]
 a.archive_read_data.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t];a.archive_read_data.restype=C.c_ssize_t
 out=[]
 with tempfile.TemporaryDirectory() as temp:
  path=Path(temp)/'registry.lzh';path.write_bytes(payload);reader=a.archive_read_new()
  try:
   a.archive_read_support_filter_all(reader);a.archive_read_support_format_all(reader)
   if a.archive_read_open_filename(reader,str(path).encode(),10240)!=0:raise ValueError('Invalid official archive')
   entry=C.c_void_p()
   while True:
    status=a.archive_read_next_header(reader,C.byref(entry))
    if status==1:break
    if status!=0:raise ValueError('Archive entry cannot be read')
    chunks=[];size=0
    while True:
     buf=C.create_string_buffer(65536);n=a.archive_read_data(reader,buf,len(buf))
     if n<0:raise ValueError('Archive decompression failed')
     if not n:break
     chunks.append(buf.raw[:n]);size+=n
     if size>10_000_000:raise ValueError('Registry archive exceeds expected size')
    out.append(b''.join(chunks))
  finally:a.archive_read_free(reader)
 return b'\n'.join(out)

def parse_registry(payload):
 records={}
 for line in payload.splitlines():
  if len(line)<52:continue
  rid=line[:4].decode('ascii',errors='ignore');sex=line[48:49].decode('ascii',errors='ignore')
  if rid.isdigit() and sex in ('1','2'):
   records[rid]={'sex':'male' if sex=='1' else 'female','branch':line[35:39].decode('cp932').strip(),'name':line[4:20].decode('cp932').strip()}
 if len(records)<1000:raise ValueError('Official registry did not match the published byte layout')
 return records

def load_registry(today):
 # Identity fields only: no future period performance is imported.
 # May data describe the half-year ended April; November data ended October.
 candidates=[]
 for year in (today.year,today.year-1):
  for month in (10,4):
   if dt.date(year,month,1)<=today-dt.timedelta(days=60):candidates.append((year,month))
 errors=[]
 for year,month in sorted(candidates,reverse=True):
  url=f'https://www.boatrace.jp/static_extra/pc_static/download/data/kibetsu/fan{year%100:02d}{month:02d}.lzh'
  try:
   with urllib.request.urlopen(url,timeout=20) as r:raw=r.read()
   return {'source':url,'sha256':hashlib.sha256(raw).hexdigest(),'records':parse_registry(extract_lha(raw)),'fields_used':['sex','branch','name']}
  except Exception as e:errors.append(str(e))
 raise RuntimeError('Official sex registry unavailable: '+'; '.join(errors))
