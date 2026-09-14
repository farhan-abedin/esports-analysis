import os
from dotenv import load_dotenv

load_dotenv()

import requests
import os
import json
import statistics
import re

api_token = os.environ["OSIRION_API_TOKEN"]
payload = {}
headers = {
    "Authorization": f"Bearer {api_token}"
}
global counterS
counterS = 1

class Game:
    def __init__(self, matchId):
        self.matchId = matchId
        self.data = self.fetchData()
        self.zoneTimings = self.getZoneTimings()

    def fetchData(self):
        data = openJson(self.matchId)
        if data is not None:
            print(f"Loaded data for match {self.matchId} from local cache.")
            return data
        url = f"https://api.osirion.gg/fortnite/v1/matches/{self.matchId}/events?include=playerInventoryUpdateEvents,safeZoneUpdateEvents,eliminationEvents"
        response = requests.get(url, headers=headers, data=payload)
        if response.status_code != 200:
            print(f"Error fetching data: {response.status_code}, {response.text}")
            counterS += 1
            print(f"Retrying... Attempt {counterS}")
            self.fetchData()
            return None
        data = response.json()
        saveJson(self.matchId, data)
        print(f"Fetched and saved data for match {self.matchId}.")
        return data
    
    def getZoneTimings(self):
        zoneTimings = []
        zoneData = self.data.get("safeZoneUpdateEvents", [])
        zoneData.sort(key=lambda x: x['currentPhase'])
        for zone in zoneData:
            try:
                phase = zone["currentPhase"]
            except:
                continue
            if phase == 12:
                break
            try:
                nextZone = zoneData[phase]
            except:
                nextZone = {"shrinkStartTime": zone["shrinkEndTime"]}         
            nextShrinkStart = nextZone["shrinkStartTime"]
            thisShrinkEnd = zone["shrinkEndTime"]
            if (nextShrinkStart - thisShrinkEnd) > 6000000: # should return 18 values
                zoneTimings.append(zone["shrinkStartTime"])
            zoneTimings.append(zone["shrinkEndTime"])
        return zoneTimings

    def getMaterialList(self, epicIds):
        materialList = []
        tempMaterials = {}
        for epicId in epicIds:
            tempMaterials[epicId] = [0,0,0]     
        inventoryUpdates = self.data.get("playerInventoryUpdateEvents", [])
        eliminations = self.data.get("eliminationEvents", [])
        events = inventoryUpdates + eliminations
        events.sort(key=lambda x: x["timestamp"])
        counter = 0
        slotNumbers = {}
        for epicId in epicIds:
            slotNumbers[epicId] = {"Wood":0, "Stone":0, "Metal":0}
        for event in events:
            currentZoneTime = self.zoneTimings[counter]
            if event["timestamp"] > currentZoneTime:
                totalMats = matAdder(tempMaterials)
                materialList.append(totalMats)
                counter += 1
                if counter >= len(self.zoneTimings):
                    break
            else:
                if "targetId" in event:
                    if event["targetId"] in epicIds:
                        tempMaterials[event["targetId"]] = [0,0,0]
                        continue
                if "itemId" in event and event["epicId"] in epicIds:
                    if "Wood" in event["itemId"] or event["slot"] == slotNumbers[event["epicId"]]["Wood"]:
                        tempMaterials[event["epicId"]][0] = event["count"]
                        slotNumbers[event["epicId"]]["Wood"] = event["slot"]
                    elif "Stone" in event["itemId"] or event["slot"] == slotNumbers[event["epicId"]]["Stone"]:
                        tempMaterials[event["epicId"]][1] = event["count"]
                        slotNumbers[event["epicId"]]["Stone"] = event["slot"]
                    elif "Metal" in event["itemId"] or event["slot"] == slotNumbers[event["epicId"]]["Metal"]:
                        tempMaterials[event["epicId"]][2] = event["count"]
                        slotNumbers[event["epicId"]]["Metal"] = event["slot"]
        return materialList 



        
def matAdder(materials):
    total = 0
    for list in materials.values():
        total += sum(list)
    return int(round(total/10,0))



def openJson(match_id):
    # Build file path to 'matches/match_id.json' in root directory
    file_path = os.path.join("matches", f"{match_id}.json")

    # Check if file exists
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
    
