総合予想の入力使用と検証仕様は [ALL_INPUT_MODEL.md](ALL_INPUT_MODEL.md) を参照してください。

全国24場の予想保存・結果取得・回収率の運用は [BOAT24_OPERATIONS.md](BOAT24_OPERATIONS.md) を参照してください。

# 丸亀モーター評価ダッシュボード

スマホから閲覧できる静的Webサイト。GitHub Actionsが毎朝CSVを取得し、`docs/data.json`を更新します。**選手の実力補正はまだ未実装**です。点数は暫定的な着順・期成績指標で、的中確率ではありません。

## 初心者向け公開手順

1. GitHubアカウントを作り、**Public**リポジトリ `marugame-motor` を作成。
2. このZIPを解凍し、`update.py`、`README.md`、`docs`、`.github`、`tests` をリポジトリ直下にアップロード。`.github` は隠しフォルダなので注意。
3. GitHubの **Settings → Actions → General → Workflow permissions** で **Read and write permissions** を選択して保存（組織ポリシーによって不可の場合あり）。
4. **Actions → Update Marugame motors → Run workflow** を押す。実行成功で `docs/data.json` が作られる。
5. **Settings → Pages → Build and deployment** で **Deploy from a branch**、Branch `main`、Folder `/docs` を選んで保存。
6. 数分後に `https://あなたのユーザー名.github.io/marugame-motor/` をスマホで開く。ブックマークまたはホーム画面に追加。

### 更新スケジュール

GitHub Actionsの `cron` はUTC指定。`15 22 * * *` は日本時間の毎朝07:15頃。実行が遅れる場合があります。無料プランの実行枠・Pagesの公開条件はGitHub側の最新規約を確認してください。

### データが出ないとき

- `Actions` のログを確認。`No Marugame motor_stats` の場合は過去22日間の対象CSVに丸亀の記録がありません。データを捏造せず更新を停止します。
- 履歴は「日付＝その節の終了日」であり、当日のファイルとは限りません。過去95日間を探します。
- CSV公開側の仕様変更、アクセス制限、履歴欠損がある場合は変更が必要です。
- GitHub Pagesは公開サイトです。秘密情報をアップロードしないでください。

### 注意点・今後の改良

- 現版は**選手の実力・コース・相手関係・展示タイムを補正していません**。着順平均からの偏差と2/3連対率で作る暫定指標です。
- 選手補正を正しく実装するには、各走の選手ID、コース、相手選手、当時の選手成績をレース単位で結合し、過去情報のみで期待成績を学習する必要があります。
- モーターの期が変わった場合、過去期の履歴を除外する追加ロジックが必要です。現版では期跨ぎを厳密に除外できないため、**期交換直後は参考値として使用しないでください**。
- 95日×最大18秒の取得で時間がかかる場合があります。節終了日一覧から探索する最適化が次の改善点です。
- 本コードは実環境でのデータ取得・Pages公開まで検証済みではありません。

## ローカルテスト

```sh
python -m unittest discover -s tests
python update.py
python -m http.server 8000 -d docs
```

`http://localhost:8000` を開くと画面を確認できます。

データ出典: https://boatracecsv.github.io/docs/data/programs.html
