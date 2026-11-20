import re
import time
import aiohttp
import warnings
import logging
from io import BytesIO
from PIL import Image
from info import DREAMXBOTZ_IMAGE_FETCH, TMDB_API_KEY, OMDB_API_KEY
from imdb import Cinemagoer


logger = logging.getLogger(__name__)
ia = Cinemagoer()
LONG_IMDB_DESCRIPTION = False

def list_to_str(lst):
    if lst:
        return ", ".join(map(str, lst))
    return ""





Image.MAX_IMAGE_PIXELS = None
warnings.simplefilter("ignore", Image.DecompressionBombWarning)
async def fetch_image(url, size=(860, 1200)):
    if not DREAMXBOTZ_IMAGE_FETCH:
        logger.info("Image fetching is disabled.")
        return None

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch image: {response.status}")
                    return None

                data = await response.read()
                img = Image.open(BytesIO(data))
                img = img.resize(size, Image.LANCZOS)


                out = BytesIO()
                img.save(out, format="JPEG")
                out.seek(0)
                return out

    except aiohttp.ClientError as e:
        logger.error(f"HTTP request error in fetch_image: {e}")
    except IOError as e:
        logger.error(f"I/O error in fetch_image: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in fetch_image: {e}")

    return None


async def _get_movie_details_imdb(query, id=False, file=None):
    try:
        if not id:
            query = query.strip().lower()
            title = query
            year = re.findall(r'[1-2]\d{3}$', query, re.IGNORECASE)
            if year:
                year = list_to_str(year[:1])
                title = query.replace(year, "").strip()
            elif file is not None:
                year = re.findall(r'[1-2]\d{3}', file, re.IGNORECASE)
                if year:
                    year = list_to_str(year[:1])
            else:
                year = None
            movieid = ia.search_movie(title.lower(), results=10)
            if not movieid:
                return None
            if year:
                filtered = list(filter(lambda k: str(k.get('year')) == str(year), movieid))
                if not filtered:
                    filtered = movieid
            else:
                filtered = movieid
            movieid = list(filter(lambda k: k.get('kind') in ['movie', 'tv series'], filtered))
            if not movieid:
                movieid = filtered
            movieid = movieid[0].movieID
        else:
            movieid = query
        movie = ia.get_movie(movieid)
        ia.update(movie, info=['main', 'vote details'])
        if movie.get("original air date"):
            date = movie["original air date"]
        elif movie.get("year"):
            date = movie.get("year")
        else:
            date = "N/A"
        plot = movie.get('plot')
        if plot and len(plot) > 0:
            plot = plot[0]
        else:
            plot = movie.get('plot outline')
        if plot and len(plot) > 800:
            plot = plot[:800] + "..."
        poster_url = movie.get('full-size cover url')
        return {
            'title': movie.get('title'),
            'votes': movie.get('votes'),
            "aka": list_to_str(movie.get("akas")),
            "seasons": movie.get("number of seasons"),
            "box_office": movie.get('box office'),
            'localized_title': movie.get('localized title'),
            'kind': movie.get("kind"),
            "imdb_id": f"tt{movie.get('imdbID')}",
            "cast": list_to_str(movie.get("cast")),
            "runtime": list_to_str(movie.get("runtimes")),
            "countries": list_to_str(movie.get("countries")),
            "certificates": list_to_str(movie.get("certificates")),
            "languages": list_to_str(movie.get("languages")),
            "director": list_to_str(movie.get("director")),
            "writer": list_to_str(movie.get("writer")),
            "producer": list_to_str(movie.get("producer")),
            "composer": list_to_str(movie.get("composer")),
            "cinematographer": list_to_str(movie.get("cinematographer")),
            "music_team": list_to_str(movie.get("music department")),
            "distributors": list_to_str(movie.get("distributors")),
            'release_date': date,
            'year': movie.get('year'),
            'genres': list_to_str(movie.get("genres")),
            'poster_url': poster_url,
            'plot': plot,
            'rating': str(movie.get("rating", "N/A")),
            'url': f'https://www.imdb.com/title/tt{movieid}'
        }
    except Exception as e:
        logger.error(f"An error occurred in get_movie_details: {e}")
        return None

TMDB_API = "https://api.themoviedb.org/3"
TMDB_IMG = "https://image.tmdb.org/t/p"


