# 실험 노트북(07·19·21·22)의 채택 코드를 글자 그대로 옮긴 파일. 노트북과 같은 결과가 나오도록 직접 고치지 않는다.
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .paths import FONT, FONT_BOLD, PAGE_W

# ---- 07 "문구 합성 함수" 셀 ----
def rel_luminance(rgb):
    # WCAG 2.1 상대 휘도 정의
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722


def contrast(l1, l2):
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def wrap(draw, text, font, max_w, max_lines):
    words, out, cur = text.split(' '), [], ''
    for w in words:
        t = (cur + ' ' + w).strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t
        else:
            if cur:
                out.append(cur)
            cur = w
    out.append(cur)
    ok = len(out) <= max_lines and all(draw.textlength(l, font=font) <= max_w for l in out)
    return out, ok


def fit(draw, text, font_path, start, max_w, max_lines=2, min_size=16):
    size = start
    while size >= min_size:
        font = ImageFont.truetype(str(font_path), size)
        out, ok = wrap(draw, text, font, max_w, max_lines)
        if ok:
            return out, font, size
        size -= 2
    font = ImageFont.truetype(str(font_path), min_size)
    return wrap(draw, text, font, max_w, max_lines)[0], font, min_size


TEXT_RGB = (255, 255, 255)


def compose(img, title, sub):
    W, H = img.size
    base = img.convert('RGBA')
    draw = ImageDraw.Draw(base)
    margin = int(min(W, H) * 0.05)
    max_w = W - 2 * margin
    t_lines, t_font, t_size = fit(draw, title, FONT_BOLD, int(min(W, H) * 0.11), max_w)
    s_lines, s_font, s_size = fit(draw, sub, FONT, int(min(W, H) * 0.045), max_w, max_lines=1)
    gap = int(t_size * 0.25)
    line_h = lambda f: f.getbbox('가Ag')[3]
    total = len(t_lines) * (line_h(t_font) + gap) + line_h(s_font)
    # 글자 영역 전체가 어두운 구간(불투명도 200/255)에 들어가도록, 글자 위쪽에서만 투명→검정으로 바뀌게 함
    ramp = int(H * 0.12)
    band = min(H, total + 2 * margin + ramp)
    alpha = np.full((band, 1), 200, dtype=np.uint8)
    alpha[:ramp, 0] = np.linspace(0, 200, ramp).astype(np.uint8)
    shade = Image.new('RGBA', (W, band), (0, 0, 0, 255))
    shade.putalpha(Image.fromarray(alpha, 'L').resize((W, band)))
    base.alpha_composite(shade, (0, H - band))
    bg = np.asarray(base.convert('RGB'))
    draw = ImageDraw.Draw(base)
    y = H - margin - total
    items = []
    for lines_, font, size, kind in [(t_lines, t_font, t_size, 'title'), (s_lines, s_font, s_size, 'sub')]:
        for l in lines_:
            box = draw.textbbox((margin, y), l, font=font)
            region = bg[max(box[1], 0):min(box[3], H), max(box[0], 0):min(box[2], W)]
            lum = rel_luminance(region.reshape(-1, 3))
            items.append(dict(kind=kind, size_px=size, text=l,
                              contrast_mean=contrast(rel_luminance(TEXT_RGB), float(lum.mean())),
                              contrast_p90=contrast(rel_luminance(TEXT_RGB), float(np.percentile(lum, 90))),
                              need=3.0 if size >= 24 else 4.5))
            draw.text((margin, y), l, font=font, fill=TEXT_RGB, stroke_width=max(2, size // 18), stroke_fill=(0, 0, 0))
            y += line_h(font) + gap
    return base.convert('RGB'), items


# ---- 21 "6단계: 상세페이지 합성" 셀의 글 상자·이어 붙이기 함수 ----
INK, SUB_INK, BOX_RGB, BADGE_RGB = (34, 34, 34), (110, 110, 110), (245, 245, 245), (214, 39, 40)
PAD, GAP, BODY_PX, HEAD_PX = 48, 24, 22, 30


def font(bold, size):
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT), size)


def lines_of(draw, text, f, max_w):
    # 07 wrap(띄어쓰기 단위 줄바꿈)을 줄 수 제한 없이 씀
    return wrap(draw, text, f, max_w, max_lines=10 ** 6)[0]


def text_box(head, paras, bg=(255, 255, 255), badge=None, note=None):
    fh, fb, fn = font(True, HEAD_PX), font(False, BODY_PX), font(False, 16)
    tmp = ImageDraw.Draw(Image.new('RGB', (PAGE_W, 10)))
    max_w = PAGE_W - 2 * PAD
    rows = [(head, fh, INK, int(HEAD_PX * 0.8))]
    for p in paras:
        rows += [(l, fb, INK, 0) for l in lines_of(tmp, p, fb, max_w)]
        rows[-1] = rows[-1][:3] + (int(BODY_PX * 0.6),)
    if note:
        rows += [(l, fn, SUB_INK, 0) for l in lines_of(tmp, note, fn, max_w)]
    lh = lambda f: int(f.getbbox('가Ag')[3] * 1.5)
    height = PAD + sum(lh(f) + extra for _, f, _, extra in rows) + PAD
    im = Image.new('RGB', (PAGE_W, height), bg)
    draw = ImageDraw.Draw(im)
    y = PAD
    for i, (t, f, color, extra) in enumerate(rows):
        draw.text((PAD, y), t, font=f, fill=color)
        if i == 0 and badge:
            x = PAD + draw.textlength(t, font=f) + 14
            fbg = font(True, 18)
            w = draw.textlength(badge, font=fbg) + 20
            draw.rounded_rectangle((x, y + 6, x + w, y + 36), radius=6, fill=BADGE_RGB)
            draw.text((x + 10, y + 9), badge, font=fbg, fill=(255, 255, 255))
        y += lh(f) + extra
    return im


def fit_w(im):
    im = im.convert('RGB')
    return im.resize((PAGE_W, int(round(im.height * PAGE_W / im.width))), Image.LANCZOS)


def stack(parts, bg=(255, 255, 255)):
    out = Image.new('RGB', (PAGE_W, sum(p.height for p in parts)), bg)
    y = 0
    for p in parts:
        out.paste(p, (0, y))
        y += p.height
    return out
