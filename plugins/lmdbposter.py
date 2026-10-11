import re
import aiohttp
import warnings
import logging
from io import BytesIO
from PIL import Image
from info import DREAMXBOTZ_IMAGE_FETCH, TMDB_API_KEY
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


async def get_movie_details(query, id=False, file=None):
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
TMDB_IMG = "https://image.tmdb.org/t/p/original"


def _img(path):
    return f"{TMDB_IMG}{path}" if path else None


async def get_movie_detailsx(query, id=False, file=None):
    """Fetch details + poster/backdrop DIRECTLY from TMDB (no third-party proxy).
    Returns a dict with the same keys as before. On any failure returns
    {"error": "..."} so callers can fall back to IMDb."""
    q = str(query).strip()
    year = None
    m = re.search(r'\b((?:19|20)\d{2})\b', q)
    if m:
        year = m.group(1)
        q = q.replace(year, " ").strip()
    elif file:
        m = re.search(r'\b((?:19|20)\d{2})\b', file)
        year = m.group(1) if m else None
    q = re.sub(r'\s+', ' ', q)
    if not q:
        return {"error": "empty query"}

    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{TMDB_API}/search/multi",
                                   params={"api_key": TMDB_API_KEY, "query": q}) as r:
                if r.status != 200:
                    logger.error(f"TMDB search failed [{r.status}] for '{q}': {await r.text()}")
                    return {"error": f"tmdb search {r.status}"}
                results = [x for x in (await r.json()).get("results", [])
                           if x.get("media_type") in ("movie", "tv")]
            if not results:
                return {"error": "no tmdb results"}

            pick = results[0]
            if year:
                for x in results:
                    d = (x.get("release_date") or x.get("first_air_date") or "")[:4]
                    if d == year:
                        pick = x
                        break

            kind = pick["media_type"]
            async with session.get(
                f"{TMDB_API}/{kind}/{pick['id']}",
                params={"api_key": TMDB_API_KEY,
                        "append_to_response": "credits,external_ids,images",
                        "include_image_language": "en,null"}) as r:
                if r.status != 200:
                    logger.error(f"TMDB details failed [{r.status}] for id={pick['id']}")
                    return {"error": f"tmdb details {r.status}"}
                data = await r.json()
    except Exception as e:
        logger.error(f"An error occurred in get_movie_detailsx: {e}")
        return {"error": str(e)}

    date = data.get("release_date") or data.get("first_air_date") or ""
    credits = data.get("credits") or {}
    crew = credits.get("crew") or []

    def crew_names(*jobs):
        return [c["name"] for c in crew if c.get("job") in jobs][:3]

    imgs = data.get("images") or {}
    poster_path = data.get("poster_path") or next(
        (p["file_path"] for p in imgs.get("posters", [])), None)
    backdrop_path = next((b["file_path"] for b in imgs.get("backdrops", [])
                          if b.get("iso_639_1") in ("en", None)), None) or data.get("backdrop_path")

    runtime = data.get("runtime") or (data.get("episode_run_time") or [None])[0]
    rating = data.get("vote_average")
    return {
        "title": data.get("title") or data.get("name"),
        "year": date[:4] or None,
        "release_date": date or None,
        "rating": round(float(rating), 1) if rating else None,
        "votes": int(data.get("vote_count") or 0),
        "runtime": f"{runtime} min" if runtime else None,
        "certificates": None,
        "tmdb_url": f"https://www.themoviedb.org/{kind}/{pick['id']}",
        "genres": [g["name"] for g in data.get("genres", [])],
        "languages": [l.get("english_name", "") for l in data.get("spoken_languages", [])],
        "countries": [c.get("name", "") for c in data.get("production_countries", [])],
        "director": crew_names("Director"),
        "writer": crew_names("Writer", "Screenplay"),
        "producer": crew_names("Producer"),
        "composer": crew_names("Original Music Composer"),
        "cinematographer": crew_names("Director of Photography"),
        "cast": [c["name"] for c in (credits.get("cast") or [])[:6]],
        "plot": data.get("overview"),
        "tagline": data.get("tagline"),
        "box_office": data.get("revenue") or None,
        "distributors": [c["name"] for c in data.get("production_companies", [])][:3],
        "imdb_id": (data.get("external_ids") or {}).get("imdb_id"),
        "tmdb_id": pick["id"],
        "poster_url": _img(poster_path),
        "backdrop_url": _img(backdrop_path),
    }
