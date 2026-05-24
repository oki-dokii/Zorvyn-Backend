# Start of HEAD
import json
import sys
import math

input_data = json.loads(sys.stdin.read())

map_size = input_data['map_size']
warehouse = [map_size[0] / 2, map_size[1] / 2]
drones = input_data['drones']
deliveries = input_data['deliveries']
no_fly_zones = input_data.get('no_fly_zones', [])
charging_stations = input_data.get('charging_stations', [])
# End of HEAD

# Start of BODY
def solve(warehouse, drones, deliveries, no_fly_zones, charging_stations):
    """
    Greedy multi-delivery scheduler.

    Strategy:
      - Sort pending deliveries by deadline (earliest first).
      - Always advance the drone with the earliest free time.
      - Pack a trip greedily: add deadline-ordered candidates while
        (a) total weight <= max_payload, (b) projected trip energy <= battery.
      - Order the trip with a nearest-neighbor heuristic from the warehouse.
      - For each leg, if it would cross an active no-fly zone, WAIT at the
        previous point until the zone deactivates, then proceed.
      - Return to the warehouse to recharge battery to full.
    """

    BATTERY_CAP = 500.0
    SPEED = 1.0  # 1 distance unit per 1 time unit

    wx, wy = warehouse[0], warehouse[1]

    def dist(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    # --- No-fly zone helpers -------------------------------------------------

    def seg_circle_time_interval(p1, p2, t1, t2, cx, cy, r):
        """If segment p1->p2 (linearly in time t1..t2) enters disk of radius r
        around (cx, cy), return (time_enter, time_exit). Else None."""
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        fx, fy = p1[0] - cx, p1[1] - cy
        a = dx * dx + dy * dy
        if a == 0.0:
            d0 = math.hypot(fx, fy)
            if d0 <= r:
                return (t1, t2)
            return None
        b = 2.0 * (fx * dx + fy * dy)
        c = fx * fx + fy * fy - r * r
        disc = b * b - 4.0 * a * c
        if disc < 0.0:
            return None
        sd = math.sqrt(disc)
        s1 = (-b - sd) / (2.0 * a)
        s2 = (-b + sd) / (2.0 * a)
        s_lo = max(0.0, s1)
        s_hi = min(1.0, s2)
        if s_lo > s_hi:
            return None
        return (t1 + s_lo * (t2 - t1), t1 + s_hi * (t2 - t1))

    def seg_rect_time_interval(p1, p2, t1, t2, xmin, ymin, xmax, ymax):
        """Intersection time interval of segment with axis-aligned rect."""
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        t_lo, t_hi = 0.0, 1.0
        for d, p, lo, hi in (
            (dx, p1[0], xmin, xmax),
            (dy, p1[1], ymin, ymax),
        ):
            if abs(d) < 1e-12:
                if p < lo or p > hi:
                    return None
            else:
                s1 = (lo - p) / d
                s2 = (hi - p) / d
                if s1 > s2:
                    s1, s2 = s2, s1
                t_lo = max(t_lo, s1)
                t_hi = min(t_hi, s2)
                if t_lo > t_hi:
                    return None
        return (t1 + t_lo * (t2 - t1), t1 + t_hi * (t2 - t1))

    def nfz_wait_until(p1, p2, t_depart):
        """If the straight leg p1->p2 departing at t_depart at speed 1 crosses
        any active no-fly zone, return the earliest time at which it would be
        safe to depart (waiting at p1). Returns t_depart if unblocked."""
        wait_to = t_depart
        leg_len = dist(p1, p2)
        if leg_len == 0.0:
            return t_depart
        # Iterate; waiting may push us into another active zone's window.
        for _ in range(len(no_fly_zones) * 2 + 2):
            blocked = False
            t1 = wait_to
            t2 = wait_to + leg_len / SPEED
            for z in no_fly_zones:
                T_start = float(z.get('T_start', -math.inf))
                T_end = float(z.get('T_end', math.inf))
                shape = z.get('shape', 'circle')
                if shape == 'circle':
                    c = z.get('center', [z.get('x', 0), z.get('y', 0)])
                    r = float(z.get('radius', 0))
                    iv = seg_circle_time_interval(p1, p2, t1, t2, c[0], c[1], r)
                elif shape == 'rectangle':
                    corners = z.get('corners')
                    if corners and len(corners) >= 2:
                        xs = [pt[0] for pt in corners]
                        ys = [pt[1] for pt in corners]
                        iv = seg_rect_time_interval(
                            p1, p2, t1, t2, min(xs), min(ys), max(xs), max(ys)
                        )
                    else:
                        iv = None
                else:
                    iv = None
                if iv is None:
                    continue
                enter, exit_ = iv
                if exit_ >= T_start and enter <= T_end:
                    new_wait = T_end + 1e-6
                    if new_wait > wait_to:
                        wait_to = new_wait
                        blocked = True
                        break
            if not blocked:
                return wait_to
        return wait_to

    # --- Trip helpers --------------------------------------------------------

    def nearest_neighbor_order(start, items):
        if not items:
            return []
        remaining = list(items)
        ordered = []
        pos = (start[0], start[1])
        while remaining:
            nxt = min(
                remaining,
                key=lambda d: (d['x'] - pos[0]) ** 2 + (d['y'] - pos[1]) ** 2,
            )
            ordered.append(nxt)
            pos = (nxt['x'], nxt['y'])
            remaining.remove(nxt)
        return ordered

    def trip_energy(ordered):
        if not ordered:
            return 0.0
        carried = sum(d['weight'] for d in ordered)
        pos = (wx, wy)
        e = 0.0
        for d in ordered:
            leg = math.hypot(pos[0] - d['x'], pos[1] - d['y'])
            e += leg * (1.0 + carried)
            carried -= d['weight']
            pos = (d['x'], d['y'])
        leg = math.hypot(pos[0] - wx, pos[1] - wy)
        e += leg * (1.0 + carried)
        return e

    # --- Drone state ---------------------------------------------------------

    states = {}
    for dr in drones:
        states[dr['id']] = {
            'drone': dr,
            'pos': (wx, wy),
            't': 0.0,
            'battery': BATTERY_CAP,
            'path': [],
        }

    active_drone_ids = [dr['id'] for dr in drones]
    pending = sorted(deliveries, key=lambda d: d.get('deadline', float('inf')))

    # --- Main scheduling loop -----------------------------------------------

    while pending and active_drone_ids:
        did = min(active_drone_ids, key=lambda x: states[x]['t'])
        st = states[did]
        max_payload = float(st['drone'].get('max_payload', 0))

        # Build trip greedily by deadline order.
        chosen = []
        chosen_ids = set()
        cur_weight = 0.0
        for cand in pending:
            if cand['id'] in chosen_ids:
                continue
            w = float(cand.get('weight', 0))
            if cur_weight + w > max_payload + 1e-9:
                continue
            tentative = chosen + [cand]
            ordered = nearest_neighbor_order(warehouse, tentative)
            if trip_energy(ordered) <= BATTERY_CAP:
                chosen = tentative
                chosen_ids.add(cand['id'])
                cur_weight += w
                if len(chosen) >= 8:  # cap trip size to bound complexity
                    break

        if not chosen:
            # This drone can't carry any remaining delivery.
            active_drone_ids.remove(did)
            continue

        ordered = nearest_neighbor_order(warehouse, chosen)

        # PICKUP at warehouse
        st['path'].append({
            'x': wx,
            'y': wy,
            't': round(st['t'], 6),
            'action': 'PICKUP',
            'delivery_ids': [d['id'] for d in ordered],
        })

        pos = (wx, wy)
        carried = sum(float(d['weight']) for d in ordered)

        # Deliver each
        for d in ordered:
            nxt_pos = (float(d['x']), float(d['y']))
            depart = nfz_wait_until(pos, nxt_pos, st['t'])
            if depart > st['t']:
                st['path'].append({
                    'x': pos[0],
                    'y': pos[1],
                    't': round(depart, 6),
                    'action': 'WAIT',
                })
                st['t'] = depart
            leg = dist(pos, nxt_pos)
            st['t'] += leg / SPEED
            st['battery'] -= leg * (1.0 + carried)
            st['path'].append({
                'x': nxt_pos[0],
                'y': nxt_pos[1],
                't': round(st['t'], 6),
                'action': 'DELIVER',
                'delivery_id': d['id'],
            })
            carried -= float(d['weight'])
            pos = nxt_pos

        # Return to warehouse
        depart = nfz_wait_until(pos, (wx, wy), st['t'])
        if depart > st['t']:
            st['path'].append({
                'x': pos[0],
                'y': pos[1],
                't': round(depart, 6),
                'action': 'WAIT',
            })
            st['t'] = depart
        leg = dist(pos, (wx, wy))
        st['t'] += leg / SPEED
        st['battery'] -= leg * (1.0 + carried)
        st['path'].append({
            'x': wx,
            'y': wy,
            't': round(st['t'], 6),
            'action': 'RETURN',
        })
        st['battery'] = BATTERY_CAP
        st['pos'] = (wx, wy)

        pending = [d for d in pending if d['id'] not in chosen_ids]

    # --- Assemble manifest ---------------------------------------------------
    flight_manifest = []
    for dr in drones:
        flight_manifest.append({
            'drone_id': dr['id'],
            'path': states[dr['id']]['path'],
        })
    return flight_manifest
# End of BODY

# Start of TAIL
result = solve(warehouse, drones, deliveries, no_fly_zones, charging_stations)
output = {"flight_manifest": result}
print(json.dumps(output))
# End of TAIL
