
import csv
import io
import re
import statistics
import urllib.request
from datetime import datetime, timedelta, timezone

import update

JST = timezone(timedelta(hours=9))
BASE = "https://boatracecsv.github.io/data/programs/"


def fetch(kind, day):
    url = f"{BASE}{kind}/{day:%Y/%m/%d}.csv"
    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "MotorCompare/2.0"}
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            content = response.read().decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(content)))
    except Exception:
        return []


def clean(value):
    return re.sub(r"\s+", "", str(value or ""))


def number(value):
    try:
        return float(str(value).replace("%", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def code(row):
    return str(
        row.get("レース場コード", row.get("場コード", ""))
    ).strip().zfill(2)


def get_history(stadium, today):
    history = {}
    dates = []

    for ago in range(95):
        day = today - timedelta(days=ago)
        rows = fetch("motor_history", day)

        selected = [
            row for row in rows
            if str(row.get("場コード", "")).zfill(2) == stadium
        ]

        if selected:
            dates.append(day.isoformat())

            for row in selected:
                key = (
                    row.get("モーター番号", ""),
                    row.get("使用終了日", ""),
                    row.get("使用者名", "")
                )
                history[key] = row

            if len(dates) >= 5:
                break

    return history, dates


def collect_race_cards(stadium, history, today):
    """
    過去のモーター使用期間に対応する出走表を調べる。
    日付・モーター番号・選手名を使って照合する。
    """
    targets = []

    for row in history.values():
        start = row.get("使用開始日", "")
        end = row.get("使用終了日", "")
        motor = str(row.get("モーター番号", "")).strip()
        racer = clean(row.get("使用者名", ""))

        try:
            start_day = datetime.strptime(start, "%Y-%m-%d").date()
            end_day = datetime.strptime(end, "%Y-%m-%d").date()
        except ValueError:
            continue

        if start_day > today or end_day > today:
            continue

        targets.append({
            "start": start_day,
            "end": end_day,
            "motor": motor,
            "racer": racer,
        })

    if not targets:
        return {}

    earliest = min(t["start"] for t in targets)
    latest = min(today, max(t["end"] for t in targets))

    # 同じ選手・モーターでも開催期間が異なれば別扱い。
    matches = {}

    day = earliest
    fetched = 0

    while day <= latest:
        rows = fetch("race_cards", day)

        for row in rows:
            if code(row) != stadium:
                continue

            for boat in range(1, 7):
                prefix = f"艇{boat}_"

                motor = str(
                    row.get(prefix + "モーター番号", "")
                ).strip()

                racer = clean(
                    row.get(prefix + "選手名", "")
                )

                rate = number(
                    row.get(prefix + "全国勝率")
                )

                registration = str(
                    row.get(prefix + "登録番号", "")
                ).strip()

                if not motor or not racer or rate is None:
                    continue

                for target in targets:
                    if (
                        target["motor"] == motor
                        and target["racer"] == racer
                        and target["start"] <= day <= target["end"]
                    ):
                        key = (
                            motor,
                            target["start"].isoformat(),
                            target["end"].isoformat(),
                            racer
                        )

                        if key not in matches:
                            matches[key] = {
                                "rate": rate,
                                "registration": registration,
                                "date": day.isoformat()
                            }

        fetched += 1
        day += timedelta(days=1)

    print("調査した日数:", fetched)
    print("照合できた使用履歴:", len(matches))

    return matches


def compare(stadium, name, today):
    print("\n" + "=" * 45)
    print(name, "選手補正比較テスト")
    print("=" * 45)

    history, dates = get_history(stadium, today)

    print("履歴取得日:", dates)
    print("取得した使用履歴:", len(history))

    matches = collect_race_cards(
        stadium, history, today
    )

    groups = {}

    for row in history.values():
        end = row.get("使用終了日", "")

        if end > today.isoformat():
            continue

        motor = str(row.get("モーター番号", "")).strip()

        if motor:
            groups.setdefault(motor, []).append(row)

    results = []
    total_uses = 0
    matched_uses = 0

    for motor, rows in groups.items():
        rows.sort(
            key=lambda r: r.get("使用終了日", ""),
            reverse=True
        )

        raw_parts = []
        corrected_parts = []
        weights = []
        details = []

        for i, row in enumerate(rows[:3]):
            finishes = update.ranks(
                row.get("着順列", "")
            )

            if not finishes:
                finishes = update.ranks(
                    row.get("着順列", row.get("着順列", ""))
                )

            if not finishes:
                for key, value in row.items():
                    if "着順" in key:
                        finishes = update.ranks(value)
                        if finishes:
                            break

            if not finishes:
                continue

            total_uses += 1

            avg = statistics.mean(finishes)
            raw = (3.5 - avg) / 2.5 * 100

            racer = clean(row.get("使用者名"))
            start = row.get("使用開始日", "")
            end = row.get("使用終了日", "")

            key = (motor, start, end, racer)
            match = matches.get(key)

            if match:
                matched_uses += 1

                # 試験用の仮補正係数。
                adjustment = (
                    match["rate"] - 5.0
                ) * 8.0

                corrected = raw - adjustment

                status = (
                    f'全国勝率{match["rate"]:.2f}'
                )
            else:
                corrected = raw
                status = "未照合"

            weight = [0.5, 0.3, 0.2][i] * min(
                1.0, len(finishes) / 5
            )

            raw_parts.append(raw * weight)
            corrected_parts.append(corrected * weight)
            weights.append(weight)

            details.append(
                f"{racer}: 平均{avg:.2f}着 / {status}"
            )

        if not weights:
            continue

        results.append({
            "motor": motor,
            "raw": round(
                sum(raw_parts) / sum(weights), 1
            ),
            "corrected": round(
                sum(corrected_parts) / sum(weights), 1
            ),
            "details": details
        })

    results.sort(
        key=lambda row: row["corrected"],
        reverse=True
    )

    print("評価対象モーター:", len(results))
    print("対象使用履歴:", total_uses)
    print("選手照合成功:", matched_uses)

    if total_uses:
        print(
            "照合率:",
            f"{matched_uses / total_uses * 100:.1f}%"
        )

    print("\n補正後ランキング上位10件")

    for row in results[:10]:
        print(
            f'{row["motor"]}号機 '
            f'補正前={row["raw"]} '
            f'補正後={row["corrected"]}'
        )

        for detail in row["details"]:
            print(" ", detail)

    print(
        "\n注意：補正係数は仮の値です。"
        "進入コース・対戦相手の補正や"
        "予測精度の検証は未実施です。"
    )


def main():
    today = datetime.now(JST).date()

    compare("15", "丸亀", today)
    compare("24", "大村", today)

    print("\n比較テスト終了。公開データは変更していません。")


if __name__ == "__main__":
    main()
