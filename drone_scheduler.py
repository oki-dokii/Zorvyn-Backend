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
    BATTERY_CAP = 500.0
    SPEED = 1.0
    MAX_TRIP_SIZE = 10
    MAX_CANDIDATES_SCAN = 200
    BRUTE_LIMIT = 7
    INF = float('inf')

    wx, wy = warehouse[0], warehouse[1]

    def dist(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

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

    def nn_order_from(items, sx, sy):
        if not items:
            return []
        pool = list(items)
        ordered = []
        px, py = sx, sy
        while pool:
            best_i = 0
            dx0 = pool[0]['x'] - px
            dy0 = pool[0]['y'] - py
            best_d = dx0 * dx0 + dy0 * dy0
            for i in range(1, len(pool)):
                dxi = pool[i]['x'] - px
                dyi = pool[i]['y'] - py
                d = dxi * dxi + dyi * dyi
                if d < best_d:
                    best_d = d
                    best_i = i
            picked = pool.pop(best_i)
            ordered.append(picked)
            px, py = picked['x'], picked['y']
        return ordered

    def nn_order(items):
        return nn_order_from(items, wx, wy)

    def eval_perm(perm, depart_t):
        if not perm:
            return (0.0, 0, depart_t)
        total_w = 0.0
        for d in perm:
            total_w += float(d['weight'])
        carried = total_w
        t = depart_t
        e = 0.0
        on_time = 0
        px, py = wx, wy
        for d in perm:
            dxv = px - d['x']
            dyv = py - d['y']
            leg = math.sqrt(dxv * dxv + dyv * dyv)
            t += leg / SPEED
            e += leg * (1.0 + carried)
            dl = d.get('deadline', INF)
            if t <= dl:
                on_time += 1
            carried -= float(d['weight'])
            px, py = d['x'], d['y']
        dxv = px - wx
        dyv = py - wy
        leg_r = math.sqrt(dxv * dxv + dyv * dyv)
        e += leg_r
        t_end = t + leg_r / SPEED
        return (e, on_time, t_end)

    def best_route_bf(items, depart_t):
        n = len(items)
        if n == 0:
            return ([], 0.0, 0, depart_t)
        best_key = None
        best_perm = None
        best_data = None
        for perm in permutations(items):
            e, ot, t_end = eval_perm(perm, depart_t)
            key = (-ot, e, t_end)
            if best_key is None or key < best_key:
                best_key = key
                best_perm = perm
                best_data = (e, ot, t_end)
        return (list(best_perm), best_data[0], best_data[1], best_data[2])

    def two_opt(perm, depart_t, max_rounds=3):
        if len(perm) < 4:
            return perm
        best = list(perm)
        best_e, best_ot, best_t_end = eval_perm(best, depart_t)
        best_key = (-best_ot, best_e, best_t_end)
        for _ in range(max_rounds):
            improved = False
            n = len(best)
            for i in range(0, n - 1):
                for j in range(i + 1, n):
                    new = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                    e, ot, t_end = eval_perm(new, depart_t)
                    key = (-ot, e, t_end)
                    if key < best_key:
                        best_key = key
                        best = new
                        improved = True
            if not improved:
                break
        return best

    def best_route(items, depart_t):
        n = len(items)
        if n == 0:
            return ([], 0.0, 0, depart_t)
        if n <= BRUTE_LIMIT:
            return best_route_bf(items, depart_t)

        nn = nn_order(items)
        dl = sorted(items, key=lambda d: d.get('deadline', INF))
        opt_nn = two_opt(nn, depart_t)
        opt_dl = two_opt(dl, depart_t)

        best_key = None
        best = None
        for perm in (nn, dl, opt_nn, opt_dl):
            e, ot, t_end = eval_perm(perm, depart_t)
            key = (-ot, e, t_end)
            if best_key is None or key < best_key:
                best_key = key
                best = (list(perm), e, ot, t_end)
        return best

    # --- Packing strategies --------------------------------------------------

    def pack_by_deadline(pool, max_payload, depart_t):
        """Greedy by deadline-asc; per-add NN-energy + on-time non-regression."""
        chosen = []
        cur_w = 0.0
        chosen_ot = 0
        scan = min(MAX_CANDIDATES_SCAN, len(pool))
        for i in range(scan):
            cand = pool[i]
            w = float(cand.get('weight', 0))
            if w > max_payload:
                continue
            if cur_w + w > max_payload + 1e-9:
                continue
            tentative = chosen + [cand]
            nn_ord = nn_order(tentative)
            e_t, ot_t, _ = eval_perm(nn_ord, depart_t)
            if e_t > BATTERY_CAP:
                continue
            if ot_t < chosen_ot:
                continue
            chosen.append(cand)
            cur_w += w
            chosen_ot = ot_t
            if len(chosen) >= MAX_TRIP_SIZE:
                break
        return chosen

    def pack_by_cluster(pool, max_payload, depart_t):
        """Pick most urgent first, then prefer items close to current trip
        centroid; per-add NN-energy + on-time non-regression."""
        if not pool:
            return []
        candidates = pool[:MAX_CANDIDATES_SCAN]
        chosen = []
        chosen_ot = 0
        cur_w = 0.0
        # Seed with most urgent feasible.
        seed_idx = None
        for i in range(len(candidates)):
            w = float(candidates[i].get('weight', 0))
            if w <= max_payload:
                seed_idx = i
                break
        if seed_idx is None:
            return []
        chosen.append(candidates[seed_idx])
        cur_w = float(candidates[seed_idx].get('weight', 0))
        _, chosen_ot, _ = eval_perm(chosen, depart_t)
        remaining = [c for c in candidates if c is not chosen[0]]

        while len(chosen) < MAX_TRIP_SIZE and remaining:
            # Centroid of current trip
            cx = sum(c['x'] for c in chosen) / len(chosen)
            cy = sum(c['y'] for c in chosen) / len(chosen)
            # Score each remaining: weighted by deadline rank + distance
            best_pick = None
            best_pick_key = None
            for c in remaining:
                w = float(c.get('weight', 0))
                if w > max_payload or cur_w + w > max_payload + 1e-9:
                    continue
                d_sq = (c['x'] - cx) ** 2 + (c['y'] - cy) ** 2
                key = (d_sq, c.get('deadline', INF))
                if best_pick_key is None or key < best_pick_key:
                    best_pick_key = key
                    best_pick = c
            if best_pick is None:
                break
            tentative = chosen + [best_pick]
            nn_ord = nn_order(tentative)
            e_t, ot_t, _ = eval_perm(nn_ord, depart_t)
            if e_t > BATTERY_CAP or ot_t < chosen_ot:
                remaining.remove(best_pick)
                continue
            chosen.append(best_pick)
            cur_w += float(best_pick.get('weight', 0))
            chosen_ot = ot_t
            remaining.remove(best_pick)
        return chosen

    def pack_score(chosen, depart_t):
        if not chosen:
            return (0, 0.0, depart_t)
        ordered, energy, ot, t_end = best_route(chosen, depart_t)
        return (ot, energy, t_end)

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
    pending = sorted(deliveries, key=lambda d: d.get('deadline', INF))

    for d in pending:
        d['_w_dist'] = math.hypot(float(d['x']) - wx, float(d['y']) - wy)

    while active_drone_ids and pending:
        did = active_drone_ids[0]
        best_t = states[did]['t']
        for i in range(1, len(active_drone_ids)):
            t_i = states[active_drone_ids[i]]['t']
            if t_i < best_t:
                best_t = t_i
                did = active_drone_ids[i]
        st = states[did]
        depart_t = st['t']
        max_payload = float(st['drone'].get('max_payload', 0))

        new_pending = []
        for d in pending:
            if depart_t + d['_w_dist'] / SPEED <= d.get('deadline', INF):
                new_pending.append(d)
        pending = new_pending
        if not pending:
            break

        # Try deadline-greedy first; only invoke the cluster strategy when
        # the deadline pack didn't fill the trip with all-on-time items.
        pack_a = pack_by_deadline(pending, max_payload, depart_t)
        sa = pack_score(pack_a, depart_t)
        if len(pack_a) >= MAX_TRIP_SIZE and sa[0] == len(pack_a):
            chosen = pack_a
        else:
            pack_b = pack_by_cluster(pending, max_payload, depart_t)
            sb = pack_score(pack_b, depart_t)
            key_a = (-sa[0], sa[1], sa[2])
            key_b = (-sb[0], sb[1], sb[2])
            chosen = pack_a if key_a <= key_b else pack_b

        if not chosen:
            active_drone_ids.remove(did)
            continue

        ordered, energy, _ot, _t_end = best_route(chosen, depart_t)

        while ordered and energy > BATTERY_CAP:
            drop_idx = 0
            drop_dl = ordered[0].get('deadline', INF)
            for k in range(1, len(ordered)):
                dlk = ordered[k].get('deadline', INF)
                if dlk > drop_dl:
                    drop_dl = dlk
                    drop_idx = k
            ordered.pop(drop_idx)
            if ordered:
                ordered, energy, _ot, _t_end = best_route(ordered, depart_t)

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
