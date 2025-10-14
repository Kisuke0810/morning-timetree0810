import os, requests, pytz, datetime as dt
from icalendar import Calendar, Event

LINE_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_TO    = os.environ["LINE_TO"]
ICS_PATH   = "data/timetree.ics"

def load_today_events(path):
    with open(path, "rb") as f:
        cal = Calendar.from_ical(f.read())
    jst = pytz.timezone("Asia/Tokyo")
    today = dt.datetime.now(jst).date()
    events = []
    for comp in cal.walk():
        if isinstance(comp, Event):
            start = comp.decoded("DTSTART")
            if isinstance(start, dt.datetime):
                start = start.astimezone(jst)
                if start.date() != today: 
                    continue
                t = start.strftime("%H:%M")
            else:
                if start != today: 
                    continue
                t = "終日"
            title = str(comp.get("SUMMARY") or "(無題)")
            loc = comp.get("LOCATION")
            events.append(f"・{t} {title}" + (f" @{loc}" if loc else ""))
    return events

def push_line(text):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"}
    body = {"to": LINE_TO, "messages": [{"type":"text","text": text[:5000]}]}
    r = requests.post(url, json=body, headers=headers, timeout=15)
    r.raise_for_status()

if __name__ == "__main__":
    evs = load_today_events(ICS_PATH)
    msg = "【今日の講座予定】\n" + ("\n".join(evs) if evs else "本日の予定はありません✨")
    push_line(msg)
    print("sent.")

