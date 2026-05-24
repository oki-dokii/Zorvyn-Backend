# Start of HEAD
import json
import sys
import math
from itertools import permutations

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
    Greedy multi-delivery scheduler with brute-force per-trip routing.

    Strategy:
      - Sort pending deliveries by deadline (earliest first).
      - Repeatedly schedule the drone with the earliest free time.
      - Pack a trip greedily from deadline-sorted candidates while respecting
        the drone's max_payload (cap MAX_TRIP_SIZE, scan MAX_CANDIDATES_SCAN).
      - Brute-force the optimal route for the packed trip: maximize on-time
        deliveries first, break ties by minimum energy, then minimum makespan.
        This is the key score driver: each on-time delivery is worth 100
        whereas energy/makespan penalties are weighted 0.1/0.05.
      - If the optimal route exceeds the battery, drop the least-urgent item
        (latest deadline) and re-optimize until it fits.
      - Per leg, wait at the prior point until any active no-fly zone closes.
      - Return to the warehouse to recharge.
    """

    BATTERY_CAP = 500.0
    SPEED = 1.0
    MAX_TRIP_SIZE = 6  # brute force is 720 perms at 6
    MAX_CANDIDATES_SCAN = 200

    wx, wy = warehouse[0], warehouse[1]

    def dist(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    # --- No-fly zone helpers -------------------------------------------------

    def seg_circle_time_interval(p1, p2, t1, t2, cx, cy, r):
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
        s_lo = s1 if s1 > 0.0 else 0.0
        s_hi = s2 if s2 < 1.0 else 1.0
        if s_lo > s_hi:
            return None
        return (t1 + s_lo * (t2 - t1), t1 + s_hi * (t2 - t1))

    def seg_rect_time_interval(p1, p2, t1, t2, xmin, ymin, xmax, ymax):
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
                if s1 > t_lo:
                    t_lo = s1
                if s2 < t_hi:
                    t_hi = s2
                if t_lo > t_hi:
                    return None
        return (t1 + t_lo * (t2 - t1), t1 + t_hi * (t2 - t1))

    nfz_norm = []
    for z in no_fly_zones:
        T_start = float(z.get('T_start', -1e18))
        T_end = float(z.get('T_end', 1e18))
        shape = z.get('shape', 'circle')
        if shape == 'circle':
            c = z.get('center', [z.get('x', 0), z.get('y', 0)])
            r = float(z.get('radius', 0))
            nfz_norm.append(('c', T_start, T_end, float(c[0]), float(c[1]), r))
        elif shape == 'rectangle':
            corners = z.get('corners')
            if corners and len(corners) >= 2:
                xs = [pt[0] for pt in corners]
                ys = [pt[1] for pt in corners]
                nfz_norm.append(('r', T_start, T_end, min(xs), min(ys), max(xs), max(ys)))

    have_nfz = bool(nfz_norm)

    def nfz_wait_until(p1, p2, t_depart):
        if not have_nfz:
            return t_depart
        leg_len = dist(p1, p2)
        if leg_len == 0.0:
            return t_depart
        wait_to = t_depart
        max_iter = len(nfz_norm) * 2 + 2
        for _ in range(max_iter):
            blocked = False
            t1 = wait_to
            t2 = wait_to + leg_len / SPEED
            for z in nfz_norm:
                kind = z[0]
                T_start = z[1]
                T_end = z[2]
                if t1 > T_end:
                    continue
                if kind == 'c':
                    iv = seg_circle_time_interval(p1, p2, t1, t2, z[3], z[4], z[5])
                else:
                    iv = seg_rect_time_interval(p1, p2, t1, t2, z[3], z[4], z[5], z[6])
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

    # --- Trip routing: brute-force optimal permutation -----------------------

    def best_route(items, depart_t):
        """Return (ordered_items, energy, t_end).

        Maximize on-time count, tie-break by minimum energy, then makespan.
        Energy includes the full forward legs (with decreasing payload) plus
        the return leg back to the warehouse.
        """
        n = len(items)
        if n == 0:
            return ([], 0.0, depart_t)
        if n == 1:
            d = items[0]
            leg = math.hypot(d['x'] - wx, d['y'] - wy)
            w = float(d['weight'])
            t_arr = depart_t + leg / SPEED
            t_end = t_arr + leg / SPEED
            e = leg * (1.0 + w) + leg
            return ([d], e, t_end)

        total_w = 0.0
        for d in items:
            total_w += float(d['weight'])

        best_key = None
        best_perm = None
        best_e = 0.0
        best_t_end = depart_t

        for perm in permutations(items):
            t = depart_t
            carried = total_w
            e = 0.0
            on_time = 0
            px, py = wx, wy
            for d in perm:
                dxv = px - d['x']
                dyv = py - d['y']
                leg = math.sqrt(dxv * dxv + dyv * dyv)
                t += leg / SPEED
                e += leg * (1.0 + carried)
                dl = d.get('deadline', float('inf'))
                if t <= dl:
                    on_time += 1
                carried -= float(d['weight'])
                px, py = d['x'], d['y']
            dxv = px - wx
            dyv = py - wy
            leg_r = math.sqrt(dxv * dxv + dyv * dyv)
            e += leg_r
            t_end = t + leg_r / SPEED
            key = (-on_time, e, t_end)
            if best_key is None or key < best_key:
                best_key = key
                best_perm = perm
                best_e = e
                best_t_end = t_end

        return (list(best_perm), best_e, best_t_end)

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

    while active_drone_ids and pending:
        did = active_drone_ids[0]
        best_t = states[did]['t']
        for i in range(1, len(active_drone_ids)):
            t_i = states[active_drone_ids[i]]['t']
            if t_i < best_t:
                best_t = t_i
                did = active_drone_ids[i]
        st = states[did]
        max_payload = float(st['drone'].get('max_payload', 0))

        chosen = []
        chosen_ids = set()
        cur_weight = 0.0
        scan_limit = MAX_CANDIDATES_SCAN
        if scan_limit > len(pending):
            scan_limit = len(pending)
        for i in range(scan_limit):
            cand = pending[i]
            w = float(cand.get('weight', 0))
            if w > max_payload:
                continue
            if cur_weight + w > max_payload + 1e-9:
                continue
            chosen.append(cand)
            chosen_ids.add(cand['id'])
            cur_weight += w
            if len(chosen) >= MAX_TRIP_SIZE:
                break

        if not chosen:
            active_drone_ids.remove(did)
            continue

        ordered, energy, _t_end = best_route(chosen, st['t'])
        while ordered and energy > BATTERY_CAP:
            # drop the least-urgent (latest deadline) item and re-optimize
            drop_idx = 0
            drop_dl = ordered[0].get('deadline', float('inf'))
            for i in range(1, len(ordered)):
                dli = ordered[i].get('deadline', float('inf'))
                if dli > drop_dl:
                    drop_dl = dli
                    drop_idx = i
            ordered.pop(drop_idx)
            ordered, energy, _t_end = best_route(ordered, st['t'])

        if not ordered:
            active_drone_ids.remove(did)
            continue

        chosen_ids = {d['id'] for d in ordered}

        st['path'].append({
            'x': wx,
            'y': wy,
            't': round(st['t'], 6),
            'action': 'PICKUP',
            'delivery_ids': [d['id'] for d in ordered],
        })

        pos = (wx, wy)
        carried = sum(float(d['weight']) for d in ordered)

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

        if chosen_ids:
            pending = [d for d in pending if d['id'] not in chosen_ids]

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
