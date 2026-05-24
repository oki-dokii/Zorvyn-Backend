import sys
import copy


def _read_input():
    data = sys.stdin.read().split()
    p = [0]

    def take(n=1):
        vals = data[p[0]:p[0] + n]
        p[0] += n
        return vals

    N, D, H = int(take()[0]), int(take()[0]), int(take()[0])

    users = []
    for _ in range(N):
        name = take()[0]
        budget = int(take()[0])
        energy = int(take()[0])
        k = int(take()[0])
        tags = set(take(k))
        users.append({'name': name, 'budget': budget,
                      'energy': energy, 'tags': tags, 'active': True})

    A = int(take()[0])
    activities = {}
    for _ in range(A):
        aid = int(take()[0])
        aname = take()[0]
        cost = int(take()[0])
        dur = int(take()[0])
        ec = int(take()[0])
        tag = take()[0]
        activities[aid] = {'id': aid, 'name': aname, 'cost': cost,
                           'duration': dur, 'energy': ec, 'tag': tag}

    E = int(take()[0])
    events = []
    for _ in range(E):
        etype = take()[0]
        if etype == 'DROP':
            day = take()[0]
            user = take()[0]
            events.append(f"DROP {day} {user}")
        elif etype == 'WEATHER':
            day = take()[0]
            tag = take()[0]
            events.append(f"WEATHER {day} {tag}")
        elif etype == 'FATIGUE':
            day = take()[0]
            user = take()[0]
            ne = take()[0]
            events.append(f"FATIGUE {day} {user} {ne}")
        elif etype == 'BUDGET':
            day = take()[0]
            user = take()[0]
            nb = take()[0]
            events.append(f"BUDGET {day} {user} {nb}")
    return N, D, H, users, activities, events


def fmt_day(day, ids, cost, sat):
    if not ids:
        return f"Day {day}: REST | cost=0 satisfaction=0"
    return (f"Day {day}: "
            f"{' '.join(str(i) for i in sorted(ids))}"
            f" | cost={cost} satisfaction={sat}")


def apply_events_for_day(users_start, active_events, target_day):
    """Apply persistent events with ev_day <= target_day, plus WEATHER only
    when ev_day == target_day. Returns (updated users, blocked_tags_set)."""
    users = copy.deepcopy(users_start)
    weather_for_target = set()

    for ev in active_events:
        parts = ev.split()
        etype = parts[0]
        ev_day = int(parts[1])
        if ev_day > target_day:
            continue

        if etype == 'DROP':
            uname = parts[2]
            for u in users:
                if u['name'] == uname:
                    u['active'] = False
        elif etype == 'FATIGUE':
            uname = parts[2]
            new_energy = int(parts[3])
            for u in users:
                if u['name'] == uname:
                    u['energy'] = new_energy
        elif etype == 'BUDGET':
            uname = parts[2]
            new_budget = int(parts[3])
            for u in users:
                if u['name'] == uname:
                    u['budget'] = new_budget
        elif etype == 'WEATHER':
            if ev_day == target_day:
                weather_for_target.add(parts[2])

    return users, weather_for_target


def best_subset_for_day(H, users_now, activities, used_ids, blocked_tags):
    """Branch-and-bound search for the lexicographically smallest
    (-satisfaction, cost, sorted_ids) over all feasible subsets.

    Crucially the empty subset (0, 0, []) is the baseline candidate, so when
    every non-empty feasible subset has sat=0 and cost>0, REST wins per the
    lex rule.
    """
    active_users = [u for u in users_now if u['active']]
    if not active_users:
        return ([], 0, 0)

    min_budget = min(u['budget'] for u in active_users)
    min_energy = min(u['energy'] for u in active_users)

    eligible = [
        a for a in activities.values()
        if a['id'] not in used_ids and a['tag'] not in blocked_tags
    ]
    eligible.sort(key=lambda a: a['id'])
    n = len(eligible)

    sat_per = [0] * n
    for i, a in enumerate(eligible):
        sat_per[i] = sum(1 for u in active_users if a['tag'] in u['tags'])

    # Suffix-sum of max possible additional satisfaction starting at index i.
    suffix_max_sat = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        suffix_max_sat[i] = suffix_max_sat[i + 1] + sat_per[i]

    # Baseline: empty subset is always feasible.
    best_key = (0, 0, [])
    best_ids = []
    best_cost = 0
    best_sat = 0

    cost_a = [a['cost'] for a in eligible]
    energy_a = [a['energy'] for a in eligible]
    dur_a = [a['duration'] for a in eligible]
    id_a = [a['id'] for a in eligible]

    def dfs(idx, cur_cost, cur_energy, cur_dur, cur_sat, cur_ids):
        nonlocal best_key, best_ids, best_cost, best_sat

        key = (-cur_sat, cur_cost, list(cur_ids))
        if key < best_key:
            best_key = key
            best_ids = list(cur_ids)
            best_cost = cur_cost
            best_sat = cur_sat

        # If even taking every remaining unit of sat cannot match the current
        # best, no descendant can beat it (and we already recorded this state).
        if cur_sat + suffix_max_sat[idx] < best_sat:
            return

        for i in range(idx, n):
            new_cost = cur_cost + cost_a[i]
            if new_cost > min_budget:
                continue
            new_energy = cur_energy + energy_a[i]
            if new_energy > min_energy:
                continue
            new_dur = cur_dur + dur_a[i]
            if new_dur > H:
                continue
            cur_ids.append(id_a[i])
            dfs(i + 1, new_cost, new_energy, new_dur,
                cur_sat + sat_per[i], cur_ids)
            cur_ids.pop()

    dfs(0, 0, 0, 0, 0, [])
    return (best_ids, best_cost, best_sat)


def plan_days(start_day, D, H, users_initial, activities,
              active_events, locked_used_ids):
    used_ids = set(locked_used_ids)
    results = []
    for day in range(start_day, D + 1):
        users_now, blocked_tags = apply_events_for_day(
            users_initial, active_events, day)
        ids, cost, sat = best_subset_for_day(
            H, users_now, activities, used_ids, blocked_tags)
        results.append((day, ids, cost, sat))
        used_ids.update(ids)
    return results


def plan_trip(N, D, H, users, activities, events):
    lines = []

    lines.append("=== PLAN ===")
    initial = plan_days(1, D, H, users, activities, [], set())
    day_results = list(initial)

    for day, ids, cost, sat in day_results:
        lines.append(fmt_day(day, ids, cost, sat))

    def cumulative_used_before(day):
        used = set()
        for d, ids, _c, _s in day_results:
            if d < day:
                used.update(ids)
        return used

    active_events = []
    for ev_idx, ev in enumerate(events, 1):
        active_events.append(ev)
        parts = ev.split()
        ev_day = int(parts[1])

        lines.append(f"=== EVENT {ev_idx}: {ev} ===")

        locked_used = cumulative_used_before(ev_day)
        replan = plan_days(
            ev_day, D, H, users, activities, active_events, locked_used)

        for entry in replan:
            day_results[entry[0] - 1] = entry
            lines.append(fmt_day(entry[0], entry[1], entry[2], entry[3]))

    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    _N, _D, _H, _users, _activities, _events = _read_input()
    sys.stdout.write(plan_trip(_N, _D, _H, _users, _activities, _events))
