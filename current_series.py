
import csv
import io
import json
import statistics
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = "https://boatracecsv.github.io/data/programs/"
JST = timezone(timedelta(hours=9))

STADIUMS = {
    "15": "丸亀",
    "24": "大村",
}


def fetch(day):
    url = f"{BASE}race_cards/{day:%Y/%m/%d}.csv"

    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "MotorCurrentSeries/1.0"}
        )

        with urllib.request.urlopen(
            request, timeout=20
        ) as response:
            text = response.read().decode("utf-8-sig")

        return list(csv.DictReader(io.StringIO(text)))

    except Exception as error:
        print("取得できません:", day, str(error)[:100])
        return []


def number(value):
    try:
        return float(str(value).replace("%", "").strip())
    except (ValueError, TypeError):
        return None


def venue_code(row):
    return str(
        row.get("レース場コード", row.get("場コード", ""))
    ).strip().zfill(2)


def get_races(days=12):
    today = datetime.now(JST).date()
    races = []

    for ago in range(days):
        day = today - timedelta(days=ago)

        for row in fetch(day):
            if venue_code(row) in STADIUMS:
                races.append((day, row))

    return races


def extract_results(races, code):
    """
    出走表の各艇データから結果を取得する。
    結果が空欄のレースは評価しない。
    """
    results = []

    for day, row in races:
        if venue_code(row) != code:
            continue

        for boat in range(1, 7):
            prefix = f"艇{boat}_"

            motor = str(
                row.get(prefix + "モーター番号", "")
            ).strip()

            racer = str(
                row.get(prefix + "選手名", "")
            ).strip()

            finish = number(
                row.get(prefix + "節D1走1_着順")
            )

            # 出走表には節D1走1～節D7走2の
            # 着順・進入・STが含まれる。
            for series_day in range(1, 8):
                for race_no in (1, 2):
                    key = (
                        f"{prefix}節D{series_day}"
                        f"走{race_no}_"
                    )

                    finish = number(
                        row.get(key + "着順")
                    )

                    course = number(
                        row.get(key + "進入")
                    )

                    if finish is None:
                        continue

                    if not 1 <= finish <= 6:
                        continue

                    if not motor:
                        continue

                    racer_rate = number(
                        row.get(prefix + "全国勝率")
                    )

                    results.append({
                        "date": day.isoformat(),
                        "motor": motor,
                        "racer": racer,
                        "finish": finish,
                        "course": course,
                        "racer_rate": racer_rate,
                        "series_day": series_day,
                        "race_no": race_no,
                    })

    return results


def evaluate(results):
    groups = {}

    # 同じ出走表が複数日に掲載されていても、
    # 同一の節内成績を二重計上しない。
    seen = set()

    for row in results:
        key = (
            row["motor"],
            row["racer"],
            row["series_day"],
            row["race_no"],
            row["finish"],
        )

        if key in seen:
            continue

        seen.add(key)

        groups.setdefault(
            row["motor"], []
        ).append(row)

    evaluations = {}

    for motor, rows in groups.items():
        scores = []

        for row in rows:
            finish = row["finish"]
            course = row["course"]
            racer_rate = row["racer_rate"]

            # 着順を基準とした仮評価
            score = 50 + (3.5 - finish) * 12

            # 外側の進入コースを考慮
            if course is not None and 1 <= course <= 6:
                score += (course - 3.5) * 3

            # 選手の全国勝率を考慮
            if racer_rate is not None:
                score -= (racer_rate - 5.0) * 8

            scores.append(
                max(0, min(100, score))
            )

        if not scores:
            continue

        evaluations[motor] = {
            "current_score": round(
                statistics.mean(scores), 1
            ),
            "current_races": len(scores),
            "current_avg_finish": round(
                statistics.mean(
                    row["finish"] for row in rows
                ), 2
            ),
            "current_racer": rows[-1]["racer"],
        }

    return evaluations


def update_file(path, evaluations):
    if not path.exists():
        print("ファイルなし:", path)
        return

    data = json.loads(
        path.read_text(encoding="utf-8")
    )

    updated = 0

    for motor in data.get("motors", []):
        number_id = str(motor.get("number", ""))
        current = evaluations.get(number_id)

        previous = motor.get(
            "corrected_score",
            motor.get("score", 50)
        )

        motor["previous_score"] = previous

        if current:
            races = current["current_races"]

            # 最大30%、走数が少なければ軽く反映
            weight = min(0.30, races * 0.05)

            combined = round(
                previous * (1 - weight)
                + current["current_score"] * weight,
                1
            )

            motor.update(current)
            motor["current_weight"] = round(
                weight, 2
            )
            motor["combined_score"] = combined
            motor["score"] = combined

            updated += 1
        else:
            motor["current_score"] = None
            motor["current_races"] = 0
            motor["current_weight"] = 0
            motor["combined_score"] = previous
            motor["score"] = previous

        score = motor["score"]

        motor["rank"] = (
            "S" if score >= 75
            else "A" if score >= 62
            else "B" if score >= 48
            else "C" if score >= 35
            else "D"
        )

    data["current_series_method"] = (
        "今節の着順・進入・選手全国勝率による仮評価"
    )

    data["current_series_updated_at"] = (
        datetime.now(JST).isoformat(
            timespec="minutes"
        )
    )

    data["warning"] = (
        "過去3節の選手補正評価と今節の仮評価を"
        "組み合わせた試験的なスコアです。"
        "今節データの収録状況と重複除外の"
        "正確性は未検証です。"
        "予測確率ではありません。"
    )

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(path, "今節評価あり:", updated)


def main():
    root = Path(__file__).parent

    races = get_races()

    for code, name in STADIUMS.items():
        evaluations = evaluate(
            extract_results(races, code)
        )

        path = (
            root / "docs" / "data.json"
            if code == "15"
            else root / "omura" / "docs" / "data.json"
        )

        print(name, "今節評価対象:", len(evaluations))

        update_file(path, evaluations)


if __name__ == "__main__":
    main()
