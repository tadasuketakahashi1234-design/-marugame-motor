import json
import statistics
from datetime import datetime, timedelta

import update


def is_omura(row):
    code = row.get('場コード', row.get('レース場コード', ''))
    return str(code).strip().zfill(2) == '24'


update.is_marugame = is_omura
update.ROOT = update.ROOT / 'omura'


def current_series_start(today):
    # Monthly schedule is the authoritative source of series boundaries.
    for month in (today.replace(day=1), (today.replace(day=1) - timedelta(days=1)).replace(day=1)):
        url = f'https://boatracecsv.github.io/data/programs/monthly_schedule/{month:%Y/%m}.csv'
        try:
            import csv
            import io
            import urllib.request
            request = urllib.request.Request(url, headers={'User-Agent': 'MotorDashboard/3.0'})
            with urllib.request.urlopen(request, timeout=18) as response:
                rows = csv.DictReader(io.StringIO(response.read().decode('utf-8-sig')))
                for row in rows:
                    if not is_omura(row):
                        continue
                    try:
                        start = datetime.strptime(row['節開始日'], '%Y-%m-%d').date()
                        end = datetime.strptime(row['節終了日'], '%Y-%m-%d').date()
                    except (KeyError, ValueError):
                        continue
                    if start <= today <= end:
                        return start
        except Exception as exc:
            print('開催日程の取得失敗:', exc)
    return None


def current_series_motors(start, today):
    # Each racer/motor is read only from its most recent available race card.
    latest = {}
    day = start
    while day <= today:
        for row in update.fetch('race_cards', day):
            if not is_omura(row):
                continue
            for boat in range(1, 7):
                prefix = f'艇{boat}_'
                motor = str(row.get(prefix + 'モーター番号', '')).strip()
                racer = str(row.get(prefix + '登録番号', '')).strip()
                if not motor or not racer:
                    continue
                finishes = []
                for d in range(1, 8):
                    for race in range(1, 3):
                        value = str(row.get(f'{prefix}節D{d}走{race}_着順', '')).strip()
                        if value in ('1', '2', '3', '4', '5', '6', '１', '２', '３', '４', '５', '６'):
                            finishes.append(int(value.translate(str.maketrans('１２３４５６', '123456'))))
                rate = update.num(row.get(prefix + '全国勝率'))
                key = (motor, racer)
                previous = latest.get(key)
                if previous is None or len(finishes) > len(previous['finishes']):
                    latest[key] = {'motor': motor, 'racer': row.get(prefix + '選手名', ''), 'finishes': finishes, 'rate': rate}
        day += timedelta(days=1)
    grouped = {}
    for item in latest.values():
        grouped.setdefault(item['motor'], []).append(item)
    return grouped


def main():
    update.main()
    path = update.ROOT / 'docs' / 'data.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    data['stadium'] = '大村'
    today = datetime.now(update.JST).date()
    start = current_series_start(today)
    data['current_series_start'] = start.isoformat() if start else None
    data['current_series_status'] = '開催期間外または日程未取得' if start is None else '集計済み'
    grouped = current_series_motors(start, today) if start else {}
    # Include motors seen in the current series even if the stats snapshot omits them.
    existing = {str(m['number']) for m in data['motors']}
    added = 0
    for number in sorted(grouped, key=lambda x: int(x) if x.isdigit() else 999):
        if number in existing:
            continue
        data['motors'].append({
            'number': number, 'score': 50.0, 'raw_score': None,
            'corrected_score': 50.0, 'score_difference': None,
            'rank': 'B', 'two_rate': None, 'three_rate': None,
            'starts': None, 'period_start': '', 'uses': [],
            'confidence': '低', 'skill_matched': 0, 'skill_total': 0,
            'past_data_missing': True,
        })
        added += 1
    print('今節から新たに追加したモーター:', added)

    for motor in data['motors']:
        motor['past_three_score'] = motor['score']
        entries = grouped.get(str(motor['number']), [])
        finishes = [f for entry in entries for f in entry['finishes']]
        motor['current_series_races'] = len(finishes)
        motor['current_series_avg_finish'] = round(statistics.mean(finishes), 2) if finishes else None
        motor['current_series_uses'] = [
            {'racer': e['racer'], 'finishes': e['finishes'], 'racer_win_rate': e['rate']}
            for e in entries
        ]
        if not finishes:
            motor['current_series_score'] = None
            motor['overall_score'] = motor['score']
            continue
        # Same deviation and provisional skill adjustment as update.py.
        deviations = []
        for entry in entries:
            raw = (3.5 - statistics.mean(entry['finishes'])) / 2.5 * 100
            adj = ((entry['rate'] - 5.0) * 8.0) if entry['rate'] is not None else 0
            deviations.extend([raw - adj] * len(entry['finishes']))
        deviation = statistics.mean(deviations)
        current_score = round(max(0, min(100, 50 + 0.28 * deviation)), 1)
        motor['current_series_score'] = current_score
        # Limited early-series sample: cap current-series weight at 35%.
        weight = min(0.35, len(finishes) / 10 * 0.35)
        # No historical stats: use neutral 50-point prior and a
        # sample-size-dependent contribution from this series alone.
        # Keep the same conservative 35% cap used for existing motors.
        overall = round(motor['past_three_score'] * (1 - weight) + current_score * weight, 1)
        motor['overall_score'] = overall
        motor['score'] = overall
        motor['corrected_score'] = overall
        motor['rank'] = ('S' if overall >= 75 else 'A' if overall >= 62 else 'B' if overall >= 48 else 'C' if overall >= 35 else 'D')
    data['motors'].sort(key=lambda x: (-x['score'], int(x['number']) if str(x['number']).isdigit() else 999))
    data['method'] = '過去3節＋今節の暫定評価（選手全国勝率による仮補正）'
    data['warning'] = '今節は出走表の節間着順を集計。過去成績のないモーターは50点を基準とした暫定評価です。欠場・失格等は平均着順から除外。補正係数と配分比率は未検証で予測確率ではありません。'
    data['current_series_motors_added'] = added
    data['current_series_motors_with_results'] = sum(bool(m['current_series_races']) for m in data['motors'])
    if start and not grouped:
        data['current_series_status'] = '開催中だが着順データ未取得'
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print('大村・今節の着順を取得したモーター:', data['current_series_motors_with_results'])


if __name__ == '__main__':
    main()
