import re

import streamlit as st

from app.core import settings as S
from app.core import store, tasks
from app.core.paths import absp
from app.views.common import download, header, job_box, picked


def choose(label, jobs, sec, fmt, img_of, key):
    if not jobs:
        st.info(f'{label}가 아직 없어요.')
        return None
    ids = [j['id'] for j in jobs]
    pre = picked(sec)
    jid = st.radio(label, ids, index=ids.index(pre) if pre in ids else 0, format_func=lambda i: fmt(next(j for j in jobs if j['id'] == i)),
                   horizontal=True, key=key)
    j = next(x for x in jobs if x['id'] == jid)
    st.image(str(absp(img_of(j))), width=320)
    return j


def cb_results(gid):
    # 이미 만든 C 이미지(B에서 가져온 것 포함)와 B 배너의 글자 얹기 전 그림
    out = [(j['result']['image'], f"C #{j['id']} {j['params'].get('request', '')[:14]}") for j in store.list_jobs(['done'], game_id=gid, kind='c_image', limit=20)]
    out += [(j['result'].get('raw') or j['params'].get('raw'), f"B #{j['id']} {j['params'].get('request', '')[:14]}")
            for j in store.list_jobs(['done'], game_id=gid, kind='b_banner', limit=20) if j['result'].get('raw') or j['params'].get('raw')]
    return [(p, lab) for p, lab in out if p and absp(p).exists()]


def show_page(job):
    r = job['result']
    st.caption(f"요청 #{job['id']} · {r['width']} × {r['height']} px · 합성 {r.get('compose_sec')}초")
    st.image(str(absp(r['page'])), width=344, caption='미리보기 (40% 축소). 실제 크기 가로 860px · 세로 길이 제한 없음')
    download(r['page'], 'PNG 다운로드', f'p_dl_{job["id"]}')
    if st.session_state.get('p_applied') != job['id']:
        # 만든 문구를 왼쪽 입력란에 채워 "글자만 고쳐 다시 합성"에 쓰게 함 (입력란은 다음 실행에서 바꿀 수 있어 다시 그림)
        st.session_state['p_applied'] = job['id']
        st.session_state['p_pending'] = tasks.page_texts(job)
        st.rerun()
    made = r.get('copy', {})
    if made:
        st.caption('자동으로 만든 문구: ' + ', '.join(f"{k} ({'규칙 통과' if not v['problems'] else '규칙 실패, 그대로 넣음'})" for k, v in made.items()))


