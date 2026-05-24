// Drone delivery scheduler - C++ port for performance.
// Compile: g++ -O2 -std=c++17 -o drone_scheduler drone_scheduler.cpp
// Run: ./drone_scheduler < input.json > output.json

#include <bits/stdc++.h>
using namespace std;

// ============================================================================
// Minimal JSON parser (sufficient for the well-formed problem input).
// ============================================================================

struct JsonVal {
    int type = 0; // 0=null 1=bool 2=num 3=str 4=arr 5=obj
    double n = 0;
    string s;
    vector<JsonVal> arr;
    vector<pair<string, JsonVal>> obj;
};

static const char* P;

static void skipWS() {
    while (*P == ' ' || *P == '\n' || *P == '\t' || *P == '\r') P++;
}

static string parseStr() {
    P++; // opening "
    string r;
    while (*P && *P != '"') {
        if (*P == '\\') {
            P++;
            if (*P == 'n') r += '\n';
            else if (*P == 't') r += '\t';
            else if (*P == '"') r += '"';
            else if (*P == '\\') r += '\\';
            else if (*P == '/') r += '/';
            else r += *P;
            P++;
        } else {
            r += *P++;
        }
    }
    if (*P == '"') P++;
    return r;
}

static JsonVal parseVal() {
    skipWS();
    JsonVal v;
    if (*P == '"') {
        v.type = 3;
        v.s = parseStr();
    } else if (*P == 't') {
        v.type = 1; v.n = 1;
        P += 4;
    } else if (*P == 'f') {
        v.type = 1; v.n = 0;
        P += 5;
    } else if (*P == 'n') {
        v.type = 0;
        P += 4;
    } else if (*P == '[') {
        v.type = 4;
        P++; skipWS();
        while (*P != ']') {
            v.arr.push_back(parseVal());
            skipWS();
            if (*P == ',') { P++; skipWS(); }
        }
        P++;
    } else if (*P == '{') {
        v.type = 5;
        P++; skipWS();
        while (*P != '}') {
            skipWS();
            string key = parseStr();
            skipWS();
            if (*P == ':') P++;
            v.obj.push_back({key, parseVal()});
            skipWS();
            if (*P == ',') { P++; skipWS(); }
        }
        P++;
    } else {
        v.type = 2;
        char* end;
        v.n = strtod(P, &end);
        P = end;
    }
    return v;
}

static const JsonVal* J_find(const JsonVal& o, const string& k) {
    if (o.type != 5) return nullptr;
    for (auto& p : o.obj) if (p.first == k) return &p.second;
    return nullptr;
}
static double J_num(const JsonVal& v) { return v.n; }
static const string& J_str(const JsonVal& v) { return v.s; }

// ============================================================================
// Globals and constants.
// ============================================================================

constexpr double BATTERY_CAP = 500.0;
constexpr double SPEED = 1.0;
constexpr double CHARGE_RATE = 2.0;
constexpr int    MAX_TRIP_SIZE = 18;        // bigger thanks to C++ speed
constexpr int    MAX_CANDIDATES_SCAN = 200;
constexpr int    BRUTE_LIMIT = 9;           // 8! = 40320 perms, OK in C++
constexpr double INF_D = 1e18;

double wx, wy;
double TRIP_ENERGY_CAP;
bool   have_nfz, have_cs;
bool   eval_uses_nfz;

// Deliveries (indexed by int id; the string id is preserved separately).
int N_DEL;
vector<string> d_id;
vector<double> d_x, d_y, d_w, d_dl, d_wdist;

// Drones.
int N_DRONE;
vector<string> dr_id;
vector<double> dr_payload;

// Charging stations.
struct CS { double x, y; };
vector<CS> cs_points;

// No-fly zones (normalized).
struct NFZ {
    char kind; // 'c' or 'r'
    double T_start, T_end;
    double cx, cy, r;          // circle
    double xmin, ymin, xmax, ymax; // rectangle
};
vector<NFZ> nfz_norm;

// ============================================================================
// Geometry helpers.
// ============================================================================

static inline double dist2(double x1, double y1, double x2, double y2) {
    double dx = x1 - x2, dy = y1 - y2;
    return dx * dx + dy * dy;
}
static inline double dist(double x1, double y1, double x2, double y2) {
    return sqrt(dist2(x1, y1, x2, y2));
}

// Returns {enter, exit} time in [t1, t2] when segment p1->p2 (linear in time)
// is inside circle (cx,cy,r). Returns {-1,-1} if no intersection.
static inline void seg_circle_iv(double x1, double y1, double x2, double y2,
                                 double t1, double t2,
                                 double cx, double cy, double r,
                                 double& out_lo, double& out_hi) {
    double dxv = x2 - x1, dyv = y2 - y1;
    double fxv = x1 - cx, fyv = y1 - cy;
    double a = dxv * dxv + dyv * dyv;
    if (a == 0.0) {
        double d0 = sqrt(fxv * fxv + fyv * fyv);
        if (d0 <= r) { out_lo = t1; out_hi = t2; return; }
        out_lo = -1; out_hi = -1; return;
    }
    double b = 2.0 * (fxv * dxv + fyv * dyv);
    double c = fxv * fxv + fyv * fyv - r * r;
    double disc = b * b - 4.0 * a * c;
    if (disc < 0.0) { out_lo = -1; out_hi = -1; return; }
    double sd = sqrt(disc);
    double s1 = (-b - sd) / (2.0 * a);
    double s2 = (-b + sd) / (2.0 * a);
    double s_lo = s1 > 0.0 ? s1 : 0.0;
    double s_hi = s2 < 1.0 ? s2 : 1.0;
    if (s_lo > s_hi) { out_lo = -1; out_hi = -1; return; }
    out_lo = t1 + s_lo * (t2 - t1);
    out_hi = t1 + s_hi * (t2 - t1);
}

