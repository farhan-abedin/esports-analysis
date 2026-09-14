"""
Placement vs Net Damage Distribution Graph
──────────────────────────────────────────
Plots team placement against cumulative net damage.

  1 game  → scatter plot  (one point per team)
  N games → box plot      (range, IQR, median, and mean via diamond marker)

* Hides range whiskers/caps for placements 25-30, 31-35, and below.
* Uses fixed, uniform y-axis boundaries (-300 to 1000) for stable timeline scrubbing.
* Hovering over a box plot reveals Mean and Median next to your cursor.
* Clicking a box plot bucket outputs raw team breakdowns to the console.
* Bucket size can be changed live with an integer slider.
"""
import os
from dotenv import load_dotenv

load_dotenv()


# ═══════════════════════════════════════════════════════════
# CONFIG  — edit these to match your setup
# ═══════════════════════════════════════════════════════════

API_TOKEN   = os.environ["OSIRION_API_TOKEN"]
CACHE_DIR   = "matchesForPlacement"        
BUCKET_SIZE = 5               # default starting bucket size
MIN_BUCKET_SIZE = 1
MAX_BUCKET_SIZE = 30

GAME_MODE_BR = [
    (180,     85),   # Zone 1: reveal, shrink
    ( 60,     90),   # Zone 2
    ( 50,      100),   # Zone 3
    ( 70,      85),   # Zone 4
    ( 40,      70),   # Zone 5
    ( 40,      70),   # Zone 6
    ( 35,      60),   # Zone 7
    ( 20,      60),   # Zone 8
    (  0,      250),   # Zone 9
]


ZONE_COLORS = [
    "#27ae60", "#2ecc71", "#f1c40f", "#e67e22", "#e74c3c", 
    "#c0392b", "#8e44ad", "#6c3483", "#4a235a"
]

# ═══════════════════════════════════════════════════════════
# IMPORTS
# ═══════════════════════════════════════════════════════════

import bisect
import json
import math
import os
import time

import numpy as np
import requests
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.widgets as mwidgets
from matplotlib.ticker import MaxNLocator

# ═══════════════════════════════════════════════════════════
# API / CACHE
# ═══════════════════════════════════════════════════════════

def _api_get(url, headers, **kwargs):
    try:
        r = requests.get(url, headers=headers, **kwargs)
        if r.status_code == 401:
            print("  ⚠️  Got 401 — retrying once…")
            time.sleep(0.5)
            r = requests.get(url, headers=headers, **kwargs)
        return r
    except requests.RequestException as exc:
        raise exc


def fetch_match_data(match_id):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{match_id}.json")

    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "knockedDownEvents" in data:
            print(f"  Base data pulled from cache: {match_id}")
            return data

    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    url = (
        f"https://api.osirion.gg/fortnite/v1/matches/{match_id}/events"
        "?include=safeZoneUpdateEvents,fireWeaponEvents,players,"
        "eliminationEvents,rebootEvents,knockedDownEvents,playerRespawnEvents"
    )
    print(f"  🌐 Fetching target dataset: {match_id}…", flush=True)
    t0 = time.time()
    r = _api_get(url, headers=headers, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"API error {r.status_code}: {r.text[:200]}")
    data = r.json()

    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, allow_nan=True)
    except Exception as exc:
        print(f"  ⚠️ Cache generation fault: {exc}")

    return data

# ═══════════════════════════════════════════════════════════
# DATA EXTRACTION
# ═══════════════════════════════════════════════════════════

