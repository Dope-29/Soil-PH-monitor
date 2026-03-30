

---

# Soil pH Monitor — Complete Technical Breakdown

---

## Project Structure

```
A:\Soil Ph\
├── bridge.py                        # Core application (Python)
├── index.html                       # Web dashboard (single-page app)
├── .env                             # Secrets (Supabase, Gemini keys)
├── .gitignore
├── readme.txt                       # Calibration formula reference
├── .venv\                           # Python virtual environment
└── arduino_test\
    └── sensor\
        └── sensor.ino               # ESP32 firmware (C++)
```

---

## Architecture Overview

```
[ Analog pH Probe ]
        |
        | analog voltage (0–3.3V)
        v
[ ESP32 GPIO 34 — 12-bit ADC ]
        |
        | USB-UART serial @ 115200 baud
        | "Raw: 1234 | pH: 6.50"
        v
[ bridge.py — Python process ]
   |           |              |
   v           v              v
[localhost  [Supabase    [Gemini AI
 :5000       PostgreSQL]  API]
 HTTP API]       |
   |             v
   |        [soil_logs table]
   v
[ index.html — browser dashboard ]
   polls every 3 seconds
```

---

## Layer 1 — Firmware (`sensor.ino`)

**Language:** C++ (Arduino framework)  
**MCU:** ESP32  
**IDE:** Arduino IDE (with ESP32 board support)

```cpp
void setup() {
  Serial.begin(115200);
}

void loop() {
  int rawValue = analogRead(34);           // GPIO 34, 12-bit ADC (0–4095)
  float voltage = rawValue * (3.3 / 4095.0); // Convert to volts (3.3V ref)
  float phValue = 7 + ((2.5 - voltage) / 0.18); // Nernst-based formula
  Serial.print("Raw: "); Serial.print(rawValue);
  Serial.print(" | pH: "); Serial.println(phValue);
  delay(2000);                             // Sample every 2 seconds
}
```

**Calibration formula:**
```
pH = 7 + ((2.5 − V) / 0.18)
```
- `2.5V` → neutral point (pH 7.0) for standard analog pH modules
- `0.18 V/pH` → Nernst-derived sensor slope at room temperature
- Inverted relationship: higher voltage = more acidic (lower pH)

**Serial output format:**
```
Raw: 1843 | pH: 6.47
```

---

## Layer 2 — Bridge (`bridge.py`)

**Language:** Python 3  
**Runtime:** local process, Windows, `.venv` virtual environment

### 2a. Serial Communication
- Opens `COM5` at `115200` baud via **pySerial**
- Polls `ser.in_waiting` in a background thread
- Parses pH directly from Arduino output (Arduino is calibration source of truth):
  ```python
  ph_value = float(line.split("pH: ")[1])
  ```
- Falls back gracefully if COM5 unavailable — API server still runs

