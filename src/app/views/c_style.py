import pandas as pd
import streamlit as st

from app.core import settings as S
from app.core import store
from app.core.paths import absp
from app.views.common import download, header, job_box, pick


def style_name(g):
    s = g['style']
    ipa = f"IP-Adapter ({'그림체 블록' if s['ipa_name'] == 'style_only' else '전체 층'}"
    ipa += f" 강도 {s['ipa']})" if not isinstance(s['ipa'], dict) else ')'
    return ('스타일 LoRA + ' if g['lora'] else '') + ipa


def show_convert(job):
    gid, k = job['game_id'], job['id']
    cv = job['result']['convert']
    st.caption(f"요청 #{k} · 생성 {cv['n_gen']}회 · {cv['sec']}초" + (' · 형식 실패: ' + ' / '.join(cv['problems']) if cv['problems'] else ''))
    scene = st.text_area('장면 태그 (영어). 변환 결과를 고치거나 태그를 더 적어 주세요', cv['scene'], key=f'c_scene_{k}', height=110)
    neg = st.text_input('빼고 싶은 요소 (영어 태그, 이번 요청에만)', key=f'c_neg_{k}', placeholder='예: 1girl, woman',
                        help='부정 프롬프트에 더해요. 게임 그림체 설정의 빼는 태그와 기본 태그(text, logo 등) 뒤에 붙어요.').strip().strip(',')
    if st.button('이미지 생성 요청', type='primary', key=f'c_go_{k}', disabled=not scene.strip()):
        p = dict(scene=scene.strip(), w=S.C_GEN['width'], h=S.C_GEN['height'], request=job['params']['request'], convert_job=k, neg=neg)
        st.session_state.setdefault('c_image_job', {})[gid] = store.add_job(gid, 'c_image', 'C 그림체 이미지', p, ['c_image'])
        st.rerun()
    st.caption('대기열의 ② 그림 단계에서 처리돼요.')


def show_image(job):
    p, r = job['params'], job['result']
    st.image(str(absp(r['image'])), caption=p['request'] or p['scene'], width='stretch')
    st.caption(f"그림 {r.get('image_sec')}초" + (f" · LoRA 불러오기·내리기 {r.get('lora_sec')}초" if r.get('lora_sec') else ''))
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        download(r['image'], 'PNG 다운로드', f'c_dl_{job["id"]}')
    if c2.button('F 굿즈 목업에 쓰기', key=f'c_f_{job["id"]}'):
        st.session_state.setdefault('f_design', {})[job['game_id']] = r['image']
        st.toast('F 굿즈 목업의 디자인으로 골랐어요.')
    if c3.button('상세 페이지 ①에 쓰기', key=f'c_p_{job["id"]}'):
        pick('①', job['id'])
    if c4.button('다시 생성', key=f'c_re_{job["id"]}'):
        q = dict(p, seed=p.get('seed', S.C_SEED) + 1)
        st.session_state['c_image_job'][job['game_id']] = store.add_job(job['game_id'], 'c_image', 'C 그림체 이미지', q, ['c_image'])
        st.rerun()


def gallery(gid):
    done = store.list_jobs(['done'], game_id=gid, kind='c_image', limit=12)
    if not done:
        return
    st.subheader('이 게임에서 만든 이미지')
    st.caption('여기 있는 이미지는 F 굿즈 목업과 상세 페이지에서 고를 수 있어요.')
    cols = st.columns(4)
    for c, j in zip(cols * 3, done):
        c.image(str(absp(j['result']['image'])), caption=f"#{j['id']} {j['params'].get('request', '')[:20]}", width='stretch')