def extract_game(raw):
    players   = raw.get("players", [])
    shots     = raw.get("fireWeaponEvents", [])
    zone_data = raw.get("safeZoneUpdateEvents", [])

    z1 = next((z for z in zone_data if z.get("currentPhase") == 1), None)
    if z1 is None:
        print("  ⚠️ No zone-1 tracking data — skipping step.")
        return None
    zone1_start = z1["shrinkStartTime"]

    squads      = {}   
    squad_names = {}   
    placement   = {}   

    for p in players:
        if p.get("isBot", False) or "athena" in p.get("epicId", ""):
            continue
        sid = p["playerSquadId"]
        eid = p["epicId"]
        plc = p.get("placement", 9999)
        
        if plc <= 0:
            continue
            
        squads.setdefault(sid, []).append(eid)
        squad_names.setdefault(sid, []).append(p.get("epicUsername", eid))
        placement[sid] = plc    

    if not squads:
        print("  ⚠️ Human target arrays evaluated empty — skipping.")
        return None

    player_to_squad = {eid: sid for sid, eids in squads.items() for eid in eids}
    raw_events = {sid: [] for sid in squads}

    for shot in shots:
        if not shot.get("hitPlayer", False):
            continue
        dmg    = float(shot.get("actualDamage", 0))
        rel_ts = shot.get("timestamp", 0) - zone1_start

        shooter_sq = player_to_squad.get(shot.get("epicId",    ""))
        target_sq  = player_to_squad.get(shot.get("hitEpicId", ""))

        if shooter_sq is not None:
            raw_events[shooter_sq].append((rel_ts, +dmg))
        if target_sq is not None:
            raw_events[target_sq].append((rel_ts, -dmg))

    squad_data  = {}
    all_rel_ts  = []

    for sid, evts in raw_events.items():
        evts.sort(key=lambda x: x[0])
        ts_arr = [e[0] for e in evts]
        deltas = [e[1] for e in evts]

        prefix = [0.0] * (len(deltas) + 1)
        for i, d in enumerate(deltas):
            prefix[i + 1] = prefix[i] + d

        squad_data[sid] = {"ts": ts_arr, "prefix": prefix}
        all_rel_ts.extend(ts_arr)

    min_rel_s = math.floor(min(all_rel_ts) / 1_000_000) if all_rel_ts else -30
    max_rel_s = math.ceil( max(all_rel_ts) / 1_000_000) if all_rel_ts else 600

    return {
        "team_placement": placement,
        "squads":         squad_data,
        "squad_names":    squad_names,
        "min_rel_s":      min_rel_s,
        "max_rel_s":      max_rel_s,
    }


def _net_damage_at(squad, cutoff_us):
    idx = bisect.bisect_right(squad["ts"], cutoff_us)
    return squad["prefix"][idx]


def load_games(match_ids):
    games = []
    for mid in match_ids:
        try:
            raw  = fetch_match_data(mid)
            game = extract_game(raw)
            if game is not None:
                games.append(game)
        except Exception as exc:
            print(f"  ❌ Initialization error on {mid}: {exc}")
    return games

# ═══════════════════════════════════════════════════════════
# PLOT DATA BUILDERS
# ═══════════════════════════════════════════════════════════

