#Thanks @dreamxbotz for helping in this journey 

import jinja2
from info import *
from dreamxbotz.Bot import dreamxbotz
from dreamxbotz.util.human_readable import humanbytes
from dreamxbotz.util.file_properties import get_file_ids
from dreamxbotz.server.exceptions import InvalidHash
import urllib.parse
import logging


async def render_page(id, secure_hash, src=None):
    file_data = await get_file_ids(dreamxbotz, int(BIN_CHANNEL), int(id))
    if file_data.unique_id[:6] != secure_hash:
        logging.debug(f"Invalid hash for message with - ID {id}")
        raise InvalidHash

    raw_name = file_data.file_name or f"{file_data.unique_id[:8]}"
    src = urllib.parse.urljoin(
        URL,
        f"{id}/{urllib.parse.quote_plus(raw_name)}?hash={secure_hash}",
    )

    mime = file_data.mime_type or "application/octet-stream"
    tag = mime.split("/")[0].strip()
    # size comes from the Telegram message itself (the old code downloaded
    # the whole file from our own server just to read Content-Length)
    file_size = humanbytes(file_data.file_size)
    if tag in ["video", "audio"]:
        template_file = "dreamxbotz/template/req.html"
    else:
        template_file = "dreamxbotz/template/dl.html"

    with open(template_file, encoding="utf-8") as f:
        template = jinja2.Template(f.read())

    return template.render(
        file_name=raw_name.replace("_", " "),
        file_url=src,
        file_size=file_size,
        file_unique_id=file_data.unique_id,
    )
