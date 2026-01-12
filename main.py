import csv, json, os, sys

if not os.path.isdir(sys.argv[1]):
    raise SystemExit("Usage: python main.py <gtfs_directory>")
os.chdir(os.path.dirname(os.path.abspath(__file__)))

gtfs_file = lambda f: open(os.path.join(sys.argv [1], f + ".txt"))

trip_stops = {}
with gtfs_file("stop_times") as f:
    for row in csv.DictReader(f):
        trip_stops.setdefault(row["trip_id"], []).append((row["stop_id"], int(row["stop_sequence"])))

unique_trips = {tuple(i for i, _ in sorted(stops, key=lambda x: x[1])): trip_id for trip_id, stops in trip_stops.items()}
unique_trips = {v: k[1:-1] for k, v in unique_trips.items()} # Remove first and last stops because their arrival times are often inaccurate
all_unique_trips = unique_trips.copy() # Save for later use
print(len(unique_trips), "unique trips")



for trip_id, stops in tuple(unique_trips.items()):
    if trip_id not in unique_trips: # already removed
        continue
    for i, j in tuple(unique_trips.items()):
        if i == trip_id:
            continue
        for k in range(len(j)):
            if j[k] == stops[0] and j[k:k+len(stops)] == stops: # find sublist
                unique_trips.pop(i)

print(len(unique_trips), "unique trips after removing sublists of longer trips")



named_unique_trips = {}
with gtfs_file("trips") as f:
    for row in csv.DictReader(f):
        if row["trip_id"] in unique_trips:
            named_unique_trips [f'{row["route_id"]} {row["trip_headsign"]} {row["shape_id"]}'.strip()] = unique_trips[row["trip_id"]]
        if row["trip_id"] in all_unique_trips:
            all_unique_trips[f'{row["route_id"]} {row["trip_headsign"]} {row["shape_id"]}'.strip()] = all_unique_trips[row["trip_id"]]
            all_unique_trips.pop(row["trip_id"], None)
len_trips = len(named_unique_trips) # Used later for assertions
assert len_trips == len(unique_trips), f"Expected {len(unique_trips)} unique trips, found {len_trips}"
assert len(set(named_unique_trips.keys())) == len_trips, "Expected unique trip names"

stop_trips = {}
with gtfs_file("stops") as f:
    for row in csv.DictReader(f):
        lines = frozenset((i for i, stops in named_unique_trips.items() if row["stop_id"] in stops))
        if len (lines) > 1:
            stop_trips[lines] = row["stop_id"]
stop_trips = {v: k for k, v in stop_trips.items()}
print(len(stop_trips), "stops served a unique set of more than one line")



for stop_id, lines in tuple(stop_trips.items()): # Remove stops served by a subset of another stop's lines
    if any((lines <= i for j, i in stop_trips.items() if j != stop_id)):
        stop_trips.pop(stop_id)

if len(frozenset.union(*stop_trips.values())) != len_trips: # Some lines may lose coverage, add them back
    for i in frozenset(named_unique_trips.keys()) - frozenset.union(*stop_trips.values()):
        stop = named_unique_trips[i][-1] # Use last stop of trip for most accuracy? (TODO: verify)
        stop_trips[stop] = frozenset((i, ))
        print(f"WARNING: {i} not covered by any stop, adding {stop} to fix")

print(len(stop_trips), "stops removing those served by a subset of another stop's lines")
assert len(frozenset.union(*stop_trips.values())) == len_trips, f"Expected {len_trips} lines covered, found {len(frozenset.union(*stop_trips.values()))}"



print("\n--- Begin stop selection ---\n")
selected_stops = set()
stop_trips_left, named_unique_trips_left = stop_trips.copy(), named_unique_trips.copy()

for trip in named_unique_trips:
    stops_covered = tuple((i, j) for i, j in stop_trips.items() if trip in j)
    if len(stops_covered) == 0:
        raise AssertionError(f"Trip {trip} not covered by any stop")
    elif len(stops_covered) == 1:
        print(f"{trip} only covered by {stops_covered[0][0]}, selecting")
        selected_stops.add(stops_covered[0][0])
        stop_trips_left.pop(stops_covered[0][0], None)
        for trip in stops_covered[0][1]:
            named_unique_trips_left.pop(trip, None)

