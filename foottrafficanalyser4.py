import os
from dotenv import load_dotenv

load_dotenv()

import requests
import os
import json
import time
import matplotlib.pyplot as plt
import matplotlib.widgets as widgets
import numpy as np
from typing import Dict, List, Optional
from matplotlib.path import Path
from matplotlib.widgets import PolygonSelector, RangeSlider, Button

# ---------------------------------------------------------------------------
# SCHEMA CONFIG
# I don't have access to a real cached match from your matches/ folder, so I
# can't confirm the exact field names Osirion uses to link a movementEvents
# entry to a specific player, or the field with a player's display name in
# the `players` include. These are best-guess field names, tried in order.
# If the title after clicking a dot shows "Unknown player" or the wrong
# match, open one cached matches/<id>.json and check:
#   - what field on a movementEvents entry identifies the player
#   - what field on a players[] entry holds their id, and what field holds
#     their display name
# then adjust the lists below to match.
# ---------------------------------------------------------------------------
PLAYER_ID_KEYS = ["accountId", "playerId", "epicId", "id"]
PLAYER_NAME_KEYS = ["epicUsername", "name", "displayName", "epicName", "username"]


def _first_present(d, keys):
    """Return the first value in dict `d` whose key is in `keys` (and truthy), else None."""
    if not isinstance(d, dict):
        return None
    for key in keys:
        value = d.get(key)
        if value:
            return value
    return None


def _extract_player_id(event):
    """
    Pull a player identifier off a single movementEvents entry.
    Handles a flat id field (e.g. event["accountId"]) as well as a nested
    shape (e.g. event["player"]["accountId"] or event["player"] == "id-string").
    """
    direct = _first_present(event, PLAYER_ID_KEYS)
    if direct is not None:
        return direct
    nested = event.get("player") if isinstance(event, dict) else None
    if isinstance(nested, dict):
        return _first_present(nested, PLAYER_ID_KEYS)
    if isinstance(nested, str):
        return nested
    return None


class Game:
    def __init__(self, matchId):
        self.matchId = matchId
        self.zone1EndTime = 0
        self.zone3EndTime = 0
        self.zone3Center = [0, 0]  # default so getMovementDatapoints never crashes if phase 3 is missing
        self.movementDatapoints = []
        self.rawData = self.getRawData()
        self.playerNames = self._buildPlayerLookup()

    def getRawData(self):
        api_token = os.environ["OSIRION_API_TOKEN"]
        payload = {}
        headers = {
            "Authorization": f"Bearer {api_token}"
        }
        data = openJson(self.matchId)
        if data is not None:
            print(f"Loaded data for match {self.matchId} from local cache.")
            return data
        url = f"https://api.osirion.gg/fortnite/v1/matches/{self.matchId}/events?include=safeZoneUpdateEvents,movementEvents,players"
        response = requests.get(url, headers=headers, data=payload)
        if response.status_code != 200:
            print(f"Error fetching data: {response.status_code}, {response.text}")
            return None
        data = response.json()
        saveJson(self.matchId, data)
        print(f"Fetched and saved data for match {self.matchId}.")
        return data

    def _buildPlayerLookup(self):
        """Map playerId -> display name using the `players` include for this match."""
        lookup = {}
        if not self.rawData:
            return lookup
        for player in self.rawData.get("players", []):
            playerId = _first_present(player, PLAYER_ID_KEYS)
            playerName = _first_present(player, PLAYER_NAME_KEYS)
            if playerId is not None:
                lookup[playerId] = playerName or str(playerId)
        return lookup

    def getZoneData(self):
        zoneData = self.rawData.get("safeZoneUpdateEvents", [])
        for zone in zoneData:
            if zone.get("currentPhase") == 1:
                self.zone1EndTime = zone.get("shrinkStartTime", 0)
            elif zone.get("currentPhase") == 4:
                self.zone3EndTime = zone.get("shrinkEndTime", 0)
                self.zone3Center = [zone["nextCenter"]["x"], zone["nextCenter"]["y"]]

    def getMovementDatapoints(self):
        movementData = self.rawData.get("movementEvents", [])
        movementDatapoints = []
        for movement in movementData:
            timestamp = movement.get("timestamp", 0)
            if timestamp >= self.zone1EndTime and timestamp < self.zone3EndTime:
                x = movement["movementData"]["location"].get("x", 0)
                y = movement["movementData"]["location"].get("y", 0)
                relativeTimestamp = timestamp - self.zone1EndTime
                playerId = _extract_player_id(movement)
                movementDatapoints.append((x, y, relativeTimestamp, self.zone3Center[0], self.zone3Center[1], self.matchId, playerId))
        return movementDatapoints


