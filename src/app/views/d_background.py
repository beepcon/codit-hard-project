import streamlit as st

from app.core import settings as S
from app.core import store, tasks
from app.core.paths import absp
from app.views.common import download, header, job_box, pick, save_upload, upload_errors, upload_rule

METHOD_CAPTION = {'R1n': '굿즈 보존 최고. 빈 배경 위에 조명만 옮겨요. 장면 묘사는 단순해요.',
                  'Y': '배경 생성. 굿즈 주변에 장면 배경을 새로 그려요.'}


def show(job):
    p, r = job['params'], job['result']
    c1, c2 = st.columns(2)
    c1.image(str(absp(p['source'])), caption='올린 굿즈 사진 (원본)', width='stretch')
    c2.image(str(absp(r['final'])), caption=f"배경 연출 결과 · {S.SCENE_LABEL[p['scene']]} 장면", width='stretch')
    if r.get('y_tries'):
        n = len(r['y_tries'])
        if n > 1:
            st.caption(f"Y 결과 가장자리에 검은 띠가 보여 seed {r['y_used_seed']}까지 {n}번 만들었어요 (최대 3번, 20 띠 판정)."
                       + (' 3번 모두 띠가 있어 마지막 결과를 썼어요.' if r['y_band_final'] else ''))
        else:
            st.caption('Y 결과에 검은 띠가 없어 한 번에 끝났어요.')
    st.caption(f"굿즈 마스크 면적 {r.get('mask_area')} · 틀 {r.get('frame')} · 굿즈 부분은 원본 픽셀(R1n은 조명만 옮긴 원본)")
    a, b, c = st.columns(3)
    with a:
        download(r['final'], 'PNG 다운로드', f'd_dl_{job["id"]}')
    if b.button('상세 페이지 ④에 쓰기', key=f'd_p_{job["id"]}'):
        pick('④', job['id'])
    if c.button('다른 장면으로', key=f'd_other_{job["id"]}'):
        st.session_state.get('d_job', {}).pop(job['game_id'], None)
        st.rerun()


def render():
    g = header('D. 굿즈 보존 배경', '굿즈 사진은 그대로 두고, 뒤 배경과 연출만 만들어 상세 페이지용 사진을 얻어요.')
    if not g:
        st.warning('먼저 게임을 등록해 주세요.')
        return
    gid = g['id']
    left, right = st.columns([1, 1.3], gap='large')
    with left:
        st.subheader('입력')
        src = st.radio('굿즈 사진', ['F에서 고른 목업', '직접 올리기'], horizontal=True, key='d_src')
        source = kind = None
        if src == 'F에서 고른 목업':
            picks = store.list_jobs(['done'], game_id=gid, kind='f_pick', limit=12)
            if not picks:
                st.info('F 굿즈 목업에서 먼저 목업을 골라 주세요.')
            else:
                j = st.selectbox('고른 목업', picks, format_func=lambda j: f"#{j['id']} {S.KIND_KO[j['params']['kind']]} · {S.MOCK_LABEL[j['params']['cand']][0]}",
                                 key='d_pick')
                source, kind = j['result']['file'], j['params']['kind']
                st.image(str(absp(source)), width=260)
        else:
            up = st.file_uploader('F 목업이나 실제 굿즈 사진 한 장', type=['png', 'jpg', 'jpeg'], key='d_up')
            st.caption(f'굿즈 사진: {upload_rule("goods")}')
            if up and upload_errors([up], 'goods'):
                up = None
            kind = st.selectbox('굿즈 종류', list(S.KIND_KO), format_func=S.KIND_KO.get, key='d_kind')
            if up:
                st.image(up, width=260)
        st.caption('굿즈 부분은 결과에서도 원본 픽셀 그대로 남아요(R1n은 원본에 조명만 옮김). 마스크는 BiRefNet으로 이 사진에서 계산해요.')
        scene = st.segmented_control('장면', list(S.SCENES), default='desk', format_func=S.SCENE_LABEL.get, key='d_scene', required=True)
        if scene and scene != 'desk':
            st.caption('desk 외 장면은 15·16에서만 썼어요(21 상세 페이지는 desk).')
        method = st.radio('배경 방식', ['R1n', 'Y'], captions=[METHOD_CAPTION['R1n'], METHOD_CAPTION['Y']], key='d_method')
        relight = st.toggle('조명 맞추기 (YR1n)', key='d_relight', disabled=method != 'Y')
        m = 'YR1n' if method == 'Y' and relight else method
        ok = scene and (source or (src == '직접 올리기' and up))
        if st.button('배경 생성 요청', type='primary', disabled=not ok):
            if src == '직접 올리기':
                source = save_upload(up, 'd_goods')
            p = dict(source=source, kind=kind, scene=scene, method=m)
            st.session_state.setdefault('d_job', {})[gid] = store.add_job(gid, 'd', f'D 굿즈 배경 ({m} · {S.SCENE_LABEL[scene]})', p,
                                                                          tasks.stages_of('d', p))
            st.rerun()
        st.caption('처리 단계: R1n → ③ SDXL 빈 배경 → ④ 마스크 → ⑥ IC-Light · Y → ④ 마스크 → ⑤ Y 배경 (조명 맞추기를 켜면 → ⑥ IC-Light).')
    with right:
        st.subheader('결과')
        jid = st.session_state.get('d_job', {}).get(gid)
        if jid:
            job_box(jid, 'D 배경', show)
        else:
            st.info('굿즈 사진과 장면을 고르고 배경 생성을 요청해 주세요.')
