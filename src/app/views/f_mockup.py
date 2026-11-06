import shutil
import time

import streamlit as st

from app.core import mockup as MK
from app.core import settings as S
from app.core import store
from app.core.paths import OUT, absp, rel
from app.views.common import download, header, job_box, pick, save_upload, upload_errors, upload_rule


def designs(gid):
    return [(j['result']['image'], f"C #{j['id']} {j['params'].get('request', '')[:16]}")
            for j in store.list_jobs(['done'], game_id=gid, kind='c_image', limit=8)]


def make_all(gid, name, kind, design, source, box_info):
    d = OUT / 'mockups' / f'{int(time.time() * 1000)}'
    d.mkdir(parents=True, exist_ok=True)
    cands = []
    for c in MK.cands_of(name):
        im, H, sec = MK.make(name, absp(design), c)
        p = d / f'{c}.png'
        im.save(p)
        cands.append(dict(cand=c, file=rel(p), sec=sec))
    st.session_state.setdefault('f_result', {})[gid] = dict(name=name, kind=kind, design=design, source=source, cands=cands,
                                                            box=list(box_info['box']), box_source=box_info['source'],
                                                            goods=rel(d / 'goods.png'))
    MK.M.GOODS_IMG[name].save(d / 'goods.png')


def save_pick(gid, res, c):
    # 고른 목업을 요청 기록(F 고른 목업)으로 남겨 D 배경·상세 페이지에서 고를 수 있게 함
    key = (res['cands'][0]['file'], c['cand'])
    saved = st.session_state.setdefault('f_saved', {})
    if key not in saved:
        p = dict(goods=res['source'], kind=res['kind'], design=res['design'], cand=c['cand'], box=res['box'])
        jid = store.add_job(gid, 'f_pick', 'F 고른 목업', p, [])
        dst = absp(c['file']).parent / f'pick_{jid}.png'
        shutil.copy(absp(c['file']), dst)
        store.set_job(jid, result=dict(file=rel(dst), sec=c['sec']), ended=time.time())
        saved[key] = jid
    return saved[key]


def after_mask(job):
    p, r = job['params'], job['result']
    gid = job['game_id']
    res = st.session_state.get('f_result', {}).get(gid)
    if res and res.get('mask_job') == job['id']:
        return
    name = f"upload_{job['id']}"
    info = MK.register_upload(name, r['goods'], r['mask'], p['kind'])
    make_all(gid, name, p['kind'], p['design'], p['source'], info)
    st.session_state['f_result'][gid]['mask_job'] = job['id']