### 2b. HTTP API Server
- Built with Python stdlib `http.server.HTTPServer` — zero external web framework
- Runs on `localhost:5000` in a **daemon thread**
- Endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/latest` | Returns `{"ph_level": 6.47, "timestamp": "..."}` |
| `POST` | `/api/ai-analysis` | Accepts `{ph_level, soil_type}`, returns AI text |
| `OPTIONS` | `*` | CORS preflight — allows all origins |

- In-memory cache: `latest_data` dict holds last reading, served instantly to dashboard

### 2c. Supabase Integration
- Client: **supabase-py** (`create_client`)
- Credentials from `.env` via **python-dotenv**
- On each valid serial read, inserts a row:
  ```python
  supabase.table("soil_logs").insert({"ph_level": ph_value}).execute()
  ```
- Table: `soil_logs` — fields: `ph_level` (float), implicit `id` + `created_at` (Supabase defaults)

### 2d. Gemini AI Integration
- Client: **google-genai** (`google.genai`)
- Model: `gemini-2.5-flash`
- Called on-demand from `/api/ai-analysis` POST endpoint
- Prompt: structured expert agronomist prompt requesting bullet-point advice based on pH + soil type
- Response returned as plain text to the dashboard

### 2e. Threading model
```
Main thread          → keeps process alive (sleep loop)
api_thread (daemon)  → HTTPServer.serve_forever()
sensor_thread (daemon) → serial read loop + Supabase writes
```

---

## Layer 3 — Dashboard (`index.html`)

**Type:** Single static HTML file — no build step, no framework, vanilla JS  
**Served:** Open directly in browser (file://) or any static server

### Polling
```js
setInterval(fetchLatest, 3000)  // hits GET /api/latest every 3s
```

### pH scale display
- Spectrum gradient track (pH 4–14, acid→alkaline color gradient)
- White cursor slides to current pH position, CSS transition `0.7s cubic-bezier`

### Soil type profiles (hardcoded JS object)
```js
const soilTypes = {
  loam:  { optimalPh: 6.5, min: 6.0, max: 7.0 },
  clay:  { optimalPh: 6.8, min: 6.0, max: 7.5 },
  sand:  { optimalPh: 6.0, min: 5.5, max: 6.5 },
  silt:  { optimalPh: 6.5, min: 6.0, max: 7.0 },
  peat:  { optimalPh: 5.0, min: 4.0, max: 6.0 },
  mixed: { optimalPh: 6.5, min: 6.0, max: 7.0 }
}
```

### AI trigger logic
- AI analysis is fetched only when pH crosses a **whole number boundary** (`Math.floor` comparison) or soil type changes — not on every poll, avoiding excessive API calls
- `isAnalyzing` flag prevents concurrent requests

### Fonts
- **Space Grotesk** — UI labels, text
- **IBM Plex Mono** — all numeric readouts, status codes

---

## Technology Stack Summary

| Layer | Technology | Purpose |
|---|---|---|
| Firmware | C++ / Arduino framework | ADC read, pH calc, serial output |
| MCU | ESP32 | 12-bit ADC, USB-UART bridge |
| Sensor | Analog pH probe module | Electrochemical voltage output |
| Serial comms | pySerial | USB-UART read on COM5 |
| HTTP server | Python stdlib `http.server` | Local REST API |
| Concurrency | Python `threading` | Parallel serial + HTTP loops |
| Database | Supabase (PostgreSQL) | Cloud time-series storage |
| Auth/config | python-dotenv | Secret management via `.env` |
| AI | Google Gemini 2.5 Flash | Agronomic recommendations |
| Frontend | Vanilla HTML/CSS/JS | Dashboard, no framework |
| Fonts | Google Fonts CDN | Space Grotesk, IBM Plex Mono |
| Environment | Python venv (`.venv`) | Dependency isolation |

---

## Data Flow (end-to-end)

```
1. pH probe outputs voltage proportional to H+ ion concentration
2. ESP32 ADC samples GPIO 34 → raw integer 0–4095
3. ESP32 computes: voltage = raw × (3.3 / 4095)
                   pH = 7 + ((2.5 − voltage) / 0.18)
4. ESP32 sends "Raw: X | pH: Y" over USB serial every 2s
5. bridge.py sensor_thread reads line, parses pH value
6. bridge.py updates latest_data{} in memory
7. bridge.py inserts {ph_level} into Supabase soil_logs table
8. Browser polls GET /api/latest every 3s
9. bridge.py api_thread responds with latest_data JSON
10. Dashboard updates pH readout, scale cursor, advice text
11. When pH crosses integer boundary → POST /api/ai-analysis
12. bridge.py calls Gemini 2.5 Flash with structured prompt
13. AI response rendered in analysis panel
```

---

## Key Design Decisions

- **No web framework** — `http.server` is stdlib only; keeps the bridge a single-file script with no heavyweight dependency
- **Arduino as calibration authority** — bridge parses pH from Arduino's serial output rather than recalculating, so calibration changes in firmware automatically propagate
- **Daemon threads** — both background threads are daemons, so the process exits cleanly on `KeyboardInterrupt` without explicit join
- **AI call throttling** — whole-number pH boundary trigger prevents Gemini API spam during stable readings
- **Single HTML file** — no bundler, no build pipeline; open in browser directly