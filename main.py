# connect to the public WebSocket
import math
import re
import json
import asyncio
from typing import Dict, Any
import requests
import websockets

RAW_BASE = "https://raw.githubusercontent.com"

station_locations = {}

def fetch_raw_file(owner: str, repo: str, path: str, ref: str = "main") -> str:
    url = f"{RAW_BASE}/{owner}/{repo}/{ref}/{path.lstrip('/')}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.text


def find_brace_block(text: str, start_pos: int) -> str:
    """Given a text and position of an opening brace, return the balanced {...} block."""
    i = start_pos
    if i < 0 or i >= len(text):
        raise ValueError("start_pos out of range")
    if text[i] != "{":
        i = text.find("{", start_pos)
        if i == -1:
            raise ValueError("Opening brace not found")
    depth = 0
    for idx in range(i, len(text)):
        ch = text[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[i : idx + 1]
    raise ValueError("Matching closing brace not found")

# Essentially, what this does is get the area markers in case if the game updates, To avoid any bugs if the game updates and the code still uses the old locations, a quick refresh of the code should do the trick.
def extract_area_markers(js_text: str) -> Dict[str, Any]:
    m = re.search(r"const\s+AREA_MARKERS\s*=\s*{", js_text)
    if not m:
        raise ValueError("AREA_MARKERS not found in the file")
    brace_start = js_text.find("{", m.end() - 1)
    block = find_brace_block(js_text, brace_start)

    s = block
    s = re.sub(r",\s*([}\]])", r"\1", s)
    s = re.sub(
        r'([{\s,])([A-Za-z_][A-Za-z0-9_\- ]*)\s*:',
        lambda mm: f'{mm.group(1)}"{mm.group(2)}":',
        s,
    )
    s = s.replace("'", '"')

    try:
        parsed = json.loads(s)
    except json.JSONDecodeError as e:
        snippet = s[max(0, e.pos - 60) : e.pos + 60]
        raise ValueError(f"Failed to parse JSON-converted AREA_MARKERS: {e}\nAround: {snippet}")

    return parsed


def station_locations(
    owner: str = "dovedalerailway",
    repo: str = "dovedale-map",
    path: str = "public/index.js",
    ref: str = "main",
) -> Dict[str, Any]:
    """Fetch AREA_MARKERS from GitHub and return as Python dict."""
    js = fetch_raw_file(owner, repo, path, ref)
    return extract_area_markers(js)


# --- WebSocket helpers ---
async def receive_websocket_data(uri: str, queue: asyncio.Queue):
    """Open a connection and push incoming messages into the queue."""
    # websockets.connect expects scheme (ws:// or wss://). Caller should pass full URI.
    async with websockets.connect(uri) as websocket:
        print(f"Connected to {uri}")
        try:
            while True:
                message = await websocket.recv()
                await queue.put(message)
        except websockets.exceptions.ConnectionClosed as e:
            print("Connection closed:", e)
            raise


async def consumer_task(queue: asyncio.Queue):
    """Consume messages from the queue and do simple preview printing."""
    stations_cache = None
    while True:
        message = await queue.get()
        try:
            data = json.loads(message)
        except Exception:
            data = message

        # Lazy-load station markers (calls the station_locations() function defined above)
        if stations_cache is None:
            try:
                stations_cache = station_locations()
            except Exception as e:
                print("Failed to load station markers:", e)
                stations_cache = {}

        if not isinstance(data, dict):
            print("Received non-dict message:", data)
            continue

        players = data.get("players", [])
        if not players:
            # nothing to do for this message
            continue
            
        # -- TASK UNDERNEATH HERE -- #

        # Initialize distances_by_player for this message (aggregates per-player distances)
        distances_by_player = {}

        for p in players:
            username = p.get("username", "<unknown>")
            pos = p.get("position") or p.get("pos") or {}
            try:
                px = float(pos.get("x"))
                py = float(pos.get("y"))
            except Exception:
                print(f"{username}: invalid position {pos}")
                continue

            # Print distance from this player to each station in the markers
            for sname, sinfo in stations_cache.items():
                sx = sy = None
                # try common shapes for station coordinate data
                if isinstance(sinfo, dict):
                    spos = sinfo.get("pos") or sinfo.get("position") or sinfo.get("coords")
                    if isinstance(spos, dict):
                        sx = spos.get("x") or spos.get("lon") or spos.get("lng")
                        sy = spos.get("y") or spos.get("lat")
                    else:
                        sx = sinfo.get("x")
                        sy = sinfo.get("y")
                elif isinstance(sinfo, (list, tuple)) and len(sinfo) >= 2:
                    sx, sy = sinfo[0], sinfo[1]

                try:
                    sx = float(sx)
                    sy = float(sy)
                except Exception:
                    # skip station entries without usable coordinates
                    continue

                dist = math.hypot(px - sx, py - sy)
                # append distance into a dict keyed by player then station
                player_entry = distances_by_player.setdefault(username, {})
                player_entry[sname] = int(round(dist))

        # Print aggregated distances for the message
        print(distances_by_player)


async def run_ws_with_reconnect(uri: str, queue: asyncio.Queue, reconnect_delay: float = 5.0):
    """Run websocket + consumer, and reconnect automatically on failure."""
    while True:
        try:
            # create consumer task
            consumer = asyncio.create_task(consumer_task(queue))
            # run receiver; it will raise when connection closes
            await receive_websocket_data(uri, queue)
        except (OSError, websockets.InvalidURI, websockets.InvalidHandshake) as e:
            print("WebSocket connection failed:", type(e).__name__, e)
        except Exception as e:
            print("WebSocket error:", type(e).__name__, e)
        finally:
            # Allow the consumer to finish processing queued messages for a short moment
            await asyncio.sleep(0.1)
            # cancel consumer if it's still running
            if 'consumer' in locals() and not consumer.done():
                consumer.cancel()
                try:
                    await consumer
                except asyncio.CancelledError:
                    pass

        # wait before trying to reconnect
        print(f"Reconnecting in {reconnect_delay} seconds...")
        await asyncio.sleep(reconnect_delay)


# --- Hardcoded configuration and main ---
def main():
    # Hardcoded values (replace as needed)
    owner = "dovedalerailway"
    repo = "dovedale-map"
    path = "public/index.js"
    ref = "main"
    out = None  # e.g., "area_markers.json" to save
    ws = True
    ws_uri = "wss://map.dovedale.wiki/ws"
    reconnect_delay = 5.0

    try:
        markers = station_locations(owner, repo, path, ref)
    except requests.HTTPError:
        return
    except ValueError:
        return

    stations = markers

    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(markers, f, indent=2, ensure_ascii=False)

    
    if ws:
        try:
            print("Starting websocket receive and consumer (Ctrl+C to stop)...")
            q = asyncio.Queue()
            asyncio.run(run_ws_with_reconnect(ws_uri, q, reconnect_delay))
        except KeyboardInterrupt:
            print("Interrupted by user; shutting down.")
        except Exception as e:
            print("Websocket error:", type(e).__name__, e)

if __name__ == "__main__":
    main()