def openJson(match_id):
    # Build file path to 'matches/match_id.json' in root directory
    file_path = os.path.join("matches", f"{match_id}.json")

    if not os.path.exists(file_path):
        return None

    # Open and read JSON
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def saveJson(match_id, data):
    # Ensure 'matches' folder exists
    os.makedirs("matches", exist_ok=True)

    # Build file path
    file_path = os.path.join("matches", f"{match_id}.json")

    # Write JSON to file
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


DEFAULT_COLOR = "tab:blue"
HIGHLIGHT_COLOR = "red"
DEFAULT_TITLE = "Click a dot to see that player's path in that match"


def displayPlot(data, playerNamesById):
    fig, ax = plt.subplots()
    fig.subplots_adjust(left=0.125, bottom=0.133, right=0.9, top=0.964, wspace=0.2, hspace=0.2)
    img = plt.imread("background.jpg")  # load the map image
    ax.imshow(img, extent=[-141373, 141373, -150048, 150048])  # display the map image with scaling of image 1520 x 1520, and 155.08cm per pixel on map

    xs = np.array([point[0] for point in data], dtype=np.float32)
    ys = np.array([-point[1] for point in data], dtype=np.float32)
    timestamps = np.array([point[2] for point in data], dtype=np.float32)
    zoneCenters = np.array([point[3:5] for point in data], dtype=np.float32)
    matchIds = np.array([point[5] for point in data], dtype=object)
    playerIds = np.array([point[6] for point in data], dtype=object)

    n = len(data)

    ax.set_xlabel("0 = Zone 1 closing, 85 = Zone 2 revealed, 145 = Zone 2 closing, 235 = Zone 3 revealed, 285 = Zone 3 closing, 385 = Zone 4 revealed, 455 = Zone 4 closing, 540 = Zone 5 revealed")
    title = ax.set_title(DEFAULT_TITLE)

    time_mask = np.ones(n, dtype=bool)
    zone_mask = np.ones(n, dtype=bool)
    visible_indices = np.arange(n)  # maps "position in the currently-displayed scatter" -> "index into the full arrays"

    scatter = ax.scatter(xs, ys, s=4, c=DEFAULT_COLOR, picker=True, linewidths=0, edgecolors="none", rasterized=True)
    scatter.set_pickradius(8)  # generous click tolerance since dots are small
    highlight_scatter = ax.scatter([], [], s=8, c=HIGHLIGHT_COLOR, linewidths=0, edgecolors="none", rasterized=True)

    slider_ax = fig.add_axes([0.2, 0.05, 0.6, 0.04])
    slider = RangeSlider(slider_ax, "Time after Zone 1", -50, 540, valinit=(-50, 540))

    zone_toggle_ax = fig.add_axes([0.02, 0.92, 0.22, 0.05])
    zone_toggle_button = Button(zone_toggle_ax, "Zone filter: OFF (click map to select players)")

    reset_ax = fig.add_axes([0.78, 0.92, 0.2, 0.05])
    reset_button = Button(reset_ax, "Reset player selection")

    # Whether the polygon zone-selector is currently allowed to consume clicks.
    # Starts OFF so plain clicks select players; toggle it ON to draw a zone filter.
    polygon_mode = {"active": False}
    selected_mask = np.zeros(n, dtype=bool)

    def redo_masks():
        nonlocal visible_indices
        combined = time_mask & zone_mask
        visible_indices = np.where(combined)[0]
        scatter.set_offsets(np.c_[xs[visible_indices], ys[visible_indices]])
        highlight_visible = selected_mask & combined
        highlight_scatter.set_offsets(np.c_[xs[highlight_visible], ys[highlight_visible]])
        fig.canvas.draw_idle()

    def update(val):
        nonlocal time_mask
        time_min, time_max = slider.val
        time_min *= 1000000
        time_max *= 1000000
        time_mask = (timestamps >= time_min) & (timestamps <= time_max)
        redo_masks()

    slider.on_changed(update)

    def on_polygon_complete(verts):
        """
        gives a list of numpy arrays containing coords of vertices of the polygon drawn by the user, in order
        """
        nonlocal zone_mask
        path = Path(verts)
        points = np.c_[zoneCenters[:, 0], -zoneCenters[:, 1]]
        zone_mask = path.contains_points(points)
        redo_masks()

    selector = PolygonSelector(ax, on_polygon_complete)
    selector.set_active(polygon_mode["active"])  # inactive by default, so it doesn't eat player-select clicks

    def toggle_zone_mode(event):
        polygon_mode["active"] = not polygon_mode["active"]
        selector.set_active(polygon_mode["active"])
        if polygon_mode["active"]:
            scatter.set_visible(False)
            highlight_scatter.set_visible(False)
            scatter.set_picker(False)
            zone_toggle_button.label.set_text("Zone filter: ON (click map to draw polygon)")
        else:
            scatter.set_visible(True)
            highlight_scatter.set_visible(True)
            scatter.set_picker(True)
            zone_toggle_button.label.set_text("Zone filter: OFF (click map to select players)")
            redo_masks()
        fig.canvas.draw_idle()

    zone_toggle_button.on_clicked(toggle_zone_mode)

    def clear_selection():
        selected_mask[:] = False
        highlight_scatter.set_offsets(np.empty((0, 2)))
        title.set_text(DEFAULT_TITLE)
        redo_masks()

    def on_pick(event):
        if polygon_mode["active"] or len(event.ind) == 0:
            return
        nonlocal selected_mask
        # event.ind indexes into the currently-displayed (offset) points, not the full array,
        # since some points may be hidden by the time/zone filters. Map back to real indices.
        candidate_positions = visible_indices[np.asarray(event.ind)]
        # If several points are within the pick radius, pick the one closest to the actual click.
        mouseevent = event.mouseevent
        if mouseevent.xdata is not None and mouseevent.ydata is not None:
            dists = (xs[candidate_positions] - mouseevent.xdata) ** 2 + (ys[candidate_positions] - mouseevent.ydata) ** 2
            original_idx = candidate_positions[np.argmin(dists)]
        else:
            original_idx = candidate_positions[0]

        clickedMatchId = matchIds[original_idx]
        clickedPlayerId = playerIds[original_idx]
        clickedPlayerName = playerNamesById.get(clickedPlayerId, "Unknown player") if clickedPlayerId is not None else "Unknown player"

        selected_mask[:] = (matchIds == clickedMatchId) & (playerIds == clickedPlayerId)
        title.set_text(f"{clickedPlayerName} - Match {clickedMatchId}")
        redo_masks()

    fig.canvas.mpl_connect("pick_event", on_pick)
    reset_button.on_clicked(lambda event: clear_selection())

    def close_plot():
        manager = fig.canvas.manager
        if manager is not None:
            from matplotlib._pylab_helpers import Gcf
            Gcf.destroy_fig(fig)
        else:
            plt.close(fig)

    fig.canvas.manager.window.protocol("WM_DELETE_WINDOW", close_plot)

    plt.show()


