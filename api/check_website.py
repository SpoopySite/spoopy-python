import logging
import urllib.parse
from urllib.parse import ParseResult

import aiohttp.client_exceptions
import sanic
import sanic.response
from sanic import Blueprint

import api.checkers.cloudflare
import api.checkers.luma
import api.handlers
import api.helpers
from api.tool_check_website_wrapper import get_check_website

bp = Blueprint("check_website")
log = logging.getLogger(__name__)


@bp.route("/check_website", methods=["GET"])
async def get_api_check_website(request):
    try:
        if "website" in request.args:
            search_query = request.args["website"][0]
        else:
            search_query = None
        if search_query is None or search_query == "":
            search_query = request.json.get("website")
    except (AttributeError, KeyError):
        error = (
            "Please specify the search query under the 'website' key."
        )
        return sanic.response.json({"error": error}, status=400)

    if not await api.helpers.validate_url(search_query):
        return sanic.response.json({"status": "Invalid URL"},
                                   status=400)

    url = search_query

    if "spoopy.oceanlord.me" in url:
        return sanic.response.json({"error": "Go away."})

    try:
        redirects = await api.helpers.redirect_gatherer(url, request.app.session)
    except aiohttp.client_exceptions.ClientConnectorError:
        log.warning(f"Error connecting to {url}")
        return sanic.response.json({"error": f"Could not establish a connection to {url}"}, status=400)

    if len(redirects) == 0:
        redirects.append(url)
    log.info(redirects)

    async with request.app.session.get(redirects[-1], allow_redirects=False) as resp:
        text = await resp.text("utf-8")
        resp.close()
    refresh_header = api.helpers.refresh_header_finder(text)
    if refresh_header:
        redirects.append(refresh_header)

    checks = {
        "urls": {},
    }

    # parsed_url = urllib.parse.urlparse(redirects[-1])
    # if "youtube.com" in parsed_url.netloc and parsed_url.path == "/redirect":
    #     if "q" in urllib.parse.parse_qs(parsed_url.query):
    #         redirects.append(urllib.parse.parse_qs(parsed_url.query).get("q")[0])
    # elif "google.com" in parsed_url.netloc and parsed_url.path == "/url":
    #     if "url" in urllib.parse.parse_qs(parsed_url.query):
    #         redirects.append(urllib.parse.parse_qs(parsed_url.query).get("url")[0])
    # elif "bitly.com" in parsed_url.netloc and parsed_url.path == "/a/warning":
    #     if "url" in urllib.parse.parse_qs(parsed_url.query):
    #         redirects.append(urllib.parse.parse_qs(parsed_url.query).get("url")[0])

    for redirect_url in redirects:
        checks["urls"][redirect_url] = {"safety": 0}
        parsed: ParseResult = urllib.parse.urlparse(redirect_url)

        try:
            data = await get_check_website(redirect_url,
                                           request.app.session,
                                           request.app.db,
                                           request.app.fish)
            status, location, safety, reasons, refresh_redirect, text, headers, hsts_check = data
        except aiohttp.client_exceptions.ClientConnectorError:
            log.warning(f"Error connecting to {redirect_url} on API")
            return sanic.response.json({"error": f"Could not establish a connection to {redirect_url}"})
        except aiohttp.client_exceptions.ClientConnectorSSLError as err:
            log.warning(f"Error connect to {redirect_url} on API due to error")
            log.error(err)
            return sanic.response.json({"error": f"Could not support the protocol version that {redirect_url} uses"})

        handler_check = await api.handlers.handlers.handlers(parsed, text, headers, request.app.session)

        adfly = False
        bitly_warning = False
        youtube_check = False

        if handler_check["url"]:
            redirects.append(handler_check.get("url"))
            youtube_check = handler_check.get("youtube")
            bitly_warning = handler_check.get("bitly")
            adfly = handler_check.get("adfly")

        checks["urls"][redirect_url] = {
            "not_safe_reasons": reasons,
            "safe": safety,
            "hsts": hsts_check if hsts_check == "preloaded" else "NO_HSTS",
            "safety": 0 - len(reasons)
        }
        if adfly:
            checks["urls"][redirect_url]["adfly"] = "Adfly detected"
        if youtube_check:
            checks["urls"][redirect_url]["youtube"] = "Youtube detected"
        if bitly_warning:
            checks["urls"][redirect_url]["Bitly"] = "Bitly detected"

        # parsed_url = await api.helpers.url_splitter(redirect_url)
        # phishtank_check = await api.helpers.parse_phistank(url, request.app.fish)
        # checks["urls"][redirect_url]["phishtank"] = phishtank_check

    # log.info(await api.helpers.redirect_gatherer(url, request.app.session))
    # checks[url]["redirects"] = await api.helpers.redirect_gatherer(url, request.app.session)

    return sanic.response.json({"processed": checks})
