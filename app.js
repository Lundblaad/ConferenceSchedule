const dayNames = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];
const weatherCodeMap = {
  0: "Clear sky",
  1: "Mainly clear",
  2: "Partly cloudy",
  3: "Overcast",
  45: "Fog",
  48: "Depositing rime fog",
  51: "Light drizzle",
  53: "Moderate drizzle",
  55: "Dense drizzle",
  56: "Light freezing drizzle",
  57: "Dense freezing drizzle",
  61: "Slight rain",
  63: "Moderate rain",
  65: "Heavy rain",
  66: "Light freezing rain",
  67: "Heavy freezing rain",
  71: "Slight snow fall",
  73: "Moderate snow fall",
  75: "Heavy snow fall",
  77: "Snow grains",
  80: "Slight rain showers",
  81: "Moderate rain showers",
  82: "Violent rain showers",
  85: "Slight snow showers",
  86: "Heavy snow showers",
  95: "Thunderstorm",
  96: "Thunderstorm with slight hail",
  99: "Thunderstorm with heavy hail"
};

function getMonday(date = new Date()) {
  const d = new Date(date);
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  d.setDate(d.getDate() + diff);
  d.setHours(0, 0, 0, 0);
  return d;
}

function addDays(date, days) {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d;
}

function isoDate(date) {
  return date.toISOString().slice(0, 10);
}

function formatDayDate(date) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric"
  }).format(date);
}

function getIsoWeekNumber(date) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
}

function formatTimeRange(startIso, endIso) {
  const start = new Date(startIso);
  const end = new Date(endIso);
  const fmt = new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit"
  });
  return `${fmt.format(start)} - ${fmt.format(end)}`;
}

function formatClock(isoTime) {
  if (!isoTime) {
    return "--:--";
  }
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(isoTime));
}

function renderCalendar(events) {
  const calendar = document.getElementById("calendar");
  const weekLabel = document.getElementById("weekLabel");
  const template = document.getElementById("eventTemplate");
  calendar.innerHTML = "";

  const monday = getMonday();
  weekLabel.textContent = `Week: ${getIsoWeekNumber(monday)} ${monday.getFullYear()}`;

  const grouped = {};
  for (const event of events) {
    const dateKey = event.start.slice(0, 10);
    if (!grouped[dateKey]) {
      grouped[dateKey] = [];
    }
    grouped[dateKey].push(event);
  }

  for (let i = 0; i < 5; i += 1) {
    const dayDate = addDays(monday, i);
    const key = isoDate(dayDate);
    const column = document.createElement("section");
    column.className = "day-column";

    const header = document.createElement("div");
    header.className = "day-header";
    header.innerHTML = `
      <h2 class="day-name">${dayNames[i]}</h2>
      <p class="day-date">${formatDayDate(dayDate)}</p>
    `;
    column.appendChild(header);

    const eventsWrap = document.createElement("div");
    eventsWrap.className = "events";

    const dayEvents = (grouped[key] || []).sort((a, b) => a.start.localeCompare(b.start));
    if (!dayEvents.length) {
      const empty = document.createElement("p");
      empty.className = "empty-note";
      empty.textContent = "No bookings";
      eventsWrap.appendChild(empty);
    } else {
      for (const event of dayEvents) {
        const node = template.content.firstElementChild.cloneNode(true);
        node.querySelector(".event-title").textContent = event.title || "(No title)";
        node.querySelector(".event-time").textContent = formatTimeRange(event.start, event.end);
        eventsWrap.appendChild(node);
      }
    }

    column.appendChild(eventsWrap);
    calendar.appendChild(column);
  }
}

function renderWeather(payload) {
  const nowEl = document.getElementById("weatherNow");
  const sunriseEl = document.getElementById("sunriseTime");
  const sunsetEl = document.getElementById("sunsetTime");
  if (!nowEl || !sunriseEl || !sunsetEl) {
    return;
  }

  const weatherText = weatherCodeMap[payload.weatherCode] || "Unknown";
  const temp = typeof payload.temperatureC === "number"
    ? `${Math.round(payload.temperatureC)} C`
    : "-- C";

  nowEl.textContent = `${temp} - ${weatherText}`;
  sunriseEl.textContent = formatClock(payload.sunrise);
  sunsetEl.textContent = formatClock(payload.sunset);
}

function renderWeatherUnavailable() {
  const nowEl = document.getElementById("weatherNow");
  const sunriseEl = document.getElementById("sunriseTime");
  const sunsetEl = document.getElementById("sunsetTime");
  if (!nowEl || !sunriseEl || !sunsetEl) {
    return;
  }
  nowEl.textContent = "Unavailable";
  sunriseEl.textContent = "--:--";
  sunsetEl.textContent = "--:--";
}

async function loadEvents() {
  try {
    const response = await fetch("/api/calendar", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Server returned ${response.status}`);
    }

    const payload = await response.json();
    if (!payload.events || !Array.isArray(payload.events)) {
      throw new Error("Invalid data format");
    }

    renderCalendar(payload.events);
  } catch (err) {
    console.error(`Could not load meetings: ${err.message}`);
  }
}

async function loadWeather() {
  try {
    let payload;
    const response = await fetch("/api/weather", { cache: "no-store" });
    if (response.ok) {
      payload = await response.json();
    } else {
      const fallbackUrl = "https://api.open-meteo.com/v1/forecast?latitude=59.3037&longitude=18.0937&current=temperature_2m,weather_code&daily=sunrise,sunset&timezone=Europe%2FStockholm&forecast_days=1";
      const fallbackResponse = await fetch(fallbackUrl, { cache: "no-store" });
      if (!fallbackResponse.ok) {
        throw new Error(`Weather fetch failed (${response.status}/${fallbackResponse.status})`);
      }
      const fallbackData = await fallbackResponse.json();
      payload = {
        temperatureC: fallbackData?.current?.temperature_2m,
        weatherCode: fallbackData?.current?.weather_code,
        sunrise: fallbackData?.daily?.sunrise?.[0],
        sunset: fallbackData?.daily?.sunset?.[0]
      };
    }

    if (!payload || typeof payload !== "object") {
      throw new Error("Invalid weather payload");
    }
    renderWeather(payload);
  } catch (err) {
    console.error(`Could not load weather: ${err.message}`);
    renderWeatherUnavailable();
  }
}

loadEvents();
loadWeather();
setInterval(loadEvents, 60 * 1000);
setInterval(loadWeather, 60 * 1000);
