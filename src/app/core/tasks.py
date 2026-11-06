# 요청 종류별로 단계마다 별도 프로세스에 넘길 작업(task)을 만들고, 결과를 요청 기록에 넣음
import json
import time

from PIL import Image

from . import compose07 as CP
from . import page_html as PH
from . import settings as S
from . import textcfg as T
from .paths import BG_DIR, absp, job_dir, rel

# 요청 종류별 단계 (모델 순서는 settings.STAGES)
D_STAGES = {'R1n': ['sdxl_bg', 'mask', 'iclight'], 'Y': ['mask', 'y'], 'YR1n': ['mask', 'y', 'iclight']}


def stages_of(kind, params):
    if kind in ('a', 'b_convert', 'c_convert'):
        return ['copy']
    if kind == 'b_banner':
        # 문구만 고쳐 다시 합성할 때는 이전 그림(raw)을 그대로 씀
        return ['compose'] if params.get('raw') else ['c_image', 'compose']
    if kind == 'c_image':
        return ['c_image']
    if kind == 'f_mask':
        return ['mask']
    if kind == 'd':
        return D_STAGES[params['method']]
    if kind == 'page':
        return (['copy'] if page_missing(params) else []) + ['compose']
    return []


# ---------------- 문구 ----------------
def user_block(points, must=None):
    # 13 must_task와 같은 사용자 입력 줄. 판매 포인트·꼭 넣을 문구가 모두 없으면 비움
    parts = []
    if points:
        parts.append(f'판매 포인트: {", ".join(points)}')
    if must:
        parts.append(f'꼭 넣을 문구: "{must}"')
    return '사용자 입력 (최우선): ' + ' / '.join(parts) if parts else ''


def section_task(tid, game, sec, image, points, tone, must='', goods_kind='tshirt', scene='desk'):
    # 21 copy_task와 같은 지시문 구성: A 지시문(INSTRUCTION_EX)의 요청 문장·출력 형식 줄만 섹션별로 바꿈
    s = T.SECTIONS[sec]
    need_must = bool(s['need_must'] and must)
    instr = T.INSTRUCTION_EX.replace(T.REQ_LINE, s['req'].format(goods=S.KIND_KO[goods_kind], scene=S.SCENE_KO[scene])).replace(
        T.FMT_A, s['fmt'])
    if not need_must:
        # 꼭 넣을 문구를 주지 않으면 규칙 1의 꼭 넣을 문구 설명·예시 줄을 뺌 (21 ①③④와 같음)
        instr = instr.replace(T.RULE1_MUST, T.RULE1_NO_MUST)
    prompt = instr.format(info=game['info'], user_block=user_block(points, must if need_must else None),
                          points='\n'.join('- ' + x for x in game['points']), tone=tone, cliche=', '.join(T.BANNED_CLICHE))
    return dict(id=tid, kind='section', section=sec, image=str(absp(image)) if image else '', system=T.SYSTEM_A, prompt=prompt,
                # 판촉 표현 허용 범위는 21과 같이 사용자 입력 전체(판매 포인트 + 꼭 넣을 문구)
                must=must if need_must else '', need_must=need_must, allowed=' '.join(list(points) + ([must] if must else [])),
                key=s['key'], n_sent=s['n_sent'], max_chars=s['max_chars'], json_fmt=s['json_fmt'], polite=s.get('polite', False))


def convert_task(tid, game, request, kind):
    # B·C 한국어 요청 → 영어 장면 태그 (07 INSTRUCTION_B2, 08 기능 B와 같은 지시문)
    prompt = T.INSTRUCTION_B2.format(info=game['info'], request=request, banned=', '.join(T.BANNED_PROMO))
    return dict(id=tid, kind=kind, section='', image='', system=T.SYSTEM_B, prompt=prompt, request=request, must='')


def copy_args():
    # 구체적 재요청의 고치는 방법: 25 후보 3 편집 지시 (꼭 넣을 문구가 있는 intro 섹션에만 쓰임)
    return dict(repo=S.QWEN_REPO, seed=S.COPY_SEED, n_cand=S.N_CAND, max_new_tokens=S.MAX_NEW_TOKENS,
                validator=T.VALIDATOR + T.VALIDATOR_SEC + T.VALIDATOR_B + T.VALIDATOR_C, banned_promo=T.BANNED_PROMO,
                banned_cliche=T.BANNED_CLICHE, fb_head=T.FB_HEAD, fb_hints=T.FB_HINTS_EDIT, fb_keys=T.FB_KEYS,
                b_max_extra=S.B_MAX_EXTRA, b_fb=S.B_FB)


