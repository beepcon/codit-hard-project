# 실험 노트북(07·19·21·22)의 채택 코드를 글자 그대로 옮긴 파일. 노트북과 같은 결과가 나오도록 직접 고치지 않는다.
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# 22 "설정" 셀의 값
# 14 F1과 같은 값
DISP_RATIO = 0.02
SHADE_BLEND = 0.6
MUG_HALF_ANGLE = np.deg2rad(60)
# 탐색값
SPEC_SIGMA_RATIO, SPEC_RANGE, SPEC_BLEND = 0.08, 30.0, 0.9
CLOTH_DISP_MULT, CLOTH_DETAIL_SIGMA, CLOTH_DETAIL = 2.0, 2.0, 1.5
TOTE_ROW_RATIO = 0.6
TORSO_SMALL, TORSO_CORE_RATIO = 256, 0.5
# 머그 두 개가 나란히 있는 사진은 한쪽 머그에만 인쇄 (11/02 사용자 결정: mug_04는 왼쪽)
MUG_SIDE = {'mug_04.jpg': 'left'}
# 14 BOX_RULE 머그 (너비 비율, 최대 높이 비율)
MUG_WR, MUG_HMAX = 0.60, 0.45
# 옷 인쇄 영역: (몸통 너비 비율, 몸통 위에서 내려올 비율, 최대 높이 비율)
GARMENT_RULE = {'tshirt': (0.55, 0.20, 0.35), 'hoodie': (0.60, 0.25, 0.35)}
CURVE_FIT_RANGE = 0.8

# 22 함수가 이름으로 찾는 굿즈 사진·마스크·종류·머그 휨·인쇄 영역 (앱이 register로 채움)
GOODS_IMG, GOODS_MASK, KIND, CURVES, BOX, TORSO = {}, {}, {}, {}, {}, {}
# 22 ASPECT: 인쇄할 그림(C 결과, 1216×832)의 가로세로 비율
ASPECT = 1216 / 832


def load_goods(name):
    return GOODS_IMG[name]


def load_mask(name):
    return GOODS_MASK[name]


# ---- 22 "인쇄 영역" 셀 ----
# 14 에코백 비율 (너비 비율, 최대 높이 비율)을 몸통 기준으로 씀
TOTE_WR, TOTE_HMAX = 0.55, 0.45


def tote_box(name):
    m = load_mask(name) > 0.5
    rows = m.sum(1)
    # 손잡이 행은 폭이 좁으므로 가장 넓은 행의 60% 이상인 행만 몸통으로 봄
    body = np.nonzero(rows >= TOTE_ROW_RATIO * rows.max())[0]
    y0, y1 = body.min(), body.max()
    sub = m[y0:y1 + 1]
    xs = np.nonzero(sub.any(0))[0]
    bw, bh = xs.max() - xs.min() + 1, y1 - y0 + 1
    cx = np.median(np.nonzero(sub)[1])
    w = TOTE_WR * bw
    h = w / ASPECT
    if h > TOTE_HMAX * bh:
        h = TOTE_HMAX * bh
        w = h * ASPECT
    return int(cx - w / 2), int(y0 + (bh - h) / 2), int(w), int(h), int(y0), int(y1)


