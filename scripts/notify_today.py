#!/usr/bin/env python3
import os
import sys
import argparse
from datetime import datetime, date, time, timedelta
from pathlib import Path

import re
from zoneinfo import ZoneInfo
import requests
from icalendar import Calendar
import time as pytime


JST = ZoneInfo("Asia/Tokyo")


def today_jst() -> date:
    """JSTベースの「今日」の日付を返す"""
    return datetime.now(JST).date()


def get_today_range_jst(now: datetime | None = None):
    """
    Return (day_start, day_end) for "today" in JST as tz-aware datetimes.
    day_start is today 00:00 JST, day_end is tomorrow 00:00 JST.
    """
    if now is None:
        now = datetime.now(JST)
    else:
        if now.tzinfo is None:
            now = now.replace(tzinfo=JST)
        else:
            now = now.astimezone(JST)
    day_start = datetime(now.year, now.month, now.day, 0, 0, tzinfo=JST)
    day_end = day_start + timedelta(days=1)
    return day_start, day_end


def load_calendar(ics_path: Path) -> Calendar:
    if not ics_path.exists():
        print(f"ICSが見つかりません: {ics_path}", file=sys.stderr)
        sys.exit(1)
    data = ics_path.read_bytes()
    return Calendar.from_ical(data)


# (旧ロジック to_tz/event_time_range_jst/normalize_event は ZoneInfo/JSTベースの as_jst_range へ統合)


def get_env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


def extract_meeting_link(text: str, url_prop: str = "") -> str:
    patterns = [
        r"https?://[\w.-]*zoom\.us/\S+",
        r"https?://meet\.google\.com/\S+",
        r"https?://teams\.microsoft\.com/\S+",
        r"https?://\w+\.webex\.com/\S+",
        r"https?://webex\.com/\S+",
    ]
    corpus = "\n".join(filter(None, [url_prop or "", text or ""]))
    for pat in patterns:
        m = re.search(pat, corpus)
        if m:
            return m.group(0)
    m = re.search(r"https?://[^\s)]+", corpus)
    return m.group(0) if m else ""


def clean_description(desc: str, max_len: int) -> str:
    if not desc:
        return ""
    lines = [re.sub(r"\s{2,}", " ", ln.strip()) for ln in desc.splitlines()]
    s = "\n".join(lines).strip()
    if max_len > 0 and len(s) > max_len:
        return s[:max_len] + "…（続きあり）"
    return s


def shape_memo(desc: str, max_len: int, allday_like: bool) -> str:
    if not desc:
        return ""
    raw_lines = [re.sub(r"\s{2,}", " ", ln.strip()) for ln in desc.splitlines()]
    shaped = []
    prev_was_time_label = False
    blank_count = 0
    for idx, ln in enumerate(raw_lines):
        # remove "【開催時刻】終日" near the beginning for all-day events
        if allday_like and idx < 3 and re.match(r"^【開催時刻】\s*終日\s*$", ln):
            continue
        # collapse consecutive lines starting with 【開催時刻】
        is_time_label = ln.startswith("【開催時刻】")
        if is_time_label and prev_was_time_label:
            continue
        prev_was_time_label = is_time_label

        # collapse multiple blank lines
        if ln == "":
            blank_count += 1
            if blank_count > 1:
                continue
        else:
            blank_count = 0

        shaped.append(ln)

    s = "\n".join(shaped).strip()
    if max_len > 0 and len(s) > max_len:
        s = s[:max_len] + "…（続きあり）"
    return s


def normalize_event_to_jst(vevent):
    """
    Normalize VEVENT's DTSTART/DTEND into JST datetimes.

    Returns: (start_jst, end_jst, allday_like, fixed)
      - start_jst, end_jst: tz-aware JST datetime objects, or None if invalid.
      - allday_like: True if DTSTART/DTEND looked like date-only (all-day style)
      - fixed: True if end was missing/zero-length and was auto-extended
    """
    dtstart_prop = vevent.get("dtstart")
    if dtstart_prop is None:
        return None, None, False, False
    dtstart = dtstart_prop.dt

    dtend_prop = vevent.get("dtend")
    dtend = dtend_prop.dt if dtend_prop is not None else None

    is_date_start = isinstance(dtstart, date) and not isinstance(dtstart, datetime)
    is_date_end = isinstance(dtend, date) and not isinstance(dtend, datetime) if dtend is not None else False
    allday_like = is_date_start or is_date_end

    def to_jst(dt_obj):
        if isinstance(dt_obj, datetime):
            if dt_obj.tzinfo is None:
                return dt_obj.replace(tzinfo=JST)
            return dt_obj.astimezone(JST)
        elif isinstance(dt_obj, date):
            return datetime(dt_obj.year, dt_obj.month, dt_obj.day, 0, 0, tzinfo=JST)
        else:
            return None

    s = to_jst(dtstart)
    e = to_jst(dtend) if dtend is not None else None
    if s is None:
        return None, None, allday_like, False

    fixed = False
    if e is None or e <= s:
        e = s + (timedelta(days=1) if allday_like else timedelta(hours=1))
        fixed = True
    return s, e, allday_like, fixed