def render():
    g = header('상세 페이지 만들기', '앞에서 만든 그림과 문구를 구역별로 모아 가로 860px 세로형 상세 페이지 한 장으로 합쳐요.')
    if not g:
        st.warning('먼저 게임을 등록해 주세요.')
        return
    gid = g['id']
    pend = st.session_state.pop('p_pending', None)
    if pend:
        st.session_state.update(p_title=' '.join(pend['title']), p_intro='\n'.join(pend['intro']), p_mock=' '.join(pend['mockup']),
                                p_stage=' '.join(pend['staging']))
    left, right = st.columns([1.25, 1], gap='large')
    with left:
        st.subheader('구역별 내용')
        with st.expander('① 대표 그림 + 제목 · C 이미지', expanded=True):
            cj = choose('그림 고르기', store.list_jobs(['done'], game_id=gid, kind='c_image', limit=8), '①',
                        lambda j: f"C #{j['id']} {j['params'].get('request', '')[:14]}", lambda j: j['result']['image'], 'p_c')
            title = st.text_input('제목 (비우면 자동 생성)', key='p_title')
        with st.expander('② 게임 소개 문구 · A 문구', expanded=True):
            aj = store.list_jobs(['done'], game_id=gid, kind='a', limit=8)
            ids = [j['id'] for j in aj]
            pre = picked('②')

            def lines_of(i):
                j = next((x for x in aj if x['id'] == i), None)
                return '\n'.join(j['result']['copy']['intro']['lines']) if j else ''

            if 'p_a' not in st.session_state or st.session_state.get('p_a_pre') != pre:
                st.session_state['p_a'] = pre if pre in ids else (ids[0] if ids else None)
                st.session_state['p_a_pre'] = pre
                st.session_state['p_intro'] = lines_of(st.session_state['p_a'])
            if not ids:
                st.info('A 홍보 문구가 아직 없어요. 상세 페이지 문구는 A에서 올린 스크린샷으로 만들어요(21과 같음).')
            a_id = st.selectbox('A 홍보 문구', ids, format_func=lambda i: f'A #{i}', key='p_a',
                                on_change=lambda: st.session_state.update(p_intro=lines_of(st.session_state['p_a'])))
            a_job = next((j for j in aj if j['id'] == a_id), None)
            intro = st.text_area('소개 문구 (한 줄에 한 문장, 마지막 줄 = SNS 문장)', key='p_intro', height=130)
            st.caption('A 홍보 문구에서 보낸 결과. 비어 있으면 상세 페이지 요청 때 A의 스크린샷으로 함께 만들어요.')
        cbs = cb_results(gid)
        with st.expander('게임 화면 · 레퍼런스 아트 + 대표 게임 화면', expanded=True):
            # 레퍼런스 아트는 등록한 것 전부. 대표 게임 화면은 A에서 올린 스크린샷, 없으면 C·B 결과에서 고름
            refs = [r for r in g['refs'] if absp(r).exists()]
            shot_opts = []
            if a_job and a_job['params'].get('image') and absp(a_job['params']['image']).exists():
                shot_opts.append((a_job['params']['image'], f"A #{a_job['id']} 스크린샷"))
            shot_opts += cbs
            if shot_opts:
                k = st.selectbox('대표 게임 화면', range(len(shot_opts)), format_func=lambda i: shot_opts[i][1], key='p_shot',
                                 help='A에서 올린 스크린샷이 없으면 C·B에서 만든 그림을 써요.')
                shot = shot_opts[k][0]
                st.image(str(absp(shot)), width=320)
            else:
                shot = None
                st.info('A 스크린샷이나 C·B 결과가 아직 없어요. 레퍼런스 아트만 넣어요.')
            st.caption(f'레퍼런스 아트 {len(refs)}장 (게임 등록에서 올린 것 전부)')
            cols = st.columns(6)
            for c, r in zip(cols * 3, refs[:18]):
                c.image(str(absp(r)), width='stretch')
        with st.expander('일러스트 · C·B 결과 여러 장', expanded=True):
            labels = {p: lab for p, lab in cbs}
            illus = st.multiselect('넣을 그림 (고른 순서대로, 비우면 구역을 넣지 않음)', list(labels), format_func=labels.get, key='p_illus',
                                   help='1~3장은 기울인 칸, 4장부터는 2열 격자로 넣어요(26).')
            if illus:
                cols = st.columns(4)
                for c, x in zip(cols * 5, illus):
                    c.image(str(absp(x)), width='stretch')
        with st.expander('③ 굿즈 목업 + 문구 · F 목업', expanded=True):
            fj = choose('F 목업', store.list_jobs(['done'], game_id=gid, kind='f_pick', limit=8), '③',
                        lambda j: f"#{j['id']} {S.KIND_KO[j['params']['kind']]} {S.MOCK_LABEL[j['params']['cand']][0]}",
                        lambda j: j['result']['file'], 'p_f')
            mtxt = st.text_area('구역 문구 (비우면 자동 생성 · 수정 가능)', key='p_mock')
        with st.expander('④ 굿즈 연출 사진 + 문구 · D 배경', expanded=True):
            # 11/03: 책상 외 카페·스튜디오도 받음. ④ 문구 요청의 장면 설명은 settings SCENE_KO (21에서 확인한 장면은 책상뿐)
            dj = choose('D 결과', store.list_jobs(['done'], game_id=gid, kind='d', limit=8), '④',
                        lambda j: f"#{j['id']} {j['params']['method']} {S.SCENE_LABEL[j['params']['scene']]}", lambda j: j['result']['final'], 'p_d')
            stxt = st.text_area('구역 문구 (비우면 자동 생성 · 수정 가능)', key='p_stage')
        with st.expander('⑤ 굿즈 구매 정보 · 직접 입력', expanded=True):
            # 입력 칸과 예시는 21 "설정" 셀 PURCHASE와 같음 (③·④ 굿즈를 파는 정보)
            st.caption('③·④에 나온 굿즈의 판매 정보를 적어 주세요. 비운 칸은 페이지에 넣지 않아요.')
            c1, c2 = st.columns(2)
            purchase = {'상품명': c1.text_input('상품명', key='p_name', placeholder='예: 냥기사의 여행 일러스트 티셔츠'),
                        '판매가': c2.text_input('판매가', key='p_price', placeholder='예: 29,000원'),
                        '옵션': c1.text_input('옵션', key='p_option', placeholder='예: S / M / L / XL'),
                        '배송비': c2.text_input('배송비', key='p_ship_fee', placeholder='예: 3,000원'),
                        '출고': c1.text_input('출고', key='p_out', placeholder='예: 주문 후 3일 이내')}
            cta_ko = st.radio('페이지 맨 아래', ['넣지 않음', '구매 버튼', '출시 예정'], key='p_cta', horizontal=True)
            buy_url = st.text_input('구매 링크', key='p_url', placeholder='https://…').strip() if cta_ko == '구매 버튼' else ''
            st.caption('구매 버튼: page.html에서는 눌러 이동하고, PNG는 누를 수 없어 버튼 아래에 주소가 글자로 들어가요. '
                       '출시 예정: 누르는 버튼이 아닌 꼬리표로 들어가요.')
            bad_url = cta_ko == '구매 버튼' and not re.match(r'^https?://\S+$', buy_url)
            if bad_url:
                st.warning('구매 버튼을 넣으려면 http:// 또는 https://로 시작하는 구매 링크를 넣어 주세요.')
        missing = [n for n, x in [('① C 이미지', cj), ('② A 문구', a_job), ('③ F 목업', fj), ('④ D 결과', dj)] if x is None]
        if missing:
            st.warning('먼저 만들어야 하는 구역: ' + ', '.join(missing) + ' → 해당 화면에서 만들어 주세요.')
        intro_lines = [x.strip() for x in intro.splitlines() if x.strip()]
        params = None
        if not missing and not bad_url:
            ap = a_job['params']
            params = dict(c_image=cj['result']['image'], mockup=fj['result']['file'], d_image=dj['result']['final'],
                          goods_kind=fj['params']['kind'], scene=dj['params']['scene'], purchase=purchase,
                          cta={'넣지 않음': 'none', '구매 버튼': 'buy', '출시 예정': 'soon'}[cta_ko], buy_url=buy_url,
                          texts=dict(title=title.strip(), intro=intro_lines, mockup=mtxt.strip(), staging=stxt.strip()),
                          points=ap.get('points', []), must=ap.get('must', ''),
                          tone=S.TONES['친근하게'],
                          # 문구 모델에 넣는 이미지: 21과 같이 게임 스크린샷 (A에서 올린 것)
                          copy_image=ap['image'],
                          # 26 2번(HTML) 페이지의 게임 화면·일러스트 구역
                          shot=shot, refs=refs, illus=illus)
        b1, b2 = st.columns(2)
        if b1.button('상세 페이지 만들기 요청', type='primary', disabled=params is None):
            st.session_state.setdefault('p_job', {})[gid] = store.add_job(gid, 'page', '상세 페이지', params, tasks.stages_of('page', params))
            st.rerun()
        if b2.button('글자만 고쳐 다시 합성', disabled=params is None or tasks.page_missing(params) != []):
            st.session_state.setdefault('p_job', {})[gid] = store.add_job(gid, 'page', '상세 페이지 (다시 합성)', params, ['compose'])
            st.rerun()
        st.caption('빈 문구 구역이 있으면 ① 문구 단계에서 만들고 ⑦ 합성 단계에서 합쳐요. "글자만 고쳐 다시 합성"은 모든 문구가 채워져 있을 때 쓸 수 있어요.')
    with right:
        st.subheader('미리보기')
        jid = st.session_state.get('p_job', {}).get(gid)
        if jid:
            job_box(jid, '합성', show_page)
        else:
            st.info('구역을 채우고 상세 페이지 만들기를 요청해 주세요.')
