
import json
import update

# 大村競艇場のコードは24
def is_omura(row):
    code = row.get('場コード', row.get('レース場コード', ''))
    return str(code).strip().zfill(2) == '24'

# 丸亀用の処理を大村用に切り替える
update.is_marugame = is_omura

# 大村のデータは別の場所に保存
update.ROOT = update.ROOT / 'omura'

def main():
    # 大村のモーターデータを取得
    update.main()

    # 表示名を大村に変更
    path = update.ROOT / 'docs' / 'data.json'

    data = json.loads(path.read_text(encoding='utf-8'))
    data['stadium'] = '大村'

    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

if __name__ == '__main__':
    main()