# ---------------------------------------------------------------------------
# EVENT ID / WINDOW ID -> MATCH ID RESOLUTION
# Ported from zoneLuckScore5.py: pulls sessionHistory off the tournament
# leaderboard for a given eventId/eventWindowId, then converts those session
# IDs into Osirion match IDs via session-id-to-match-id.
# Uses the API token zoneLuckScore5.py has confirmed working against the
# leaderboard + session-id-to-match-id endpoints. This is separate from the
# token Game.getRawData() uses to fetch a match's own event data above -
# swap LEADERBOARD_API_TOKEN below if that stops working for you.
# ---------------------------------------------------------------------------
LEADERBOARD_API_TOKEN = os.environ["OSIRION_API_TOKEN"]
LEADERBOARD_HEADERS = {
    "Authorization": f"Bearer {LEADERBOARD_API_TOKEN}",
    "x-api-key": LEADERBOARD_API_TOKEN,
}
MAX_RETRIES = 3
RETRY_DELAY = 1


def fetch_with_retry(url: str, params: Optional[Dict] = None, timeout: int = 15) -> Optional[Dict]:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            res = requests.get(url, headers=LEADERBOARD_HEADERS, params=params, timeout=timeout)
            if res.status_code == 200:
                return res.json()
            print(f"    HTTP {res.status_code} on attempt {attempt}: {res.text[:250]}")
        except Exception as e:
            print(f"    Network exception on attempt {attempt}: {e}")
        time.sleep(RETRY_DELAY)
    return None