static inline void seg_rect_iv(double x1, double y1, double x2, double y2,
                               double t1, double t2,
                               double xmin, double ymin, double xmax, double ymax,
                               double& out_lo, double& out_hi) {
    double dxv = x2 - x1, dyv = y2 - y1;
    double t_lo = 0.0, t_hi = 1.0;
    // x slab
    if (fabs(dxv) < 1e-12) {
        if (x1 < xmin || x1 > xmax) { out_lo = -1; out_hi = -1; return; }
    } else {
        double s1 = (xmin - x1) / dxv;
        double s2 = (xmax - x1) / dxv;
        if (s1 > s2) swap(s1, s2);
        if (s1 > t_lo) t_lo = s1;
        if (s2 < t_hi) t_hi = s2;
        if (t_lo > t_hi) { out_lo = -1; out_hi = -1; return; }
    }
    // y slab
    if (fabs(dyv) < 1e-12) {
        if (y1 < ymin || y1 > ymax) { out_lo = -1; out_hi = -1; return; }
    } else {
        double s1 = (ymin - y1) / dyv;
        double s2 = (ymax - y1) / dyv;
        if (s1 > s2) swap(s1, s2);
        if (s1 > t_lo) t_lo = s1;
        if (s2 < t_hi) t_hi = s2;
        if (t_lo > t_hi) { out_lo = -1; out_hi = -1; return; }
    }
    out_lo = t1 + t_lo * (t2 - t1);
    out_hi = t1 + t_hi * (t2 - t1);
}

static double nfz_wait_until(double px, double py, double tx, double ty, double t_depart) {
    if (!have_nfz) return t_depart;
    double leg_len = dist(px, py, tx, ty);
    if (leg_len == 0.0) return t_depart;
    double wait_to = t_depart;
    int max_iter = (int)nfz_norm.size() * 2 + 2;
    for (int it = 0; it < max_iter; it++) {
        bool blocked = false;
        double t1 = wait_to;
        double t2 = wait_to + leg_len / SPEED;
        for (const auto& z : nfz_norm) {
            if (t1 > z.T_end) continue;
            double iv_lo, iv_hi;
            if (z.kind == 'c') {
                seg_circle_iv(px, py, tx, ty, t1, t2, z.cx, z.cy, z.r, iv_lo, iv_hi);
            } else {
                seg_rect_iv(px, py, tx, ty, t1, t2, z.xmin, z.ymin, z.xmax, z.ymax, iv_lo, iv_hi);
            }
            if (iv_lo < 0) continue;
            if (iv_hi >= z.T_start && iv_lo <= z.T_end) {
                double new_wait = z.T_end + 1e-6;
                if (new_wait > wait_to) {
                    wait_to = new_wait;
                    blocked = true;
                    break;
                }
            }
        }
        if (!blocked) return wait_to;
    }
    return wait_to;
}

// ============================================================================
// Permutation evaluation.
// ============================================================================

// Items are referenced by delivery index (int).

// eval_perm: returns energy, on-time count, t_end of trip ending back at warehouse.
// If eval_uses_nfz, includes NFZ wait time per leg (so brute force picks
// permutations that avoid NFZ).
static inline void eval_perm(const int* items, int n, double depart_t,
                             double& out_e, int& out_ot, double& out_t_end) {
    if (n == 0) { out_e = 0.0; out_ot = 0; out_t_end = depart_t; return; }
    double total_w = 0.0;
    for (int i = 0; i < n; i++) total_w += d_w[items[i]];
    double carried = total_w;
    double t = depart_t;
    double e = 0.0;
    int on_time = 0;
    double px = wx, py = wy;
    for (int i = 0; i < n; i++) {
        int idx = items[i];
        double nx = d_x[idx], ny = d_y[idx];
        if (eval_uses_nfz) {
            double tw = nfz_wait_until(px, py, nx, ny, t);
            if (tw > t) t = tw;
        }
        double leg = dist(px, py, nx, ny);
        t += leg / SPEED;
        e += leg * (1.0 + carried);
        if (t <= d_dl[idx]) on_time++;
        carried -= d_w[idx];
        px = nx; py = ny;
    }
    if (eval_uses_nfz) {
        double tw = nfz_wait_until(px, py, wx, wy, t);
        if (tw > t) t = tw;
    }
    double leg_r = dist(px, py, wx, wy);
    e += leg_r;
    out_e = e;
    out_ot = on_time;
    out_t_end = t + leg_r / SPEED;
}

