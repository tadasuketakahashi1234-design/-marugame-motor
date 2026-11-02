
#!/usr/bin/env python3
"""24-venue forward prediction ledger."""
import csv
import datetime as dt
import io
import itertools
import json
import math
import os
import pathlib
import tempfile
import urllib.request
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
NOW = dt.datetime.now(JST)
DAY = NOW.strftime("%Y-%m-%d")
DATEPATH = NOW.strftime("%Y/%m/%d")
ROOT = "https://boatracecsv.github.io/data/"
OUT = pathlib.Path("omura/docs/boat24_ledger.json")

KINDS = {
    "cards": "programs/race_cards",
    "waku": "programs/waku10",
    "motor": "programs/motor_stats",
    "ex": "previews/tkz",
    "st": "previews/stt",
    "weather": "previews/sui",
    "original": "previews/original_exhibition",
    "odds": "previews/od3",
    "results": "results/realtime",
    "payouts": "results/payouts",
}

def load(kind, path=DATEPATH):
    try:
        url = ROOT + KINDS[kind] + "/" + path + ".csv"
        req = urllib.request.Request(
            url, headers={"User-Agent": "boat24-research/1.1"}
        )
        with urllib.request.urlopen(req, timeout=18) as f:
            return list(csv.DictReader(
                io.StringIO(f.read().decode("utf-8-sig"))
            ))
    except Exception as e:
        print("unavailable", kind, str(e)[:100])
        return []

def num(x):
    try:
        return float(str(x).replace(",", "").replace("円", "").strip())
    except (ValueError, TypeError):
        return None

def timestamp(s):
    if not s:
        return None
    s = str(s).strip().replace("T", " ").replace("Z", "+00:00")
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
    ):
        try:
            return dt.datetime.strptime(s, fmt).replace(tzinfo=JST)
        except ValueError:
            pass
    try:
        t = dt.datetime.fromisoformat(s)
        return t.replace(tzinfo=JST) if t.tzinfo is None else t.astimezone(JST)
    except ValueError:
        return None

def deadline(row):
    if not row:
        return None
    v = row.get("締切時刻") or row.get("締切予定時刻")
    t = timestamp(v)
    if t:
        return t
    if v and ":" in str(v):
        try:
            return dt.datetime.combine(
                NOW.date(),
                dt.time.fromisoformat(str(v).strip()[:5]),
                JST,
            )
        except ValueError:
            pass
    return None

def pre_cutoff(row, limit):
    if not row or not limit:
        return False
    t = timestamp(
        row.get("取得日時")
        or row.get("更新日時")
        or row.get("気象観測時刻")
    )
    return bool(t and t <= NOW and t < limit)

def index(rows):
    return {
        r["レースコード"]: r
        for r in rows if r.get("レースコード")
    }

def motor_index(rows):
    return {
        (
            str(r.get("場コード", "")).zfill(2),
            str(r.get("モーター番号", "")).lstrip("0"),
        ): r
        for r in rows
    }