def _extract_leaderboard_entries(data: Dict) -> List[Dict]:
    """Supports both {leaderboard: {entries: [...]}} and {entries: [...]} response shapes."""
    if not data:
        return []
    entries = data.get("leaderboard", {}).get("entries")
    if entries is None:
        entries = data.get("entries", [])
    return entries or []


def _fetch_leaderboard_page(event_id: str, window_id: str, page: int = 0) -> Dict:
    url = "https://fnapi.osirion.gg/v1/tournaments/leaderboard"
    params = {
        "leaderboardEventId": event_id,
        "leaderboardEventWindowId": window_id,
        "page": page,
    }
    data = fetch_with_retry(url, params=params, timeout=15)
    if data is None:
        raise Exception(f"Failed to fetch leaderboard page {page} for {event_id} / {window_id}")
    return data


def _get_leaderboard_session_ids(event_id: str, window_id: str, max_pages: int = 5) -> List[str]:
    """Collect unique session IDs (sessionHistory) from a leaderboard window."""
    seen_session_ids = set()
    ordered_session_ids = []

    for page in range(max_pages):
        print(f"    Page {page}...")
        data = _fetch_leaderboard_page(event_id, window_id, page=page)
        entries = _extract_leaderboard_entries(data)
        print(f"    Leaderboard has {len(entries)} entries on page {page}")
        if not entries:
            break

        for entry in entries:
            for session in entry.get("sessionHistory", []):
                session_id = session.get("sessionId")
                if session_id and session_id not in seen_session_ids:
                    seen_session_ids.add(session_id)
                    ordered_session_ids.append(session_id)

    print(f"    Collected {len(ordered_session_ids)} unique session(s)")
    return ordered_session_ids


def _convert_sessions_to_match_ids(session_ids: List[str]) -> Dict[str, str]:
    """Convert Fortnite session IDs into Osirion match IDs."""
    if not session_ids:
        return {}

    chunk_size = 50
    mapping = {}

    for i in range(0, len(session_ids), chunk_size):
        chunk = session_ids[i:i + chunk_size]
        query = ",".join(chunk)
        url = (
            "https://api.osirion.gg/fortnite/v1/matches/session-id-to-match-id"
            f"?sessionIds={query}&server_recorded_only=true"
        )
        data = fetch_with_retry(url, timeout=15)
        if data is None:
            raise Exception(f"Failed converting session chunk {i // chunk_size + 1}")
        mapping.update(data.get("matchIds", {}))
        print(f"  Chunk {i // chunk_size + 1}: converted {len(chunk)} session(s)")

    return mapping


def collect_event_windows() -> List[Dict[str, str]]:
    """Read one or more Event ID / Window ID pairs from the terminal. Blank eventId ends the loop."""
    print("\nEnter one event window per line. Press ENTER on a blank eventId when done.")
    print("Use this for multi-day tournaments: enter Day 1, then Day 2, etc.\n")

    events = []
    while True:
        idx = len(events) + 1
        event_id = input(f"  Event {idx} - eventId       (blank to finish): ").strip()
        if not event_id:
            break

        window_id = input(f"  Event {idx} - eventWindowId : ").strip()
        if not window_id:
            print("  windowId cannot be blank - skipping.")
            continue

        events.append({"eventId": event_id, "windowId": window_id})
        print()

    return events