// trip_actual_score: full execution simulation incl. NFZ + min-charging.
// Returns {0, 1e18, 1e18} on infeasibility.
static void trip_actual_score(const int* items, int n, double depart_t,
                              int& out_ot, double& out_e, double& out_t_end) {
    if (n == 0) { out_ot = 0; out_e = 0.0; out_t_end = depart_t; return; }
    // Carried per leg, positions, suffix energy.
    static thread_local vector<double> carrieds, leg_energies, suffix_e;
    static thread_local vector<double> px_, py_;
    carrieds.assign(n + 1, 0.0);
    px_.assign(n + 2, 0.0); py_.assign(n + 2, 0.0);
    px_[0] = wx; py_[0] = wy;
    px_[n + 1] = wx; py_[n + 1] = wy;
    double total_w = 0.0;
    for (int i = 0; i < n; i++) {
        px_[i + 1] = d_x[items[i]];
        py_[i + 1] = d_y[items[i]];
        total_w += d_w[items[i]];
    }
    carrieds[0] = total_w;
    for (int i = 1; i <= n; i++) carrieds[i] = carrieds[i - 1] - d_w[items[i - 1]];
    leg_energies.assign(n + 1, 0.0);
    for (int i = 0; i <= n; i++) {
        leg_energies[i] = dist(px_[i], py_[i], px_[i + 1], py_[i + 1]) * (1.0 + carrieds[i]);
    }
    suffix_e.assign(n + 2, 0.0);
    for (int i = n; i >= 0; i--) suffix_e[i] = suffix_e[i + 1] + leg_energies[i];

    double pos_x = px_[0], pos_y = py_[0];
    double battery = BATTERY_CAP;
    double t = depart_t;
    double energy = 0.0;
    int on_time = 0;
    constexpr double SAFETY = 1e-6;
    for (int i = 0; i <= n; i++) {
        double tx = px_[i + 1], ty = py_[i + 1];
        double carried = carrieds[i];
        double future_after = suffix_e[i + 1];
        bool charge_ok = false;
        for (int it = 0; it < 8; it++) {
            double leg_d = dist(pos_x, pos_y, tx, ty);
            double leg_e = leg_d * (1.0 + carried);
            if (leg_e <= battery + SAFETY) { charge_ok = true; break; }
            if (!have_cs) { out_ot = 0; out_e = 1e18; out_t_end = 1e18; return; }
            int best = -1;
            double best_extra = INF_D;
            double best_e_to = 0, best_e_from = 0;
            for (size_t k = 0; k < cs_points.size(); k++) {
                double e_to = dist(pos_x, pos_y, cs_points[k].x, cs_points[k].y) * (1.0 + carried);
                if (e_to > battery + SAFETY) continue;
                double e_from = dist(cs_points[k].x, cs_points[k].y, tx, ty) * (1.0 + carried);
                if (e_from > BATTERY_CAP + SAFETY) continue;
                double extra = e_to + e_from - leg_e;
                if (extra < best_extra) {
                    best_extra = extra;
                    best = (int)k;
                    best_e_to = e_to;
                    best_e_from = e_from;
                }
            }
            if (best < 0) { out_ot = 0; out_e = 1e18; out_t_end = 1e18; return; }
            double d_to_cs = dist(pos_x, pos_y, cs_points[best].x, cs_points[best].y);
            if (have_nfz) {
                double tw = nfz_wait_until(pos_x, pos_y, cs_points[best].x, cs_points[best].y, t);
                if (tw > t) t = tw;
            }
            t += d_to_cs / SPEED;
            battery -= best_e_to;
            energy += best_e_to;
            pos_x = cs_points[best].x;
            pos_y = cs_points[best].y;
            double needed = best_e_from + future_after;
            double target_battery = needed > BATTERY_CAP ? BATTERY_CAP : needed;
            double charge_amount = target_battery - battery;
            if (charge_amount < 0.0) charge_amount = 0.0;
            t += charge_amount / CHARGE_RATE;
            battery += charge_amount;
        }
        if (!charge_ok) { out_ot = 0; out_e = 1e18; out_t_end = 1e18; return; }
        if (have_nfz) {
            double tw = nfz_wait_until(pos_x, pos_y, tx, ty, t);
            if (tw > t) t = tw;
        }
        double leg_d = dist(pos_x, pos_y, tx, ty);
        double leg_e = leg_d * (1.0 + carried);
        battery -= leg_e;
        energy += leg_e;
        t += leg_d / SPEED;
        pos_x = tx; pos_y = ty;
        if (i < n) {
            if (t <= d_dl[items[i]]) on_time++;
        }
    }
    out_ot = on_time;
    out_e = energy;
    out_t_end = t;
}

// is_trip_feasible: same simulation but only returns feasibility.
static bool is_trip_feasible(const int* items, int n) {
    if (n == 0) return true;
    static thread_local vector<double> carrieds;
    carrieds.assign(n + 1, 0.0);
    double total_w = 0.0;
    for (int i = 0; i < n; i++) total_w += d_w[items[i]];
    carrieds[0] = total_w;
    for (int i = 1; i <= n; i++) carrieds[i] = carrieds[i - 1] - d_w[items[i - 1]];
    double pos_x = wx, pos_y = wy;
    double battery = BATTERY_CAP;
    constexpr double SAFETY = 1e-6;
    // Precompute suffix e
    static thread_local vector<double> leg_e_arr, suffix_e;
    leg_e_arr.assign(n + 1, 0.0);
    static thread_local vector<double> px_, py_;
    px_.assign(n + 2, 0.0); py_.assign(n + 2, 0.0);
    px_[0] = wx; py_[0] = wy;
    px_[n + 1] = wx; py_[n + 1] = wy;
    for (int i = 0; i < n; i++) { px_[i + 1] = d_x[items[i]]; py_[i + 1] = d_y[items[i]]; }
    for (int i = 0; i <= n; i++) leg_e_arr[i] = dist(px_[i], py_[i], px_[i + 1], py_[i + 1]) * (1.0 + carrieds[i]);
    suffix_e.assign(n + 2, 0.0);
    for (int i = n; i >= 0; i--) suffix_e[i] = suffix_e[i + 1] + leg_e_arr[i];

    for (int i = 0; i <= n; i++) {
        double tx = px_[i + 1], ty = py_[i + 1];
        double carried = carrieds[i];
        double future_after = suffix_e[i + 1];
        bool charge_ok = false;
        for (int it = 0; it < 8; it++) {
            double leg_e = dist(pos_x, pos_y, tx, ty) * (1.0 + carried);
            if (leg_e <= battery + SAFETY) { charge_ok = true; break; }
            if (!have_cs) return false;
            int best = -1;
            double best_extra = INF_D;
            double best_e_to = 0, best_e_from = 0;
            for (size_t k = 0; k < cs_points.size(); k++) {
                double e_to = dist(pos_x, pos_y, cs_points[k].x, cs_points[k].y) * (1.0 + carried);
                if (e_to > battery + SAFETY) continue;
                double e_from = dist(cs_points[k].x, cs_points[k].y, tx, ty) * (1.0 + carried);
                if (e_from > BATTERY_CAP + SAFETY) continue;
                double extra = e_to + e_from - leg_e;
                if (extra < best_extra) {
                    best_extra = extra;
                    best = (int)k;
                    best_e_to = e_to;
                    best_e_from = e_from;
                }
            }
            if (best < 0) return false;
            battery -= best_e_to;
            pos_x = cs_points[best].x;
            pos_y = cs_points[best].y;
            double needed = best_e_from + future_after;
            double target_battery = needed > BATTERY_CAP ? BATTERY_CAP : needed;
            if (target_battery > battery) battery = target_battery;
        }
        if (!charge_ok) return false;
        double leg_e = dist(pos_x, pos_y, tx, ty) * (1.0 + carried);
        if (leg_e > battery + SAFETY) return false;
        battery -= leg_e;
        pos_x = tx; pos_y = ty;
    }
    return true;
}

