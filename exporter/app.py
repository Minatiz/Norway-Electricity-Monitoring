import os
import asyncio
import logging
import aiohttp
from datetime import date, timedelta
from typing import Optional
from fastapi import FastAPI, Response
from dotenv import load_dotenv
from prometheus_client import Gauge, generate_latest, CONTENT_TYPE_LATEST
from contextlib import asynccontextmanager



load_dotenv()
API_KEY = os.getenv("API_KEY_ELECTRICITYMAP")
UPDATE_INTERVAL = 60
ZONES = ["NO-NO1", "NO-NO2", "NO-NO3", "NO-NO4", "NO-NO5"]
ZONE_NAMES = {"NO1": "Southeast-Norway", "NO2": "Southwest-Norway", "NO3": "Central-Norway", "NO4": "North-Norway", "NO5": "West-Norway"}

API_URL_CARBON_INTENSITY = "https://api.electricitymap.org/v3/carbon-intensity/latest?zone={}"
API_URL_CARBON_FREE = "https://api.electricitymaps.com/v3/carbon-free-energy/latest?zone={}"
API_URL_PRICE = "https://api.electricitymaps.com/v3/price-day-ahead/latest?zone={}"
API_NORGES_BANK = "https://data.norges-bank.no/api/data/EXR/B.EUR.NOK.SP?format=sdmx-json&startPeriod={}&endPeriod={}&locale=no"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("electricity-exporter")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not API_KEY:
        raise RuntimeError("API_KEY_NOT_SET")
    task = asyncio.create_task(update_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.info("Shutdown")

app = FastAPI(title="Electricity Prometheus Exporter", lifespan=lifespan)

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Prometheus Metrics
CARBON_INTENSITY = Gauge("grid_carbon_intensity_stats","Carbon Intensity (gCO2eq/kWh)",["zone"])
RENEWABLE_SHARE = Gauge("grid_renewable_percentage","Renewable share (%)",["zone"])
PRICE_KWH_NOK = Gauge("electricity_price_nok_per_kwh","Electricity price (NOK/kWh)",["zone"])
EXPORTER_UP = Gauge("electricity_exporter_up","Exporter health (1 = up, 0 = failure)")

# HTTP Helpers
async def fetch_json(session: aiohttp.ClientSession, url: str, headers=None) -> Optional[dict]:
    try:
        async with session.get(url, headers=headers, timeout=10) as response:
            if response.status == 200:
                return await response.json()
            logger.warning(f"Bad status {response.status} for {url}")
    except Exception as e:
        logger.error(f"Request failed: {e}")
    return None

async def get_exchange_rate(session: aiohttp.ClientSession) -> Optional[float]:
    end_date = date.today()
    start_date = end_date - timedelta(days=7)
    url = API_NORGES_BANK.format(start_date, end_date)

    data = await fetch_json(session, url)
    if not data:
        return None

    try:
        observations = data["data"]["dataSets"][0]["series"]["0:0:0:0"]["observations"]
        latest_key = sorted(observations.keys())[-1]
        return float(observations[latest_key][0])
    except (KeyError, IndexError):
        logger.error("Exchange rate format")
        return None



# Zone Update Logic
async def update_zone(session, zone: str, exchange_rate: float):
    """
    Fetches electricity metrics for a zone and updates Prometheus gauges.
    """
    clean_zone = zone.split("-")[1]
    name_zone = ZONE_NAMES[clean_zone]
    headers = {"auth-token": API_KEY}

    carbon_task = fetch_json(session, API_URL_CARBON_INTENSITY.format(zone), headers)
    renewable_task = fetch_json(session, API_URL_CARBON_FREE.format(zone), headers)
    price_task = fetch_json(session, API_URL_PRICE.format(zone), headers)

    carbon, renewable, price = await asyncio.gather(carbon_task, renewable_task, price_task)

    if not (carbon and renewable and price and exchange_rate):
        logger.warning(f"Incomplete data for {clean_zone}")
        return

    carbon_value = carbon["carbonIntensity"]
    renewable_value = renewable["value"]
    price_eur = price["value"]

    price_nok_kwh = (price_eur * exchange_rate) / 1000

    CARBON_INTENSITY.labels(zone=name_zone).set(carbon_value)
    RENEWABLE_SHARE.labels(zone=name_zone).set(renewable_value)
    PRICE_KWH_NOK.labels(zone=name_zone).set(price_nok_kwh)

    logger.info(f"Updated {name_zone}")


# Background Task
async def update_loop():
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                exchange_rate = await get_exchange_rate(session)
                if not exchange_rate:
                    EXPORTER_UP.set(0)
                    await asyncio.sleep(UPDATE_INTERVAL)
                    continue

                tasks = [update_zone(session, zone, exchange_rate) for zone in ZONES]

                await asyncio.gather(*tasks)

                EXPORTER_UP.set(1)

            except Exception as e:
                logger.error(f"Critical failure: {e}")
                EXPORTER_UP.set(0)

            await asyncio.sleep(UPDATE_INTERVAL)