def get_match_ids_from_event_windows(events: List[Dict[str, str]]) -> List[str]:
    """Resolve a list of {eventId, windowId} pairs into Osirion match IDs via sessionHistory."""
    all_session_ids = []
    seen_session_ids = set()

    print(f"\nCollected {len(events)} event window(s). Fetching session IDs...\n")
    for i, ev in enumerate(events, start=1):
        event_id = ev["eventId"]
        window_id = ev["windowId"]
        print(f"  [{i}/{len(events)}] {window_id} ({event_id})")

        try:
            session_ids = _get_leaderboard_session_ids(event_id, window_id)
        except Exception as e:
            print(f"    Failed to fetch sessions: {e}")
            session_ids = []

        for sid in session_ids:
            if sid not in seen_session_ids:
                seen_session_ids.add(sid)
                all_session_ids.append(sid)
        print()

    if not all_session_ids:
        print("No session IDs collected from those event/window pairs.")
        return []

    print(f"Converting {len(all_session_ids)} session ID(s) to Osirion match IDs...\n")
    try:
        mapping = _convert_sessions_to_match_ids(all_session_ids)
    except Exception as e:
        print(f"Osirion conversion failed: {e}")
        return []

    match_ids = []
    seen_match_ids = set()
    failed = 0

    for sid in all_session_ids:
        match_id = mapping.get(sid)
        if match_id:
            if match_id not in seen_match_ids:
                seen_match_ids.add(match_id)
                match_ids.append(match_id)
            print(f"  {sid}  ->  {match_id}")
        else:
            failed += 1
            print(f"  {sid}  ->  NOT FOUND (skipping)")

    if failed:
        print(f"\n  {failed} session(s) could not be converted and will be skipped.")

    print(f"\n{len(match_ids)} match ID(s) resolved from event/window pairs.\n")
    return match_ids


def collect_manual_match_ids(existing_ids: Optional[List[str]] = None) -> List[str]:
    """One match ID per line, blank line to finish. Skips duplicates already in existing_ids."""
    seen = set(existing_ids or [])
    collected = []
    while True:
        matchId = input("Enter a match ID or press Enter to exit:").strip()
        if matchId == "":
            break
        if matchId in seen:
            print("  Already added - skipping duplicate.")
            continue
        seen.add(matchId)
        collected.append(matchId)
    return collected


def get_match_ids() -> List[str]:
    """
    Top-level prompt: choose match IDs directly, event/window pairs, or both.
      1 - Match IDs directly: old flow, one per line, blank to finish.
      2 - Event ID + Window ID pairs: auto-resolves match IDs, then stops.
      3 - Both: resolves event/window pairs first, then also lets you add
          your own match IDs on top of the resolved ones.
    """
    print("\nHow would you like to choose matches?")
    print("  1 - Match IDs directly")
    print("  2 - Event ID + Window ID pairs (auto-resolves match IDs)")
    print("  3 - Both (event/window pairs, then add your own match IDs too)")

    while True:
        mode = input("\nChoice (1/2/3): ").strip()
        if mode in ("1", "2", "3"):
            break
        print("  Please enter 1, 2, or 3.")

    match_ids = []

    if mode in ("2", "3"):
        events = collect_event_windows()
        if events:
            match_ids.extend(get_match_ids_from_event_windows(events))
        else:
            print("No event/window pairs entered.")

    if mode in ("1", "3"):
        match_ids.extend(collect_manual_match_ids(existing_ids=match_ids))

    return match_ids


if __name__ == "__main__":
    matchIds = get_match_ids()

    if not matchIds:
        print("No match IDs to analyze. Exiting.")
    else:
        data = []  # each entry: (x, y, t, zoneCenterX, zoneCenterY, matchId, playerId)
        playerNamesById = {}
        for matchId in matchIds:
            game = Game(matchId)
            game.getZoneData()
            movementDatapoints = game.getMovementDatapoints()
            data.extend(movementDatapoints)
            playerNamesById.update(game.playerNames)
        displayPlot(data, playerNamesById)