// ============================================================================
// Routing: nearest-neighbor, brute force, 2-opt, best route.
// ============================================================================

static void nn_order(const vector<int>& items, vector<int>& out) {
    out.clear();
    if (items.empty()) return;
    vector<int> pool = items;
    double px = wx, py = wy;
    while (!pool.empty()) {
        int best_i = 0;
        double best_d = dist2(pool[0] >= 0 ? d_x[pool[0]] : 0, pool[0] >= 0 ? d_y[pool[0]] : 0, px, py);
        for (size_t i = 1; i < pool.size(); i++) {
            double dd = dist2(d_x[pool[i]], d_y[pool[i]], px, py);
            if (dd < best_d) { best_d = dd; best_i = (int)i; }
        }
        int picked = pool[best_i];
        out.push_back(picked);
        px = d_x[picked]; py = d_y[picked];
        pool.erase(pool.begin() + best_i);
    }
}

static void best_route_bf(const vector<int>& items, double depart_t,
                          vector<int>& out_ordered, double& out_e, int& out_ot, double& out_t_end) {
    int n = (int)items.size();
    out_ordered.clear();
    if (n == 0) { out_e = 0.0; out_ot = 0; out_t_end = depart_t; return; }
    vector<int> perm = items;
    sort(perm.begin(), perm.end());
    vector<int> best_perm = perm;
    double best_e = 0; int best_ot = -1; double best_t_end = 0;
    bool first = true;
    do {
        double e, t_end; int ot;
        eval_perm(perm.data(), n, depart_t, e, ot, t_end);
        if (first || (-ot < -best_ot) || (-ot == -best_ot && (e < best_e || (e == best_e && t_end < best_t_end)))) {
            best_ot = ot; best_e = e; best_t_end = t_end; best_perm = perm;
            first = false;
        }
    } while (next_permutation(perm.begin(), perm.end()));
    out_ordered = best_perm;
    out_e = best_e; out_ot = best_ot; out_t_end = best_t_end;
}

static void two_opt(vector<int>& perm, double depart_t, int max_rounds = 3) {
    int n = (int)perm.size();
    if (n < 4) return;
    double best_e, best_t_end; int best_ot;
    eval_perm(perm.data(), n, depart_t, best_e, best_ot, best_t_end);
    for (int r = 0; r < max_rounds; r++) {
        bool improved = false;
        for (int i = 0; i < n - 1; i++) {
            for (int j = i + 1; j < n; j++) {
                // reverse perm[i..j]
                reverse(perm.begin() + i, perm.begin() + j + 1);
                double e, t_end; int ot;
                eval_perm(perm.data(), n, depart_t, e, ot, t_end);
                if (-ot < -best_ot || (-ot == -best_ot && (e < best_e || (e == best_e && t_end < best_t_end)))) {
                    best_ot = ot; best_e = e; best_t_end = t_end;
                    improved = true;
                } else {
                    reverse(perm.begin() + i, perm.begin() + j + 1);
                }
            }
        }
        if (!improved) break;
    }
}

static void best_route(const vector<int>& items, double depart_t,
                       vector<int>& out_ordered, double& out_e, int& out_ot, double& out_t_end) {
    int n = (int)items.size();
    out_ordered.clear();
    if (n == 0) { out_e = 0.0; out_ot = 0; out_t_end = depart_t; return; }
    if (n <= BRUTE_LIMIT) {
        best_route_bf(items, depart_t, out_ordered, out_e, out_ot, out_t_end);
        return;
    }
    vector<int> nn; nn_order(items, nn);
    vector<int> dl_sorted = items;
    sort(dl_sorted.begin(), dl_sorted.end(), [](int a, int b) { return d_dl[a] < d_dl[b]; });
    vector<int> opt_nn = nn;  two_opt(opt_nn, depart_t);
    vector<int> opt_dl = dl_sorted; two_opt(opt_dl, depart_t);
    vector<vector<int>*> cands = { &nn, &dl_sorted, &opt_nn, &opt_dl };
    int best_ot = -1; double best_e = 0, best_t_end = 0;
    bool first = true;
    for (auto* c : cands) {
        double e, t_end; int ot;
        eval_perm(c->data(), n, depart_t, e, ot, t_end);
        if (first || -ot < -best_ot || (-ot == -best_ot && (e < best_e || (e == best_e && t_end < best_t_end)))) {
            best_ot = ot; best_e = e; best_t_end = t_end;
            out_ordered = *c;
            first = false;
        }
    }
    out_e = best_e; out_ot = best_ot; out_t_end = best_t_end;
}

