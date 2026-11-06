# 실행: 프로젝트 폴더에서  streamlit run src/app/streamlit_app.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from app.core import runner, store  # noqa: E402
from app.core import settings as S  # noqa: E402
from app.views import a_copy, b_banner, c_style, d_background, detail_page, f_mockup, main, queue  # noqa: E402

st.set_page_config(page_title='광고 콘텐츠 스튜디오', layout='wide')
store.init()
runner.ensure_worker()

PAGES = {
    'main': st.Page(main.render, title='게임 등록·목록', url_path='games', default=True),
    'a': st.Page(a_copy.render, title='A 홍보 문구', url_path='copy'),
    'b': st.Page(b_banner.render, title='B 이벤트 배너', url_path='banner'),
    'c': st.Page(c_style.render, title='C 그림체 이미지', url_path='style'),
    'f': st.Page(f_mockup.render, title='F 굿즈 목업', url_path='mockup'),
    'd': st.Page(d_background.render, title='D 굿즈 배경', url_path='background'),
    'page': st.Page(detail_page.render, title='상세 페이지 만들기', url_path='detail'),
    'queue': st.Page(queue.render, title='작업 대기열', url_path='queue'),
}
st.session_state['pages'] = PAGES
GROUPS = {'게임': ['main'], '콘텐츠 (A · B · C)': ['a', 'b', 'c'], '굿즈 (F · D)': ['f', 'd'], '상세 페이지': ['page'], '작업': ['queue']}
# 캔버스 사이드바 순서(제목 → 게임 선택 → 메뉴 → 대기열)로 그리려고 기본 메뉴는 숨기고 링크를 직접 둠
nav = st.navigation([PAGES[k] for ks in GROUPS.values() for k in ks], position='hidden')

with st.sidebar:
    st.markdown('### 광고 콘텐츠 스튜디오')
    st.caption('1인 인디게임 개발사용')
    games = store.list_games()
    if games:
        ids = [g['id'] for g in games]
        # 게임 등록 직후 고른 게임: 선택 위젯을 만들기 전에 넣어야 함
        if 'game_id_pending' in st.session_state:
            st.session_state['game_id'] = st.session_state.pop('game_id_pending')
        if st.session_state.get('game_id') not in ids:
            st.session_state['game_id'] = ids[0]
        st.selectbox('작업할 게임', ids, key='game_id', format_func=lambda i: next(g['name'] for g in games if g['id'] == i))
        g = store.get_game(st.session_state['game_id'])
        st.caption(' · '.join(x for x in [g['label'], '레퍼런스 아트 등록됨' if g['refs'] else '레퍼런스 아트 없음',
                                          'LoRA 있음' if g['lora'] else 'LoRA 없음'] if x))
    for grp, ks in GROUPS.items():
        st.caption(grp)
        for k in ks:
            st.page_link(PAGES[k])

    @st.fragment(run_every=3)
    def _queue_box():
        with st.container(border=True):
            waiting = store.list_jobs(['queued', 'running'], limit=1000)
            stt = runner.state()
            st.markdown(f'**작업 대기열** · 대기 {len(waiting)}건')
            if not runner.alive(stt):
                st.caption('워커가 꺼져 있음 → 다시 띄우는 중')
                runner.ensure_worker()
            elif stt.get('stage'):
                k = list(S.STAGES).index(stt['stage']) + 1
                st.progress(min(stt.get('done', 0) / max(stt.get('total', 1), 1), 1.0),
                            text=f"지금 단계: {S.STAGE_INFO[stt['stage']][0]} ({len(S.STAGES)}단계 중 {k})")
            else:
                st.caption('처리할 요청 없음')
            st.page_link(PAGES['queue'], label='진행 상황 보기 →')
    _queue_box()

nav.run()
