import datetime
import logging
import os.path
import pickle

import aiohttp

from app.config import Config

config = Config.from_file()
log = logging.getLogger(__name__)


async def update(session: aiohttp.client.ClientSession) -> dict:
    log.info("Updating Luma")
    async with session.get("https://curly-cloud-495d.lostluma.workers.dev/",
                           headers={"Authorization": config.luma}) as resp:
        json_content: dict = await resp.json()
    return {"fetch_time": datetime.datetime.now(), "list": json_content}


def save(json_content: dict):
    with open("luma.pickle", "wb") as f:
        pickle.dump(json_content, f, pickle.HIGHEST_PROTOCOL)


def load() -> dict:
    with open("luma.pickle", "rb") as f:
        return pickle.load(f)


async def check(url: str, session: aiohttp.client.ClientSession):
    if os.path.isfile("luma.pickle"):
        json = load()
        if (json.get("fetch_time") + datetime.timedelta(minutes=1)) > datetime.datetime.now():
            return url in json.get("list")
        else:
            json = await update(session)
            save(json)
            return url in json.get("list")
    else:
        json = await update(session)
        save(json)
        return url in json.get("list")