def _tmdb_auth():
    """Supports both TMDB v3 API key and v4 'Read Access Token' (starts with eyJ)."""
    key = (TMDB_API_KEY or "").strip()
    if key.startswith("eyJ"):
        return {"Authorization": f"Bearer {key}", "accept": "application/json"}, {}
    return {"accept": "application/json"}, {"api_key": key}


async def _tmdb_get(session, path, **params):
    headers, auth_params = _tmdb_auth()
    params.update(auth_params)
    async with session.get(f"{TMDB_API}{path}", params=params, headers=headers,
                           timeout=aiohttp.ClientTimeout(total=20)) as resp:
        if resp.status != 200:
            text = await resp.text()
            logger.error(f"TMDB request failed [{resp.status}] {path}: {text[:200]}")
            return None
        return await resp.json()


def _img(path, size="original"):
    return f"{TMDB_IMG}/{size}{path}" if path else None


def _pick_image(items, lang):
    """Best image path: preferred language first, then language-less, then anything."""
    if not items:
        return None
    for want in ("en", lang, None):
        for it in items:
            if it.get("iso_639_1") == want and it.get("file_path"):
                return it["file_path"]
    return items[0].get("file_path")


async def _get_tmdb_details(query, id=False, file=None):
    """
    Fetch details + poster/backdrop straight from the official TMDB API.
    ALWAYS returns a dict. On failure -> {"error": "..."} (never None),
    so callers can safely fall back to IMDb.
    """
    if not TMDB_API_KEY or TMDB_API_KEY.startswith("http"):
        return {"error": "TMDB_API_KEY is not set (get one from https://www.themoviedb.org/settings/api)"}

    q = str(query).strip()
    try:
        async with aiohttp.ClientSession() as session:
            media_type, tmdb_id = None, None

            if id:
                if q.startswith("tt"):
                    found = await _tmdb_get(session, f"/find/{q}", external_source="imdb_id")
                    if found:
                        for kind, key in (("movie", "movie_results"), ("tv", "tv_results")):
                            if found.get(key):
                                media_type, tmdb_id = kind, found[key][0]["id"]
                                break
                elif q.isdigit():
                    tmdb_id = int(q)
                    media_type = "movie" if await _tmdb_get(session, f"/movie/{q}") else "tv"
            else:
                title = q.lower()
                year = None
                m = re.search(r'\b([12]\d{3})\b\s*$', title)
                if m:
                    year = m.group(1)
                    title = title[:m.start()].strip()
                elif file:
                    m = re.search(r'\b([12]\d{3})\b', file)
                    if m:
                        year = m.group(1)
                if not title:
                    title = q.lower()

                res = await _tmdb_get(session, "/search/multi", query=title, include_adult="false")
                results = [r for r in (res or {}).get("results", []) if r.get("media_type") in ("movie", "tv")]
                if not results:
                    return {"error": f"No TMDB result for '{q}'"}
                chosen = results[0]
                if year:
                    for r in results:
                        d = r.get("release_date") or r.get("first_air_date") or ""
                        if d.startswith(year):
                            chosen = r
                            break
                media_type, tmdb_id = chosen["media_type"], chosen["id"]

            if not tmdb_id or not media_type:
                return {"error": f"TMDB id not found for '{q}'"}

            extra = "credits,images,external_ids," + ("release_dates" if media_type == "movie" else "content_ratings")
            data = await _tmdb_get(session, f"/{media_type}/{tmdb_id}",
                                   append_to_response=extra,
                                   include_image_language="en,null,hi")
            if not data:
                return {"error": f"TMDB details failed for id {tmdb_id}"}
    except Exception as e:
        logger.error(f"An error occurred in get_movie_detailsx: {e}")
        return {"error": str(e)}

    credits = data.get("credits") or {}
    crew = credits.get("crew") or []

    def crew_of(*jobs):
        return [c["name"] for c in crew if c.get("job") in jobs and c.get("name")]

    is_movie = media_type == "movie"
    date = data.get("release_date") if is_movie else data.get("first_air_date")
    year_val = int(date[:4]) if date and date[:4].isdigit() else None
    runtime = data.get("runtime") if is_movie else (data.get("episode_run_time") or [None])[0]

    cert = None
    try:
        if is_movie:
            for c in (data.get("release_dates") or {}).get("results", []):
                if c.get("iso_3166_1") in ("IN", "US"):
                    for r in c.get("release_dates", []):
                        if r.get("certification"):
                            cert = r["certification"]
                            break
                if cert:
                    break
        else:
            for c in (data.get("content_ratings") or {}).get("results", []):
                if c.get("iso_3166_1") in ("IN", "US") and c.get("rating"):
                    cert = c["rating"]
                    break
    except Exception:
        pass

    lang = data.get("original_language")
    images = data.get("images") or {}
    poster_path = _pick_image(images.get("posters"), lang) or data.get("poster_path")
    backdrop_path = _pick_image(images.get("backdrops"), lang) or data.get("backdrop_path")

    return {
        "title": data.get("title") or data.get("name"),
        "localized_title": data.get("original_title") or data.get("original_name"),
        "year": year_val,
        "release_date": date,
        "rating": round(float(data["vote_average"]), 1) if data.get("vote_average") else None,
        "votes": int(data.get("vote_count") or 0),
        "runtime": f"{runtime} min" if runtime else None,
        "certificates": cert,
        "tmdb_url": f"https://www.themoviedb.org/{media_type}/{tmdb_id}",
        "genres": [g["name"] for g in data.get("genres", [])],
        "languages": [l.get("english_name") or l.get("name") for l in data.get("spoken_languages", [])],
        "countries": [c["name"] for c in data.get("production_countries", [])] if is_movie
                     else list(data.get("origin_country") or []),
        "director": crew_of("Director") if is_movie else [c["name"] for c in data.get("created_by", [])],
        "writer": crew_of("Writer", "Screenplay", "Story"),
        "producer": crew_of("Producer", "Executive Producer"),
        "composer": crew_of("Original Music Composer", "Composer"),
        "cinematographer": crew_of("Director of Photography"),
        "cast": [c["name"] for c in (credits.get("cast") or [])[:10] if c.get("name")],
        "plot": data.get("overview"),
        "tagline": data.get("tagline"),
        "box_office": data.get("revenue") or None,
        "seasons": data.get("number_of_seasons"),
        "distributors": [c["name"] for c in data.get("production_companies", [])],
        "imdb_id": (data.get("external_ids") or {}).get("imdb_id") or data.get("imdb_id"),
        "tmdb_id": tmdb_id,
        "poster_url": _img(poster_path),
        "backdrop_url": _img(backdrop_path),
    }