def overlaps_today_jst(start: datetime, end: datetime, day_start: datetime, day_end: datetime) -> bool:
    """Return True if [start, end) and [day_start, day_end) overlap in JST."""
    return start < day_end and end > day_start


# 旧 overlaps/clipped は使用しない（JSTヘルパーへ統合）


def format_events_for_today(cal: Calendar, today_jst: date):
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    header_plain = f"本日の予定 {today_jst.strftime('%Y-%m-%d')}（{weekdays_jp[today_jst.weekday()]}）"

    items = []
    previews = []
    total = 0
    normalized_count = 0
    day_start, day_end = get_today_range_jst()
    for vevent in cal.walk("vevent"):
        total += 1
        s, e, allday_like, fixed = normalize_event_to_jst(vevent)
        if s is None or e is None:
            continue
        if fixed:
            normalized_count += 1
        if not overlaps_today_jst(s, e, day_start, day_end):
            continue

        # 表示時間は今日の範囲でクリップ
        disp_start = s if s >= day_start else day_start
        disp_end = e if e <= day_end else day_end

        summary = vevent.get("summary")
        title = str(summary) if summary is not None else "(無題)"

        location = vevent.get("location")
        loc = str(location).strip() if location else ""

        url_prop = str(vevent.get("url") or "").strip()
        desc_raw = str(vevent.get("description") or "")

        show_memo = get_env_bool("SHOW_MEMO", True)
        show_links = get_env_bool("SHOW_LINKS", True)
        try:
            memo_max = int(os.getenv("MEMO_MAX", "180") or 180)
        except Exception:
            memo_max = 180

        memo = shape_memo(desc_raw, memo_max, allday_like) if show_memo else ""
        link = extract_meeting_link("\n".join([desc_raw, loc]), url_prop) if show_links else ""

        when = "終日" if allday_like else f"{disp_start.strftime('%H:%M')}"

        # New format: bullet, title, optional link, memo only (no auto labels)
        lines = [f"・{when}", f"{title}"]
        if get_env_bool("SHOW_LINKS", True) and link:
            lines.append(f"リンク：{link}")
        if get_env_bool("SHOW_MEMO", True) and memo:
            lines.append("メモ：")
            lines.append(memo)
        line_joined = "\n".join(lines)

        # 1 VEVENT = 1件。重複排除は行わず、そのまま蓄積。
        items.append((disp_start, title, line_joined))
        token = "終日" if allday_like else disp_start.strftime('%H:%M')
        previews.append(f"{token}:{title}")

    matched = len(items)
    # デバッグ出力（必ず1行出す）
    print(f"デバッグ: today={today_jst.strftime('%Y-%m-%d')}, events_total={total}, normalized={normalized_count}, matched={matched}")

    if not items:
        header_msg = f"【{header_plain} 全0件】"
        return header_msg, []

    # 開始時刻→タイトルでソート（同時刻の並びが安定するように）
    items.sort(key=lambda x: (x[0], x[1]))
    # プレビュー（先頭3件）
    preview = " / ".join(previews[:3])
    if preview:
        print(f"抽出プレビュー: {preview}")
    body = "\n".join(line for _, _, line in items)
    header_msg = f"【{header_plain} 全{matched}件】"
    event_msgs = [line for _, _, line in items]
    return header_msg, event_msgs


def send_push(message: str):
    access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    to = os.getenv("LINE_TO")
    if not access_token or not to:
        print("[DRY RUN] PUSH: 必要な環境変数が未設定のため送信スキップ\n---\n" + message)
        return 0, True, "dry-run"
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {"to": to, "messages": [{"type": "text", "text": message}]}
    resp = requests.post(url, headers=headers, json=payload, timeout=15)
    ok = 200 <= resp.status_code < 300
    return resp.status_code, ok, (resp.text[:200] if resp.text else "")


