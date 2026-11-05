"""Measured pipeline stages; observation times do not replace source times."""
import datetime as dt,time
from contextlib import contextmanager
from boat24_integrity import JST

@contextmanager
def stage(trace,name):
    start=time.perf_counter();row={'started_at':dt.datetime.now(JST).isoformat()};trace.setdefault('stages',{})[name]=row
    try:yield row
    except Exception:
        row['state']='failed';raise
    else:row['state']='ok'
    finally:row.update(completed_at=dt.datetime.now(JST).isoformat(),seconds=round(time.perf_counter()-start,4))