trip_covered_stops, same_coverage_skips = {}, 0
for trip in named_unique_trips_left.keys():
    covered_stops = frozenset(i for i, j in stop_trips_left.items() if trip in j)
    if covered_stops in trip_covered_stops:
        print(f"{trip} has the same covered stops as {trip_covered_stops[covered_stops] }, skipping")
        named_unique_trips_left.pop(trip, None)
        same_coverage_skips += 1
    else:
        trip_covered_stops[covered_stops] = trip

print(f"{len(selected_stops)} stops selected, {len(named_unique_trips_left)} trips left after selecting trips only covered by one stop")
assert len(set(trip_covered_stops.keys())) == len(trip_covered_stops), "Expected unique covered stop sets"
assert len(trip_covered_stops) + same_coverage_skips == len(named_unique_trips_left), "Expected all remaining trips to be covered or skipped"



# Test greedy set cover algorithm

import random
min_stops_selected = len(stop_trips_left) + 1
covered_trips_orig = set().union(*(j for i, j in stop_trips.items() if i in selected_stops))
selected_stops_optimal = None
experimental_min = 63
max_total_lines = -1

try:
    with open("stop_selection_freq.json") as f:
        stop_selection_freq = json.load(f)
except (FileNotFoundError, json.decoder.JSONDecodeError):
    stop_selection_freq = {"__runs__": 0}

def write_freq():
    global stop_selection_freq
    print ("\nWriting stop selection frequencies...")
    with open("stop_selection_freq.json", "w") as f:
        f.write(json.dumps({k: v for k, v in sorted(stop_selection_freq.items(), key=lambda x: (x[1], x[0]), reverse=True)}, indent=4))

def write_stops():
    global selected_stops_optimal
    with open("selected_stops.txt", "w") as f:
        for i in sorted(selected_stops_optimal):
            f.write(i + "  " + ", ".join(j for j, k in all_unique_trips.items() if i in k) + "\n")

try:
    while True:
        selected_stops_copy = selected_stops.copy()
        covered_trips = covered_trips_orig.copy()

        while len(covered_trips) < len_trips: # Greedy set cover
            trip_costs, max_cost = {}, -1
            for i in stop_trips_left.keys(): # Calculate cost (number of new trips covered) for each stop
                cost = len(stop_trips_left[i] - covered_trips)
                if cost >= max_cost:
                    trip_costs.setdefault(cost, []).append(i)
                    max_cost = cost

            selected_stop = random.choice(trip_costs[max(trip_costs.keys())]) # Select stop with highest cost
            covered_trips.update(stop_trips_left[selected_stop] - covered_trips)
            selected_stops_copy.add(selected_stop)

        if len(selected_stops_copy) == experimental_min:
            total_lines = 0
            for stop in selected_stops_copy:
                total_lines += sum(1 for i, j in all_unique_trips.items() if i[0].isalpha() and stop in j) # count only PTN
            if total_lines <= max_total_lines:
                continue
            max_total_lines = total_lines
            print("New max total lines:", max_total_lines)
            selected_stops_optimal = selected_stops_copy.copy()
            write_stops()
            continue

            for i in selected_stops_optimal:
                stop_selection_freq.setdefault(i, 0)
                stop_selection_freq[i] += 1
            stop_selection_freq["__runs__"] += 1
            """ if stop_selection_freq["__runs__"] % 100 == 0:
                write_freq() """

        elif len(selected_stops_copy) < experimental_min:
            selected_stops_optimal = selected_stops_copy.copy()
            print("--- WARNING: New optimal found with", len(selected_stops_copy), "stops ---")
            break

except KeyboardInterrupt:
    print()

# write_freq()

geojson = {
    "type": "FeatureCollection",
    "features": []
}
with gtfs_file("stops") as f:
    for row in csv.DictReader(f):
        if row["stop_id"] in selected_stops_optimal:
            geojson["features"].append({
                "type": "Feature",
                "properties": {
                    "stop_id": row["stop_id"],
                    "lines": ", ".join(stop_trips[row["stop_id"]])
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row["stop_lon"]), float(row["stop_lat"])]
                }
            })
with open("unique_stops.geojson", "w") as f:
    f.write(json.dumps(geojson, indent=4))