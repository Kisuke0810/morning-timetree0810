#!/usr/bin/env python3
import os
import sys
import argparse
from datetime import datetime, date, time, timedelta
from pathlib import Path

import pytz
import requests
from icalendar import Calendar


JST = pytz.timezone("Asia/Tokyo")


def load_calendar(ics_path: Path) -> Calendar:
    if not ics_path.exists():
        print(f"ICSが見つかりません: {ics_path}", file=sys.stderr)
        sys.exit(1)
    data = ics_path.read_bytes()
    return Calendar.from_ical(data)


def to_tz(dt_obj, tz):
    """Convert an ical dt object (date or datetime) to tz-aware datetime in tz.

    - date: interpret as 00:00 in tz
    - naive datetime: interpret as time already in tz (JST) and localize
    - tz-aware datetime: convert to tz
    """
    if isinstance(dt_obj, datetime):
        if dt_obj.tzinfo is None:
            # 依頼: naive は JST とみなす
            return tz.localize(dt_obj)
        return dt_obj.astimezone(tz)
    elif isinstance(dt_obj, date):
        # 終日: その日の 00:00（inclusive）。
        return tz.localize(datetime(dt_obj.year, dt_obj.month, dt_obj.day))
    else:
        raise TypeError(f"Unsupported dt type: {type(dt_obj)}")


def event_time_range_jst(vevent):
    dtstart_prop = vevent.get("dtstart")
    if dtstart_prop is None:
        return None
    dtstart = dtstart_prop.dt
    dtend_prop = vevent.get("dtend")
    dtend = dtend_prop.dt if dtend_prop is not None else None

    # JSTへ変換（ここでは終了未指定時の補完は行わない）
    start_jst = to_tz(dtstart, JST)
    end_jst = to_tz(dtend, JST) if dtend is not None else None

    # allday_like: DTSTART/DTEND のいずれかが日付のみの場合
    is_date_start = isinstance(dtstart, date) and not isinstance(dtstart, datetime)
    is_date_end = isinstance(dtend, date) and not isinstance(dtend, datetime) if dtend is not None else False
    allday_like = is_date_start or is_date_end

    return start_jst, end_jst, allday_like


def normalize_event(start_jst: datetime, end_jst, allday_like: bool):
    """Ensure non-zero duration and tz-aware JST datetimes.

    - allday_like True (VALUE=DATEを含む) → end<=start or None は +1日
    - それ以外（時刻あり） → end<=start or None は +1時間
    Returns (start, end, normalized_flag)
    """
    # ensure tz
    def ensure_jst(dt):
        if dt is None:
            return None
        if dt.tzinfo is None:
            return JST.localize(dt)
        return dt.astimezone(JST)

    s = ensure_jst(start_jst)
    e = ensure_jst(end_jst)
    normalized = False
    if allday_like:
        if e is None or e <= s:
            e = s + timedelta(days=1)
            normalized = True
    else:
        if e is None or e <= s:
            e = s + timedelta(hours=1)
            normalized = True
    return s, e, normalized


def overlaps_today(start_jst: datetime, end_jst: datetime, today_jst: date) -> bool:
    # 今日 00:00 ～ 明日 00:00 の半開区間と少しでも重なるか
    day_start = JST.localize(datetime.combine(today_jst, time(0, 0, 0)))
    day_end = day_start + timedelta(days=1)
    return not (end_jst <= day_start or start_jst >= day_end)


def clipped_range_for_today(start_jst: datetime, end_jst: datetime, today_jst: date):
    day_start = JST.localize(datetime.combine(today_jst, time(0, 0, 0)))
    day_end = day_start + timedelta(days=1)
    s = max(start_jst, day_start)
    e = min(end_jst, day_end)
    return s, e


