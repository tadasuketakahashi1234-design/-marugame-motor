
import csv
import io
import json
import re
import statistics
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = "https://boatracecsv.github.io/data/programs/"
JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).parent
CACHE = {}


def fetch(kind, day):
    key = (kind, day.isoformat())
    if key in CACHE:
        return CACHE[key]

    url = f"{BASE}{kind}/{day:%Y/%m/%d}.csv"

    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "MotorDashboard/3.0"}
        )
        with urllib.request.urlopen(
            request, timeout=18
        ) as response:
            content = response.read().decode("utf-8-sig")

        rows = list(csv.DictReader(io.StringIO(content)))
    except Exception:
        rows = []

    CACHE[key] = rows
    return rows


def is_marugame(row):
    code = row.get(
        "場コード",
        row.get("レース場コード", "")
    )
    return str(code).strip().zfill(2) == "15"


def num(value):
    try:
        return float(
            str(value).replace("%", "").replace(",", "")
        )
    except (TypeError, ValueError):
        return None


def ranks(value):
    value = str(value).translate(
        str.maketrans("１２３４５６", "123456")
    )
    return [int(c) for c in value if c in "123456"]


def clean(value):
    return re.sub(r"\s+", "", str(value or ""))


def unique_history(rows):
    result = {}

    for row in rows:
        if not is_marugame(row):
            continue

        motor = str(
            row.get("モーター番号", "")
        ).strip()
        end = row.get("使用終了日", "")

        if not motor or not end:
            continue

        key = (
            motor,
            end,
            row.get("使用者名", "")
        )
        result[key] = row

    return result


def stadium_code():
    # 大村用スクリプトから呼ばれた場合も対応
    return "24" if ROOT.name == "omura" else "15"


def find_racer_rate(history_row, code):
    """
    使用当時の出走表を参照し、
    モーター番号と選手名が一致する選手の
    全国勝率を取得する。
    """
    motor = str(
        history_row.get("モーター番号", "")
    ).strip()
    racer = clean(
        history_row.get("使用者名", "")
    )

    start = history_row.get("使用開始日", "")
    end = history_row.get("使用終了日", "")

    try:
        start_day = datetime.strptime(
            start, "%Y-%m-%d"
        ).date()
        end_day = datetime.strptime(
            end, "%Y-%m-%d"
        ).date()
    except ValueError:
        return None

    if not motor or not racer:
        return None

    # 開催期間中の出走表を順番に確認
    day = start_day

    while day <= end_day:
        rows = fetch("race_cards", day)

        for row in rows:
            row_code = str(
                row.get("レース場コード", "")
            ).strip().zfill(2)

            if row_code != code:
                continue

            for boat in range(1, 7):
                prefix = f"艇{boat}_"

                card_motor = str(
                    row.get(
                        prefix + "モーター番号", ""
                    )
                ).strip()

                card_racer = clean(
                    row.get(prefix + "選手名", "")
                )

                if (
                    card_motor == motor
                    and card_racer == racer
                ):
                    rate = num(
                        row.get(prefix + "全国勝率")
                    )

                    if rate is not None:
                        return rate

        day += timedelta(days=1)

    return None