# =====================================================================
#                       OMDb  (omdbapi.com)  SUPPORT
# =====================================================================
OMDB_API = "https://www.omdbapi.com/"
OMDB_CACHE_TTL = 24 * 3600          # cache each lookup for 24h (saves the 1000/day free quota)
OMDB_CACHE_MAX = 1000
_omdb_cache = {}                    # key -> (timestamp, result_dict)
_omdb_blocked_until = 0             # set when OMDb says "Request limit reached!"


def _na(v):
    """OMDb returns the string 'N/A' for missing values."""
    if v is None:
        return None
    v = str(v).strip()
    return None if not v or v.upper() == "N/A" else v


def _split(v):
    v = _na(v)
    return [x.strip() for x in v.split(",") if x.strip()] if v else []


def _split_title_year(query, file=None):
    """'avatar 2009' -> ('avatar', '2009').  Year can also come from the file name."""
    title = str(query).strip().lower()
    year = None
    m = re.search(r'\b([12]\d{3})\b\s*$', title)
    if m:
        year = m.group(1)
        title = title[:m.start()].strip()
    elif file:
        m = re.search(r'\b([12]\d{3})\b', file)
        if m:
            year = m.group(1)
    return (title or str(query).strip().lower()), year


def _normalize_omdb(o):
    """Raw OMDb JSON -> the same dict shape used by get_movie_detailsx()."""
    ratings = {r.get("Source"): r.get("Value") for r in (o.get("Ratings") or [])}
    imdb_id = _na(o.get("imdbID"))
    url = f"https://www.imdb.com/title/{imdb_id}" if imdb_id else None

    votes = _na(o.get("imdbVotes"))
    try:
        votes = int(votes.replace(",", "")) if votes else None
    except ValueError:
        votes = None
    try:
        rating = float(_na(o.get("imdbRating"))) if _na(o.get("imdbRating")) else None
    except ValueError:
        rating = None

    kind = "tv series" if (o.get("Type") or "").lower() == "series" else "movie"
    released = _na(o.get("Released"))
    year = _na(o.get("Year"))
    year_val = int(year[:4]) if year and year[:4].isdigit() else None
    seasons = _na(o.get("totalSeasons"))

    return {
        "title": _na(o.get("Title")),
        "localized_title": None,
        "year": year_val,
        "release_date": released or year,
        "rating": rating,
        "votes": votes,
        "runtime": _na(o.get("Runtime")),
        "certificates": _na(o.get("Rated")),
        "tmdb_url": url,            # kept so older code paths (which read tmdb_url) still get a link
        "url": url,
        "imdb_url": url,
        "kind": kind,
        "genres": _split(o.get("Genre")),
        "languages": _split(o.get("Language")),
        "countries": _split(o.get("Country")),
        "director": _split(o.get("Director")),
        "writer": _split(o.get("Writer")),
        "producer": [], "composer": [], "cinematographer": [],
        "cast": _split(o.get("Actors")),
        "plot": _na(o.get("Plot")),
        "tagline": None,
        "box_office": _na(o.get("BoxOffice")),
        "seasons": int(seasons) if seasons and seasons.isdigit() else None,
        "distributors": [],
        "imdb_id": imdb_id,
        "tmdb_id": None,
        "poster_url": _na(o.get("Poster")),
        "backdrop_url": None,
        # OMDb-only extras
        "rt_rating": ratings.get("Rotten Tomatoes"),
        "metascore": _na(o.get("Metascore")),
        "awards": _na(o.get("Awards")),
    }