def send_broadcast(message: str):
    access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    if not access_token:
        print("[DRY RUN] BROADCAST: 環境変数が未設定のため送信スキップ\n---\n" + message)
        return 0, True, "dry-run"
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {"messages": [{"type": "text", "text": message}]}
    resp = requests.post(url, headers=headers, json=payload, timeout=15)
    ok = 200 <= resp.status_code < 300
    return resp.status_code, ok, (resp.text[:200] if resp.text else "")


def clip_message(message: str) -> str:
    if len(message) <= 5000:
        return message
    suffix = "…（長文省略）"
    limit = max(0, 4800 - len(suffix))
    return message[:limit] + suffix


def send_one(message: str):
    use_broadcast = os.getenv("USE_BROADCAST", "").strip().lower() in {"1", "true", "yes", "on"}
    if use_broadcast:
        status, ok, summary = send_broadcast(message)
        route = "broadcast"
    else:
        status, ok, summary = send_push(message)
        route = "push"
    print(f"LINE送信 route={route} status={status} summary={summary}")
    return status, ok, summary


def send_messages(header: str, messages: list, titles: list = None):
    # Preview
    print("送信前プレビュー: ヘッダー")
    print(header)
    for i, msg in enumerate(messages[:3]):
        parts = msg.splitlines()
        p1 = parts[0] if parts else ""
        p2 = parts[1] if len(parts) > 1 else ""
        print(f"送信前プレビュー[{i}]: {p1} | {p2}")

    try:
        sleep_ms = int(os.getenv("SLEEP_MS", "250") or 250)
    except Exception:
        sleep_ms = 250

    sent = 0
    errors = 0

    # Header first
    status, ok, _ = send_one(clip_message(header))
    sent += 1
    if not ok:
        errors += 1

    pytime.sleep(sleep_ms / 1000.0)

    # Each event as one message
    for idx, msg in enumerate(messages):
        status, ok, summary = send_one(clip_message(msg))
        sent += 1
        if not ok:
            errors += 1
            title_hint = titles[idx] if titles and idx < len(titles) else "(no-title)"
            print(f"送信失敗: title={title_hint} status={status} summary={summary}")
        pytime.sleep(sleep_ms / 1000.0)

    print(f"送信完了: sent={sent}, errors={errors}")
    return errors == 0


def main():
    parser = argparse.ArgumentParser(description="Send today's TimeTree events to LINE, or send test message.")
    parser.add_argument("--test", dest="test_message", help="テスト送信用の文言（指定時はICSを読まずに送信）")
    parser.add_argument("--dump", action="store_true", help="全イベントのJST換算をCSVで表示（送信しない）")
    args = parser.parse_args()

    ics_path = Path("data/timetree.ics")
    if args.dump:
        cal = load_calendar(ics_path)
        today = today_jst()
        day_start, day_end = get_today_range_jst()
        # Dump all events (max 200)
        total = 0
        matched = 0
        normalized_count = 0
        print(f"today_range_jst: {day_start.isoformat()} .. {day_end.isoformat()}")
        for i, vevent in enumerate(cal.walk("vevent")):
            total += 1
            s, e, allday_like, fixed = normalize_event_to_jst(vevent)
            if s is None or e is None:
                continue
            if fixed:
                normalized_count += 1
            overlaps = overlaps_today_jst(s, e, day_start, day_end)
            if overlaps:
                matched += 1
            summary = str(vevent.get("summary") or "(無題)").replace("\n", " ")
            if i < 200:
                print(f"{s.isoformat()}, {e.isoformat()}, {bool(allday_like)}, {overlaps}, {summary}")
        print(f"ゼロ長さ補正した件数: {normalized_count}")
        print(f"totals: all={total}, matched={matched}")
        sys.exit(0)

    if args.test_message:
        # テストでも整形を使い、1件のダミーイベントとして送信
        today = today_jst()
        weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
        header = f"【本日の予定 {today.strftime('%Y-%m-%d')}（{weekdays_jp[today.weekday()]}） 全1件】"
        when = datetime.now(JST).strftime('%H:%M')
        lines = [f"・{when}", f"{args.test_message}"]
        if get_env_bool("SHOW_MEMO", True):
            lines.append("メモ：")
            # no auto time/labels; only memo placeholder in test
        event_msgs = ["\n".join(lines)]
        ok = send_messages(header, event_msgs, [args.test_message])
    else:
        cal = load_calendar(ics_path)
        today = today_jst()
        header, event_msgs = format_events_for_today(cal, today)
        ok = send_messages(header, event_msgs)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

