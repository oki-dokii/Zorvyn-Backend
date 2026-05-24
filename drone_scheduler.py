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
    Multi-drone scheduler with charging-station support.

    Score model: 100 * on_time - 0.1 * energy - 0.05 * makespan.

    Strategy:
      - Pre-filter only items whose direct distance from warehouse already
        exceeds their deadline (intrinsically impossible), not the more
        aggressive time-relative filter (which was killing borderline cases
        such as TC3).
      - Per-drone, run two packing strategies (deadline-greedy and
        cluster-greedy) and keep whichever yields the better routed result.
      - Brute-force optimal TSP for trips with n <= 7, multi-candidate +
        2-opt for 8..MAX_TRIP_SIZE.
      - When charging stations are available, allow trips whose direct energy
        exceeds the 500 battery; during execution, divert via the cheapest
        charging station whenever the next leg would deplete the battery.
    """

    BATTERY_CAP = 500.0
    SPEED = 1.0
    CHARGE_RATE = 2.0  # energy units per timestep (matches problem statement)
    MAX_TRIP_SIZE = 12
    MAX_CANDIDATES_SCAN = 200
    BRUTE_LIMIT = 7
    INF = float('inf')

    wx, wy = warehouse[0], warehouse[1]

    cs_points = []
    for cs in charging_stations:
        cs_points.append((float(cs['x']), float(cs['y'])))
    have_cs = bool(cs_points)
    # If charging is available, allow trips with effective higher energy ceiling;
    # actual execution will insert CHARGE stops as needed.
    if have_cs:
        TRIP_ENERGY_CAP = BATTERY_CAP * 2.0
    else:
        TRIP_ENERGY_CAP = BATTERY_CAP

    def dist(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    # --- NFZ helpers ---------------------------------------------------------

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
    # Only fold NFZ-wait into per-perm eval for small inputs; for large
    # inputs the cost (brute force over many perms) becomes prohibitive
    # and trip_actual_score still handles NFZ correctly for final scoring.
    eval_uses_nfz = have_nfz and len(deliveries) <= 500

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

    # --- Routing helpers -----------------------------------------------------

    def nn_order(items):
        if not items:
            return []
        pool = list(items)
        ordered = []
        px, py = wx, wy
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
            nxt = (float(d['x']), float(d['y']))
            if eval_uses_nfz:
                t_wait = nfz_wait_until((px, py), nxt, t)
                if t_wait > t:
                    t = t_wait
            dxv = px - nxt[0]
            dyv = py - nxt[1]
            leg = math.sqrt(dxv * dxv + dyv * dyv)
            t += leg / SPEED
            e += leg * (1.0 + carried)
            dl = d.get('deadline', INF)
            if t <= dl:
                on_time += 1
            carried -= float(d['weight'])
            px, py = nxt[0], nxt[1]
        if eval_uses_nfz:
            t_wait = nfz_wait_until((px, py), (wx, wy), t)
            if t_wait > t:
                t = t_wait
        dxv = px - wx
        dyv = py - wy
        leg_r = math.sqrt(dxv * dxv + dyv * dyv)
        e += leg_r
        t_end = t + leg_r / SPEED
        return (e, on_time, t_end)

    def trip_actual_score(perm, depart_t):
        """Simulate the trip including NFZ waits and min-charge stops. Returns
        (on_time_count, energy, t_end). Returns (0, 1e18, 1e18) on infeasibility."""
        if not perm:
            return (0, 0.0, depart_t)
        n = len(perm)
        positions = [(wx, wy)] + [(p['x'], p['y']) for p in perm] + [(wx, wy)]
        carrieds = [0.0] * (n + 1)
        total_w = 0.0
        for p in perm:
            total_w += float(p['weight'])
        carrieds[0] = total_w
        for i in range(1, n + 1):
            carrieds[i] = carrieds[i - 1] - float(perm[i - 1]['weight'])
        leg_energies = [0.0] * (n + 1)
        for i in range(n + 1):
            ld = dist(positions[i], positions[i + 1])
            leg_energies[i] = ld * (1.0 + carrieds[i])
        suffix_e = [0.0] * (n + 2)
        for i in range(n, -1, -1):
            suffix_e[i] = suffix_e[i + 1] + leg_energies[i]
        pos = positions[0]
        battery = BATTERY_CAP
        t = depart_t
        energy = 0.0
        on_time = 0
        SAFETY = 1e-6
        for i in range(n + 1):
            target = positions[i + 1]
            carried = carrieds[i]
            future_after = suffix_e[i + 1]
            for _ in range(8):
                leg_d = dist(pos, target)
                leg_e = leg_d * (1.0 + carried)
                if leg_e <= battery + SAFETY:
                    break
                if not have_cs:
                    return (0, 1e18, 1e18)
                best = None
                best_extra = INF
                for cs in cs_points:
                    e_to = dist(pos, cs) * (1.0 + carried)
                    if e_to > battery + SAFETY:
                        continue
                    e_from = dist(cs, target) * (1.0 + carried)
                    if e_from > BATTERY_CAP + SAFETY:
                        continue
                    extra = e_to + e_from - leg_e
                    if extra < best_extra:
                        best_extra = extra
                        best = (cs, e_to, e_from)
                if best is None:
                    return (0, 1e18, 1e18)
                cs, e_to, e_from = best
                d_to_cs = dist(pos, cs)
                if have_nfz:
                    tw = nfz_wait_until(pos, cs, t)
                    if tw > t:
                        t = tw
                t += d_to_cs / SPEED
                battery -= e_to
                energy += e_to
                pos = cs
                needed = e_from + future_after
                target_battery = needed
                if target_battery > BATTERY_CAP:
                    target_battery = BATTERY_CAP
                charge_amount = target_battery - battery
                if charge_amount < 0.0:
                    charge_amount = 0.0
                t += charge_amount / CHARGE_RATE
                battery += charge_amount
            else:
                return (0, 1e18, 1e18)
            if have_nfz:
                tw = nfz_wait_until(pos, target, t)
                if tw > t:
                    t = tw
            leg_d = dist(pos, target)
            leg_e = leg_d * (1.0 + carried)
            battery -= leg_e
            energy += leg_e
            t += leg_d / SPEED
            pos = target
            if i < n:
                dl = perm[i].get('deadline', INF)
                if t <= dl:
                    on_time += 1
        return (on_time, energy, t)

    def is_trip_feasible(perm):
        """Simulate the trip exactly as execution will: charge MINIMALLY at
        the cheapest reachable station when a leg would otherwise drain the
        battery. Returns True iff every leg (and final return) completes with
        non-negative battery."""
        if not perm:
            return True
        n = len(perm)
        positions = [(wx, wy)] + [(p['x'], p['y']) for p in perm] + [(wx, wy)]
        carrieds = [0.0] * (n + 1)
        total_w = 0.0
        for p in perm:
            total_w += float(p['weight'])
        carrieds[0] = total_w
        for i in range(1, n + 1):
            carrieds[i] = carrieds[i - 1] - float(perm[i - 1]['weight'])
        leg_energies = [0.0] * (n + 1)
        for i in range(n + 1):
            ld = dist(positions[i], positions[i + 1])
            leg_energies[i] = ld * (1.0 + carrieds[i])
        suffix_e = [0.0] * (n + 2)
        for i in range(n, -1, -1):
            suffix_e[i] = suffix_e[i + 1] + leg_energies[i]
        pos = positions[0]
        battery = BATTERY_CAP
        SAFETY = 1e-6
        for i in range(n + 1):
            target = positions[i + 1]
            carried = carrieds[i]
            future_after = suffix_e[i + 1]
            for _ in range(8):
                leg_e = dist(pos, target) * (1.0 + carried)
                if leg_e <= battery + SAFETY:
                    break
                if not have_cs:
                    return False
                best = None
                best_extra = INF
                for cs in cs_points:
                    e_to = dist(pos, cs) * (1.0 + carried)
                    if e_to > battery + SAFETY:
                        continue
                    e_from = dist(cs, target) * (1.0 + carried)
                    if e_from > BATTERY_CAP + SAFETY:
                        continue
                    extra = e_to + e_from - leg_e
                    if extra < best_extra:
                        best_extra = extra
                        best = (cs, e_to, e_from)
                if best is None:
                    return False
                cs, e_to, e_from = best
                battery -= e_to
                pos = cs
                # Minimum charge: just enough for remainder of trip.
                needed_from_cs = e_from + future_after
                target_battery = needed_from_cs
                if target_battery > BATTERY_CAP:
                    target_battery = BATTERY_CAP
                if target_battery > battery:
                    battery = target_battery
            else:
                return False
            leg_e = dist(pos, target) * (1.0 + carried)
            if leg_e > battery + SAFETY:
                return False
            battery -= leg_e
            pos = target
        return True

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

    def pack_by_deadline(pool, max_payload, depart_t, energy_cap):
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
            if depart_t + cand['_w_dist'] / SPEED > cand.get('deadline', INF):
                continue
            tentative = chosen + [cand]
            nn_ord = nn_order(tentative)
            e_t, ot_t, _ = eval_perm(nn_ord, depart_t)
            if e_t > energy_cap:
                continue
            if ot_t < chosen_ot:
                continue
            chosen.append(cand)
            cur_w += w
            chosen_ot = ot_t
            if len(chosen) >= MAX_TRIP_SIZE:
                break
        return chosen

    def pack_by_cluster(pool, max_payload, depart_t, energy_cap):
        if not pool:
            return []
        candidates = pool[:MAX_CANDIDATES_SCAN]
        chosen = []
        chosen_ot = 0
        cur_w = 0.0
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
            cx = sum(c['x'] for c in chosen) / len(chosen)
            cy = sum(c['y'] for c in chosen) / len(chosen)
            best_pick = None
            best_pick_key = None
            for c in remaining:
                w = float(c.get('weight', 0))
                if w > max_payload or cur_w + w > max_payload + 1e-9:
                    continue
                if depart_t + c['_w_dist'] / SPEED > c.get('deadline', INF):
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
            if e_t > energy_cap or ot_t < chosen_ot:
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
        _, energy, ot, t_end = best_route(chosen, depart_t)
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

        # Pre-filter: drop items whose earliest possible arrival from the
        # current min-t drone already exceeds their deadline. Drone times only
        # ever increase, so such items can never be on-time anywhere.
        new_pending = []
        for d in pending:
            if depart_t + d['_w_dist'] / SPEED <= d.get('deadline', INF) + 1e-6:
                new_pending.append(d)
        pending = new_pending
        if not pending:
            break

        # Always run the strict-cap pack first.
        pack_strict_a = pack_by_deadline(pending, max_payload, depart_t, BATTERY_CAP)
        pack_strict_b = pack_by_cluster(pending, max_payload, depart_t, BATTERY_CAP)
        # Run the relaxed-cap (charging-aware) pack too when it could plausibly
        # add deliveries beyond what the strict pack covers.
        pack_relaxed_a = []
        pack_relaxed_b = []
        if have_cs and TRIP_ENERGY_CAP > BATTERY_CAP:
            strict_size = max(len(pack_strict_a), len(pack_strict_b))
            if strict_size < MAX_TRIP_SIZE:
                pack_relaxed_a = pack_by_deadline(pending, max_payload, depart_t, TRIP_ENERGY_CAP)
                pack_relaxed_b = pack_by_cluster(pending, max_payload, depart_t, TRIP_ENERGY_CAP)
        # Score each pack with the realistic simulator (handles charging + NFZ).
        best_ordered = None
        best_key = None
        best_t_end_est = depart_t
        for p in (pack_strict_a, pack_strict_b, pack_relaxed_a, pack_relaxed_b):
            if not p:
                continue
            ordered_p, _, _, _ = best_route(p, depart_t)
            # Trim infeasible tails so trip_actual_score won't reject.
            while ordered_p:
                if have_cs:
                    if is_trip_feasible(ordered_p):
                        break
                else:
                    _, e_test, _ = eval_perm(ordered_p, depart_t)
                    if e_test <= BATTERY_CAP:
                        break
                drop_idx = 0
                drop_dl = ordered_p[0].get('deadline', INF)
                for k in range(1, len(ordered_p)):
                    dlk = ordered_p[k].get('deadline', INF)
                    if dlk > drop_dl:
                        drop_dl = dlk
                        drop_idx = k
                ordered_p.pop(drop_idx)
                if ordered_p:
                    ordered_p, _, _, _ = best_route(ordered_p, depart_t)
            if not ordered_p:
                continue
            sim_ot, sim_e, sim_t_end = trip_actual_score(ordered_p, depart_t)
            if sim_e >= 1e17:
                continue
            key = (-sim_ot, sim_e, sim_t_end)
            if best_key is None or key < best_key:
                best_key = key
                best_ordered = ordered_p
                best_t_end_est = sim_t_end
        chosen = best_ordered if best_ordered else []

        if not chosen:
            active_drone_ids.remove(did)
            continue

        # chosen is already optimally routed and feasibility-trimmed above.
        ordered = chosen
        if ordered:
            _, energy, _ot, _t_end = best_route(ordered, depart_t)
        else:
            energy = 0.0

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

        def maybe_charge(target_pos, carried, future_needed):
            """If the next leg pos->target_pos would deplete the battery,
            divert via the cheapest reachable charging station and charge
            JUST enough for (leg_to_target + future_needed) so makespan is
            minimized. Iterative; bounded by MAX_CHARGES_PER_LEG."""
            if not have_cs:
                return
            MAX_CHARGES_PER_LEG = 6
            for _ in range(MAX_CHARGES_PER_LEG):
                leg = dist(pos_ref[0], target_pos)
                leg_e = leg * (1.0 + carried)
                if leg_e <= st['battery']:
                    return
                best_cs = None
                best_extra = INF
                best_d_to = 0.0
                for cs in cs_points:
                    d_to = dist(pos_ref[0], cs)
                    e_to = d_to * (1.0 + carried)
                    if e_to > st['battery']:
                        continue
                    d_from = dist(cs, target_pos)
                    e_from = d_from * (1.0 + carried)
                    if e_from > BATTERY_CAP:
                        continue
                    extra = e_to + e_from - leg_e
                    if extra < best_extra:
                        best_extra = extra
                        best_cs = cs
                        best_d_to = d_to
                if best_cs is None:
                    return
                e_cs_to_target = dist(best_cs, target_pos) * (1.0 + carried)
                needed_from_cs = e_cs_to_target + future_needed
                depart = nfz_wait_until(pos_ref[0], best_cs, st['t'])
                if depart > st['t']:
                    st['path'].append({
                        'x': pos_ref[0][0], 'y': pos_ref[0][1],
                        't': round(depart, 6), 'action': 'WAIT',
                    })
                    st['t'] = depart
                st['t'] += best_d_to / SPEED
                st['battery'] -= best_d_to * (1.0 + carried)
                st['path'].append({
                    'x': best_cs[0], 'y': best_cs[1],
                    't': round(st['t'], 6), 'action': 'CHARGE',
                })
                # Charge MINIMALLY: just enough for leg-to-target + remainder of trip.
                target_battery = needed_from_cs
                if target_battery > BATTERY_CAP:
                    target_battery = BATTERY_CAP
                charge_amount = target_battery - st['battery']
                if charge_amount < 0.0:
                    charge_amount = 0.0
                charge_time = charge_amount / CHARGE_RATE
                st['t'] += charge_time
                st['battery'] += charge_amount
                st['path'].append({
                    'x': best_cs[0], 'y': best_cs[1],
                    't': round(st['t'], 6), 'action': 'CHARGE_COMPLETE',
                })
                pos_ref[0] = best_cs

        pos_ref = [pos]

        # Precompute leg energies and a suffix-sum of remaining trip energy
        # so charging can stop as soon as it has enough to finish the trip.
        n_ord = len(ordered)
        positions = [(wx, wy)] + [(d['x'], d['y']) for d in ordered] + [(wx, wy)]
        carried_at_leg = [0.0] * (n_ord + 1)
        carried_at_leg[0] = sum(float(d['weight']) for d in ordered)
        for i in range(1, n_ord + 1):
            carried_at_leg[i] = carried_at_leg[i - 1] - float(ordered[i - 1]['weight'])
        leg_energies = [0.0] * (n_ord + 1)
        for i in range(n_ord + 1):
            ld = dist(positions[i], positions[i + 1])
            leg_energies[i] = ld * (1.0 + carried_at_leg[i])
        # suffix_e[i] = energy of legs i..n_ord
        suffix_e = [0.0] * (n_ord + 2)
        for i in range(n_ord, -1, -1):
            suffix_e[i] = suffix_e[i + 1] + leg_energies[i]

        for idx, d in enumerate(ordered):
            nxt_pos = (float(d['x']), float(d['y']))
            # future_needed = energy of legs AFTER this one (idx+1..n_ord)
            future_needed = suffix_e[idx + 1]
            maybe_charge(nxt_pos, carried, future_needed)
            depart = nfz_wait_until(pos_ref[0], nxt_pos, st['t'])
            if depart > st['t']:
                st['path'].append({
                    'x': pos_ref[0][0],
                    'y': pos_ref[0][1],
                    't': round(depart, 6),
                    'action': 'WAIT',
                })
                st['t'] = depart
            leg = dist(pos_ref[0], nxt_pos)
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
            pos_ref[0] = nxt_pos

        maybe_charge((wx, wy), carried, 0.0)
        depart = nfz_wait_until(pos_ref[0], (wx, wy), st['t'])
        if depart > st['t']:
            st['path'].append({
                'x': pos_ref[0][0],
                'y': pos_ref[0][1],
                't': round(depart, 6),
                'action': 'WAIT',
            })
            st['t'] = depart
        leg = dist(pos_ref[0], (wx, wy))
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