def render():
    g = header('F. 굿즈 목업', '무지 굿즈 실물 사진에 게임 그림을 입혀, 제작 전에 완성품 모습을 미리 봐요.')
    if not g:
        st.warning('먼저 게임을 등록해 주세요.')
        return
    gid = g['id']
    left, right = st.columns([1, 1.4], gap='large')
    with left:
        st.subheader('입력')
        src = st.radio('무지 굿즈 사진', ['등록된 굿즈 사진', '직접 올리기'], horizontal=True, key='f_src')
        if src == '등록된 굿즈 사진':
            samples = MK.sample_goods()
            sel = st.selectbox('굿즈 사진', samples, format_func=lambda x: f'{x[0]} ({S.KIND_KO[x[1]]})', key='f_sample') if samples else None
            if sel:
                st.image(str(MK.GOODS_DIR / sel[0]), width=260)
            up, kind = None, sel[1] if sel else None
        else:
            up = st.file_uploader('아무 그림 없는 실물 사진 한 장', type=['png', 'jpg', 'jpeg'], key='f_up')
            st.caption(f'굿즈 사진: {upload_rule("goods")}')
            if up and upload_errors([up], 'goods'):
                up = None
            kind = st.selectbox('굿즈 종류', list(S.KIND_KO), format_func=S.KIND_KO.get, key='f_kind')
            st.caption('새 사진은 굿즈 마스크(BiRefNet)를 먼저 계산해야 인쇄 영역을 잡을 수 있어, 대기열의 ④ 마스크 단계를 거친 뒤 후보를 만들어요.')
        dmode = st.radio('입힐 디자인', ['C에서 만든 이미지', '직접 업로드'], horizontal=True, key='f_dmode')
        design, df = None, None
        if dmode == 'C에서 만든 이미지':
            ds = designs(gid)
            if not ds:
                st.info('C 그림체 이미지에서 먼저 그림을 만들어 주세요.')
            else:
                pre = st.session_state.get('f_design', {}).get(gid)
                paths = [d[0] for d in ds]
                design = st.radio('C 결과', paths, index=paths.index(pre) if pre in paths else 0,
                                  format_func=lambda x: next(l for p, l in ds if p == x), key='f_design_pick')
                st.image(str(absp(design)), width=260)
        else:
            df = st.file_uploader('디자인 이미지', type=['png', 'jpg', 'jpeg'], key='f_design_up')
            if df:
                st.caption('인쇄 영역 비율(1216×832)로 가운데를 잘라 써요.')
        st.info('생성 방식: 합성 후보 전부. 굿즈 사진의 인쇄 영역에 디자인을 붙이고 사진의 밝기·주름을 따라 휘게 해요. '
                '굿즈 종류에 맞는 후보를 모두 만들어 나란히 보여 줘요 (티셔츠·후드·에코백 2장, 머그 3장).')
        ready = (src == '등록된 굿즈 사진' and kind) or up
        if st.button('목업 후보 만들기', type='primary', disabled=not (ready and (design or dmode == '직접 업로드' and df))):
            if dmode == '직접 업로드':
                raw = absp(save_upload(df, 'designs'))
                design = rel(MK.design_file(raw, raw.with_suffix('.crop.png')))
            st.session_state.get('f_result', {}).pop(gid, None)
            if src == '등록된 굿즈 사진':
                info = MK.register_sample(sel[0], kind)
                make_all(gid, sel[0], kind, design, rel(MK.GOODS_DIR / sel[0]), info)
                st.session_state.get('f_mask_job', {}).pop(gid, None)
            else:
                p = dict(source=save_upload(up, 'goods'), kind=kind, design=design)
                st.session_state.setdefault('f_mask_job', {})[gid] = store.add_job(gid, 'f_mask', 'F 굿즈 마스크', p, ['mask'])
            st.rerun()
        st.caption('합성은 GPU 모델을 쓰지 않아 바로 만들어요 (후보 1장 약 0.3초, 22 기록).')
    with right:
        st.subheader('결과')
        mj = st.session_state.get('f_mask_job', {}).get(gid)
        if mj:
            job_box(mj, '굿즈 마스크', after_mask)
        res = st.session_state.get('f_result', {}).get(gid)
        if not res:
            st.info('후보를 만들면 여기에 나란히 보여요.')
            return
        st.status(f"후보 {len(res['cands'])}장 완료 · {S.KIND_KO[res['kind']]} · {sum(c['sec'] for c in res['cands']):.1f}초", state='complete')
        st.caption(f"인쇄 영역 {res['box']} ({res['box_source']})")
        cols = st.columns(len(res['cands']) + 1)
        cols[0].image(str(absp(res['goods'])), caption='원본 무지 굿즈', width='stretch')
        for c, x in zip(cols[1:], res['cands']):
            lab, desc = S.MOCK_LABEL[x['cand']]
            c.image(str(absp(x['file'])), caption=f'{lab} · {desc}', width='stretch')
        choice = st.radio('마음에 드는 목업을 고르세요', [x['cand'] for x in res['cands']], index=None, horizontal=True,
                          format_func=lambda c: S.MOCK_LABEL[c][0], key=f"f_choice_{res['cands'][0]['file']}")
        st.caption('처음에는 아무것도 고르지 않은 상태예요. 머그는 기본 · 위아래 휨 · 반사광 3장이 나와요.')
        c1, c2 = st.columns(2)
        if choice:
            x = next(x for x in res['cands'] if x['cand'] == choice)
            jid = save_pick(gid, res, x)
            with c1:
                download(store.get_job(jid)['result']['file'], '고른 목업 PNG 다운로드', f'f_dl_{jid}')
            if c2.button('상세 페이지 ③에 쓰기', key=f'f_p_{jid}'):
                pick('③', jid)
            st.caption(f'고른 목업은 요청 #{jid}로 저장되어 D 굿즈 배경에서도 고를 수 있어요.')
        else:
            c1.button('고른 목업 PNG 다운로드', disabled=True)
            c2.button('상세 페이지 ③에 쓰기', disabled=True)