def format_events_for_today(cal: Calendar, today_jst: date) -> str:
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    header = f"本日の予定 {today_jst.strftime('%Y-%m-%d')}（{weekdays_jp[today_jst.weekday()]}）"

    items = []
    previews = []
    total = 0
    normalized_count = 0
    for vevent in cal.walk("vevent"):
        total += 1
        times = event_time_range_jst(vevent)
        if times is None:
            continue
        start_jst, end_jst, allday_like = times
        start_jst, end_jst, did_norm = normalize_event(start_jst, end_jst, allday_like)
        if did_norm:
            normalized_count += 1
        if not overlaps_today(start_jst, end_jst, today_jst):
            continue

        # 表示時間は今日の範囲でクリップ
        disp_start, disp_end = clipped_range_for_today(start_jst, end_jst, today_jst)

        summary = vevent.get("summary")
        title = str(summary) if summary is not None else "(無題)"

        location = vevent.get("location")
        loc = str(location).strip() if location else ""

        if allday_like:
            when = "終日"
        else:
            when = f"{disp_start.strftime('%H:%M')}-{disp_end.strftime('%H:%M')}"

        line = f"{when}  {title}"
        if loc:
            line += f"（{loc}）"

        items.append((disp_start, line))
        # preview token
        token = "終日" if allday_like else disp_start.strftime('%H:%M')
        previews.append(f"{token}:{title}")

    matched = len(items)
    # デバッグ出力（必ず1行出す）
    print(f"デバッグ: today={today_jst.strftime('%Y-%m-%d')}, events_total={total}, normalized={normalized_count}, matched={matched}")

    if not items:
        return f"{header}\n本日の予定はありません。"

    # 開始時刻でソート
    items.sort(key=lambda x: x[0])
    # プレビュー（先頭3件）
    preview = " / ".join(previews[:3])
    if preview:
        print(f"抽出プレビュー: {preview}")
    body = "\n".join(line for _, line in items)
    return f"{header}\n{body}"


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


def send_line(message: str):
    use_broadcast = os.getenv("USE_BROADCAST", "").strip().lower() in {"1", "true", "yes", "on"}
    if use_broadcast:
        status, ok, summary = send_broadcast(message)
        route = "broadcast"
    else:
        status, ok, summary = send_push(message)
        route = "push"
    print(f"LINE送信 route={route} status={status} summary={summary}")
    return ok


def main():
    parser = argparse.ArgumentParser(description="Send today's TimeTree events to LINE, or send test message.")
    parser.add_argument("--test", dest="test_message", help="テスト送信用の文言（指定時はICSを読まずに送信）")
    parser.add_argument("--dump", action="store_true", help="全イベントのJST換算をCSVで表示（送信しない）")
    args = parser.parse_args()

    ics_path = Path("data/timetree.ics")
    if args.dump:
        cal = load_calendar(ics_path)
        today = datetime.now(JST).date()
        # Dump all events (max 200)
        total = 0
        matched = 0
        normalized_count = 0
        day_start = JST.localize(datetime.combine(today, time(0, 0, 0)))
        day_end = day_start + timedelta(days=1)
        for i, vevent in enumerate(cal.walk("vevent")):
            total += 1
            times = event_time_range_jst(vevent)
            if not times:
                continue
            s, e, allday_like = times
            s, e, did_norm = normalize_event(s, e, allday_like)
            if did_norm:
                normalized_count += 1
            if not (e <= day_start or s >= day_end):
                matched += 1
            summary = str(vevent.get("summary") or "(無題)").replace("\n", " ")
            if i < 200:
                print(f"{s.isoformat()}, {e.isoformat()}, {bool(allday_like)}, {summary}")
        print(f"ゼロ長さ補正した件数: {normalized_count}")
        print(f"totals: all={total}, matched={matched}")
        sys.exit(0)

    if args.test_message:
        message = args.test_message
    else:
        cal = load_calendar(ics_path)
        today = datetime.now(JST).date()
        message = format_events_for_today(cal, today)

    ok = send_line(message)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

