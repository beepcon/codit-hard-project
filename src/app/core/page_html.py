# 상세 페이지 합성 (26 2번 방식): HTML·CSS로 짜고 Chromium으로 찍음. 26에서 극단 입력 30개 자동 검사 문제 0건, 이모지도 그림
import colorsys
import html
import time
from pathlib import Path

import numpy as np
from PIL import Image

W, PAD = 860, 64          # 상세 페이지 가로 860px (21과 같음), 좌우 여백
CW = W - 2 * PAD
DEFAULT_HUE = 0.6         # 색이 거의 없는 그림일 때 쓰는 기본 남색
SAT_MIN, SAT_SHARE = 0.12, 0.08  # 채도 0.12 넘는 픽셀이 8% 미만이면 기본 남색 (26)


def theme(img):
    # 대표 그림에서 채도 있는 픽셀의 색상(hue) 최빈값을 테마 색으로 씀
    a = np.asarray(img.convert('RGB').resize((128, 128))).reshape(-1, 3) / 255.0
    hsv = np.array([colorsys.rgb_to_hsv(*p) for p in a])
    sel = hsv[hsv[:, 1] > SAT_MIN]
    if len(sel) / len(hsv) < SAT_SHARE:
        h, src = DEFAULT_HUE, 'default'
    else:
        hist, e = np.histogram(sel[:, 0], bins=24, range=(0, 1))
        h, src = (e[hist.argmax()] + e[hist.argmax() + 1]) / 2, 'image'
    rgb = lambda s, v: tuple(int(x * 255) for x in colorsys.hsv_to_rgb(h, s, v))
    return dict(bg=rgb(.6, .09), bg2=rgb(.55, .16), accent=rgb(.45, .98), line=rgb(.5, .6), ink=(232, 241, 247), sub=(157, 179, 194),
                hue=round(float(h), 3), source=src)


def hexc(c):
    return '#%02x%02x%02x' % c


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{width:%(W)dpx;background:var(--bg);color:var(--ink);font-family:"Malgun Gothic","Noto Sans CJK KR","Noto Color Emoji","Segoe UI Emoji",sans-serif;
  word-break:keep-all;overflow-wrap:anywhere}
