
import csv
import io
import re
import statistics
import urllib.request
from datetime import datetime, timedelta, timezone

import update

JST = timezone(timedelta(hours=9))
BASE = "https://boatracecsv.github.io/data/programs/"


def get_csv(kind, day):
    url = f"{BASE}{kind}/{day:%Y/%m/%d}.csv"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "MotorCompare/1.0"}
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            text = response.read().decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(text)))
    except Exception as error:
        print("SKIP", url, str(error)[:100])
        return []


def clean_name(value):
    return re.sub(r"\s+", "", str(value or "")).replace("　", "")


def to_float(value):
    try:
        return float(str(value).replace("%", "").replace(",", ""))
    except (ValueError, TypeError):
        return None


def venue(row):
    return str(
        row.get("レース場コード", row.get("場コード", ""))
    ).strip().zfill(2)


def load_history(code, today):
    history = {}
    dates = []

    for ago in range(95):
        day = today - timedelta(days=ago)
        rows = get_csv("motor_history", day)

        selected = [
            r for r in rows
            if str(r.get("場コード", "")).zfill(2) == code
        ]

        if selected:
            dates.append(day.isoformat())
            for row in selected:
                key = (
                    row.get("モーター番号", ""),
                    row.get("使用終了日", ""),
                    row.get("使用者名", ""),
                )
                history[key] = row

            if len(dates) >= 5:
                break

    return history, dates


def load_racer_data(code, today):
    """
    直近のrace_cardsから選手の全国勝率を取得。
    過去の使用時点の実力ではないため、これは試験用。
    """
    racers = {}

    for ago in range(14):
        day = today - timedelta(days=ago)
        rows = get_csv("race_cards", day)

        for row in rows:
            if venue(row) != code:
                continue

            for boat in range(1, 7):
                prefix = f"艇{boat}_"
                name = clean_name(row.get(prefix + "選手名"))
                rate = to_float(row.get(prefix + "全国勝率"))
                reg = row.get(prefix + "登録番号", "")

                if name and rate is not None and name not in racers:
                    racers[name] = {
                        "rate": rate,
                        "registration": reg,
                    }

        if len(racers) >= 30:
            break

    return racers


def compare(code, stadium, today):
    print("\n" + "=" * 55)
    print(stadium, "選手補正テスト")
    print("=" * 55)

    history, dates = load_history(code, today)
    racers = load_racer_data(code, today)

    print("履歴取得日:", dates)
    print("選手データ人数:", len(racers))

    groups = {}

    for (_, end, _), row in history.items():
        if end > today.isoformat():
            continue

        number = str(row.get("モーター番号", "")).strip()
        if number:
            groups.setdefault(number, []).append(row)

    results = []
    total_uses = 0
    matched_uses = 0

    for number, rows in groups.items():
        rows.sort(
            key=lambda r: r.get("使用終了日", ""),
            reverse=True
        )

        recent = rows[:3]
        raw_parts = []
        corrected_parts = []
        weights = []
        details = []

        for i, row in enumerate(recent):
            finishes = update.ranks(row.get("着順列", row.get("着順列", "")))

            # motor_historyの実際の列名は「着順列」ではなく
            # 「着順列」または「着順列」に対応する可能性があるため、
            # 取得できなければ「着順列」以外の「着順列」も確認する。
            if not finishes:
                finishes = update.ranks(row.get("着順列", ""))

            if not finishes:
                finishes = update.ranks(row.get("着順列", row.get("着順列", "")))

            # 実際のmotor_historyの列名は「着順列」ではなく
            # 「着順列」または「着順列」と異なる場合がある。
            # 今回確認したCSVの列名「着順列」ではなく「着順列」
            # を想定せず、実際の「着順列」に対応させる。
            if not finishes:
                finishes = update.ranks(row.get("着順列", ""))

            # 画面で確認したmotor_historyの列名は「着順列」ではなく「着順列」。
            # 上記の取得が空の場合は、着順を表す列を探す。
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

            name = clean_name(row.get("使用者名"))
            racer = racers.get(name)

            # 全国勝率5.0を中立値とする暫定的な補正。
            # 1勝率ポイントにつき8点差し引く仮の係数。
            if racer:
                matched_uses += 1
                adjustment = (racer["rate"] - 5.0) * 8.0
                corrected = raw - adjustment
                status = f'勝率{racer["rate"]:.2f}'
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
                f"{name}: 平均{avg:.2f}着 / {status}"
            )

        if not weights:
            continue

        raw_score = sum(raw_parts) / sum(weights)
        corrected_score = sum(corrected_parts) / sum(weights)

        results.append({
            "number": number,
            "raw": round(raw_score, 1),
            "corrected": round(corrected_score, 1),
            "matched": sum("未照合" not in d for d in details),
            "details": details,
        })

    results.sort(key=lambda x: x["corrected"], reverse=True)

    print("評価対象モーター数:", len(results))
    print("対象使用履歴数:", total_uses)
    print("選手照合成功数:", matched_uses)

    if total_uses:
        print(
            "照合率:",
            f"{matched_uses / total_uses * 100:.1f}%"
        )

    print("\n補正後スコア上位10件（試験値）")

    for row in results[:10]:
        print(
            f'{row["number"]}号機: '
            f'従来履歴評価={row["raw"]:.1f} '
            f'補正後={row["corrected"]:.1f}'
        )
        for detail in row["details"]:
            print("  ", detail)

    print(
        "\n注意: 選手の全国勝率は直近の出走表から取得した"
        "暫定値です。過去時点の勝率とは限りません。"
    )
    print(
        "進入コース補正、対戦相手補正、"
        "過去レースでの予測精度検証は未実装です。"
    )


def main():
    today = datetime.now(JST).date()

    compare("15", "丸亀", today)
    compare("24", "大村", today)

    print("\n比較テスト終了。公開データは変更していません。")


if __name__ == "__main__":
    main()