def b_import(gid):
    # B 배너에서 글자를 얹기 전 그림(banner_raw)을 그대로 C 결과로 가져옴. B와 C는 같은 ② 그림 단계(같은 모델·그림체 설정)라 새로 그리지 않음
    bs = [j for j in store.list_jobs(['done'], game_id=gid, kind='b_banner', limit=12) if j['result'].get('raw') or j['params'].get('raw')]
    if not bs:
        st.caption('B 이벤트 배너에서 만든 그림이 아직 없어요.')
        return
    raw_of = lambda j: j['result'].get('raw') or j['params'].get('raw')
    j = st.selectbox('B 배너', bs, format_func=lambda j: f"B #{j['id']} {j['params'].get('request', '')[:24]}", key='c_b_pick')
    st.image(str(absp(raw_of(j))), caption='글자를 얹기 전 B 그림', width='stretch')
    if st.button('이 그림을 C 이미지로 가져오기', key='c_b_go'):
        bp = j['params']
        p = dict(scene=bp['scene'], w=bp['w'], h=bp['h'], request=bp.get('request', ''), neg=bp.get('neg', ''), seed=bp.get('seed', S.C_SEED),
                 from_b=j['id'])
        jid = store.add_job(gid, 'c_image', f"C 그림체 이미지 (B #{j['id']} 가져옴)", p, [])
        store.set_job(jid, result=dict(image=raw_of(j), image_sec=j['result'].get('image_sec'), from_b=j['id']))
        st.session_state.setdefault('c_image_job', {})[gid] = jid
        st.rerun()


def render():
    g = header('C. 게임 그림체 홍보 이미지', '원하는 장면을 적으면 등록한 게임의 그림체를 유지한 홍보 이미지를 만들어요.')
    if not g:
        st.warning('먼저 게임을 등록해 주세요.')
        return
    gid = g['id']
    left, right = st.columns([1, 1.3], gap='large')
    with left:
        st.subheader('입력')
        with st.expander('B 배너 그림 가져오기 (B 결과를 그대로 C 이미지로 씀)', expanded=True):
            b_import(gid)
        req = st.text_area('장면 요청', key='c_req', placeholder='저녁 노을이 지는 성문 앞에서 칼과 방패를 든 냥기사, 옆에 부엉이 마법사',
                           help='인물, 장소, 시간대, 행동을 적으면 결과가 또렷해져요.')
        if st.button('장면 태그로 변환', disabled=not req.strip()):
            p = dict(request=req.strip())
            st.session_state.setdefault('c_convert_job', {})[gid] = store.add_job(gid, 'c_convert', 'C 장면 변환', p, ['copy'])
            st.session_state.get('c_image_job', {}).pop(gid, None)
            st.rerun()
        st.caption('Qwen3-VL-8B가 B와 같은 변환 지시문으로 영어 장면 태그를 만들어요 (대기열 ① 문구 단계). 결과를 고치고 태그를 더한 뒤 생성해 주세요.')
        cj = st.session_state.get('c_convert_job', {}).get(gid)
        if cj:
            job_box(cj, '변환', show_convert)
        st.markdown('**그림체 맞추기** · 자동')
        st.caption('등록한 게임의 그림체 설정에 따라 자동으로 정해져요. 그림체 수정을 원하실 시 태그 변경을 해주세요. (게임 등록·목록 → 수정 → 그림체 설정)')
        st.dataframe(pd.DataFrame([{'게임': x['name'], '방식': style_name(x), '선택': '선택됨' if x['id'] == gid else ''}
                                   for x in store.list_games()]), hide_index=True, width='stretch')
        st.markdown('사용할 레퍼런스 아트 (첫 장이 IP-Adapter 대표 아트)')
        cols = st.columns(4)
        for c, r in zip(cols, g['refs'][:4]):
            if absp(r).exists():
                c.image(str(absp(r)), width='stretch')
    with right:
        st.subheader('결과')
        ij = st.session_state.get('c_image_job', {}).get(gid)
        if ij:
            job_box(ij, 'C 이미지', show_image)
        else:
            st.info('장면 태그를 확인한 뒤 이미지 생성을 요청해 주세요.')
    gallery(gid)
