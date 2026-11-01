
import csv
import io
import json
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://boatracecsv.github.io/data/programs/"
JST = timezone(timedelta(hours=9))


def fetch(kind, day):
    url = f"{BASE}{kind}/{day:%Y/%m/%d}.csv"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "MotorDataTest/1.0"}
        )
        with urllib.request.urlopen(req, timeout=18) as response:
            content = response.read().decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(content)))
        print(f"OK: {kind} {day} ({len(rows)} rows)")
        return rows
    except Exception as error:
        print(f"SKIP: {kind} {day}: {str(error)[:100]}")
        return []


def venue(row):
    return str(
        row.get("場コード", row.get("レース場コード", ""))
    ).strip().zfill(2)


def sample_fields(rows, title):
    print(f"\n--- {title} ---")
    if not rows:
        print("データなし")
        return

    print("項目名:")
    for key in rows[0].keys():
        print(" -", key)

    print("先頭データ（最大3件）:")
    for row in rows[:3]:
        print(json.dumps(row, ensure_ascii=False))


def find_latest(kind, days=14):
    today = datetime.now(JST).date()
    for ago in range(days):
        day = today - timedelta(days=ago)
        rows = fetch(kind, day)
        if rows:
            return day, rows
    return None, []


def main():
    print("=== 選手補正用データの確認 ===")

    kinds = [
        "race_cards",
        "recent_national",
        "recent_local",
        "motor_history",
    ]

    for kind in kinds:
        day, rows = find_latest(kind)

        if not rows:
            print(f"\n{kind}: 取得できませんでした")
            continue

        selected = [
            row for row in rows
            if venue(row) in ("15", "24")
        ]

        print(f"\n取得日: {day}")
        print(f"全件: {len(rows)}")
        print(f"丸亀・大村: {len(selected)}")

        sample_fields(
            selected if selected else rows,
            kind
        )

    print("\n=== テスト終了 ===")
    print("既存のランキングデータは変更していません。")


if __name__ == "__main__":
    main()