def page_missing(params):
    return [s for s in ['title', 'intro', 'mockup', 'staging'] if not params['texts'].get(s)]


def copy_tasks(job, game):
    p, j = job['params'], job['id']
    if job['kind'] == 'a':
        return [section_task(f'j{j}__intro', game, 'intro', p['image'], p['points'], S.TONES[p['tone']], p['must'])]
    if job['kind'] in ('b_convert', 'c_convert'):
        return [convert_task(f'j{j}__convert', game, p['request'], job['kind'][0])]
    if job['kind'] == 'page':
        return [section_task(f'j{j}__{s}', game, s, p['copy_image'], p['points'], p['tone'], p.get('must', ''), p['goods_kind'],
                             p['scene']) for s in page_missing(p)]
    return []


def parse_section(text, sec):
    # 21 page_texts와 같음: JSON으로 읽을 수 없으면 받은 글 전체
    d = T.parse_json(text)
    if sec == 'intro' and d and isinstance(d.get('store'), list) and isinstance(d.get('sns'), str):
        return [str(x) for x in d['store']] + [d['sns']]
    key = T.SECTIONS[sec]['key']
    if sec != 'intro' and d and isinstance(d.get(key), (list, str)):
        v = d[key]
        return [v] if isinstance(v, str) else [str(x) for x in v]
    return [str(text).strip() or '(문구 없음)']


def apply_copy(job, recs):
    res = dict(job['result'])
    for r in recs:
        info = json.loads(r['info'])
        sec = r['file'].split('__')[1]
        item = dict(text=info['text'], problems=info['problems'], first_problems=info['first_problems'], fb_sent=info['fb_sent'],
                    n_gen=info['n_gen'], n_calls=info['n_calls'], texts_all=info['texts_all'], sec=r.get('sec'))
        if sec == 'convert':
            d = T.parse_json(info['text']) or {}
            item.update(scene=d.get('scene', ''), title=d.get('title', ''), sub=d.get('sub', ''))
            res['convert'] = item
        else:
            item['lines'] = parse_section(info['text'], sec)
            res.setdefault('copy', {})[sec] = item
    return res


# ---------------- 그림 (B 배너 · C) ----------------
def image_task(job, game):
    p = job['params']
    style = game['style']
    lora = game.get('lora') or ''
    # 18 prompt_of: LoRA를 쓸 때만 장면 뒤에 트리거
    scene = f"{p['scene']}, {game['trigger']}" if lora and game.get('trigger') else p['scene']
    out = job_dir(job['id']) / ('banner_raw.png' if job['kind'] == 'b_banner' else 'C.png')
    lp = absp(lora) if lora else None
    return [dict(file=f"j{job['id']}__img", out=str(out), prompt=style['prompt_example'].replace('{scene}', scene),
                 negative=style['negative'] + (f", {p['neg']}" if p.get('neg') else ''), ipa_scale=style['ipa'], compel=style['compel'], ref=str(absp(game['refs'][0])),
                 lora=str(lp.parent) if lp else '', lora_weight=lp.name if lp else '', w=p['w'], h=p['h'], seed=p.get('seed', S.C_SEED))]


def image_args():
    return dict(model=S.C_MODEL, ipa=S.C_IPA, steps=S.C_GEN['steps'], cfg=S.C_GEN['cfg'])


# ---------------- D ----------------
def bg_file(scene):
    return BG_DIR / f'BG__{scene}.png'


def bg_ready(scene):
    side = bg_file(scene).with_suffix('.json')
    return bg_file(scene).exists() and side.exists() and json.loads(side.read_text(encoding='utf-8')) == dict(
        model=S.SDXL_BASE, **S.bg_args(scene))


def d_paths(job):
    d = job_dir(job['id'])
    return dict(goods=d / 'IN.png', mask=d / 'IN_mask.png', mask_full=d / 'MASK_full.png', y=d / 'Y.png', ydir=d / 'y',
                fill=d / 'FILL.png', ic=d / 'IC.png', out=d / 'D.png')


