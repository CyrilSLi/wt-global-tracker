import csv, json, os, random, sys

if not os.path.isdir(sys.argv[1]):
    raise SystemExit("Usage: python main.py <gtfs_directory>")
os.chdir(os.path.dirname(os.path.abspath(__file__)))

gtfs_file = lambda f: open(os.path.join(sys.argv [1], f + ".txt"))
global_max_total_lines = -1

class GlobalMaxTotalLines(Exception):
    pass



def main():
    global global_max_total_lines
    trip_stops = {}
    with gtfs_file("stop_times") as f:
        for row in csv.DictReader(f):
            trip_stops.setdefault(row["trip_id"], []).append((row["stop_id"], int(row["stop_sequence"])))

    stops_removed = 1
    unique_trips = {tuple(i for i, _ in sorted(stops, key=lambda x: x[1])): trip_id for trip_id, stops in trip_stops.items()}
    all_unique_trips = {v: k for k, v in unique_trips.items()} # Do not remove stops for this copy
    unique_trips = {v: k[stops_removed:-stops_removed] for k, v in unique_trips.items()} # Remove first and last stops because their arrival times are often inaccurate
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
                for i, j in all_unique_trips.items(): # Skip stops that are first or last stop of any line
                    if row["stop_id"] in j and (j.index(row["stop_id"]) == 0 or j.index(row["stop_id"]) == len(j) - 1):
                        # print(f"WARNING: stop {row['stop_id']} is first or last stop of trip {i}, skipping")
                        break
                else:
                    stop_trips[lines] = row["stop_id"]
    stop_trips = {v: k for k, v in stop_trips.items()}
    print(len(stop_trips), "stops served a unique set of more than one line")



    if sys.argv[-1] == "--count":
        count = 0
        with open("selected_stops.txt") as f:
            stop_trips = {}
            for line in f:
                stop_id = line.strip().split()[0]
                print(stop_id, end="")
                for i, j in all_unique_trips.items():
                    if stop_id in j:
                        stop_trips.setdefault(stop_id, set()).add(i)
                        if j.index(stop_id) == 0 or j.index(stop_id) == len(j) - 1:
                            print(f"ERROR: stop {stop_id} is first or last stop of trip {i}")
                            raise ValueError("Invalid stop in selected stops")
                        count += 1
                        print(f" {i.split()[0]}-{j.index(stop_id)}/{len(j)}", end="")
                print("", flush=True)

            if set.union(*stop_trips.values()) != set(all_unique_trips.keys()):
                missing = set(all_unique_trips.keys()) - set.union(*stop_trips.values())
                raise ValueError("ERROR: Missing trips:", ", ".join(missing))

        print(count, "lines served by selected stops")
        raise SystemExit("Debug exit successful")



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

    experimental_min = 64 # TODO: CHANGE IF TRANSIT NETWORK UPDATES

    min_stops_selected = len(stop_trips_left) + 1
    covered_trips_orig = set().union(*(j for i, j in stop_trips.items() if i in selected_stops))
    selected_stops_optimal = None
    max_total_lines = -1

    try:
        with open("stop_selection_freq.json") as f:
            stop_selection_freq = json.load(f)
    except (FileNotFoundError, json.decoder.JSONDecodeError):
        stop_selection_freq = {"__runs__": 0}

    def write_freq():
        nonlocal stop_selection_freq
        print ("\nWriting stop selection frequencies...")
        with open("stop_selection_freq.json", "w") as f:
            f.write(json.dumps({k: v for k, v in sorted(stop_selection_freq.items(), key=lambda x: (x[1], x[0]), reverse=True)}, indent=4))

    def write_stops():
        nonlocal selected_stops_optimal
        with open("selected_stops.txt", "w") as f:
            f.write("\n".join((f'{i}  {", ".join(stop_trips[i])}' for i in sorted(selected_stops_optimal))))
            """ for i in sorted(selected_stops_optimal):
                f.write(i + "  " + ", ".join(j for j, k in all_unique_trips.items() if i in k) + "\n") """

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

            if len(selected_stops_copy) < min_stops_selected:
                min_stops_selected = len(selected_stops_copy)
                print("New optimal found with", len(selected_stops_copy), "stops")
                selected_stops_optimal = selected_stops_copy.copy()

                total_lines = sum(sum(1 for j in all_unique_trips.values() if stop in j) for stop in selected_stops_optimal)
                print("  Max total lines:", total_lines)
                max_total_lines = total_lines

                if len(selected_stops_copy) <= experimental_min:
                    if global_max_total_lines < max_total_lines:
                        global_max_total_lines = max_total_lines
                        print(" " * 50, "INFO: New global max total lines:", global_max_total_lines)
                        write_stops()
                    raise GlobalMaxTotalLines()

                """ for i in selected_stops_optimal:
                    stop_selection_freq.setdefault(i, 0)
                    stop_selection_freq[i] += 1
                stop_selection_freq["__runs__"] += 1
                if stop_selection_freq["__runs__"] % 100 == 0:
                    write_freq() """

            elif len(selected_stops_copy) == min_stops_selected:
                # print("Found another optimal with", len(selected_stops_copy), "stops")
                total_lines = sum(sum(1 for j in all_unique_trips.values() if stop in j) for stop in selected_stops_optimal)
                # print("  Total lines:", total_lines)
                if total_lines > max_total_lines:
                    print("  New max total lines:", total_lines)
                    max_total_lines = total_lines
                    selected_stops_optimal = selected_stops_copy.copy()
                    # write_stops()

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



if __name__ == "__main__":
    while True:
        try:
            main()
        except (GlobalMaxTotalLines, ):
            pass