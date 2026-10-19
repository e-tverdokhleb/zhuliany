"""2D-геометрія плану (чистий Python, без Fusion). Усі координати в мм."""

import math

EPS = 1e-6


def polygon_area(pts):
    """Знакова площа (додатна для обходу проти годинникової стрілки)."""
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def ensure_ccw(pts):
    return list(pts) if polygon_area(pts) >= 0 else list(reversed(pts))


def edges(pts):
    n = len(pts)
    return [(pts[i], pts[(i + 1) % n]) for i in range(n)]


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def mul(a, k):
    return (a[0] * k, a[1] * k)


def length(v):
    return math.hypot(v[0], v[1])


def unit(v):
    l = length(v)
    if l < EPS:
        raise ValueError("Нульовий вектор")
    return (v[0] / l, v[1] / l)


def outward_normal_ccw(a, b):
    """Зовнішня нормаль ребра a→b полігону з обходом проти годинникової стрілки."""
    d = unit(sub(b, a))
    return (d[1], -d[0])


def point_in_polygon(p, pts, tol=0.5):
    """True, якщо точка всередині або на межі (з допуском tol мм)."""
    for a, b in edges(pts):
        if dist_point_segment(p, a, b) <= tol:
            return True
    x, y = p
    inside = False
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if xi > x:
                inside = not inside
    return inside


def dist_point_segment(p, a, b):
    ab = sub(b, a)
    l2 = ab[0] ** 2 + ab[1] ** 2
    if l2 < EPS:
        return length(sub(p, a))
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / l2))
    proj = (a[0] + ab[0] * t, a[1] + ab[1] * t)
    return length(sub(p, proj))


def ray_segment(origin, direction, a, b):
    """Відстань t>0 уздовж променя до перетину з відрізком a-b, або None."""
    dx, dy = direction
    ex, ey = b[0] - a[0], b[1] - a[1]
    denom = dx * ey - dy * ex
    if abs(denom) < EPS:
        return None
    ox, oy = a[0] - origin[0], a[1] - origin[1]
    t = (ox * ey - oy * ex) / denom
    u = (ox * dy - oy * dx) / denom
    if t > EPS and -EPS <= u <= 1 + EPS:
        return t
    return None


def raycast(origin, direction, targets):
    """targets: список (tag, [точки полігону]). Повертає (t, tag) найближчого перетину або (None, None)."""
    best_t, best_tag = None, None
    for tag, pts in targets:
        for a, b in edges(pts):
            t = ray_segment(origin, direction, a, b)
            if t is not None and (best_t is None or t < best_t):
                best_t, best_tag = t, tag
    return best_t, best_tag


def clip_convex(subject, clip):
    """Перетин полігону subject з опуклим полігоном clip (Сазерленд — Ходжмен)."""
    clip = ensure_ccw(clip)
    output = list(subject)
    for a, b in edges(clip):
        if not output:
            break
        inp, output = output, []

        def inside(p):
            return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= -EPS

        def inter(p, q):
            x1, y1 = p
            x2, y2 = q
            x3, y3 = a
            x4, y4 = b
            den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if abs(den) < EPS:
                return q
            t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
            return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))

        for i in range(len(inp)):
            cur, prev = inp[i], inp[i - 1]
            if inside(cur):
                if not inside(prev):
                    output.append(inter(prev, cur))
                output.append(cur)
            elif inside(prev):
                output.append(inter(prev, cur))
    return output


def overlap_area(p1, p2):
    """Площа перетину двох опуклих полігонів (мм²)."""
    res = clip_convex(ensure_ccw(p1), p2)
    return abs(polygon_area(res)) if len(res) >= 3 else 0.0


def offset_polygon(pts, d):
    """Зсув полігону всередину на d (для простих полігонів без самоперетинів)."""
    pts = ensure_ccw(pts)
    n = len(pts)
    lines = []
    for a, b in edges(pts):
        nrm = outward_normal_ccw(a, b)
        shift = mul(nrm, -d)
        lines.append((add(a, shift), add(b, shift)))
    out = []
    for i in range(n):
        (p1, p2), (p3, p4) = lines[i - 1], lines[i]
        x1, y1 = p1
        x2, y2 = p2
        x3, y3 = p3
        x4, y4 = p4
        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(den) < EPS:
            out.append(p3)
            continue
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
        out.append((x1 + t * (x2 - x1), y1 + t * (y2 - y1)))
    return out