def mask_task(job):
    p = job['params']
    d = job_dir(job['id'])
    if job['kind'] == 'f_mask':
        return [dict(file=f"j{job['id']}__mask", source_path=str(absp(p['source'])), crop=False, goods_out=str(d / 'goods.png'),
                     mask_out=str(d / 'mask.png'), mask_full_out=str(d / 'mask.png'))]
    q = d_paths(job)
    return [dict(file=f"j{job['id']}__mask", source_path=str(absp(p['source'])), crop=True, goods_out=str(q['goods']),
                 mask_out=str(q['mask']), mask_full_out=str(q['mask_full']))]


def mask_args():
    return dict(repo=S.BIREFNET, frame=dict(max_side=S.MAX_SIDE, ic_max_side=S.D2_ARGS['max_side'],
                                            highres_scale=S.D2_ARGS['highres_scale']))


def y_task(job):
    p, q = job['params'], d_paths(job)
    q['ydir'].mkdir(exist_ok=True)
    (q['ydir'] / 'raw').mkdir(exist_ok=True)
    return [dict(file=f"j{job['id']}__y", prompt=S.scene_prompt(p['kind'], p['scene']), goods_path=str(q['goods']),
                 mask_path=str(q['mask']), out=str(q['y']), try_tpl=str(q['ydir'] / 'Y_s{seed}.png'),
                 raw_tpl=str(q['ydir'] / 'raw' / 'Y_s{seed}.png'))]


def y_args():
    return dict(repo=S.Y_REPO, seeds=S.Y_SEEDS, dark=S.DARK, edge_px=S.EDGE_PX, **S.Y_ARGS)


def ic_task(job):
    p, q = job['params'], d_paths(job)
    opt = 'R1n' if p['method'] == 'R1n' else 'YR1n'
    return [dict(file=f"j{job['id']}__ic", opt=opt, sigma=S.D_CFG[opt]['sigma'], base=S.D_CFG[opt]['base'],
                 prompt=S.scene_prompt(p['kind'], p['scene']), goods_path=str(q['goods']), mask_path=str(q['mask']),
                 bg_path=str(bg_file(p['scene'])), y_path=str(q['y']), fill_out=str(q['fill']), ic_out=str(q['ic']), out=str(q['out']))]


def ic_args():
    return dict(sd15=S.SD15, iclight=S.ICLIGHT, d2=S.D2_ARGS, seed=S.IC_SEED, ratio_clip=S.RATIO_CLIP, fill_dilate_px=S.FILL_DILATE_PX)


def sdxl_task(job):
    sc = job['params']['scene']
    if bg_ready(sc):
        return []
    return [dict(file=f'bg__{sc}', out=str(bg_file(sc)), bg=S.bg_args(sc))]


def sdxl_args():
    return dict(model=S.SDXL_BASE)


# ---------------- 단계 표 ----------------
def tasks_for(stage, job, game):
    if stage == 'copy':
        return copy_tasks(job, game)
    if stage == 'c_image':
        return image_task(job, game)
    if stage == 'sdxl_bg':
        return sdxl_task(job)
    if stage == 'mask':
        return mask_task(job)
    if stage == 'y':
        return y_task(job)
    if stage == 'iclight':
        return ic_task(job)
    return []


STAGE_ARGS = {'copy': copy_args, 'c_image': image_args, 'sdxl_bg': sdxl_args, 'mask': mask_args, 'y': y_args, 'iclight': ic_args}
STAGE_MODEL = {'copy': S.QWEN_REPO, 'c_image': S.C_MODEL + ' + IP-Adapter (+ LoRA)', 'sdxl_bg': S.SDXL_BASE + ' (빈 배경)',
               'mask': S.BIREFNET, 'y': S.Y_REPO, 'iclight': f"{S.SD15} + {S.ICLIGHT['file']}", 'compose': 'Pillow · Chromium'}