def build(stats, history, asof):
    groups = {}

    for (motor, end, _), row in history.items():
        if end <= asof:
            groups.setdefault(motor, []).append(row)

    for rows in groups.values():
        rows.sort(
            key=lambda row: row.get(
                "使用終了日", ""
            ),
            reverse=True
        )

    output = []
    code = stadium_code()

    matched = 0
    attempted = 0

    for stat in stats:
        if not is_marugame(stat):
            continue

        motor = str(
            stat.get("モーター番号", "")
        ).strip()

        if not motor:
            continue

        recent = groups.get(motor, [])[:3]

        uses = []
        raw_parts = []
        corrected_parts = []
        weights = []

        for i, row in enumerate(recent):
            placings = ranks(
                row.get("着順列", "")
            )

            if not placings:
                continue

            avg = statistics.mean(placings)

            raw_deviation = (
                (3.5 - avg) / 2.5 * 100
            )

            attempted += 1

            racer_rate = find_racer_rate(
                row, code
            )

            if racer_rate is not None:
                matched += 1

                # 試験用の選手補正係数
                skill_adjustment = (
                    racer_rate - 5.0
                ) * 8.0

                corrected_deviation = (
                    raw_deviation - skill_adjustment
                )
            else:
                corrected_deviation = raw_deviation

            weight = (
                [0.5, 0.3, 0.2][i]
                * min(1, len(placings) / 5)
            )

            raw_parts.append(
                raw_deviation * weight
            )
            corrected_parts.append(
                corrected_deviation * weight
            )
            weights.append(weight)

            uses.append({
                "start": row.get(
                    "使用開始日", ""
                ),
                "end": row.get(
                    "使用終了日", ""
                ),
                "racer": row.get(
                    "使用者名", ""
                ),
                "grade": row.get(
                    "グレード", ""
                ),
                "finishes": row.get(
                    "着順列", ""
                ),
                "races": len(placings),
                "avg_finish": round(avg, 2),
                "racer_win_rate": racer_rate,
                "skill_adjusted": (
                    racer_rate is not None
                )
            })

        raw_history = (
            sum(raw_parts) / sum(weights)
            if weights else 0
        )

        corrected_history = (
            sum(corrected_parts) / sum(weights)
            if weights else 0
        )

        two = num(stat.get("2連対率"))
        three = num(stat.get("3連対率"))

        base = (
            50
            + 0.22 * (
                (two if two is not None else 33)
                - 33
            )
            + 0.10 * (
                (three if three is not None else 50)
                - 50
            )
        )

        raw_score = round(
            max(
                0,
                min(
                    100,
                    base + 0.28 * raw_history
                )
            ),
            1
        )

        corrected_score = round(
            max(
                0,
                min(
                    100,
                    base + 0.28 * corrected_history
                )
            ),
            1
        )

        if corrected_score >= 75:
            rank = "S"
        elif corrected_score >= 62:
            rank = "A"
        elif corrected_score >= 48:
            rank = "B"
        elif corrected_score >= 35:
            rank = "C"
        else:
            rank = "D"

        confidence = (
            "高"
            if len(uses) == 3
            and sum(
                u["races"] for u in uses
            ) >= 15
            else (
                "中"
                if len(uses) >= 2
                else "低"
            )
        )

        output.append({
            "number": motor,
            "score": corrected_score,
            "raw_score": raw_score,
            "corrected_score": corrected_score,
            "score_difference": round(
                corrected_score - raw_score,
                1
            ),
            "rank": rank,
            "two_rate": two,
            "three_rate": three,
            "starts": num(
                stat.get("出走数")
            ),
            "period_start": stat.get(
                "モーター期起算日", ""
            ),
            "uses": uses,
            "confidence": confidence,
            "skill_matched": sum(
                1 for u in uses
                if u["skill_adjusted"]
            ),
            "skill_total": len(uses)
        })

    output.sort(
        key=lambda row: (
            -row["score"],
            int(row["number"])
            if row["number"].isdigit()
            else 999
        )
    )

    print("選手照合:", matched, "/", attempted)

    return output


def main():
    today = datetime.now(JST).date()

    stats = []
    stat_date = None

    for ago in range(22):
        day = today - timedelta(days=ago)

        rows = [
            row
            for row in fetch(
                "motor_stats", day
            )
            if is_marugame(row)
        ]

        if rows:
            stats = rows
            stat_date = day
            break

    if not stats:
        raise SystemExit(
            "モーター期成績が取得できません。"
        )

    history = {}
    found = []

    for ago in range(95):
        day = today - timedelta(days=ago)

        selected = [
            row
            for row in fetch(
                "motor_history", day
            )
            if is_marugame(row)
        ]

        if selected:
            history.update(
                unique_history(selected)
            )
            found.append(day.isoformat())

            if len(found) >= 5:
                break

    motors = build(
        stats,
        history,
        today.isoformat()
    )

    if not motors:
        raise SystemExit(
            "モーター評価が空のため中止"
        )

    name = (
        "大村"
        if stadium_code() == "24"
        else "丸亀"
    )

    output = {
        "updated_at": datetime.now(
            JST
        ).isoformat(timespec="minutes"),
        "stats_date": stat_date.isoformat(),
        "history_snapshot_dates": found,
        "stadium": name,
        "method": "選手全国勝率による仮補正",
        "warning": (
            "選手の全国勝率を用いた"
            "試験的な補正評価です。"
            "補正係数は未検証で、"
            "進入コース・対戦相手は未補正。"
            "予測確率ではありません。"
        ),
        "motors": motors
    }

    destination = ROOT / "docs" / "data.json"
    destination.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    destination.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(
        f"{name}: {len(motors)}基の"
        "補正後データを作成しました"
    )


if __name__ == "__main__":
    main()
