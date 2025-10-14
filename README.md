# Morning TimeTree → LINE Notifier

毎朝 9:00（JST）に TimeTree の予定（ICS）を読み取り、LINE にプッシュ通知する最小構成です。GitHub Actions のスケジュールで自動実行されます。

## 仕組み概要

- `timetree-exporter` を用いて TimeTree から ICS を生成（`data/timetree.ics`）。
- 生成した ICS を `scripts/notify_today.py` が読み取り、当日分に該当する予定を整形。
- LINE Messaging API の Push メッセージで送信。

## 必要な GitHub Secrets

以下のシークレットを、このリポジトリの Settings → Secrets and variables → Actions に登録してください。

- `TIMETREE_EMAIL`: TimeTree ログイン用メールアドレス
- `TIMETREE_PASSWORD`: TimeTree パスワード
- `TIMETREE_CAL_CODE`: （任意）対象カレンダーのコード。複数カレンダーがある場合などに指定
- `LINE_CHANNEL_ACCESS_TOKEN`: LINE Messaging API のチャネルアクセストークン（ロングリブ）
- `LINE_TO`: 送信先の User ID / Group ID など（Bot と友だち／グループ参加済みであること）

> メモ: `TIMETREE_CAL_CODE` は未設定でも動作を試みます。必要に応じて TimeTree 側の共有設定や URL に含まれるコードを利用してください。

## ディレクトリ構成

- `requirements.txt`: 使用パッケージ（timetree-exporter / icalendar / requests / pytz）
- `scripts/notify_today.py`: 本日の予定を整形し LINE に Push
- `.github/workflows/morning.yml`: 毎日 9:00 JST 実行（UTC 0:00）。まず ICS 生成 → 次に通知
- `data/timetree.ics`: 生成される ICS ファイル（GitHub Actions で生成）
- `data/.keep`: 空ファイル（ディレクトリ確保用）

## 実行（GitHub Actions）

ワークフローは以下のトリガーで実行されます。

- スケジュール: `0 0 * * *`（UTC）= 毎日 9:00（JST）
- 手動実行: Actions タブから `Run workflow`

処理手順（ワークフロー内）

1. 依存パッケージのインストール
2. `timetree-exporter` を用いて `data/timetree.ics` を生成
3. `scripts/notify_today.py` を実行し LINE に通知

## ローカルでのテスト方法

1. 依存インストール

   ```bash
   pip install -r requirements.txt
   ```

2. ICS の生成（例）

   代表的な CLI 例（環境によりオプションは異なる場合があります）:

   ```bash
   timetree-exporter -u "$TIMETREE_EMAIL" -p "$TIMETREE_PASSWORD" -c "$TIMETREE_CAL_CODE" -o data/timetree.ics
   ```

   うまくいかない場合は `python -m timetree_exporter` でも試せます。

3. 通知スクリプトの実行

   実際に LINE へ送る場合:

   ```bash
   export LINE_CHANNEL_ACCESS_TOKEN=xxxxxxxx
   export LINE_TO=yyyyyyyyyyyy
   python scripts/notify_today.py
   ```

   環境変数を設定しないで実行すると、DRY RUN として整形結果を標準出力に表示します（送信は行いません）。

## 時間（実行時刻）の変更方法

- `.github/workflows/morning.yml` の `schedule.cron` を編集します。GitHub Actions の cron は UTC です。
  - 例: JST 08:00 にしたい → UTC 23:00（前日）なので `0 23 * * *`

## 補足（仕様）

- タイムゾーンは JST 固定で処理しています。
- 全日イベント（終日）は「終日 タイトル」として表示します。
- 時刻付きイベントは当日範囲に重なる部分のみを `HH:MM-HH:MM` で表示します。
- ICS が存在しない場合、エラーで終了します（Actions では先に生成されます）。