def apply(stage, job, recs):
    # recs: 이 요청의 작업 결과 (오류 없는 것만 들어옴)
    res = dict(job['result'])
    if stage == 'copy':
        return apply_copy(job, recs)
    if stage == 'c_image':
        r = recs[0]
        key = 'raw' if job['kind'] == 'b_banner' else 'image'
        res[key] = rel(job_dir(job['id']) / ('banner_raw.png' if job['kind'] == 'b_banner' else 'C.png'))
        res['image_sec'] = r.get('sec')
        res['lora_sec'] = r.get('extra_sec')
        return res
    if stage == 'sdxl_bg':
        sc = job['params']['scene']
        if recs:
            bg_file(sc).with_suffix('.json').write_text(json.dumps(dict(model=S.SDXL_BASE, **S.bg_args(sc))), encoding='utf-8')
        res['bg'] = rel(bg_file(sc))
        return res
    if stage == 'mask':
        r = recs[0]
        info = json.loads(r['info'])
        d = job_dir(job['id'])
        if job['kind'] == 'f_mask':
            res.update(goods=rel(d / 'goods.png'), mask=rel(d / 'mask.png'))
        else:
            q = d_paths(job)
            res.update(goods_in=rel(q['goods']), mask_in=rel(q['mask']))
        res.update(mask_sec=r.get('sec'), frame=info['frame'], mask_area=info['mask_area'])
        return res
    if stage == 'y':
        info = json.loads(recs[0]['info'])
        res.update(y=rel(d_paths(job)['y']), y_sec=recs[0].get('sec'), y_tries=info['tries'], y_used_seed=info['used_seed'],
                   y_band_final=info['band_final'])
        if job['params']['method'] == 'Y':
            res['final'] = res['y']
        return res
    if stage == 'iclight':
        info = json.loads(recs[0]['info'])
        res.update(final=rel(d_paths(job)['out']), ic_sec=recs[0].get('sec'), ic_info=info)
        return res
    return res


# ---------------- 합성 (Pillow, 워커 프로세스에서 바로) ----------------
def compose_job(job, game):
    t0 = time.perf_counter()
    res = dict(job['result'])
    d = job_dir(job['id'])
    if job['kind'] == 'b_banner':
        p = job['params']
        img = Image.open(absp(res.get('raw') or p['raw'])).convert('RGB')
        banner, items = CP.compose(img, p['title'], p['sub'])
        banner.save(d / 'banner.png')
        res.update(banner=rel(d / 'banner.png'), contrast=[
            dict(kind=x['kind'], text=x['text'], size_px=x['size_px'], contrast_mean=round(x['contrast_mean'], 2),
                 contrast_p90=round(x['contrast_p90'], 2), need=x['need']) for x in items])
    elif job['kind'] == 'page':
        info = PH.render(page_spec(job, game), d / 'page.png', d / 'page.html')
        res.update(page=rel(d / 'page.png'), page_html=rel(d / 'page.html'), width=info['width'], height=info['height'],
                   sections=info['sections'], theme=info['theme'], hue=info['hue'], render_sec=info['render_sec'])
    res['compose_sec'] = round(time.perf_counter() - t0, 2)
    return res


def page_texts(job):
    # 사용자가 적은 글이 있으면 그 글, 없으면 문구 단계에서 만든 글
    p, res = job['params'], job['result']
    out = {}
    for s in ['title', 'intro', 'mockup', 'staging']:
        if p['texts'].get(s):
            v = p['texts'][s]
            out[s] = v if isinstance(v, list) else [v]
        else:
            out[s] = res.get('copy', {}).get(s, {}).get('lines', ['(문구 없음)'])
    return out


def page_spec(job, game):
    # 26 2번(HTML) 상세 페이지 사양. 구역: 대표 그림 + 제목 → 게임 소개 → 게임 화면 → 일러스트 → 굿즈 디자인 → 연출 사진 → 굿즈 구매 정보
    p = job['params']
    tx = page_texts(job)
    intro = tx['intro']
    return dict(hero=str(absp(p['c_image'])), eyebrow=game['name'], title=' '.join(tx['title']), info=game['info'],
                intro=intro[:-1] if len(intro) > 1 else intro, sns=intro[-1] if len(intro) > 1 else '',
                shot=str(absp(p['shot'])) if p.get('shot') else None, refs=[str(absp(r)) for r in p.get('refs', [])],
                illus=[str(absp(x)) for x in p.get('illus', [])], mockup=str(absp(p['mockup'])), mock_text=' '.join(tx['mockup']),
                d=str(absp(p['d_image'])), d_text=' '.join(tx['staging']), purchase=p['purchase'],
                cta=p.get('cta', ''), buy_url=p.get('buy_url', ''))
