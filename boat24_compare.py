#!/usr/bin/env python3
"""Forward-only shadow comparison of baseline vs experimental motor model.
Never rewrites original predictions. Research only; no betting recommendation.
"""
import datetime as dt
import json
import math
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from boat24_integrity import atomic_write, eligible, timeparse as parse_time

JST = ZoneInfo('Asia/Tokyo')
LEDGER = Path('omura/docs/boat24_ledger.json')
MOTORS = Path('omura/docs/boat24_motor_analysis.json')
OUT = Path('omura/docs/boat24_comparison.json')


def timeparse(v):
    try:
        x = dt.datetime.fromisoformat(str(v))
        return x if x.tzinfo else x.replace(tzinfo=JST)
    except (ValueError, TypeError):
        return None


def numeric(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def normalize(weights):
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()} if total > 0 else {}


def motor_model(rec, motor_data):
    baseline = rec.get('probabilities') or {}
    snapshot = rec.get('input_snapshot') or {}
    cards = snapshot.get('cards') or {}
    venue = rec.get('venue')
    if not baseline or not cards or venue is None:
        return None, 'baseline_or_cards_missing', []
    scores = {}
    missing = []
    for lane in range(1, 7):
        raw = str(cards.get(f'艇{lane}_モーター番号', '')).strip().lstrip('0')
        key = f'{int(venue):02d}-{raw}'
        motor = motor_data.get(key) if raw else None
        score = numeric((motor or {}).get('racer_adjusted_motor_score_experimental'))
        if score is None:
            missing.append(key)
            continue
        # Conservative bounded perturbation, not calibrated probability.
        scores[lane] = max(-0.25, min(0.25, (score - 50) / 100.0))
    if len(scores) != 6:
        return None, 'six_motor_scores_required', missing
    weighted = {}
    for combo, p in baseline.items():
        try:
            a, b, c = [int(x) for x in combo.split('-')]
        except ValueError:
            continue
        p = numeric(p)
        if p is None or p < 0:
            continue
        adjustment = scores[a] * 0.58 + scores[b] * 0.29 + scores[c] * 0.13
        weighted[combo] = p * math.exp(adjustment)
    return normalize(weighted), None, []


def selection(probabilities, n):
    return sorted(probabilities, key=probabilities.get, reverse=True)[:n]


def score_predictions(records, variant):
    settled = [r for r in records.values() if r.get('actual') and r.get(variant)
               and parse_time(r.get('created_at')) and parse_time(r.get('cutoff'))
               and parse_time(r['created_at']) < parse_time(r['cutoff'])
               and numeric(r.get('payout_100yen')) is not None
               and numeric(r.get('payout_100yen')) > 0]
    result = {'evaluated_races': len(settled)}
    if not settled:
        return result
    log_losses = []
    briers = []
    for r in settled:
        p = r[variant]
        actual = r['actual']
        log_losses.append(-math.log(max(p.get(actual, 0), 1e-12)))
        briers.append(sum((v - (1 if k == actual else 0)) ** 2 for k, v in p.items()))
    result['mean_log_loss'] = round(sum(log_losses) / len(log_losses), 6)
    result['mean_brier_score'] = round(sum(briers) / len(briers), 6)
    for n in (12, 18):
        bets = [r for r in settled if r.get(f'{variant}_top{n}')]
        hit = sum(r['actual'] in r[f'{variant}_top{n}'] for r in bets)
        stake = len(bets) * n * 100
        returns = sum(r.get('payout_100yen', 0) for r in bets if r['actual'] in r[f'{variant}_top{n}'])
        result[f'top{n}'] = {'races': len(bets), 'hits': hit,
            'hit_rate': round(hit / len(bets), 6) if bets else None,
            'paper_stake_yen': stake, 'paper_return_yen': returns,
            'paper_roi': round(returns / stake, 6) if stake else None}
    return result


def main():
    now = dt.datetime.now(JST)
    if not LEDGER.exists() or not MOTORS.exists():
        raise SystemExit('Required ledger or motor analysis file is missing')
    ledger = json.loads(LEDGER.read_text(encoding='utf-8'))
    research = json.loads(MOTORS.read_text(encoding='utf-8'))
    previous = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}
    records = previous.get('records', {})
    motor_time = timeparse(research.get('generated_at'))
    added = settled = skipped = 0
    for code, rec in ledger.get('predictions', {}).items():
        if code not in records:
            created = timeparse(rec.get('created_at'))
            cutoff = timeparse(rec.get('cutoff'))
            # Strictly forbid using a motor report created after the forecast or race cutoff.
            # A shadow forecast is created NOW, not retroactively at baseline forecast time.
            if not eligible(rec) or rec.get("result") or not cutoff or now >= cutoff or not motor_time or motor_time > now:
                skipped += 1
                continue
            # Report must exist before the original forecast; no retrospective features.
            if not created or motor_time > created:
                skipped += 1
                continue
            alt, error, missing = motor_model(rec, research.get('motors') or {})
            if error:
                skipped += 1
                continue
            baseline = rec.get('probabilities') or {}
            records[code] = {'created_at': now.isoformat(), 'cutoff': rec.get('cutoff'),
                'motor_report_at': research.get('generated_at'),
                'model': 'shadow-motor-0.1-UNVALIDATED',
                'baseline': baseline, 'experimental': alt,
                'baseline_top12': selection(baseline, 12), 'baseline_top18': selection(baseline, 18),
                'experimental_top12': selection(alt, 12), 'experimental_top18': selection(alt, 18),
                'actual': None, 'payout_100yen': None,
                'decision': '見送り（予測確率・期待値未検証）'}
            added += 1
        item = records.get(code)
        if item and item.get('actual') is None and rec.get('result'):
            result = rec['result']
            item['actual'] = result.get('combo')
            item['payout_100yen'] = numeric(result.get('payout_100yen'))
            settled += 1
    summary = {v: score_predictions(records, v) for v in ('baseline', 'experimental')}
    report = {'schema': 1, 'updated_at': now.isoformat(),
        'model': 'forward-only shadow comparison; experimental motor weights are uncalibrated',
        'records': records, 'summary': summary,
        'diagnostics': {'new_comparisons': added, 'new_settlements': settled,
            'skipped_not_eligible': skipped, 'total_comparisons': len(records)},
        'limitations': ['No retrospective backfill: motor reports generated after cutoff cannot be used',
            'Motor report timestamp must precede the baseline forecast timestamp',
            'Motor replacement dates and official series boundaries unverified',
            'ROI is hypothetical flat-stake paper trading, not live execution',
            'No edge claim until sufficient forward holdout validation']}
    atomic_write(OUT, report)
    print(json.dumps(report['diagnostics'], ensure_ascii=False))


if __name__ == '__main__':
    main()