// ============================================================================
// Packing strategies.
// ============================================================================

static vector<int> pack_by_deadline(const vector<int>& pool, double max_payload, double depart_t, double energy_cap) {
    vector<int> chosen;
    double cur_w = 0.0;
    int chosen_ot = 0;
    int scan = min((int)pool.size(), MAX_CANDIDATES_SCAN);
    vector<int> tentative;
    vector<int> nn;
    for (int i = 0; i < scan; i++) {
        int idx = pool[i];
        double w = d_w[idx];
        if (w > max_payload) continue;
        if (cur_w + w > max_payload + 1e-9) continue;
        if (depart_t + d_wdist[idx] / SPEED > d_dl[idx]) continue;
        tentative = chosen;
        tentative.push_back(idx);
        nn_order(tentative, nn);
        double e_t, t_end; int ot_t;
        eval_perm(nn.data(), (int)nn.size(), depart_t, e_t, ot_t, t_end);
        if (e_t > energy_cap) continue;
        if (ot_t < chosen_ot + 1) continue;
        chosen.push_back(idx);
        cur_w += w;
        chosen_ot = ot_t;
        if ((int)chosen.size() >= MAX_TRIP_SIZE) break;
    }
    return chosen;
}

static vector<int> pack_by_cluster(const vector<int>& pool, double max_payload, double depart_t, double energy_cap) {
    vector<int> chosen;
    if (pool.empty()) return chosen;
    int scan_n = min((int)pool.size(), MAX_CANDIDATES_SCAN);
    vector<int> candidates(pool.begin(), pool.begin() + scan_n);
    int seed_idx = -1;
    for (int i = 0; i < (int)candidates.size(); i++) {
        if (d_w[candidates[i]] <= max_payload) { seed_idx = i; break; }
    }
    if (seed_idx < 0) return chosen;
    chosen.push_back(candidates[seed_idx]);
    double cur_w = d_w[chosen[0]];
    int chosen_ot;
    double tmp_e, tmp_t;
    eval_perm(chosen.data(), 1, depart_t, tmp_e, chosen_ot, tmp_t);
    vector<int> remaining;
    for (int i = 0; i < (int)candidates.size(); i++) if (candidates[i] != chosen[0]) remaining.push_back(candidates[i]);

    vector<int> tentative;
    vector<int> nn;
    while ((int)chosen.size() < MAX_TRIP_SIZE && !remaining.empty()) {
        double cx = 0, cy = 0;
        for (int x : chosen) { cx += d_x[x]; cy += d_y[x]; }
        cx /= chosen.size(); cy /= chosen.size();
        int best_i = -1;
        double best_d_sq = INF_D;
        double best_dl = INF_D;
        for (int i = 0; i < (int)remaining.size(); i++) {
            int idx = remaining[i];
            double w = d_w[idx];
            if (w > max_payload || cur_w + w > max_payload + 1e-9) continue;
            if (depart_t + d_wdist[idx] / SPEED > d_dl[idx]) continue;
            double d_sq = (d_x[idx] - cx) * (d_x[idx] - cx) + (d_y[idx] - cy) * (d_y[idx] - cy);
            if (d_sq < best_d_sq || (d_sq == best_d_sq && d_dl[idx] < best_dl)) {
                best_d_sq = d_sq;
                best_dl = d_dl[idx];
                best_i = i;
            }
        }
        if (best_i < 0) break;
        int pick = remaining[best_i];
        tentative = chosen;
        tentative.push_back(pick);
        nn_order(tentative, nn);
        double e_t, t_end; int ot_t;
        eval_perm(nn.data(), (int)nn.size(), depart_t, e_t, ot_t, t_end);
        if (e_t > energy_cap || ot_t < chosen_ot + 1) {
            remaining.erase(remaining.begin() + best_i);
            continue;
        }
        chosen.push_back(pick);
        cur_w += d_w[pick];
        chosen_ot = ot_t;
        remaining.erase(remaining.begin() + best_i);
    }
    return chosen;
}

// ============================================================================
// Output path step.
// ============================================================================

struct PathStep {
    double x, y, t;
    string action;
    int delivery_id_idx = -1;   // single (DELIVER)
    vector<int> delivery_ids_idx; // for PICKUP
};

// Drone state.
struct DroneState {
    double t = 0.0;
    double battery = BATTERY_CAP;
    double pos_x, pos_y;
    vector<PathStep> path;
};

// ============================================================================
// Execution: trip step-by-step with NFZ + charging.
// ============================================================================

static double pos_ref_x, pos_ref_y;

