#!/usr/bin/env bash
set -euo pipefail

REPO_FULL="Kisuke0810/morning-timetree0810"
WORKFLOW_NAME="Morning TimeTree → LINE"

echo "[1/7] 前提チェック: CWDと必要ファイルを確認"
pwd
for f in requirements.txt scripts/notify_today.py data .github/workflows/morning.yml; do
  if [ ! -e "$f" ]; then
    echo "ERROR: 必要ファイルが見つかりません: $f" >&2
    exit 1
  fi
done

echo "[2/7] Git 初期化と設定確認"
if [ ! -d .git ]; then
  git init -b main
fi
current_branch=$(git rev-parse --abbrev-ref HEAD)
if [ "$current_branch" != "main" ]; then
  git branch -M main
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
  git add -A
  git commit -m "chore: bootstrap"
fi
echo "git user.name: $(git config --get user.name || echo '<unset>')"
echo "git user.email: $(git config --get user.email || echo '<unset>')"

echo "[3/7] gh の有無とログイン確認（ブラウザ承認が必要）"
if ! command -v gh >/dev/null 2>&1; then
  echo "ERROR: gh が見つかりません。GitHub CLI をインストールしてください。" >&2
  echo "参考: https://github.com/cli/cli#installation" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "gh auth login を開始します。ブラウザで承認してください。" >&2
  gh auth login --web --hostname github.com
fi
gh auth status || true

echo "[4/7] リポジトリの作成/紐づけとプッシュ"
if ! gh repo view "$REPO_FULL" >/dev/null 2>&1; then
  gh repo create "$REPO_FULL" --public --source=. --remote=origin --push
else
  # 既存なら remote を張り直して push
  if git remote get-url origin >/dev/null 2>&1; then
    git remote remove origin || true
  fi
  git remote add origin "https://github.com/${REPO_FULL}.git"
  git push -u origin main
fi

echo "[5/7] Secrets の登録（値は表示しません）"
set_secret() {
  local key="$1"; shift
  local prompt="$1"; shift
  local optional="${1:-}" # optional if 'optional'
  local val=""
  if [ "$optional" = "optional" ]; then
    read -r -s -p "$prompt (空ならスキップ): " val || true; echo
    if [ -z "$val" ]; then
      echo "skip $key"
      return 0
    fi
  else
    read -r -s -p "$prompt: " val; echo
    if [ -z "$val" ]; then
      echo "ERROR: $key が空です" >&2
      exit 1
    fi
  fi
  printf %s "$val" | gh secret set "$key" -b - >/dev/null
  echo "set $key"
}

set_secret TIMETREE_EMAIL "TIMETREE_EMAIL (TimeTree ログインメール)"
set_secret TIMETREE_PASSWORD "TIMETREE_PASSWORD (TimeTree パスワード)"
set_secret TIMETREE_CAL_CODE "TIMETREE_CAL_CODE (任意)" optional
set_secret LINE_CHANNEL_ACCESS_TOKEN "LINE_CHANNEL_ACCESS_TOKEN"
set_secret LINE_TO "LINE_TO (自分=U… / グループ=C…)"

echo "登録済みSecrets:"
gh secret list

echo "[6/7] ワークフローの手動実行"
gh workflow list | sed -n '1,200p'
gh workflow run "$WORKFLOW_NAME"
sleep 3
run_url=$(gh run list --workflow "$WORKFLOW_NAME" --limit 1 --json url -q '.[0].url' || true)
echo "Triggered: ${run_url:-<url not detected>}"
echo "ログを追跡します（Ctrl+Cで中断可）"
if gh run watch; then
  status_summary="success"
else
  status_summary="completed (check details)"
fi

# 直近の実行の結果を取得
conclusion=$(gh run list --workflow "$WORKFLOW_NAME" --limit 1 --json conclusion -q '.[0].conclusion' 2>/dev/null || true)
html_url=$(gh run list --workflow "$WORKFLOW_NAME" --limit 1 --json url -q '.[0].url' 2>/dev/null || true)

echo "[7/7] 完了"
echo "リポURL: https://github.com/${REPO_FULL}"
echo "毎朝の送信時刻: JST 9:00（cron: 0 0 * * *）"
echo "直近の実行: ${html_url:-<unknown>}"
echo "結論: ${conclusion:-<unknown>}"
echo "失敗時のチェックリスト:"
echo "- TimeTree 連携: TIMETREE_EMAIL/PASSWORD/CAL_CODE（必要なら）"
echo "- LINE: LINE_CHANNEL_ACCESS_TOKEN/LINE_TO（友だち・参加済みか）"
echo "- 実行ログ: Export/Send 各ステップのエラー詳細"
