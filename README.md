# Norway Electricity Monitoring

This project monitors electricity metrics in Norway including **carbon intensity**, **renewable share**, and **day-ahead electricity price**.

It ases a **FastAPI exporter**, **Prometheus**, and **Grafana**. to build a scraping, monitoring, and visualization stack.

The system is designed for observability, visualization, and alerting of electricity grid data.

---

## Features

- **FastAPI exporter** fetching:
  - Carbon intensity per zone
  - Renewable share per zone
  - Day-ahead electricity price (NOK/kWh) per zone
- **Prometheus** scraping metrics every 30 seconds
- **Grafana dashboard** for visualization
- Optional alert rules (via Prometheus) for:
  - Exporter downtime
  - Carbon intensity spikes
  - Electricity price spikes

---

## ElectricityMap API Key

This project requires an **API key** from [ElectricityMap](https://api.electricitymap.org/).

**Steps to get your API key:**

1. Go to [https://app.electricitymaps.com/auth/signup](https://app.electricitymaps.com/auth/signup)
2. Create a free account
3. Copy your API key
4. Add it to a `.env` file in the project root:

```env
API_KEY_ELECTRICITYMAP=your_api_key_here
```

---

## Running the Project & Grafana Dashboard Setup

### 1. Build and start the Docker

From the project root, run:

```bash
docker compose up --build
```

### 2. Configure Grafana Data Source

The provided dashboard JSON uses a **templated data source variable** (`${DS_PROMETHEUS}`)

**Steps:**

1. Open Grafana in your browser: [http://localhost:3000](http://localhost:3000)
   - Default login: `admin` / `admin` (remember to change the password after first login)

2. Add Prometheus as a data source:
   - On left bar go to **Connections → Data sources → Add new data source → Prometheus**
   - URL: `http://prometheus:9090`
   - Name: (any name you like, e.g., `Prometheus`)
   - Click **Save & Test** to verify the connection

3. Import the dashboard:
   - Go to **Dashboards → Import → Upload JSON**
   - Select `grafana/dashboards/electricity-dashboard.json`
   - Click **Edit - > Settings -> Variables** select DS_PRMETHEUS under Data source options dropdown, select the newly created data source (this sets `DS_PROMETHEUS`).
   - Save the dashboard

## APIs

The exporter exposes a **FastAPI** HTTP endpoint for Prometheus to scrape metrics:

### `/metrics` – GET

- **Description:** Returns Prometheus-formatted metrics for all configured zones.
- **Response Content-Type:** `text/plain; version=0.0.4`
- **Prometheus Metrics:**

| Metric Name                     | Description                            | Labels |
| ------------------------------- | -------------------------------------- | ------ |
| `grid_carbon_intensity_stats`   | Carbon intensity (gCO₂eq/kWh)          | `zone` |
| `grid_renewable_percentage`     | Renewable energy share (%)             | `zone` |
| `electricity_price_nok_per_kwh` | Day-ahead electricity price in NOK/kWh | `zone` |
| `electricity_exporter_up`       | Exporter health (1 = up, 0 = failure)  |        |

**Example Request:**

```bash
curl http://localhost:8000/metrics
```

### External APIs Used

1. **ElectricityMap API**
   - Carbon Intensity: `https://api.electricitymap.org/v3/carbon-intensity/latest?zone={zone}`
   - Renewable Share: `https://api.electricitymaps.com/v3/carbon-free-energy/latest?zone={zone}`
   - Day-Ahead Price: `https://api.electricitymaps.com/v3/price-day-ahead/latest?zone={zone}`
   - **Authentication:** `auth-token` header with your API key

2. **Norges Bank Exchange Rate API**
   - URL: `https://data.norges-bank.no/api/data/EXR/B.EUR.NOK.SP?format=sdmx-json&startPeriod={start}&endPeriod={end}&locale=no`
   - **Used to:** Convert electricity prices from EUR/kWh to NOK/kWh.

---

## Architecture

The system is designed as a microservice stack for monitoring electricity metrics:

### Components

1. **Electricity Exporter (FastAPI)**
   - Fetches electricity metrics from external APIs
   - Updates Prometheus metrics every `UPDATE_INTERVAL` seconds (default 60s)
   - Handles exchange rate conversions using Norges Bank API
   - Provides `/metrics` endpoint for Prometheus

2. **Prometheus**
   - Scrapes the `/metrics` endpoint every 30 seconds
   - Stores metrics for visualization and alerting
   - Optional alert rules for downtime, carbon intensity spikes, and electricity price spikes

3. **Grafana**
   - Connects to Prometheus as a datasource
   - Visualizes electricity metrics with dashboards
   - Can trigger alerts based on Prometheus rules

4. **Docker & Docker Compose**
   - Each component runs in its own container
   - Easy deployment and scalability

### Data Flow

```text
┌───────────────────────┐
│ ElectricityMap API    │
└─────────┬─────────────┘
          │ JSON Metrics
          ▼
┌───────────────────────┐
│ Electricity Exporter  │
│  - Fetches metrics    │
│  - Converts prices    │
│  - Updates Prometheus │
└─────────┬─────────────┘
          │ /metrics
          ▼
┌───────────────────────┐
│ Prometheus            │
│  - Scrapes exporter   │
│  - Stores metrics     │
└─────────┬─────────────┘
          │ Data queries
          ▼
┌───────────────────────┐
│ Grafana Dashboard     │
│  - Visualizes metrics │
│  - Alerting rules     │
└───────────────────────┘
```