def _bucket_start(plc, bucket_size):
    return ((plc - 1) // bucket_size) * bucket_size + 1


def _bucket_label(bs, bucket_size):
    return f"{bs}–{bs + bucket_size - 1}"


def build_scatter_data(game, cutoff_us):
    placements, net_dmgs, team_labels = [], [], []
    for sid, squad in game["squads"].items():
        plc = game["team_placement"].get(sid, 9999)
        if plc == 9999:
            continue
        placements.append(plc)
        net_dmgs.append(_net_damage_at(squad, cutoff_us))
        names = game.get("squad_names", {}).get(sid, [])
        team_labels.append("\n".join(names) if names else f"Squad {sid}")
    return placements, net_dmgs, team_labels


def build_box_data(games, cutoff_us, bucket_size):
    bucket_details = {}   

    for game in games:
        for sid, squad in game["squads"].items():
            plc = game["team_placement"].get(sid, 9999)
            if plc == 9999:
                continue
                
            if 45 <= plc <= 50:
                continue
                
            bs = _bucket_start(plc, bucket_size)
            net_dmg = _net_damage_at(squad, cutoff_us)
            names = game.get("squad_names", {}).get(sid, [])
            team_label = ", ".join(names) if names else f"Squad {sid}"
            
            bucket_details.setdefault(bs, []).append({
                "net_dmg": net_dmg,
                "label": team_label
            })

    sorted_bs = sorted(bucket_details.keys())
    labels   = [_bucket_label(bs, bucket_size) for bs in sorted_bs]
    datasets = [[item["net_dmg"] for item in bucket_details[bs]] for bs in sorted_bs]
    return labels, datasets, sorted_bs, bucket_details

# ═══════════════════════════════════════════════════════════
# TIMELINE / ZONE GENERATION
# ═══════════════════════════════════════════════════════════

def compute_zone_bands():
    bands = []
    cursor = 0  
    for i, (revealed, shrink) in enumerate(GAME_MODE_BR):
        zone_num = i + 1
        color    = ZONE_COLORS[min(i, len(ZONE_COLORS) - 1)]
        if zone_num == 1:
            if revealed > 0:
                bands.append({"start_s": -revealed, "end_s": 0, "zone": 1, "phase": "revealed", "color": color, "alpha": 0.25})
            bands.append({"start_s": 0, "end_s": shrink, "zone": 1, "phase": "shrink", "color": color, "alpha": 0.55})
            cursor = shrink
        else:
            if revealed > 0:
                bands.append({"start_s": cursor, "end_s": cursor + revealed, "zone": zone_num, "phase": "revealed", "color": color, "alpha": 0.25})
                cursor += revealed
            bands.append({"start_s": cursor, "end_s": cursor + shrink, "zone": zone_num, "phase": "shrink", "color": color, "alpha": 0.55})
            cursor += shrink
    return bands


def _zone_at_time(bands, rel_s):
    for b in bands:
        if b["start_s"] <= rel_s < b["end_s"]:
            return b["zone"], b["phase"]
    return None, None

# ═══════════════════════════════════════════════════════════
# STYLING
# ═══════════════════════════════════════════════════════════

_BG      = "#1a1a2e"
_PANEL   = "#16213e"
_SPINE   = "#404060"
_GRID    = "#2a3a5a"
_WHITE   = "#e0e0e0"
_MUTED   = "#7788aa"
_POS     = "#00c2d4"   
_NEG     = "#ff5e5e"   
_ZERO    = "#ff7070"   


def _style_ax(ax, xlabel, ylabel, title):
    ax.set_facecolor(_PANEL)
    for sp in ax.spines.values():
        sp.set_edgecolor(_SPINE)
    ax.tick_params(colors=_WHITE, labelsize=9)
    ax.set_xlabel(xlabel, color=_WHITE, fontsize=10)
    ax.set_ylabel(ylabel, color=_WHITE, fontsize=10)
    ax.set_title(title, color=_WHITE, fontsize=12, pad=8)
    ax.grid(axis="y", color=_GRID, linewidth=0.5, alpha=0.7)
    ax.axhline(0, color=_ZERO, linewidth=0.8, linestyle="--", alpha=0.55)


def _fmt_time(rel_s, zone_bands):
    if rel_s == 0:
        base = "t = 0s   (zone 1 shrink start)"
    else:
        a, mm = abs(rel_s), abs(rel_s) // 60
        ss    = a % 60
        ts    = f"{mm}m {ss:02d}s" if mm else f"{ss}s"
        base = f"t = {'+' if rel_s > 0 else '−'}{ts}   ({'after' if rel_s > 0 else 'before'} zone 1 shrink start)"

    zone_num, phase = _zone_at_time(zone_bands, rel_s)
    if zone_num is not None:
        base += f"   ·   Zone {zone_num} {'shrinking' if phase == 'shrink' else 'revealed'}"
    return base


def _draw_zone_bands_on_slider(ax_slider, zone_bands, slider_min, slider_max):
    slider_range = slider_max - slider_min
    if slider_range <= 0:
        return
    prev_end = None
    for b in zone_bands:
        s, e = max(b["start_s"], slider_min), min(b["end_s"], slider_max)
        if s >= e:
            continue
        ax_slider.axvspan(s, e, facecolor=b["color"], alpha=b["alpha"], zorder=0)
        if prev_end is not None and prev_end == s:
            ax_slider.axvline(s, color="#ffffff44", linewidth=0.6, zorder=2)
        prev_end = e
        if (e - s) / slider_range < 0.02:
            continue
        ax_slider.text((s + e) / 2, 0.50, f"{b['zone']}·{'R' if b['phase'] == 'revealed' else 'S'}",
                       transform=ax_slider.get_xaxis_transform(), ha="center", va="center",
                       fontsize=7, fontweight="bold", color="#ffffffcc", zorder=5)

# ═══════════════════════════════════════════════════════════
# RUN INTERACTIVE CANVAS
# ═══════════════════════════════════════════════════════════

def run_graph(games, match_ids):
    if not games:
        print("❌ Data validation parameters failed.")
        return

    is_single  = len(games) == 1
    min_rel_s  = min(g["min_rel_s"] for g in games)
    max_rel_s  = max(g["max_rel_s"] for g in games)
    zone_bands = compute_zone_bands()

    graph_title = (
        f"Placement vs Net Damage Distribution   —   Game: {match_ids[0][:14]}…"
        if is_single
        else f"Placement Distributions vs Net Damage   —   {len(games)} Loaded Matches"
    )
    y_label = "Net Damage (Dealt − Taken)"

    fig, ax = plt.subplots(figsize=(13, 6))
    fig.patch.set_facecolor(_BG)
    plt.subplots_adjust(left=0.09, right=0.97, top=0.91, bottom=0.31 if not is_single else 0.25)

    ax_slider = fig.add_axes([0.12, 0.085, 0.76, 0.045], facecolor="#0a0a1a")
    for sp in ax_slider.spines.values():
        sp.set_edgecolor(_SPINE)
        sp.set_linewidth(0.5)

    slider = mwidgets.Slider(ax_slider, label="", valmin=min_rel_s, valmax=max_rel_s, valinit=0, valstep=1, color="#e94560")
    slider.poly.set_alpha(0.15)
    slider.poly.set_zorder(1)
    slider.valtext.set_color(_WHITE)
    slider.valtext.set_fontsize(9)

    bucket_slider = None
    if not is_single:
        ax_bucket = fig.add_axes([0.12, 0.165, 0.76, 0.035], facecolor="#0a0a1a")
        for sp in ax_bucket.spines.values():
            sp.set_edgecolor(_SPINE)
            sp.set_linewidth(0.5)

        bucket_slider = mwidgets.Slider(
            ax_bucket,
            label="Bucket size",
            valmin=MIN_BUCKET_SIZE,
            valmax=MAX_BUCKET_SIZE,
            valinit=BUCKET_SIZE,
            valstep=1,
            color=_POS
        )
        bucket_slider.label.set_color(_WHITE)
        bucket_slider.label.set_fontsize(9)
        bucket_slider.valtext.set_color(_WHITE)
        bucket_slider.valtext.set_fontsize(9)

    _draw_zone_bands_on_slider(ax_slider, zone_bands, min_rel_s, max_rel_s)

    fig.text(0.12, 0.050, "◀   before zone 1", color=_MUTED, fontsize=8, ha="left")
    fig.text(0.88, 0.050, "after zone 1   ▶",  color=_MUTED, fontsize=8, ha="right")
    time_txt = fig.text(0.5, 0.028, _fmt_time(0, zone_bands), color=_WHITE, fontsize=10, ha="center")

    hover_state = {
        "scatter": None, "labels": [], "placements": [], "net_dmgs": [],
        "box_labels": [], "box_datasets": []
    }
    click_state = {"sorted_bs": [], "bucket_details": {}, "current_time_str": "", "bucket_size": BUCKET_SIZE}

    annot = ax.annotate("", xy=(0, 0), xytext=(14, 14), textcoords="offset points", fontsize=8.5,
                        color=_WHITE, bbox=dict(boxstyle="round,pad=0.45", fc="#16213eee", ec=_SPINE, lw=0.7),
                        arrowprops=dict(arrowstyle="->", color=_SPINE, lw=0.8), zorder=10, visible=False)

    def _on_hover(event):
        if event.inaxes != ax or event.xdata is None or event.ydata is None:
            if annot.get_visible():
                annot.set_visible(False)
                fig.canvas.draw_idle()
            return

        if is_single:
            sc = hover_state["scatter"]
            if sc is None: return
            cont, ind = sc.contains(event)
            if cont:
                idx = ind["ind"][0]
                px, py = hover_state["placements"][idx], hover_state["net_dmgs"][idx]
                annot.xy = (px, py)
                annot.set_text(f"#{px}   |   Net: {py:+,.0f}\n{hover_state['labels'][idx]}")
                annot.set_visible(True)
            else:
                if annot.get_visible(): annot.set_visible(False)
        else:
            idx = int(np.round(event.xdata))
            box_labels = hover_state.get("box_labels", [])
            box_datasets = hover_state.get("box_datasets", [])
            
            if 0 <= idx < len(box_labels) and abs(event.xdata - idx) < 0.35:
                dataset = box_datasets[idx]
                if dataset:
                    box_mean = np.mean(dataset)
                    box_median = np.median(dataset)
                    
                    annot.xy = (event.xdata, event.ydata)
                    annot.set_text(
                        f"Range Block: {box_labels[idx]}\n"
                        f"───────────────────\n"
                        f"Mean Damage:   {box_mean:+,.0f}\n"
                        f"Median Damage: {box_median:+,.0f}"
                    )
                    annot.set_visible(True)
                else:
                    if annot.get_visible(): annot.set_visible(False)
            else:
                if annot.get_visible(): annot.set_visible(False)
                
        fig.canvas.draw_idle()

    def _on_click(event):
        if is_single or event.inaxes != ax or event.xdata is None:
            return
        
        idx = int(np.round(event.xdata))
        sorted_bs = click_state.get("sorted_bs", [])
        
        if 0 <= idx < len(sorted_bs):
            bs = sorted_bs[idx]
            bucket_size = click_state.get("bucket_size", BUCKET_SIZE)
            label = _bucket_label(bs, bucket_size)
            details = click_state["bucket_details"].get(bs, [])
            
            print(f"\n📊 RAW TEAMS & DAMAGES INSIDE BUCKET [{label}]  ({click_state['current_time_str']})")
            print("─" * 70)
            
            sorted_details = sorted(details, key=lambda x: x["net_dmg"], reverse=True)
            for item in sorted_details:
                print(f"  • {item['label']:<48} | Net Damage: {item['net_dmg'] :+,.0f}")
            print("─" * 70)

    fig.canvas.mpl_connect("motion_notify_event", _on_hover)
    fig.canvas.mpl_connect("button_press_event", _on_click)

    def redraw(rel_s=None):
        if rel_s is None:
            rel_s = int(slider.val)
        else:
            rel_s = int(rel_s)

        bucket_size = int(bucket_slider.val) if bucket_slider is not None else BUCKET_SIZE
        x_label = "Placement Range" if is_single else f"Placement Bucket Ranges (Groups of {bucket_size})"

        cutoff_us = rel_s * 1_000_000
        ax.cla()
        _style_ax(ax, x_label, y_label, graph_title)

        nonlocal annot
        annot = ax.annotate("", xy=(0, 0), xytext=(14, 14), textcoords="offset points", fontsize=8.5,
                            color=_WHITE, bbox=dict(boxstyle="round,pad=0.45", fc="#16213eee", ec=_SPINE, lw=0.7),
                            arrowprops=dict(arrowstyle="->", color=_SPINE, lw=0.8), zorder=10, visible=False)

        time_str = _fmt_time(rel_s, zone_bands)
        click_state["current_time_str"] = time_str

        if is_single:
            placements, net_dmgs, labels = build_scatter_data(games[0], cutoff_us)
            if not placements:
                hover_state["scatter"] = None
                time_txt.set_text(time_str)
                fig.canvas.draw_idle()
                return

            colors = [_POS if nd >= 0 else _NEG for nd in net_dmgs]
            sc = ax.scatter(placements, net_dmgs, c=colors, s=90, alpha=0.90, zorder=3, edgecolors="#ffffff28", linewidths=0.5)
            ax.set_xlim(0.5, max(placements) + 0.5)
            ax.xaxis.set_major_locator(MaxNLocator(integer=True))

            hover_state.update({"scatter": sc, "labels": labels, "placements": placements, "net_dmgs": net_dmgs})

        else:
            hover_state["scatter"] = None   
            labels, datasets, sorted_bs, bucket_details = build_box_data(games, cutoff_us, bucket_size)
            
            click_state["sorted_bs"] = sorted_bs
            click_state["bucket_details"] = bucket_details
            click_state["bucket_size"] = bucket_size
            hover_state.update({"box_labels": labels, "box_datasets": datasets})
            
            if not labels:
                time_txt.set_text(time_str)
                fig.canvas.draw_idle()
                return

            bp = ax.boxplot(
                datasets,
                positions=range(len(labels)),
                patch_artist=True,
                showmeans=True,
                boxprops=dict(facecolor="#2a4365", color="#63b3ed", alpha=0.95, linewidth=1.2),
                whiskerprops=dict(color="#a0aec0", linestyle="-", linewidth=1.2),
                capprops=dict(color="#a0aec0", linewidth=1.2),
                medianprops=dict(color="#e94560", linewidth=2.2), 
                meanprops=dict(marker="D", markerfacecolor=_POS, markeredgecolor="none", markersize=6), 
                flierprops=dict(marker="o", markerfacecolor=_NEG, markeredgecolor="none", markersize=4, alpha=0.6)
            )
            
            for i, bs in enumerate(sorted_bs):
                if bs + bucket_size - 1 >= 25:
                    bp['whiskers'][2 * i].set_visible(False)
                    bp['whiskers'][2 * i + 1].set_visible(False)
                    bp['caps'][2 * i].set_visible(False)
                    bp['caps'][2 * i + 1].set_visible(False)
            
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, color=_WHITE, fontsize=9)
            ax.set_xlim(-0.5, len(labels) - 0.5)

        # ── FIXED VISUAL MATRIX WINDOW ──
        ax.set_ylim(-300, 600)

        time_txt.set_text(time_str)
        fig.canvas.draw_idle()

    redraw(0)
    slider.on_changed(lambda v: redraw(int(v)))
    if bucket_slider is not None:
        bucket_slider.on_changed(lambda v: redraw())
    plt.show()

# ═══════════════════════════════════════════════════════════
# SYSTEM INITIALIZATION ENTRY
# ═══════════════════════════════════════════════════════════

def get_match_ids():
    print("Enter Osirion match IDs one per line.   Blank line when done.\n")
    match_ids, seen = [], set()
    while True:
        mid = input(f"   Match ID {len(match_ids) + 1} (blank to finish): ").strip()
        if not mid:
            if not match_ids:
                print("No IDs entered. Exiting.")
                exit(0)
            break
        if mid in seen:
            print("   ⚠️   Duplicate identifier detected — skipping loop line.")
            continue
        seen.add(mid)
        match_ids.append(mid)
    print(f"\n✅ {len(match_ids)} match ID(s) ready.\n")
    return match_ids


if __name__ == "__main__":
    match_ids = get_match_ids()
    print("Loading match data…\n")
    games = load_games(match_ids)
    print(f"\n✅ {len(games)}/{len(match_ids)} game(s) loaded successfully.\n")
    run_graph(games, match_ids)