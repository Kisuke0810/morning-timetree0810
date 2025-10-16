# Morning TimeTree → LINE Notifier

毎朝 10:00（JST）に TimeTree の予定（ICS）を読み取り、LINE にプッシュ通知する最小構成です。GitHub Actions のスケジュールで自動実行されます。

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
- `USE_BROADCAST`: （任意）`true/1/on/yes` のいずれかで Broadcast 送信に切替（`LINE_TO` は不要）
  
オプション（表示トグル）:

- `SHOW_MEMO`: （任意, 既定 true）false でメモを非表示
- `SHOW_LINKS`: （任意, 既定 true）false で「リンク：」行を非表示
- `MEMO_MAX`: （任意, 既定 180）メモの最大文字数

> メモ: `TIMETREE_CAL_CODE` は未設定でも動作を試みます。必要に応じて TimeTree 側の共有設定や URL に含まれるコードを利用してください。

## ディレクトリ構成

- `requirements.txt`: 使用パッケージ（timetree-exporter / icalendar / requests / pytz）
- `scripts/notify_today.py`: 本日の予定を整形し LINE に Push
- `.github/workflows/morning.yml`: 毎日 10:00 JST 実行（UTC 1:00）。まず ICS 生成 → 次に通知
- `data/timetree.ics`: 生成される ICS ファイル（GitHub Actions で生成）
- `data/.keep`: 空ファイル（ディレクトリ確保用）

## 実行（GitHub Actions）

ワークフローは以下のトリガーで実行されます。

- スケジュール: `0 1 * * *`（UTC）= 毎日 10:00（JST）
- 手動実行: Actions タブから `Run workflow`

処理手順（ワークフロー内）

1. 依存パッケージのインストール
2. `timetree-exporter` を用いて `data/timetree.ics` を生成
3. `scripts/notify_today.py` を実行し LINE に通知

メッセージの例（メモ/リンク付き）:

```
【本日の予定 2025-10-17（金）全2件】
・終日 サブスク登録&利用方法サポート
  メモ：◯◯◯…（続きあり）
  リンク：https://zoom.us/j/xxxx
・20:00 AUBE講座
  メモ：◯◯◯
```

### 手動テスト（test_message 入力）

Actions の手動実行時に `test_message` を入力すると、TimeTree の取得を行わず、その文言をそのまま送信します。

- 使い方: Actions → Morning TimeTree → LINE → Run workflow → `test_message` に任意のテキストを入力
- 送信経路: `USE_BROADCAST` が真なら Broadcast、未設定/偽なら Push（`LINE_TO` 必須）
- スクリプトは送信の HTTP ステータスと短い要約を表示します

## GitHub 自動化（gh使用）

ローカルに GitHub CLI（gh）をインストールし、以下のスクリプトでリポ作成→プッシュ→Secrets登録→ワークフロー実行まで対話で自動化できます。

1) gh の用意とログイン（認証はブラウザ承認）

- gh インストール: https://github.com/cli/cli#installation
- ログイン: `gh auth login --web --hostname github.com`

2) ブートストラップスクリプトの実行

```bash
./scripts/gh_bootstrap.sh
```

スクリプトが行うこと:
- CWD と必要ファイルの確認
- Git 初期化/ブランチ統一/初回コミット
- リポ作成/remote設定/プッシュ（`Kisuke0810/morning-timetree0810`）
- Secrets 登録（対話・値は表示しません）
  - `TIMETREE_EMAIL` / `TIMETREE_PASSWORD` / `TIMETREE_CAL_CODE(任意)`
  - `LINE_CHANNEL_ACCESS_TOKEN` / `LINE_TO`
  - 表示トグル（任意）: `SHOW_MEMO` / `SHOW_LINKS` / `MEMO_MAX`
- ワークフローを手動トリガーし、実行ログを追跡

3) 初回実行の確認

- ターミナルに表示される Run のURLを確認し、結果をチェックします。

## トラブルシューティング

- TimeTreeのICS生成に失敗する:
  - `TIMETREE_EMAIL` / `TIMETREE_PASSWORD` が正しいか
  - 必要なら `TIMETREE_CAL_CODE` を設定
- LINE送信で 401/403:
  - `LINE_CHANNEL_ACCESS_TOKEN` が正しく有効か
  - 送信先（`LINE_TO`）が Bot と友だち or グループ参加済みか
- 実行時刻の変更:
  - `.github/workflows/morning.yml` の `cron` はUTC。JSTとの差は+9時間
  - 既定は JST 10:00 → UTC 1:00（cron: `0 1 * * *`）

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

4. テスト送信（--test）

   TimeTree を読まずに任意メッセージを送るテスト:

   ```bash
   export LINE_CHANNEL_ACCESS_TOKEN=xxxxxxxx
   export LINE_TO=yyyyyyyyyyyy   # または USE_BROADCAST=true
   python scripts/notify_today.py --test "通知テストです"
   ```

## 時間（実行時刻）の変更方法

- `.github/workflows/morning.yml` の `schedule.cron` を編集します。GitHub Actions の cron は UTC です。
  - 例: JST 08:00 にしたい → UTC 23:00（前日）なので `0 23 * * *`

## 補足（仕様）

- タイムゾーンは JST 固定で処理しています。
- 全日イベント（終日）は「終日 タイトル」として表示します。
- 時刻付きイベントは開始時刻のみ `HH:MM` を表示します。
- ICS が存在しない場合、エラーで終了します（Actions では先に生成されます）。