def getIds():
    title = input("What would you like this file to be titled?")
    matchIds = []
    while True:
        matchId = input("Enter match ID, press Enter when you are done: ")
        if matchId:
            matchIds.append(matchId)
        else:
            break
    epicIds = []
    while True:
        epicId = input("Enter epic ID of the team to analyse, press Enter when you are done: ")
        if epicId:
            epicIds.append(epicId)
        else:
            break
    epicIds.sort()
    return title, matchIds, epicIds

def writeToFile(finalList, title):
    """
    Writes game zone data to a neatly aligned text file inside an 'outputs' folder.
    Includes:
      - Title
      - Column headers
      - One row per game
      - Average usage row (avg change between columns)
      - Mean and median rows for each column
    File name will be based on the title.
    """
    # Ensure outputs folder exists
    os.makedirs("outputs", exist_ok=True)
    
    # Sanitize title to be a safe file name
    safe_title = re.sub(r'[\\/*?:"<>|]', "_", title)
    
    # File path
    output_file = os.path.join("outputs", f"{safe_title}.txt")
    
    # Find the maximum number of columns across all games
    max_cols = max(len(row) for row in finalList) if finalList else 0
    
    # Build column headers
    headers = ["Game number", "Zone 1 Closing"]
    for zone in range(2, 8):  # Zones 2–8 have both Revealed + Closing
        headers.append(f"Zone {zone} Revealed")
        headers.append(f"Zone {zone} Closing")
    headers.append("Zone 8 Revealed")  # Zone 9 only has revealed
    for zone in range(9, 13):  # Zones 10–12 revealed only
        headers.append(f"Zone {zone} Revealed")
    
    # Trim headers to match actual data width
    headers = headers[:max_cols + 1]  # +1 for game number column
    
    # Create all rows of data
    all_rows = []
    
    # Add header row
    all_rows.append(headers)
    
    # Add game data rows
    for game_num, values in enumerate(finalList, start=1):
        row_data = [str(game_num)] + [str(round(v)) for v in values]
        all_rows.append(row_data)
    
    # Calculate average usage row
    avg_usage = ["Average Usage"]
    for col in range(1, max_cols):
        # Only include rows that have both col and col-1, and exclude 0 differences
        diffs = [row[col] - row[col - 1] for row in finalList if len(row) > col]
        diffs = [d for d in diffs if d != 0]  # Exclude 0 values
        if diffs:
            avg_usage.append(str(round(sum(diffs) / len(diffs))))
        else:
            avg_usage.append("N/A")
    all_rows.append(avg_usage)
    
    # Calculate mean row
    means = ["Mean"]
    for col in range(max_cols):
        col_vals = [row[col] for row in finalList if len(row) > col]
        if col_vals:
            means.append(str(round(statistics.mean(col_vals))))
        else:
            means.append("N/A")
    all_rows.append(means)
    
    # Calculate median row
    medians = ["Median"]
    for col in range(max_cols):
        col_vals = [row[col] for row in finalList if len(row) > col]
        if col_vals:
            medians.append(str(round(statistics.median(col_vals))))
        else:
            medians.append("N/A")
    all_rows.append(medians)
    
    # Calculate column widths based on all data
    col_widths = []
    for col_idx in range(len(headers)):
        max_width = 0
        for row in all_rows:
            if col_idx < len(row):
                max_width = max(max_width, len(str(row[col_idx])))
        col_widths.append(max_width)
    
    # Write to file
    with open(output_file, "w") as f:
        # Write the title
        f.write(f"{title}\n\n")
        
        # Write all rows with proper alignment
        for row in all_rows:
            formatted_row = []
            for col_idx, cell in enumerate(row):
                if col_idx < len(col_widths):
                    formatted_row.append(f"{str(cell):<{col_widths[col_idx]}}")
                else:
                    formatted_row.append(str(cell))
            f.write("  ".join(formatted_row) + "\n")
    
    print(f"Output written to: {output_file}")


if __name__ == "__main__":  
    finalList = []
    title, matchIds, epicIds = getIds()
    for matchId in matchIds:
        game = Game(matchId)
        materialList = game.getMaterialList(epicIds)
        if materialList:
            finalList.append(materialList)
    if finalList:
        writeToFile(finalList, title)
    