def torso_mask(name):
    m = load_mask(name) > 0.5
    H, W = m.shape
    s = TORSO_SMALL / max(H, W)
    cur = Image.fromarray((m * 255).astype(np.uint8)).resize((max(1, round(W * s)), max(1, round(H * s))), Image.NEAREST)
    small = np.asarray(cur) > 127
    # 3×3로 깎아 낸 횟수 = 경계에서의 거리
    depth = np.zeros(small.shape, np.int32)
    while (np.asarray(cur) > 127).any():
        depth += np.asarray(cur) > 127
        cur = cur.filter(ImageFilter.MinFilter(3))
    maxd = int(depth.max())
    ys, xs = np.nonzero(depth == maxd)
    i = np.argsort(xs)[len(xs) // 2]
    kd = int(round(TORSO_CORE_RATIO * maxd))
    # fromarray 이미지는 배열 메모리를 공유해 floodfill이 반영되지 않으므로 copy
    core = Image.fromarray(((depth >= kd) * 128).astype(np.uint8)).copy()
    ImageDraw.floodfill(core, (int(xs[i]), int(ys[i])), 255)
    comp = Image.fromarray(((np.asarray(core) == 255) * 255).astype(np.uint8))
    for _ in range(kd):
        comp = comp.filter(ImageFilter.MaxFilter(3))
    t = (np.asarray(comp) > 127) & small
    big = (np.asarray(Image.fromarray((t * 255).astype(np.uint8)).resize((W, H), Image.NEAREST)) > 127) & m
    # 가장 깊은 점 = 몸통 가운데, 깊이 × 2 = 몸통 안쪽 너비 (몸통에 붙어 남은 청바지·손에 영향받지 않음)
    return big, float(xs[i] / s), 2 * maxd / s


def garment_box(name, kind):
    t, cx, tw = torso_mask(name)
    TORSO[name] = t
    ys = np.nonzero(t.any(1))[0]
    y0, y1 = ys.min(), ys.max()
    th = y1 - y0 + 1
    wr, top, hmax = GARMENT_RULE[kind]
    w = wr * tw
    h = w / ASPECT
    if h > hmax * th:
        h = hmax * th
        w = h * ASPECT
    return int(cx - w / 2), int(y0 + top * th), int(w), int(h), int(y0), int(y1)


def mug_box_side(name, side):
    m = load_mask(name) > 0.5
    ys, xs = np.nonzero(m)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    body = m[y0:y1 + 1, x0:x1 + 1].sum(0)
    body = body >= 0.6 * body.max()
    runs, i = [], 0
    while i < len(body):
        if body[i]:
            j = i
            while j + 1 < len(body) and body[j + 1]:
                j += 1
            runs.append((i + x0, j + x0))
            i = j + 1
        else:
            i += 1
    l, r = runs[0] if side == 'left' else runs[-1]
    rows_ = np.nonzero(m[:, l:r + 1].any(1))[0]
    by0, bh = rows_.min(), rows_.max() - rows_.min() + 1
    w = MUG_WR * (r - l + 1)
    h = w / ASPECT
    if h > MUG_HMAX * bh:
        h = MUG_HMAX * bh
        w = h * ASPECT
    return int((l + r) / 2 - w / 2), int(by0 + (bh - h) / 2), int(w), int(h), int(by0), int(by0 + bh - 1), len(runs)


# ---- 22 "머그 몸통 휨 측정" 셀 ----

def mug_curve(name):
    m = load_mask(name) > 0.5
    x, y, w, h = BOX[name]
    ys, xs = np.nonzero(m)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    col = m[y0:y1 + 1, x0:x1 + 1].sum(0)
    # 14 인쇄 영역과 같은 기준: 세로로 많이 채워진 열이 몸통(손잡이 제외)
    body = col >= 0.6 * col.max()
    c = int(x + w / 2) - x0
    if not body[c]:
        return dict(file=name, ok=False, reason='인쇄 영역 가운데가 몸통 열이 아님', reason_en='box center not on body column')
    l, r = c, c
    while l > 0 and body[l - 1]:
        l -= 1
    while r < len(body) - 1 and body[r + 1]:
        r += 1
    cols = np.arange(l, r + 1) + x0
    bottom = np.array([np.nonzero(m[:, cx])[0].max() for cx in cols], dtype=float)
    cx, half = (cols[0] + cols[-1]) / 2, (cols[-1] - cols[0] + 1) / 2
    u = (cols - cx) / half
    # 몸통 양 끝은 마스크 경계가 흐려 가운데 80%만 맞춤
    sel = np.abs(u) <= CURVE_FIT_RANGE
    A = np.stack([np.ones(sel.sum()), np.sqrt(1 - u[sel] ** 2)], 1)
    (yb, b), *_ = np.linalg.lstsq(A, bottom[sel], rcond=None)
    rmse = float(np.sqrt(np.mean((A @ np.array([yb, b]) - bottom[sel]) ** 2)))
    return dict(file=name, ok=True, reason='', reason_en='', cx=float(cx), half=float(half), b=float(b), y0=float(yb), fit_rmse=rmse,
                cols=cols, bottom=bottom)


# ---- 22 "합성 함수·14 F1 재현 확인" 셀 (21 COMPOSE_22와 같음) ----
def bilinear(img, yy, xx):
    h, w = img.shape[:2]
    yy, xx = np.clip(yy, 0, h - 1), np.clip(xx, 0, w - 1)
    y0, x0 = np.floor(yy).astype(int), np.floor(xx).astype(int)
    y1, x1 = np.minimum(y0 + 1, h - 1), np.minimum(x0 + 1, w - 1)
    wy, wx = (yy - y0)[..., None], (xx - x0)[..., None]
    return (img[y0, x0] * (1 - wy) * (1 - wx) + img[y0, x1] * (1 - wy) * wx + img[y1, x0] * wy * (1 - wx) + img[y1, x1] * wy * wx)


def compose(name, design_path, box, curve=False, spec=False, cloth=False):
    # 반환: (합성 이미지, 실제로 그린 높이). F1curve는 가운데가 내려간 만큼 영역이 아래로 늘어남
    img = load_goods(name)
    kind = KIND[name]
    x, y, w, h = box
    d = np.asarray(Image.open(design_path).convert('RGB').resize((w, h), Image.LANCZOS), dtype=np.float64)
    lift, H = None, h
    if curve:
        c = CURVES[name]
        us = np.clip((x + np.arange(w) + 0.5 - c['cx']) / c['half'], -1, 1)
        lift = c['b'] * np.sqrt(1 - us ** 2)
        lift = lift - lift.min()
        H = min(h + int(np.ceil(lift.max())), img.height - y)
    yy, xx = np.mgrid[0:H, 0:w].astype(np.float64)
    if kind == 'mug':
        # 원통 곡면: 화면 가로 위치 u → 그림 가로 위치 θ/θmax (가장자리일수록 눌림)
        u = (xx + 0.5) / w * 2 - 1
        xx = (np.arcsin(np.clip(u, -1, 1) * np.sin(MUG_HALF_ANGLE)) / MUG_HALF_ANGLE + 1) / 2 * w - 0.5
    if lift is not None:
        yy = yy - lift[None, :]
    gray_l = img.convert('L')
    gray_raw = np.asarray(gray_l, dtype=np.float64)[y:y + H, x:x + w]
    gray = np.asarray(gray_l.filter(ImageFilter.GaussianBlur(2)), dtype=np.float64)[y:y + H, x:x + w]
    region = load_mask(name)[y:y + H, x:x + w]
    inside = gray[region > 0.5] if (region > 0.5).any() else gray.ravel()
    lo, hi = np.percentile(inside, 2), np.percentile(inside, 98)
    ln = np.clip((gray - lo) / max(hi - lo, 1e-6), 0, 1)
    disp = (ln - 0.5) * DISP_RATIO * (CLOTH_DISP_MULT if cloth else 1) * w
    sy, sx = yy + disp, xx + disp
    # 휨으로 그림 밖을 가리키는 픽셀은 원본을 그대로 둠
    valid = ((sy >= -0.5) & (sy <= h - 0.5)).astype(np.float64) if lift is not None else 1.0
    warped = bilinear(d, sy, sx)
    shade = np.clip(gray / max(np.percentile(inside, 95), 1e-6), 0, 1)
    warped = warped * (1 - (1 - shade) * SHADE_BLEND)[..., None]
    if cloth:
        g = Image.fromarray(gray_raw.clip(0, 255).astype(np.uint8))
        detail = gray_raw - np.asarray(g.filter(ImageFilter.GaussianBlur(CLOTH_DETAIL_SIGMA)), dtype=np.float64)
        warped = warped + (detail * CLOTH_DETAIL)[..., None]
    if spec:
        # 큰 흐림보다 밝은 좁은 띠만 반사광으로 봄 (넓은 밝기 변화는 음영이 이미 반영)
        blur = np.asarray(gray_l.filter(ImageFilter.GaussianBlur(SPEC_SIGMA_RATIO * w)), dtype=np.float64)[y:y + H, x:x + w]
        hl = np.clip((gray - blur) / SPEC_RANGE, 0, 1)
        warped = warped + (255 - warped) * (hl * SPEC_BLEND)[..., None]
    a = np.asarray(img, dtype=np.float64).copy()
    alpha = (region * valid)[..., None]
    a[y:y + H, x:x + w] = a[y:y + H, x:x + w] * (1 - alpha) + warped.clip(0, 255) * alpha
    return Image.fromarray(a.clip(0, 255).astype(np.uint8)), H
