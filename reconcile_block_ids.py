# Built-in modules
import csv, json, os, sys, threading, time

# Third-party modules
import requests as r

if not os.path.isdir(sys.argv[1]):
    raise SystemExit("Usage: python main.py <gtfs_directory>")
os.chdir(os.path.dirname(os.path.abspath(__file__)))

gtfs_file = lambda f: open(os.path.join(sys.argv[1], f + ".txt"))

base64_chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz|~" # Sortable by ASCII order



with gtfs_file("calendar") as f:
    # TODO: Check if start_date could be different for weekday, sat, and sun services
    start_date = next(csv.DictReader(f))["start_date"]
    start_date = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}" # Convert from YYYYMMDD to YYYY-MM-DD
    wtlive_url = f'https://www.wtlivewpg.com/Pages/Tracker/Stops/{start_date}/%stop.txt'
    print("Using WTLive URL", wtlive_url)

# TODO: Update if WTLive changes their CSV format
wtlive_header = ("block_id", "route_id", object(), object(), "arrival_time", object(), "service_id")



trips = {}

def fetch_wtlive(stop_id):
    resp = r.get(wtlive_url.replace("%stop", str(stop_id))).text
    for row in csv.DictReader(resp.splitlines(), fieldnames=wtlive_header):
        compressed_id = ""
        quot = stop_id
        for _ in range(3): # 3 base64 characters covers 2^18 = 262144 numbers, larger than 5-digit stop IDs
            quot, rem = divmod(quot, 64)
            compressed_id = base64_chars[rem] + compressed_id

        compressed_id += f'{row["service_id"]}{row["route_id"]}'

        hour, minute, second = map(int, row["arrival_time"].split(":"))
        if hour <= 3: # Previous service day
            hour += 24
        compressed_id += "".join(base64_chars[i] for i in (hour, minute, second))

        if compressed_id in trips:
            raise ValueError(f"Duplicate trip ID {compressed_id} for stop {stop_id}")
        trips[compressed_id] = row["block_id"]
    print("*", end="", flush=True)

with open("selected_stops.txt") as f:
    threads = []
    for line in f:
        stop_id = int(line.strip().split()[0])
        t = threading.Thread(target=fetch_wtlive, args=(stop_id,))
        threads.append(t)
        t.start()
    while threads:
        threads = [t for t in threads if t.is_alive()]
        time.sleep(0.1)

print()
with open("block_ids.csv", "w") as f:
    writer = csv.writer(f)
    writer.writerow(("trip", "block_id"))
    for trip in sorted(trips):
        writer.writerow((trip, trips[trip]))