// maybe_charge mirrors Python implementation.
static void maybe_charge(double tx, double ty, double carried, double future_needed,
                         DroneState& st) {
    if (!have_cs) return;
    constexpr int MAX_CHARGES_PER_LEG = 6;
    for (int it = 0; it < MAX_CHARGES_PER_LEG; it++) {
        double leg = dist(pos_ref_x, pos_ref_y, tx, ty);
        double leg_e = leg * (1.0 + carried);
        if (leg_e <= st.battery) return;
        int best = -1;
        double best_extra = INF_D;
        double best_d_to = 0;
        for (size_t k = 0; k < cs_points.size(); k++) {
            double d_to = dist(pos_ref_x, pos_ref_y, cs_points[k].x, cs_points[k].y);
            double e_to = d_to * (1.0 + carried);
            if (e_to > st.battery) continue;
            double d_from = dist(cs_points[k].x, cs_points[k].y, tx, ty);
            double e_from = d_from * (1.0 + carried);
            if (e_from > BATTERY_CAP) continue;
            double extra = e_to + e_from - leg_e;
            if (extra < best_extra) {
                best_extra = extra;
                best = (int)k;
                best_d_to = d_to;
            }
        }
        if (best < 0) return;
        double e_cs_to_target = dist(cs_points[best].x, cs_points[best].y, tx, ty) * (1.0 + carried);
        double needed_from_cs = e_cs_to_target + future_needed;
        double depart_t_wait = nfz_wait_until(pos_ref_x, pos_ref_y, cs_points[best].x, cs_points[best].y, st.t);
        if (depart_t_wait > st.t) {
            PathStep ps; ps.x = pos_ref_x; ps.y = pos_ref_y; ps.t = depart_t_wait; ps.action = "WAIT";
            st.path.push_back(ps);
            st.t = depart_t_wait;
        }
        st.t += best_d_to / SPEED;
        st.battery -= best_d_to * (1.0 + carried);
        {
            PathStep ps; ps.x = cs_points[best].x; ps.y = cs_points[best].y; ps.t = st.t; ps.action = "CHARGE";
            st.path.push_back(ps);
        }
        double target_battery = needed_from_cs > BATTERY_CAP ? BATTERY_CAP : needed_from_cs;
        double charge_amount = target_battery - st.battery;
        if (charge_amount < 0.0) charge_amount = 0.0;
        double charge_time = charge_amount / CHARGE_RATE;
        st.t += charge_time;
        st.battery += charge_amount;
        {
            PathStep ps; ps.x = cs_points[best].x; ps.y = cs_points[best].y; ps.t = st.t; ps.action = "CHARGE_COMPLETE";
            st.path.push_back(ps);
        }
        pos_ref_x = cs_points[best].x;
        pos_ref_y = cs_points[best].y;
    }
}

// ============================================================================
// JSON output.
// ============================================================================

static void print_num(double x) {
    // Match Python's compact float output (avoid e-notation for typical range).
    char buf[64];
    if (x == (long long)x && fabs(x) < 1e15) {
        snprintf(buf, sizeof(buf), "%.1f", x);
    } else {
        snprintf(buf, sizeof(buf), "%.6f", x);
        // Trim trailing zeros but keep at least one decimal
        int len = (int)strlen(buf);
        int dot = -1;
        for (int i = 0; i < len; i++) if (buf[i] == '.') { dot = i; break; }
        if (dot >= 0) {
            int end = len - 1;
            while (end > dot + 1 && buf[end] == '0') end--;
            buf[end + 1] = 0;
        }
    }
    fputs(buf, stdout);
}

static void print_str(const string& s) {
    putchar('"');
    for (char c : s) {
        if (c == '"') { putchar('\\'); putchar('"'); }
        else if (c == '\\') { putchar('\\'); putchar('\\'); }
        else putchar(c);
    }
    putchar('"');
}

// ============================================================================
// Main scheduler.
// ============================================================================

