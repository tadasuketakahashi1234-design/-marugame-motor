"""Shared ledger validation; all amounts are flat 100-yen paper stakes."""
import copy
import datetime as dt
import json
import math
import os
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo('Asia/Tokyo')


def timeparse(value):
    try:
        t = dt.datetime.fromisoformat(str(value))
        return t.replace(tzinfo=JST) if t.tzinfo is None else t.astimezone(JST)
    except (ValueError, TypeError):
        return None


def eligible(rec, final=False):
    created, cutoff = timeparse(rec.get('created_at')), timeparse(rec.get('cutoff'))
    valid = bool(created and cutoff and created < cutoff
                 and created.date() == cutoff.date()
                 and rec.get('evaluation_eligible') is not False)
    if final:
        snapshot = rec.get('final_snapshot') or {}
        captured = timeparse(snapshot.get('created_at'))
        valid = bool(valid and captured and created <= captured < cutoff)
    return valid


def valid_combo(value):
    parts = str(value).split('-')
    return len(parts) == 3 and len(set(parts)) == 3 and all(x in '123456' and len(x) == 1 for x in parts)


def paper(selection, combo, money):
    result = {}
    for n in (12, 18):
        picks = selection.get(str(n), [])
        if len(picks) != n or len(set(picks)) != n or not all(valid_combo(x) for x in picks):
            continue
        result[str(n)] = {'hit': combo in picks, 'stake': len(picks) * 100,
                          'return': money if combo in picks else 0}
    return result


def result_paper(rec, final=False):
    result = rec.get('result') or {}
    money = result.get('payout_100yen')
    if not valid_combo(result.get('combo')) or not isinstance(money, (int, float)) or not math.isfinite(money) or money <= 0:
        return {}
    snapshot = rec.get('final_snapshot') or {} if final else rec
    return paper(snapshot.get('selection') or {}, result['combo'], money)


def summarize(predictions, final=False):
    records = list(predictions.values())
    approved = [r for r in records if eligible(r, final)]
    output = {'saved': len(records), 'eligible': len(approved),
              'excluded': len(records) - len(approved),
              'pending': sum(not r.get('result') for r in approved)}
    for n in (12, 18):
        bets = [b for r in approved if (b := result_paper(r, final).get(str(n)))]
        hits = sum(b['hit'] for b in bets)
        stake = sum(b['stake'] for b in bets)
        returned = sum(b['return'] for b in bets)
        output[str(n)] = {'races': len(bets), 'hits': hits, 'stake': stake,
                          'return': returned, 'profit': returned - stake,
                          'hit_rate': hits / len(bets) if bets else None,
                          'roi': returned / stake if stake else None}
    return output


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as f:
            name = f.name
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def merge_ledgers(remote, collected, key='predictions'):
    """Remote forecasts win on collision; add observations, never overwrite picks."""
    output = copy.deepcopy(collected)
    output[key] = copy.deepcopy(remote.get(key, {}))
    for code, incoming in collected.get(key, {}).items():
        if code not in output[key]:
            output[key][code] = copy.deepcopy(incoming)
            continue
        current = output[key][code]
        # Only enrich observations from the SAME immutable prediction.
        same = current.get('created_at') == incoming.get('created_at')
        if key == 'predictions':
            if same and not current.get("cutoff_verified_at"):
                for field in ('cutoff', 'cutoff_verified', 'cutoff_verified_at', 'cutoff_source', 'evaluation_eligible'):
                    if incoming.get(field) is not None:
                        current[field] = copy.deepcopy(incoming[field])
            if same and not current.get('final_snapshot') and incoming.get('final_snapshot'):
                current['final_snapshot'] = copy.deepcopy(incoming['final_snapshot'])
                current['stage'] = incoming.get('stage')
            if not current.get('result') and incoming.get('result'):
                current['result'] = copy.deepcopy(incoming['result'])
                current['result']['paper'] = result_paper(current)
                if current.get('final_snapshot'):
                    current['result']['paper_final'] = result_paper(current, True)
        elif not current.get('actual') and incoming.get('actual'):
            current['actual'] = incoming['actual']
            current['payout_100yen'] = incoming.get('payout_100yen')
    if key == 'predictions':
        output['summary'] = summarize(output[key])
        output['summary_final'] = summarize(output[key], True)
    return output
