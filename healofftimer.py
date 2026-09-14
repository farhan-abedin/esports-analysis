import os
from dotenv import load_dotenv

load_dotenv()

import requests

api_token = os.environ["OSIRION_API_TOKEN"]
payload={}
headers = {
    "Authorization": f"Bearer {api_token}"
}

matchIds = []
while True:
    match_id = input("Enter match ID (or 'done' to finish): ")
    if match_id.lower() == 'done':
        break
    matchIds.append(match_id)

latestDeath = 0
beforeClosing = 0
tenSecondHealoffs = 0
tenToThirtySecondHealoffs = 0
thirtyToFiftySecondHealoffs = 0
sicknessHealoffs = 0
games = 0
elimsOfWinner = []
levelOfWinner = []
lowestLevelOfWinner = 999
lowestLevelWinner = ""
for match_id in matchIds:
    games += 1
    zone12Time = 0
    secondPlaceTeam = []
    url = f"https://api.osirion.gg/fortnite/v1/matches/{match_id}/events?include=safeZoneUpdateEvents,eliminationEvents,players"
    response = requests.get(url, headers=headers, data=payload)
    if response.status_code != 200:
        raise Exception(f"Error fetching match data: {response.status_code} {response.text}")
    data = response.json()

    zoneData = data["safeZoneUpdateEvents"]
    for zone in zoneData:
        if zone["currentPhase"] == 12:
            zone12Time = zone["shrinkEndTime"]
    for player in data["players"]:
        if player["placement"] == 1:
            elimsOfWinner.append(player["teamEliminations"])
            levelOfWinner.append(player["level"])
            if player["level"] < lowestLevelOfWinner:
                lowestLevelOfWinner = player["level"]
                lowestLevelWinner = player["epicId"]
        if player["placement"] == 2:
            secondPlaceTeam.append(player["epicId"])
    print(secondPlaceTeam)
    eliminationData = data["eliminationEvents"]
    eliminationData.sort(key=lambda x: x["timestamp"])  # Sort eliminations by time
    for elimination in eliminationData:
        if elimination["targetId"] in secondPlaceTeam:
            latestDeath = elimination["timestamp"]
            print(latestDeath)
    healoffLength = (latestDeath - zone12Time) / 1000
    print(healoffLength)
    if healoffLength <= 0:
        beforeClosing += 1
    elif healoffLength <= 10:
        tenSecondHealoffs += 1
    elif healoffLength <= 30:
        tenToThirtySecondHealoffs += 1
    elif healoffLength <= 50:
        thirtyToFiftySecondHealoffs += 1
    else:
        sicknessHealoffs += 1
print(f"Total games analyzed: {games}")
print(f"Healoffs ended before zone closed: {beforeClosing}")
print(f"Healoffs lasting up to 10 seconds: {tenSecondHealoffs}")
print(f"Healoffs lasting 10 to 30 seconds: {tenToThirtySecondHealoffs}")
print(f"Healoffs lasting 30 to 50 seconds: {thirtyToFiftySecondHealoffs}")
print(f"Healoffs lasting over 50 seconds (sickness): {sicknessHealoffs}")
print(f"Average eliminations of winning team: {sum(elimsOfWinner)/len(elimsOfWinner)}")
print(f"Average level of winning player: {sum(levelOfWinner)/len(levelOfWinner)}")
print(f"Lowest level winner: {lowestLevelWinner} with level {lowestLevelOfWinner}")

    
    