int main() {
    // --- Read all stdin ---
    string input;
    {
        char buf[1 << 16];
        ssize_t r;
        while ((r = read(0, buf, sizeof(buf))) > 0) input.append(buf, r);
    }
    P = input.c_str();
    JsonVal root = parseVal();

    // --- Parse map_size, warehouse ---
    {
        const JsonVal* m = J_find(root, "map_size");
        wx = J_num(m->arr[0]) / 2.0;
        wy = J_num(m->arr[1]) / 2.0;
    }

    // --- Parse drones ---
    {
        const JsonVal* dr = J_find(root, "drones");
        N_DRONE = (int)dr->arr.size();
        dr_id.resize(N_DRONE);
        dr_payload.resize(N_DRONE);
        for (int i = 0; i < N_DRONE; i++) {
            dr_id[i] = J_str(*J_find(dr->arr[i], "id"));
            dr_payload[i] = J_num(*J_find(dr->arr[i], "max_payload"));
        }
    }

    // --- Parse deliveries ---
    {
        const JsonVal* dv = J_find(root, "deliveries");
        N_DEL = (int)dv->arr.size();
        d_id.resize(N_DEL); d_x.resize(N_DEL); d_y.resize(N_DEL);
        d_w.resize(N_DEL); d_dl.resize(N_DEL); d_wdist.resize(N_DEL);
        for (int i = 0; i < N_DEL; i++) {
            d_id[i] = J_str(*J_find(dv->arr[i], "id"));
            d_x[i] = J_num(*J_find(dv->arr[i], "x"));
            d_y[i] = J_num(*J_find(dv->arr[i], "y"));
            d_w[i] = J_num(*J_find(dv->arr[i], "weight"));
            d_dl[i] = J_num(*J_find(dv->arr[i], "deadline"));
            d_wdist[i] = dist(d_x[i], d_y[i], wx, wy);
        }
    }

    // --- Parse charging stations ---
    cs_points.clear();
    if (const JsonVal* cs = J_find(root, "charging_stations")) {
        for (auto& c : cs->arr) {
            cs_points.push_back({J_num(*J_find(c, "x")), J_num(*J_find(c, "y"))});
        }
    }
    have_cs = !cs_points.empty();
    TRIP_ENERGY_CAP = have_cs ? BATTERY_CAP * 2.0 : BATTERY_CAP;

    // --- Parse no-fly zones ---
    nfz_norm.clear();
    if (const JsonVal* nz = J_find(root, "no_fly_zones")) {
        for (auto& z : nz->arr) {
            NFZ n; n.kind = 'c';
            const JsonVal* ts = J_find(z, "T_start");
            const JsonVal* te = J_find(z, "T_end");
            n.T_start = ts ? J_num(*ts) : -1e18;
            n.T_end = te ? J_num(*te) : 1e18;
            const JsonVal* sh = J_find(z, "shape");
            string shape = sh ? J_str(*sh) : "circle";
            if (shape == "circle") {
                n.kind = 'c';
                const JsonVal* c = J_find(z, "center");
                n.cx = c->arr[0].n;
                n.cy = c->arr[1].n;
                n.r = J_num(*J_find(z, "radius"));
            } else if (shape == "rectangle") {
                n.kind = 'r';
                const JsonVal* cs2 = J_find(z, "corners");
                if (!cs2 || cs2->arr.size() < 2) continue;
                double xs[8], ys[8];
                int cnt = (int)min((size_t)8, cs2->arr.size());
                for (int i = 0; i < cnt; i++) {
                    xs[i] = cs2->arr[i].arr[0].n;
                    ys[i] = cs2->arr[i].arr[1].n;
                }
                n.xmin = *min_element(xs, xs + cnt);
                n.ymin = *min_element(ys, ys + cnt);
                n.xmax = *max_element(xs, xs + cnt);
                n.ymax = *max_element(ys, ys + cnt);
            } else {
                continue;
            }
            nfz_norm.push_back(n);
        }
    }
    have_nfz = !nfz_norm.empty();
    eval_uses_nfz = have_nfz && N_DEL <= 3000; // higher than Python's 500

    // --- Drone states ---
    vector<DroneState> states(N_DRONE);
    for (int i = 0; i < N_DRONE; i++) {
        states[i].t = 0.0; states[i].battery = BATTERY_CAP;
        states[i].pos_x = wx; states[i].pos_y = wy;
    }

    // --- Pending sorted by deadline ---
    vector<int> pending(N_DEL);
    iota(pending.begin(), pending.end(), 0);
    sort(pending.begin(), pending.end(), [](int a, int b) { return d_dl[a] < d_dl[b]; });

    // --- Active drones ---
    vector<int> active_drones(N_DRONE);
    iota(active_drones.begin(), active_drones.end(), 0);

    // --- Main loop ---
    while (!active_drones.empty() && !pending.empty()) {
        // Pick min-t drone
        int best = active_drones[0];
        double best_t = states[best].t;
        for (size_t i = 1; i < active_drones.size(); i++) {
            if (states[active_drones[i]].t < best_t) {
                best_t = states[active_drones[i]].t;
                best = active_drones[i];
            }
        }
        DroneState& st = states[best];
        double depart_t = st.t;
        double max_payload = dr_payload[best];

        // Pre-filter pending
        {
            vector<int> np;
            np.reserve(pending.size());
            for (int p : pending) {
                if (depart_t + d_wdist[p] / SPEED <= d_dl[p] + 1e-6) np.push_back(p);
            }
            pending = std::move(np);
        }
        if (pending.empty()) break;

        // Pack candidates
        vector<int> pack_a = pack_by_deadline(pending, max_payload, depart_t, BATTERY_CAP);
        vector<int> pack_b = pack_by_cluster(pending, max_payload, depart_t, BATTERY_CAP);
        vector<int> pack_ra, pack_rb;
        if (have_cs && TRIP_ENERGY_CAP > BATTERY_CAP) {
            int strict_sz = max((int)pack_a.size(), (int)pack_b.size());
            if (strict_sz < MAX_TRIP_SIZE) {
                pack_ra = pack_by_deadline(pending, max_payload, depart_t, TRIP_ENERGY_CAP);
                pack_rb = pack_by_cluster(pending, max_payload, depart_t, TRIP_ENERGY_CAP);
            }
        }

        vector<vector<int>*> cands = { &pack_a, &pack_b, &pack_ra, &pack_rb };
        vector<int> best_ordered;
        int best_ot = -1; double best_e = 0, best_t_end = 0;
        bool any = false;
        for (auto* p : cands) {
            if (p->empty()) continue;
            vector<int> ordered_p;
            double e_, t_end_; int ot_;
            best_route(*p, depart_t, ordered_p, e_, ot_, t_end_);
            // Trim infeasible tails
            while (!ordered_p.empty()) {
                bool ok;
                if (have_cs) ok = is_trip_feasible(ordered_p.data(), (int)ordered_p.size());
                else {
                    double et, tend; int ott;
                    eval_perm(ordered_p.data(), (int)ordered_p.size(), depart_t, et, ott, tend);
                    ok = et <= BATTERY_CAP;
                }
                if (ok) break;
                int drop_idx = 0; double drop_dl = d_dl[ordered_p[0]];
                for (size_t k = 1; k < ordered_p.size(); k++) {
                    if (d_dl[ordered_p[k]] > drop_dl) { drop_dl = d_dl[ordered_p[k]]; drop_idx = (int)k; }
                }
                ordered_p.erase(ordered_p.begin() + drop_idx);
                if (!ordered_p.empty()) {
                    vector<int> tmp; double te, ttend; int tot;
                    best_route(ordered_p, depart_t, tmp, te, tot, ttend);
                    ordered_p = tmp;
                }
            }
            if (ordered_p.empty()) continue;
            int sim_ot; double sim_e, sim_t_end;
            trip_actual_score(ordered_p.data(), (int)ordered_p.size(), depart_t, sim_ot, sim_e, sim_t_end);
            if (sim_e >= 1e17) continue;
            if (!any || -sim_ot < -best_ot ||
                (-sim_ot == -best_ot && (sim_e < best_e || (sim_e == best_e && sim_t_end < best_t_end)))) {
                best_ot = sim_ot; best_e = sim_e; best_t_end = sim_t_end;
                best_ordered = ordered_p;
                any = true;
            }
        }

        if (!any || best_ordered.empty()) {
            // Drop this drone
            for (size_t i = 0; i < active_drones.size(); i++) {
                if (active_drones[i] == best) { active_drones.erase(active_drones.begin() + i); break; }
            }
            continue;
        }

        // Execute trip
        vector<int>& ordered = best_ordered;
        int n_ord = (int)ordered.size();

        // PICKUP
        {
            PathStep ps; ps.x = wx; ps.y = wy; ps.t = st.t; ps.action = "PICKUP";
            for (int idx : ordered) ps.delivery_ids_idx.push_back(idx);
            st.path.push_back(ps);
        }

        // Precompute leg energies and suffix.
        vector<double> carried_at_leg(n_ord + 1, 0.0);
        double total_w = 0.0;
        for (int idx : ordered) total_w += d_w[idx];
        carried_at_leg[0] = total_w;
        for (int i = 1; i <= n_ord; i++) carried_at_leg[i] = carried_at_leg[i - 1] - d_w[ordered[i - 1]];
        vector<double> pos_x_arr(n_ord + 2), pos_y_arr(n_ord + 2);
        pos_x_arr[0] = wx; pos_y_arr[0] = wy;
        for (int i = 0; i < n_ord; i++) { pos_x_arr[i + 1] = d_x[ordered[i]]; pos_y_arr[i + 1] = d_y[ordered[i]]; }
        pos_x_arr[n_ord + 1] = wx; pos_y_arr[n_ord + 1] = wy;
        vector<double> leg_energies_(n_ord + 1, 0.0);
        for (int i = 0; i <= n_ord; i++) {
            leg_energies_[i] = dist(pos_x_arr[i], pos_y_arr[i], pos_x_arr[i + 1], pos_y_arr[i + 1]) * (1.0 + carried_at_leg[i]);
        }
        vector<double> suf_e(n_ord + 2, 0.0);
        for (int i = n_ord; i >= 0; i--) suf_e[i] = suf_e[i + 1] + leg_energies_[i];

        pos_ref_x = wx; pos_ref_y = wy;
        double carried = total_w;
        for (int idx_i = 0; idx_i < n_ord; idx_i++) {
            int idx = ordered[idx_i];
            double tx = d_x[idx], ty = d_y[idx];
            double future_needed = suf_e[idx_i + 1];
            maybe_charge(tx, ty, carried, future_needed, st);
            double depart_t_wait = nfz_wait_until(pos_ref_x, pos_ref_y, tx, ty, st.t);
            if (depart_t_wait > st.t) {
                PathStep ps; ps.x = pos_ref_x; ps.y = pos_ref_y; ps.t = depart_t_wait; ps.action = "WAIT";
                st.path.push_back(ps);
                st.t = depart_t_wait;
            }
            double leg = dist(pos_ref_x, pos_ref_y, tx, ty);
            st.t += leg / SPEED;
            st.battery -= leg * (1.0 + carried);
            {
                PathStep ps; ps.x = tx; ps.y = ty; ps.t = st.t; ps.action = "DELIVER";
                ps.delivery_id_idx = idx;
                st.path.push_back(ps);
            }
            carried -= d_w[idx];
            pos_ref_x = tx; pos_ref_y = ty;
        }
        // Return
        maybe_charge(wx, wy, carried, 0.0, st);
        double depart_t_wait = nfz_wait_until(pos_ref_x, pos_ref_y, wx, wy, st.t);
        if (depart_t_wait > st.t) {
            PathStep ps; ps.x = pos_ref_x; ps.y = pos_ref_y; ps.t = depart_t_wait; ps.action = "WAIT";
            st.path.push_back(ps);
            st.t = depart_t_wait;
        }
        double leg = dist(pos_ref_x, pos_ref_y, wx, wy);
        st.t += leg / SPEED;
        st.battery -= leg * (1.0 + carried);
        {
            PathStep ps; ps.x = wx; ps.y = wy; ps.t = st.t; ps.action = "RETURN";
            st.path.push_back(ps);
        }
        st.battery = BATTERY_CAP;
        st.pos_x = wx; st.pos_y = wy;

        // Remove delivered from pending.
        unordered_set<int> chosen_set(ordered.begin(), ordered.end());
        vector<int> new_pending;
        new_pending.reserve(pending.size());
        for (int p : pending) if (!chosen_set.count(p)) new_pending.push_back(p);
        pending = std::move(new_pending);
    }

    // --- Output JSON ---
    printf("{\"flight_manifest\": [");
    for (int i = 0; i < N_DRONE; i++) {
        if (i > 0) printf(", ");
        printf("{\"drone_id\": ");
        print_str(dr_id[i]);
        printf(", \"path\": [");
        const auto& path = states[i].path;
        for (size_t j = 0; j < path.size(); j++) {
            if (j > 0) printf(", ");
            const auto& s = path[j];
            printf("{\"x\": "); print_num(s.x);
            printf(", \"y\": "); print_num(s.y);
            printf(", \"t\": "); print_num(s.t);
            printf(", \"action\": "); print_str(s.action);
            if (s.delivery_id_idx >= 0) {
                printf(", \"delivery_id\": ");
                print_str(d_id[s.delivery_id_idx]);
            }
            if (!s.delivery_ids_idx.empty()) {
                printf(", \"delivery_ids\": [");
                for (size_t k = 0; k < s.delivery_ids_idx.size(); k++) {
                    if (k > 0) printf(", ");
                    print_str(d_id[s.delivery_ids_idx[k]]);
                }
                printf("]");
            }
            printf("}");
        }
        printf("]}");
    }
    printf("]}\n");

    return 0;
}
