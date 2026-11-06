# F 목업 후보 합성 (GPU 없이 앱에서 바로): 22 합성 함수와 인쇄 영역 규칙을 그대로 씀
import time
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from . import mockup22 as M
from . import settings as S
from .paths import RAW, ROOT, absp

GOODS_DIR = RAW / 'goods'
F22_DIR = ROOT / 'outputs' / 'mockup_f1map'
MASK14_DIR = ROOT / 'outputs' / 'mockup_f' / 'masks'


def sample_goods():
    # 03에서 받은 무지 굿즈 사진 11장 (22 인쇄 영역이 있는 사진)
    src = GOODS_DIR / 'goods_sources.csv'
    if not src.exists():
        return []
    g = pd.read_csv(src, keep_default_na=False)
    g = g[(g.error == '') & g.file.map(lambda f: (GOODS_DIR / f).exists())]
    return list(zip(g.file, g.kind))


def load_goods14(name):
    # 14 load_goods와 같음: 원본 사진을 긴 변 1024(8의 배수)로 줄임
    im = Image.open(GOODS_DIR / name).convert('RGB')
    s = S.MAX_SIDE / max(im.size)
    return im.resize((int(round(im.width * s / 8)) * 8, int(round(im.height * s / 8)) * 8), Image.LANCZOS)


def register_sample(name, kind):
    # 등록된 굿즈 사진: 14 마스크, 22 인쇄 영역(print_boxes_22.csv)·머그 휨(mug_curve.csv) 그대로 (21과 같은 입력)
    M.GOODS_IMG[name] = load_goods14(name)
    M.GOODS_MASK[name] = np.asarray(Image.open(MASK14_DIR / f'{Path(name).stem}.png')).astype(np.float32) / 255.0
    M.KIND[name] = kind
    b = pd.read_csv(F22_DIR / 'print_boxes_22.csv', keep_default_na=False).set_index('file')
    M.BOX[name] = (int(b.x[name]), int(b.y[name]), int(b.w[name]), int(b.h[name]))
    if kind == 'mug':
        c = pd.read_csv(F22_DIR / 'mug_curve.csv', keep_default_na=False).set_index('file')
        ok = str(c.ok[name]) == 'True'
        M.CURVES[name] = dict(ok=ok, cx=float(c.cx[name]), half=float(c.half[name]), b=float(c.b[name])) if ok else dict(ok=False)
    return dict(box=M.BOX[name], source='22 print_boxes_22.csv')


def box_rule(name, kind):
    # 새 사진: 22에서 정한 종류별 규칙 (에코백 몸통 행, 옷 몸통 깊이, 머그 몸통 열. 머그가 여러 개면 왼쪽 머그)
    if kind == 'tote':
        return M.tote_box(name)[:4], 'tote body rows'
    if kind in M.GARMENT_RULE:
        return M.garment_box(name, kind)[:4], 'torso (depth core)'
    x, y, w, h, _, _, n = M.mug_box_side(name, 'left')
    return (x, y, w, h), f'left mug body ({n} mugs)'


def register_upload(name, goods_path, mask_path, kind):
    # 새 사진: 마스크 단계(BiRefNet)가 긴 변 1024로 줄인 사진과 마스크
    M.GOODS_IMG[name] = Image.open(absp(goods_path)).convert('RGB')
    M.GOODS_MASK[name] = np.asarray(Image.open(absp(mask_path)).convert('L')).astype(np.float32) / 255.0
    M.KIND[name] = kind
    box, source = box_rule(name, kind)
    M.BOX[name] = tuple(int(v) for v in box)
    if kind == 'mug':
        M.CURVES[name] = M.mug_curve(name)
    return dict(box=M.BOX[name], source=source)


def cands_of(name):
    kind = M.KIND[name]
    c = dict(S.MOCK_CANDS['mug' if kind == 'mug' else 'fabric'])
    if kind == 'mug' and not M.CURVES.get(name, {}).get('ok'):
        # 머그 휨을 잴 수 없는 사진(22 mug_curve 조건)은 위아래 휨 후보를 뺌
        c.pop('F1curve')
    return c


def design_file(src_path, out_path):
    # 직접 올린 디자인은 인쇄 영역 비율(C 결과 1216×832)로 가운데를 잘라 늘어나지 않게 함
    im = Image.open(src_path).convert('RGB')
    a = im.width / im.height
    if abs(a - M.ASPECT) > 1e-3:
        if a > M.ASPECT:
            w = int(round(im.height * M.ASPECT))
            im = im.crop(((im.width - w) // 2, 0, (im.width - w) // 2 + w, im.height))
        else:
            h = int(round(im.width / M.ASPECT))
            im = im.crop((0, (im.height - h) // 2, im.width, (im.height - h) // 2 + h))
    im.save(out_path)
    return out_path


def make(name, design_path, cand):
    t0 = time.perf_counter()
    im, H = M.compose(name, str(design_path), M.BOX[name], **cands_of(name)[cand])
    return im, H, round(time.perf_counter() - t0, 3)