def probabilities(card, ex, mot):
    exs = [
        num(ex.get(f"艇{i}_展示タイム"))
        for i in range(1, 7)
    ]
    xs = sorted(v for v in exs if v is not None)
    med = xs[len(xs) // 2] if xs else None
    score = []

    for i in range(1, 7):
        w = num(card.get(f"艇{i}_全国勝率")) or 5
        local = num(card.get(f"艇{i}_当地勝率"))
        motor = num(card.get(f"艇{i}_モーター2連対率"))
        e = exs[i - 1]

        s = (w - 5) * .62
        if local is not None:
            s += (local - 5) * .18

        s += [1, .35, 0, -.25, -.48, -.65][i - 1]

        if motor is not None:
            s += max(-4, min(4, (motor - 35) * .11)) * .12
        if med is not None and e is not None:
            s += max(-3, min(3, (med - e) * 9)) * .12

        score.append(s)

    combos = [
        (
            f"{a+1}-{b+1}-{c+1}",
            score[a] * .58 + score[b] * .29 + score[c] * .13,
        )
        for a, b, c in itertools.permutations(range(6), 3)
    ]

    peak = max(s for _, s in combos)
    weights = [math.exp((s - peak) * 1.15) for _, s in combos]
    total = sum(weights)

    return {
        c: round(v / total, 9)
        for (c, _), v in zip(combos, weights)
    }

def settlement(rec, res, pay):
    if rec.get("result") is not None or not res or not pay:
        return False

    vals = [
        str(res.get(f"{i}着_艇番", "")).strip()
        for i in (1, 2, 3)
    ]
    if any(v not in "123456" or len(v) != 1 for v in vals):
        return False
    if len(set(vals)) != 3:
        return False

    money = num(next(
        (v for k, v in pay.items()
         if "3連単" in k and "払戻" in k),
        None,
    ))
    if money is None:
        return False

    actual = "-".join(vals)
    rec["result"] = {
        "combo": actual,
        "payout_100yen": money,
        "settled_at": NOW.isoformat(),
        "paper": {
            str(n): {
                "hit": actual in rec["selection"][str(n)],
                "stake": n * 100,
                "return": (
                    money if actual in rec["selection"][str(n)]
                    else 0
                ),
            }
            for n in (12, 18)
        },
    }
    return True

def main():
    if OUT.exists():
        old = json.loads(OUT.read_text(encoding="utf-8"))
    else:
        old = {
            "schema": 2,
            "model": "baseline-0.2-UNVALIDATED",
            "predictions": {},
            "diagnostics": {},
        }

    preds = old.setdefault("predictions", {})
    data = {k: load(k) for k in KINDS}
    ix = {
        k: index(v)
        for k, v in data.items() if k != "motor"
    }
    mi = motor_index(data["motor"])

    made = 0
    settled = 0
    skipped = {}

    for code, card in ix["cards"].items():
        if len(code) != 12:
            continue
        if code[:8] != NOW.strftime("%Y%m%d"):
            continue

        try:
            venue = int(code[8:10])
            race = int(code[10:12])
        except ValueError:
            continue

        if not (1 <= venue <= 24 and 1 <= race <= 12):
            continue

        rec = preds.get(code)
        res = ix["results"].get(code)
        pay = ix["payouts"].get(code)

        if rec is None:
            odds = ix["odds"].get(code) or {}
            ex = ix["ex"].get(code) or {}
            st = ix["st"].get(code) or {}

            limit = (
                deadline(card)
                or deadline(odds)
                or deadline(ex)
                or deadline(st)
            )

            if limit and NOW >= limit - dt.timedelta(minutes=2):
                skipped["cutoff_passed"] = (
                    skipped.get("cutoff_passed", 0) + 1
                )
                continue

            # Do not create a new forecast after a result exists.
            if res or pay:
                skipped["result_already_available"] = (
                    skipped.get("result_already_available", 0) + 1
                )
                continue

            # Unknown cutoff is explicitly marked unverified.
            verified = bool(limit and NOW < limit)

            sources = {}
            for kind in ("ex", "st", "weather", "original"):
                row = ix[kind].get(code) or {}
                sources[kind] = (
                    row if pre_cutoff(row, limit) else None
                )

            motors = {}
            for i in range(1, 7):
                motor_no = str(
                    card.get(f"艇{i}_モーター番号", "")
                ).lstrip("0")
                motors[str(i)] = mi.get(
                    (str(venue).zfill(2), motor_no)
                )

            p = probabilities(card, sources["ex"] or {}, motors)
            ranked = sorted(p, key=p.get, reverse=True)
            safe_odds = (
                odds if pre_cutoff(odds, limit) else None
            )

            rec = {
                "race_code": code,
                "date": DAY,
                "venue": venue,
                "race": race,
                "created_at": NOW.isoformat(),
                "cutoff": limit.isoformat() if limit else None,
                "cutoff_verified": verified,
                "evaluation_eligible": verified,
                "model": "baseline-0.2-UNVALIDATED",
                "decision": "見送り（確率未検証）",
                "stage": "provisional",
                "final_snapshot": None,
                "selection": {
                    str(n): ranked[:n] for n in (12, 18)
                },
                "probabilities": p,
                "odds": {
                    c: (
                        num(safe_odds.get("3連単_" + c))
                        if safe_odds else None
                    )
                    for c in ranked
                },
                "input_snapshot": {
                    "cards": card,
                    "waku": ix["waku"].get(code),
                    "motor_stats": motors,
                    "exhibition": sources["ex"],
                    "start_exhibition": sources["st"],
                    "weather": sources["weather"],
                    "original_exhibition": sources["original"],
                    "odds": safe_odds,
                    "motor_last_3_series": {
                        "status": "not_available",
                        "reason": "過去3節の個別使用履歴は別途再構築が必要",
                    },
                    "motor_traits": {
                        "status": "raw_original_exhibition_only",
                        "reason": "計測項目の意味と正規化は未検証",
                    },
                    "tide": {
                        "status": "not_available",
                        "reason": "全国の時刻別潮位ソース未接続",
                    },
                    "captured_at": NOW.isoformat(),
                },
                "result": None,
            }

            preds[code] = rec
            made += 1

        limit = timestamp(rec.get("cutoff"))

        if (
            limit
            and rec.get("final_snapshot") is None
            and NOW < limit
            and pre_cutoff(ix["odds"].get(code), limit)
        ):
            odds_now = ix["odds"][code]
            ex_now = ix["ex"].get(code) or {}
            ex_safe = (
                ex_now if pre_cutoff(ex_now, limit) else {}
            )

            p_final = probabilities(card, ex_safe, {})
            ranked_final = sorted(
                p_final, key=p_final.get, reverse=True
            )

            rec["final_snapshot"] = {
                "created_at": NOW.isoformat(),
                "selection": {
                    str(n): ranked_final[:n]
                    for n in (12, 18)
                },
                "probabilities": p_final,
                "odds": {
                    c: num(odds_now.get("3連単_" + c))
                    for c in ranked_final
                },
                "exhibition": ex_safe,
            }
            rec["stage"] = "final_available"

        if settlement(rec, res, pay):
            settled += 1
            if rec.get("final_snapshot"):
                actual = rec["result"]["combo"]
                money = rec["result"]["payout_100yen"]
                rec["result"]["paper_final"] = {
                    str(n): {
                        "hit": actual in
                        rec["final_snapshot"]["selection"][str(n)],
                        "stake": n * 100,
                        "return": (
                            money if actual in
                            rec["final_snapshot"]["selection"][str(n)]
                            else 0
                        ),
                    }
                    for n in (12, 18)
                }

    pending_days = sorted({
        v["date"]
        for v in preds.values()
        if v.get("result") is None and v["date"] != DAY
    })[-14:]

    for day in pending_days:
        path = day.replace("-", "/")
        results = index(load("results", path))
        payouts = index(load("payouts", path))

        for code, rec in preds.items():
            if rec["date"] == day:
                if settlement(
                    rec,
                    results.get(code),
                    payouts.get(code),
                ):
                    settled += 1

    old["schema"] = 2
    old["updated_at"] = NOW.isoformat()
    old["diagnostics"] = {
        "new_predictions": made,
        "new_settlements": settled,
        "skipped": skipped,
        "source_counts": {
            k: len(v) for k, v in data.items()
        },
        "notes": (
            "Unknown-cutoff predictions are unverified "
            "and must be excluded from performance evaluation."
        ),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=OUT.parent,
        delete=False,
    ) as f:
        json.dump(
            old, f, ensure_ascii=False, separators=(",", ":")
        )
        name = f.name

    os.replace(name, OUT)

    print(json.dumps({
        "new": made,
        "settled": settled,
        "total": len(preds),
        "skipped": skipped,
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
