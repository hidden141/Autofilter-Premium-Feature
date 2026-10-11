from aiohttp import web
import re
import asyncio
import math
import logging
import secrets
import time
import mimetypes
import urllib.parse
from aiohttp.http_exceptions import BadStatusLine
from dreamxbotz.Bot import multi_clients, work_loads, dreamxbotz
from dreamxbotz.server.exceptions import FIleNotFound, InvalidHash
from dreamxbotz.zzint import StartTime, __version__
from dreamxbotz.util.custom_dl import ByteStreamer
from dreamxbotz.util.time_format import get_readable_time
from dreamxbotz.util.render_template import render_page
from info import *


routes = web.RouteTableDef()

@routes.get("/favicon.ico")
async def favicon_route_handler(request):
    return web.FileResponse('dreamxbotz/template/favicon.ico')

@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response("dreamxbotz")

@routes.get(r"/watch/{path:\S+}", allow_head=True)
async def stream_handler(request: web.Request):
    try:
        path = request.match_info["path"]
        match = re.search(r"^([a-zA-Z0-9_-]{6})(\d+)$", path)
        if match:
            secure_hash = match.group(1)
            id = int(match.group(2))
        else:
            id = int(re.search(r"(\d+)(?:\/\S+)?", path).group(1))
            secure_hash = request.rel_url.query.get("hash")
        return web.Response(text=await render_page(id, secure_hash), content_type='text/html')
    except InvalidHash as e:
        raise web.HTTPForbidden(text=e.message)
    except FIleNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        raise web.HTTPBadRequest(text="Bad request")
    except Exception as e:
        logging.critical(e.with_traceback(None))
        raise web.HTTPInternalServerError(text=str(e))

@routes.get(r"/{path:\S+}", allow_head=True)
async def stream_handler(request: web.Request):
    try:
        path = request.match_info["path"]
        match = re.search(r"^([a-zA-Z0-9_-]{6})(\d+)$", path)
        if match:
            secure_hash = match.group(1)
            id = int(match.group(2))
        else:
            id = int(re.search(r"(\d+)(?:\/\S+)?", path).group(1))
            secure_hash = request.rel_url.query.get("hash")
        return await media_streamer(request, id, secure_hash)
    except InvalidHash as e:
        raise web.HTTPForbidden(text=e.message)
    except FIleNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        raise web.HTTPBadRequest(text="Bad request")
    except Exception as e:
        logging.critical(e.with_traceback(None))
        raise web.HTTPInternalServerError(text=str(e))

class_cache = {}

def _content_disposition(disposition: str, file_name: str) -> str:
    """Header-safe filename (non-latin names / quotes used to crash the response)."""
    ascii_name = re.sub(r'[^A-Za-z0-9._ -]', '_', file_name.encode("ascii", "ignore").decode() or "file")
    ascii_name = ascii_name.strip() or "file"
    return (f'{disposition}; filename="{ascii_name}"; '
            f"filename*=UTF-8''{urllib.parse.quote(file_name, safe='')}")

async def media_streamer(request: web.Request, id: int, secure_hash: str):
    range_header = request.headers.get("Range", "")

    index = min(work_loads, key=work_loads.get)
    faster_client = multi_clients[index]

    if faster_client in class_cache:
        tg_connect = class_cache[faster_client]
    else:
        tg_connect = ByteStreamer(faster_client)
        class_cache[faster_client] = tg_connect

    file_id = await tg_connect.get_file_properties(id)

    if file_id.unique_id[:6] != secure_hash:
        logging.debug(f"Invalid hash for message with ID {id}")
        raise InvalidHash

    file_size = file_id.file_size

    # ---- Range parsing (supports "a-b", "a-" and suffix "-n") ----
    try:
        if range_header:
            raw_range = range_header.replace("bytes=", "").split(",")[0].strip()
            start_s, end_s = raw_range.split("-", 1)
            if start_s == "":
                suffix = int(end_s)
                from_bytes = max(file_size - suffix, 0)
                until_bytes = file_size - 1
            else:
                from_bytes = int(start_s)
                until_bytes = int(end_s) if end_s else file_size - 1
        else:
            from_bytes = 0
            until_bytes = file_size - 1
    except ValueError:
        return web.Response(
            status=416,
            body="416: Range not satisfiable",
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    until_bytes = min(until_bytes, file_size - 1)
    if from_bytes < 0 or until_bytes < from_bytes or from_bytes >= file_size:
        return web.Response(
            status=416,
            body="416: Range not satisfiable",
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    chunk_size = 1024 * 1024
    offset = from_bytes - (from_bytes % chunk_size)
    first_part_cut = from_bytes - offset
    last_part_cut = until_bytes % chunk_size + 1

    req_length = until_bytes - from_bytes + 1
    # inclusive chunk count (the old formula dropped a chunk when the range
    # ended exactly on a 1 MB boundary)
    part_count = (until_bytes // chunk_size) - (offset // chunk_size) + 1

    mime_type = file_id.mime_type or None
    file_name = file_id.file_name or None
    disposition = "attachment"

    if mime_type:
        if not file_name:
            try:
                file_name = f"{secrets.token_hex(2)}.{mime_type.split('/')[1]}"
            except (IndexError, AttributeError):
                file_name = f"{secrets.token_hex(2)}.unknown"
    else:
        if file_name:
            mime_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        else:
            mime_type = "application/octet-stream"
            file_name = f"{secrets.token_hex(2)}.unknown"

    headers = {
        "Content-Type": f"{mime_type}",
        "Content-Length": str(req_length),
        "Content-Disposition": _content_disposition(disposition, file_name),
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=3600",
    }
    if range_header:
        headers["Content-Range"] = f"bytes {from_bytes}-{until_bytes}/{file_size}"

    resp = web.StreamResponse(status=206 if range_header else 200, headers=headers)
    await resp.prepare(request)
    if request.method == "HEAD":
        return resp

    body = tg_connect.yield_file(
        file_id, index, offset, first_part_cut, last_part_cut, part_count, chunk_size
    )
    try:
        async for chunk in body:
            await resp.write(chunk)
        await resp.write_eof()
    except (ConnectionResetError, ConnectionError, asyncio.CancelledError):
        # viewer seeked / closed the player: stop pulling from Telegram
        await body.aclose()
    except Exception as e:
        logging.warning(f"Stream aborted for message {id}: {e!r}")
        await body.aclose()
    return resp