.hero{position:relative;min-height:640px;display:flex;flex-direction:column;justify-content:flex-end;padding:300px 64px 56px;overflow:hidden}
.hero>img{position:absolute;inset:0;width:100%%;height:100%%;object-fit:cover}
.hero::after{content:"";position:absolute;inset:0;background:linear-gradient(0deg,var(--bg) 0,var(--bgA) var(--block),transparent var(--fade))}
.hero .txt{position:relative;z-index:2;text-align:center}
.eyebrow{display:inline-block;max-width:100%%;font-size:15px;line-height:1.5;letter-spacing:.3em;color:var(--accent);font-weight:700;padding:4px 18px;border:1px solid var(--line);border-radius:16px;background:var(--bg)}
.hero h1{margin-top:18px;font-size:56px;line-height:1.22;font-weight:900;color:#fff;text-shadow:0 0 18px var(--glow),0 4px 0 rgba(0,0,0,.6)}
.hero .info{margin-top:12px;font-size:19px;line-height:1.5;color:var(--sub)}
section{padding:0 64px;text-align:center;position:relative}
.head{padding-top:0;height:190px;position:relative}
.head::before{content:"";position:absolute;top:0;left:50%%;width:1px;height:44px;background:var(--line)}
.label{position:absolute;top:73px;left:0;right:0;font-size:14px;letter-spacing:.4em;color:var(--accent);font-weight:700}
.head h2{position:absolute;top:100px;left:0;right:0;font-size:36px;line-height:48px;font-weight:900;color:#fff}
.bar{position:absolute;top:160px;left:50%%;width:56px;height:4px;margin-left:-28px;background:var(--accent);box-shadow:0 0 12px var(--accent)}
p.body{margin:0 auto;font-size:20px;line-height:1.85}
.quote{margin:32px auto 0;max-width:620px;padding:22px 10px;font-size:21px;line-height:1.6;font-weight:700;color:var(--accent);border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.card{margin:36px auto 0;padding:10px;border:1px solid var(--line);border-radius:14px;background:var(--bg2);box-shadow:0 0 40px var(--glow2)}
.card img{display:block;width:100%%;max-height:var(--maxh);object-fit:contain;border-radius:8px}
.grid{margin:14px auto 0;display:flex;flex-wrap:wrap;justify-content:center;gap:12px}
.grid div{overflow:hidden;border:1px solid var(--line);border-radius:10px;background:var(--bg2)}
.grid img{width:100%%;height:100%%;object-fit:cover;display:block}
.slant{margin:40px auto 0;height:420px;display:flex;justify-content:center}
.slant div{height:100%%;position:relative;flex:none}
.slant img{width:100%%;height:100%%;object-fit:cover;display:block}
.slant .edge{position:absolute;inset:0;background:var(--accent)}
.full{margin:36px -64px 0}
.full img{display:block;width:100%%;max-height:900px;object-fit:contain;-webkit-mask-image:linear-gradient(180deg,transparent 0,#000 12%%,#000 88%%,transparent 100%%)}
.tiles{margin-top:36px;display:flex;flex-direction:column;gap:14px}
.row{display:flex;gap:14px}
.tile{flex:1 1 0;min-width:0;padding:14px 12px 20px;border:1px solid var(--line);border-radius:12px;background:var(--bg2)}
.tile .k{font-size:14px;line-height:1.5;color:var(--sub)}
.tile .v{margin-top:6px;font-size:21px;line-height:1.4;font-weight:700;color:#fff}
.note{margin-top:14px;font-size:13px;color:var(--sub)}
.cta{display:inline-block;margin:40px 0 50px;padding:18px 54px;font-size:21px;font-weight:900;color:var(--bg);background:var(--accent);border-radius:999px;box-shadow:0 0 24px var(--glow);text-decoration:none}
.url{margin:-34px auto 50px;max-width:640px;font-size:14px;line-height:1.5;color:var(--sub);word-break:break-all}
.soon{display:inline-block;margin:40px 0 50px;padding:14px 44px;font-size:20px;font-weight:800;letter-spacing:.08em;color:var(--accent);border:2px solid var(--accent);border-radius:999px}
"""

FIT_JS = """
() => {
  // 제목: 3줄 안에 드는 가장 큰 크기(56→30px), 이름표: 2줄 안(15→11px), 구매 정보 값: 2줄 안(21→15px)
  const fitEl = (el, big, small, maxLines, lh) => {
    for (let s = big; s >= small; s -= 2) { el.style.fontSize = s + 'px'; if (el.offsetHeight <= s * lh * maxLines + 1) return; }
    el.style.fontSize = small + 'px';
  };
  const h1 = document.querySelector('.hero h1'); if (h1) fitEl(h1, 56, 30, 3, 1.22);
  const eb = document.querySelector('.eyebrow'); if (eb) fitEl(eb, 15, 11, 2, 1.5);
  document.querySelectorAll('.tile .v').forEach(v => fitEl(v, 21, 15, 2, 1.4));
  // 첫 화면 그라데이션: 글자 덩어리 위로 220px부터 어두워지게
  const hero = document.querySelector('.hero'), txt = document.querySelector('.hero .txt');
  hero.style.setProperty('--block', (txt.offsetHeight + 56) + 'px');
  hero.style.setProperty('--fade', (txt.offsetHeight + 56 + 220) + 'px');
}
"""

SECTIONS_JS = """
() => [...document.querySelectorAll('.hero, section')].map(e => {
  const h = e.querySelector('h2'); const b = e.getBoundingClientRect();
  return {name: h ? h.textContent : '대표 그림 + 제목', y0: Math.round(b.top + scrollY), y1: Math.round(b.bottom + scrollY)}; })
"""

E = html.escape


def img_tag(p):
    return f'<img src="{Path(p).resolve().as_uri()}">'


def build_html(spec):
    # spec: hero, eyebrow, title, info, intro(문장 목록), sns, shot(없으면 None), refs, illus, mockup, mock_text, d, d_text, purchase, cta('none'·'buy'·'soon'), buy_url
    T = theme(Image.open(spec['hero']))
    v = {k: hexc(T[k]) for k in ['bg', 'bg2', 'accent', 'line', 'ink', 'sub']}
    a = T['accent']
    root = (':root{' + ';'.join(f'--{k}:{c}' for k, c in v.items()) +
            f';--glow:rgba({a[0]},{a[1]},{a[2]},.75);--glow2:rgba({a[0]},{a[1]},{a[2]},.18);--bgA:rgba({T["bg"][0]},{T["bg"][1]},{T["bg"][2]},.75)' + '}')
    h = [f'<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><style>{root}{CSS % {"W": W}}</style></head><body>']
    h.append(f'<div class="hero">{img_tag(spec["hero"])}<div class="txt">' +
             (f'<span class="eyebrow">{E(spec["eyebrow"])}</span>' if spec['eyebrow'] else '') +
             (f'<h1>{E(spec["title"])}</h1>' if spec['title'] else '') +
             (f'<div class="info">{E(spec["info"])}</div>' if spec['info'] else '') + '</div></div>')
    head = lambda lab, t: f'<div class="head"><div class="label">{lab}</div><h2>{t}</h2><div class="bar"></div></div>'
    if spec['intro'] or spec['sns']:
        h.append('<section>' + head('ABOUT THE GAME', '게임 소개') +
                 (f'<p class="body" style="max-width:600px;padding-top:24px">{E(" ".join(spec["intro"]))}</p>' if spec['intro'] else '') +
                 (f'<div class="quote">“{E(spec["sns"])}”</div>' if spec['sns'] else '') + '<div style="height:40px"></div></section>')
    if spec['shot'] or spec['refs']:
        s = '<section>' + head('GAME SCREENS', '게임 화면')
        if spec['shot']:
            s += f'<div class="card" style="--maxh:900px">{img_tag(spec["shot"])}</div>'
        if spec['refs']:
            cols = min(4, len(spec['refs']))
            tw = min(240, (CW - 12 * (cols - 1)) // cols)
            s += f'<div class="grid" style="max-width:{cols * tw + (cols - 1) * 12}px">' + ''.join(
                f'<div style="width:{tw}px;height:{tw}px">{img_tag(p)}</div>' for p in spec['refs']) + '</div>'
        h.append(s + '<div style="height:50px"></div></section>')
    n = len(spec['illus'])
    if n:
        s = '<section>' + head('ILLUSTRATION', '일러스트')
        if n >= 4:  # 4장부터 2열 격자 (기울인 칸은 3장까지만 페이지 안에 들어감, 26)
            tw = (CW - 14) // 2
            s += f'<div class="grid" style="max-width:{CW}px;gap:14px">' + ''.join(
                f'<div style="width:{tw}px;height:{int(tw * 10 / 16)}px">{img_tag(p)}</div>' for p in spec['illus']) + '</div>'
        else:
            ov = 100 if n > 1 else 0
            pw = min(330 if n > 1 else 520, (W - 48 + ov * (n - 1)) // n)
            k = 28 if n > 1 else 12
            poly = f'polygon({k}% 0,100% 0,{100 - k}% 100%,0 100%)'
            edge = f'polygon({k}% 0,{k + 1.2}% 0,1.2% 100%,0 100%)'
            s += '<div class="slant" style="margin-left:-64px;margin-right:-64px">' + ''.join(
                f'<div style="width:{pw}px;margin-left:{-ov if i else 0}px;clip-path:{poly}">{img_tag(p)}<span class="edge" style="clip-path:{edge}"></span></div>'
                for i, p in enumerate(spec['illus'])) + '</div>'
        h.append(s + '<div style="height:40px"></div></section>')
    h.append('<section>' + head('GOODS DESIGN', '굿즈 디자인') + f'<div class="card" style="width:640px;--maxh:820px">{img_tag(spec["mockup"])}</div>' +
             (f'<p class="body" style="max-width:640px;margin-top:36px">{E(spec["mock_text"])}</p>' if spec['mock_text'] else '') +
             '<div style="height:40px"></div></section>')
    h.append('<section>' + head('ON YOUR DESK', '연출 사진') + f'<div class="full">{img_tag(spec["d"])}</div>' +
             (f'<p class="body" style="max-width:680px;margin-top:16px">{E(spec["d_text"])}</p>' if spec['d_text'] else '') +
             '<div style="height:40px"></div></section>')
    vals = {k: x for k, x in spec['purchase'].items() if str(x).strip()} or {'구매 정보': '(입력 없음)'}
    wide = [k for k in vals if k in ('상품명', '출고', '구매 정보')]
    small = [k for k in vals if k not in wide]
    rows = [[k] for k in wide[:1]] + ([small] if small else []) + [[k] for k in wide[1:]]
    tiles = ''.join('<div class="row">' + ''.join(f'<div class="tile"><div class="k">{E(k)}</div><div class="v">{E(str(vals[k]))}</div></div>' for k in r) + '</div>'
                    for r in rows)
    # 맨 아래는 사용자가 고른 것만 그린다(11/05 결정, 기본 'none'). 'buy'는 구매 링크가 있어야 하고 page.html에서는 눌리며 PNG에는 주소를 글자로 남긴다.
    # 'soon'은 누르는 것이 아니므로 버튼이 아닌 테두리 꼬리표로 그린다. cta가 없는 예전 사양은 링크가 있으면 'buy'로 본다
    url = str(spec.get('buy_url') or '').strip()
    kind = spec.get('cta') or ('buy' if url else 'none')
    if kind == 'buy' and url:
        cta = f'<a class="cta" href="{E(url)}" target="_blank" rel="noopener">굿즈 구매하러 가기 ›</a><div class="url">{E(url)}</div>'
    elif kind == 'soon':
        cta = '<div class="soon">출시 예정</div>'
    else:
        cta = '<div style="height:50px"></div>'
    h.append('<section>' + head('GOODS INFO', '굿즈 구매 정보') + f'<div class="tiles">{tiles}</div>' +
             (f'<div class="note">{E(spec["note"])}</div>' if spec.get('note') else '') + cta + '</section>')
    h.append('</body></html>')
    return ''.join(h), T


def render(spec, out_png, out_html, browser=None):
    # browser를 넘기면 그 Chromium을 다시 씀(여러 장), 없으면 이번 한 장만 위해 띄웠다 닫음
    doc, T = build_html(spec)
    Path(out_html).write_text(doc, encoding='utf-8')
    t0 = time.perf_counter()
    own = browser is None
    if own:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch()
    try:
        pg = browser.new_page(viewport={'width': W, 'height': 1000}, device_scale_factor=1)
        pg.goto(Path(out_html).resolve().as_uri())
        pg.wait_for_load_state('networkidle')
        pg.evaluate('document.fonts.ready')
        pg.evaluate(FIT_JS)
        secs = pg.evaluate(SECTIONS_JS)
        pg.screenshot(path=str(out_png), full_page=True)
        pg.close()
    finally:
        if own:
            browser.close()
            pw.stop()
    w, hgt = Image.open(out_png).size
    return dict(width=w, height=hgt, sections=secs, theme=T['source'], hue=T['hue'], render_sec=round(time.perf_counter() - t0, 2))
