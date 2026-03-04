import datetime as dt
import json
import re
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib import parse, request

ROOT = Path(__file__).resolve().parent
MEETING_LINK_FILE = ROOT / "meetinglink.txt"
WEATHER_LAT = 59.3037
WEATHER_LON = 18.0937
WEATHER_TIMEZONE = "Europe/Stockholm"


def fold_unwrap(text: str) -> list[str]:
    lines = text.replace("\r\n", "\n").split("\n")
    out = []
    for line in lines:
        if not line:
            out.append("")
            continue
        if line[0] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def parse_ics_datetime(value: str) -> dt.datetime | None:
    value = value.strip()
    try:
        if value.endswith("Z"):
            return dt.datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
        if "T" in value:
            return dt.datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=dt.timezone.utc)
        return dt.datetime.strptime(value, "%Y%m%d").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def parse_ics(content: str) -> list[dict]:
    lines = fold_unwrap(content)
    events = []
    current = None

    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current and current.get("start") and current.get("end"):
                events.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue

        key, value = line.split(":", 1)
        key_upper = key.upper()

        if key_upper.startswith("SUMMARY"):
            current["title"] = value.strip()
        elif key_upper.startswith("DTSTART"):
            parsed = parse_ics_datetime(value)
            if parsed:
                current["start"] = parsed.isoformat()
        elif key_upper.startswith("DTEND"):
            parsed = parse_ics_datetime(value)
            if parsed:
                current["end"] = parsed.isoformat()
        elif key_upper.startswith("ORGANIZER"):
            cn_match = re.search(r"CN=([^;:]+)", key, re.IGNORECASE)
            if cn_match:
                current["organizer"] = cn_match.group(1).strip().strip('"')
            else:
                name = value.replace("MAILTO:", "").strip()
                current["organizer"] = name

    now_utc = dt.datetime.now(dt.timezone.utc)
    monday_utc = (now_utc - dt.timedelta(days=(now_utc.weekday()))).replace(hour=0, minute=0, second=0, microsecond=0)
    friday_utc = monday_utc + dt.timedelta(days=5)

    filtered = []
    for event in events:
        start_dt = dt.datetime.fromisoformat(event["start"])
        if monday_utc <= start_dt < friday_utc:
            filtered.append(
                {
                    "title": event.get("title", ""),
                    "organizer": event.get("organizer") or event.get("title", "Unknown"),
                    "start": event["start"],
                    "end": event["end"],
                }
            )

    return filtered


def fetch_url(url: str) -> tuple[str, str]:
    req = request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with request.urlopen(req, timeout=20) as resp:
        content_type = resp.headers.get_content_type()
        raw = resp.read()
        text = raw.decode("utf-8", errors="replace")
        return content_type, text


def fetch_json(url: str) -> dict:
    req = request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with request.urlopen(req, timeout=20) as resp:
        raw = resp.read()
        text = raw.decode("utf-8", errors="replace")
        return json.loads(text)


def weather_summary() -> dict:
    query = parse.urlencode(
        {
            "latitude": WEATHER_LAT,
            "longitude": WEATHER_LON,
            "current": "temperature_2m,weather_code",
            "daily": "sunrise,sunset",
            "timezone": WEATHER_TIMEZONE,
            "forecast_days": "1",
        }
    )
    url = f"https://api.open-meteo.com/v1/forecast?{query}"
    data = fetch_json(url)

    current = data.get("current", {})
    daily = data.get("daily", {})
    sunrise = daily.get("sunrise", [None])[0]
    sunset = daily.get("sunset", [None])[0]

    return {
        "location": "Virkesvagen 12, Stockholm",
        "temperatureC": current.get("temperature_2m"),
        "weatherCode": current.get("weather_code"),
        "sunrise": sunrise,
        "sunset": sunset,
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def extract_ics_url_from_html(html: str, base_url: str) -> str | None:
    match = re.search(r'https?://[^"\']+\.ics', html, flags=re.IGNORECASE)
    if match:
        return match.group(0)

    rel = re.search(r'href=["\']([^"\']+\.ics)["\']', html, flags=re.IGNORECASE)
    if rel:
        return parse.urljoin(base_url, rel.group(1))

    return None


def calendar_events() -> list[dict]:
    link = MEETING_LINK_FILE.read_text(encoding="utf-8").strip()
    candidates = [link]

    if link.endswith("calendar.html"):
        candidates.append(link[:-len("calendar.html")] + "calendar.ics")

    errors_seen = []
    for candidate in candidates:
        try:
            ctype, text = fetch_url(candidate)
            if "text/calendar" in ctype or text.startswith("BEGIN:VCALENDAR"):
                return parse_ics(text)
            if "html" in ctype or "<html" in text.lower():
                possible_ics = extract_ics_url_from_html(text, candidate)
                if possible_ics:
                    _, ics_text = fetch_url(possible_ics)
                    return parse_ics(ics_text)
        except Exception as exc:  # noqa: BLE001
            errors_seen.append(f"{candidate}: {exc}")

    raise RuntimeError("Could not read calendar data. " + " | ".join(errors_seen))


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.startswith("/api/calendar"):
            self.serve_calendar_api()
            return
        if self.path.startswith("/api/weather"):
            self.serve_weather_api()
            return
        return super().do_GET()

    def serve_calendar_api(self) -> None:
        try:
            events = calendar_events()
            payload = {
                "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
                "events": events,
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:  # noqa: BLE001
            body = json.dumps({"error": str(exc)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def serve_weather_api(self) -> None:
        try:
            payload = weather_summary()
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:  # noqa: BLE001
            body = json.dumps({"error": str(exc)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


def main() -> None:
    server = HTTPServer(("127.0.0.1", 8000), Handler)
    print("Serving calendar at http://127.0.0.1:8000")
    server.serve_forever()


if __name__ == "__main__":
    main()

