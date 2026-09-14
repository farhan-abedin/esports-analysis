import os
from dotenv import load_dotenv

load_dotenv()

import requests
import matplotlib.pyplot as plt
import os
import json

def openJson(match_id):
    # Build file path to 'matches/match_id.json' in root directory
    file_path = os.path.join("matches1", f"{match_id}.json")

    # Check if file exists
    if not os.path.exists(file_path):
        return None

    # Open and read JSON
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data

def saveJson(match_id, data):
    # Ensure 'matches' folder exists
    os.makedirs("matches1", exist_ok=True)

    # Build file path
    file_path = os.path.join("matches", f"{match_id}.json")

    # Write JSON to file
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

api_token = os.environ["OSIRION_API_TOKEN"]
headers = {"Authorization": f"Bearer {api_token}"}

matchIds = []
while True:
    match_id = input("Enter match ID (or 'done' to finish, or 'removelast' to remove the last entered ID): ")
    if match_id.lower() == 'done' or match_id == '':
        break
    elif match_id.lower() == 'removelast':
        if matchIds:
            removed_id = matchIds.pop()
            print(f"Removed last match ID: {removed_id}")
        else:
            print("No match IDs to remove.")
    matchIds.append(match_id)

npcNameToMovementEvents = {}
for match_id in matchIds:
    data = openJson(match_id)
    if data is None:
        url = f"https://api.osirion.gg/fortnite/v1/matches/{match_id}/events?include=npcs,npcMovementEvents"
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Error fetching match data: {response.status_code} {response.text}")
        data = response.json()
        saveJson(match_id, data)

    npcIdToNpcName = {npc["npcId"]: npc["npcType"] for npc in data["npcs"]}
    sortedMovementEvents = sorted(data["npcMovementEvents"], key=lambda x: x["timestamp"])
    
    for event in sortedMovementEvents:
        npcId = event["npcId"]
        npcName = npcIdToNpcName.get(npcId, "Unknown NPC")
        npcNameToMovementEvents.setdefault(npcName, []).append(
            event["movementData"]["location"]
        )

print(npcNameToMovementEvents)

# Bug 1 fixed: single figure with correct figsize
fig, ax = plt.subplots(figsize=(10, 6))

img = plt.imread("background.jpg")
ax.imshow(img, extent=[-141373, 141373, -150048, 150048], zorder=0)

for npcName, locations in npcNameToMovementEvents.items():
    x_coords = [loc["x"] for loc in locations]
    y_coords = [-loc["y"] for loc in locations]
    ax.scatter(
        x_coords, y_coords,
        label=npcName,
        alpha=0.8,
        s=120,                  # much bigger markers
        edgecolors='white',     # white outline for contrast on any background
        linewidths=0.8,
        zorder=5                # guaranteed above the map image
    )

# Bug 3 fixed: all calls on ax, not plt
ax.legend()
ax.set_xlabel("X Coordinate")
ax.set_ylabel("Y Coordinate")
ax.set_title("All Movement Events of NPCs")
plt.show()