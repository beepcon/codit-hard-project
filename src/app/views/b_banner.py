import json

import pandas as pd
import streamlit as st

from app.core import settings as S
from app.core import store, tasks
from app.core import textcfg as T
from app.core.paths import absp
from app.views.common import download, header, job_box


def steps(now):
    cols = st.columns(4)
    for i, (c, t) in enumerate(zip(cols, ['요청 입력', '장면·문구 변환', '확인·수정 후 생성', '글자 합성·대비 검사']), 1):
        c.markdown(f"{'**' if i == now else ''}{i}. {t}{'**' if i == now else ''}")


def show_convert(job):
    gid = job['game_id']
    cv = job['result']['convert']
    probs = cv['problems']
    st.caption(f"요청 #{job['id']} · 생성 {cv['n_gen']}회 · {cv['sec']}초 · 규칙 " + ('전부 통과' if not probs else '실패: ' + ' / '.join(probs)))
    k = job['id']
    scene = st.text_area('장면 태그 (영어, 고칠 수 있음)', cv['scene'], key=f'b_scene_{k}',
                         help='이미지 생성에 쓰는 영어 태그. 그림체는 등록한 게임의 그림체 설정으로 자동으로 맞춰요.')
    st.caption('그림체 수정을 원하실 시 태그 변경을 해주세요. (게임 등록·목록 → 수정 → 그림체 설정)')
    neg = st.text_input('빼고 싶은 요소 (영어 태그, 이번 요청에만)', key=f'b_neg_{k}', placeholder='예: 1girl, woman',
                        help='부정 프롬프트에 더해요. 게임 그림체 설정의 빼는 태그와 기본 태그(text, logo 등) 뒤에 붙어요.').strip().strip(',')
    title = st.text_input('제목', cv['title'], key=f'b_title_{k}')
    sub = st.text_input('부제', cv['sub'], key=f'b_sub_{k}')
    now = T.check_b(json.dumps(dict(scene=scene, title=title, sub=sub), ensure_ascii=False), job['params']['request'], T.BANNED_PROMO)
    if now:
        st.warning('고친 글이 규칙에 걸린다: ' + ' / '.join(now))
    if st.button('배너 생성 요청', type='primary', key=f'b_go_{k}'):
        w, h = S.BANNER_SIZES[job['params']['size']]
        p = dict(scene=scene.strip(), title=title.strip(), sub=sub.strip(), w=w, h=h, size=job['params']['size'],
                 request=job['params']['request'], convert_job=k, neg=neg)
        st.session_state.setdefault('b_banner_job', {})[gid] = store.add_job(gid, 'b_banner', 'B 이벤트 배너', p, tasks.stages_of('b_banner', p))
        st.rerun()
    st.caption('대기열의 ② 그림 단계에서 그림을 만들고 ⑦ 합성 단계에서 글자를 얹어요.')


def show_banner(job):
    p, r = job['params'], job['result']
    st.image(str(absp(r['banner'])), caption=f"{p['size']} · 그림 {r.get('image_sec', '-')}초", width='stretch')
    st.caption('제목·부제는 그림 생성 뒤 Pillow로 얹어요 (07 문구 합성 함수).')
    rows = []
    for kind, label in [('title', '제목'), ('sub', '부제')]:
        xs = [x for x in r['contrast'] if x['kind'] == kind]
        if xs:
            v, need = min(x['contrast_p90'] for x in xs), xs[0]['need']
            rows.append({'글자': label, '대비 (밝은 쪽 10% 기준)': f'{v:.2f}:1',
                         '기준': '큰 글자 AA 3:1 이상' if need == 3.0 else '일반 글자 AA 4.5:1 이상', '결과': '통과' if v >= need else '실패'})
    ok = all(x['결과'] == '통과' for x in rows)
    st.markdown(f"**글자 대비 검사 (WCAG 2.1)** · {'통과' if ok else '실패 있음'}")
    st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
    c1, c2, c3 = st.columns(3)
    with c1:
        download(r['banner'], 'PNG 다운로드', f'b_dl_{job["id"]}')
    gid = job['game_id']
    with c2.popover('문구만 고쳐 다시 합성'):
        t2 = st.text_input('제목', p['title'], key=f'b_t2_{job["id"]}')
        s2 = st.text_input('부제', p['sub'], key=f'b_s2_{job["id"]}')
        if st.button('다시 합성', key=f'b_rc_{job["id"]}'):
            q = dict(p, title=t2, sub=s2, raw=r.get('raw') or p.get('raw'))
            st.session_state['b_banner_job'][gid] = store.add_job(gid, 'b_banner', 'B 배너 다시 합성', q, tasks.stages_of('b_banner', q))
            st.rerun()
    if c3.button('그림 다시 생성', key=f'b_regen_{job["id"]}'):
        q = {k: v for k, v in p.items() if k != 'raw'}
        q['seed'] = p.get('seed', S.C_SEED) + 1
        st.session_state.setdefault('b_banner_job', {})[gid] = store.add_job(gid, 'b_banner', 'B 이벤트 배너', q, tasks.stages_of('b_banner', q))
        st.rerun()


def render():
    g = header('B. 텍스트 → 이벤트 배너', '한 문장으로 요청하면 장면과 배너 문구로 나눈 뒤, 확인을 거쳐 게임 그림체 배너를 만들어요.')
    if not g:
        st.warning('먼저 게임을 등록해 주세요.')
        return
    gid = g['id']
    cj = st.session_state.get('b_convert_job', {}).get(gid)
    bj = st.session_state.get('b_banner_job', {}).get(gid)
    steps(4 if bj else 2 if cj else 1)
    left, right = st.columns([1, 1.3], gap='large')
    with left:
        st.subheader('1. 요청')
        req = st.text_area('배너 요청 문장', key='b_req', placeholder='여름 바다 배경으로 냥기사 할인 배너, 50% 할인, 10월 25일~11월 3일',
                           help='배경, 할인율, 기간처럼 배너에 들어갈 내용을 한 문장으로 적어 주세요.')
        size = list(S.BANNER_SIZES)[0]
        st.caption(f'크기: {size}')
        if st.button('장면·문구로 변환', disabled=not req.strip()):
            p = dict(request=req.strip(), size=size)
            st.session_state.setdefault('b_convert_job', {})[gid] = store.add_job(gid, 'b_convert', 'B 장면·문구 변환', p, ['copy'])
            st.session_state.get('b_banner_job', {}).pop(gid, None)
            st.rerun()
        st.caption('Qwen3-VL-8B가 변환해요 (대기열 ① 문구 단계).')
        if cj:
            st.subheader('2. 변환 결과 확인·수정')
            job_box(cj, '변환', show_convert)
    with right:
        st.subheader('결과')
        if bj:
            job_box(bj, '배너', show_banner)
        else:
            st.info('변환 결과를 확인한 뒤 배너 생성을 요청해 주세요.')