async def _omdb_request(params):
    """One OMDb call. Returns raw JSON dict or None. Handles quota / bad key gracefully."""
    global _omdb_blocked_until
    if time.time() < _omdb_blocked_until:
        return None
    q = dict(params, apikey=OMDB_API_KEY.strip(), r="json")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(OMDB_API, params=q, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json(content_type=None)
                if resp.status == 401 or "limit" in str(data.get("Error", "")).lower():
                    logger.error(f"OMDb: {data.get('Error')} - pausing OMDb for 6 hours")
                    _omdb_blocked_until = time.time() + 6 * 3600
                    return None
                if resp.status != 200:
                    logger.error(f"OMDb request failed [{resp.status}]")
                    return None
                return data
    except Exception as e:
        logger.error(f"OMDb request error: {e}")
        return None


async def get_omdb_details(title=None, imdb_id=None, year=None):
    """
    Look a title up on OMDb (by IMDb id when known, else by title [+year]).
    ALWAYS returns a dict: normalized details, or {"error": "..."}.
    Results are cached for 24h.
    """
    if not OMDB_API_KEY:
        return {"error": "OMDB_API_KEY is not set (free key: https://www.omdbapi.com/apikey.aspx)"}

    key = (imdb_id or f"{title}|{year}").lower()
    hit = _omdb_cache.get(key)
    if hit and time.time() - hit[0] < OMDB_CACHE_TTL:
        return hit[1]

    data = None
    if imdb_id:
        data = await _omdb_request({"i": imdb_id, "plot": "full"})
    elif title:
        if year:
            data = await _omdb_request({"t": title, "y": year, "plot": "full"})
        if not data or data.get("Response") != "True":
            data = await _omdb_request({"t": title, "plot": "full"})
        if not data or data.get("Response") != "True":
            found = await _omdb_request({"s": title})
            hits = (found or {}).get("Search") or []
            hits = [h for h in hits if h.get("Type") in ("movie", "series")] or hits
            if year:
                hits = sorted(hits, key=lambda h: str(h.get("Year", "")).startswith(str(year)), reverse=True)
            if hits:
                data = await _omdb_request({"i": hits[0]["imdbID"], "plot": "full"})

    if not data or data.get("Response") != "True":
        return {"error": f"OMDb: {(data or {}).get('Error', 'no response')}"}

    result = _normalize_omdb(data)
    if len(_omdb_cache) >= OMDB_CACHE_MAX:
        _omdb_cache.clear()
    _omdb_cache[key] = (time.time(), result)
    return result


def _merge_omdb(base, omdb):
    """
    Merge OMDb into an existing details dict (TMDB or IMDb-scraper).
      - IMDb rating + votes come from OMDb (official IMDb numbers)
      - RT / Metascore / awards are added
      - anything missing in `base` is filled from OMDb
    """
    if not omdb or omdb.get("error"):
        return base
    out = dict(base)
    if omdb.get("rating"):
        out["rating"] = omdb["rating"]
    if omdb.get("votes"):
        out["votes"] = omdb["votes"]
    for k in ("rt_rating", "metascore", "awards"):
        out[k] = omdb.get(k)
    for k in ("plot", "certificates", "runtime", "languages", "countries", "director", "writer",
              "cast", "genres", "poster_url", "year", "release_date", "box_office", "imdb_id", "seasons"):
        if not out.get(k) and omdb.get(k):
            out[k] = omdb[k]
    if omdb.get("url") and not out.get("imdb_url"):
        out["imdb_url"] = omdb["url"]
    out["sources"] = (out.get("sources") or "base") + "+OMDb"
    return out


# =====================================================================
#              PUBLIC FUNCTIONS (TMDB + OMDb + IMDb chained)
# =====================================================================
async def get_movie_detailsx(query, id=False, file=None):
    """
    TMDB first (posters/backdrop/cast), enriched with OMDb (IMDb rating, RT, Metascore, awards).
      * TMDB ok  + OMDb key  -> merged result
      * TMDB fail/no key     -> OMDb-only result (if OMDB_API_KEY set)
      * OMDb fail            -> plain TMDB result
    ALWAYS returns a dict; failure -> {"error": "..."}.
    """
    tmdb = await _get_tmdb_details(query, id=id, file=file)
    if not OMDB_API_KEY:
        return tmdb

    q = str(query).strip()
    if tmdb and not tmdb.get("error"):
        if tmdb.get("imdb_id"):
            omdb = await get_omdb_details(imdb_id=tmdb["imdb_id"])
        else:
            title = tmdb.get("title") or q
            omdb = await get_omdb_details(title=title, year=tmdb.get("year"))
        tmdb["imdb_url"] = tmdb.get("imdb_url") or (
            f"https://www.imdb.com/title/{tmdb['imdb_id']}" if tmdb.get("imdb_id") else None)
        merged = _merge_omdb(tmdb, omdb)
        merged["sources"] = merged.get("sources", "TMDB").replace("base", "TMDB")
        return merged

    # ---- TMDB failed -> OMDb only ----
    if id:
        if q.startswith("tt"):
            omdb = await get_omdb_details(imdb_id=q)
        else:
            return tmdb                      # a bare TMDB id can't be looked up on OMDb
    else:
        title, year = _split_title_year(q, file)
        omdb = await get_omdb_details(title=title, year=year)
    if omdb.get("error"):
        return {"error": f"{(tmdb or {}).get('error')} | {omdb['error']}"}
    omdb["sources"] = "OMDb"
    return omdb


async def get_movie_details(query, id=False, file=None):
    """
    IMDb (Cinemagoer) details, enriched with OMDb extras.  If IMDb scraping fails
    (it breaks often) and OMDB_API_KEY is set, OMDb is used instead.
    """
    base = None
    try:
        base = await _get_movie_details_imdb(query, id=id, file=file)
    except Exception as e:
        logger.error(f"IMDb lookup failed: {e}")
    if not OMDB_API_KEY:
        return base

    if base:
        imdb_id = base.get("imdb_id")
        if imdb_id and imdb_id != "ttNone":
            omdb = await get_omdb_details(imdb_id=imdb_id)
        else:
            omdb = await get_omdb_details(title=base.get("title"), year=base.get("year"))
        merged = _merge_omdb(base, omdb)
        merged["imdb_url"] = merged.get("imdb_url") or merged.get("url")
        return merged

    q = str(query).strip()
    if id:
        imdb_id = q if q.startswith("tt") else ("tt" + q.zfill(7) if q.isdigit() else None)
        omdb = await get_omdb_details(imdb_id=imdb_id) if imdb_id else {"error": "bad id"}
    else:
        title, year = _split_title_year(q, file)
        omdb = await get_omdb_details(title=title, year=year)
    if omdb.get("error"):
        return None
    omdb["sources"] = "OMDb"
    return omdb
