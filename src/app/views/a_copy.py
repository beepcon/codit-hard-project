import html

import pandas as pd
import streamlit as st

from app.core import settings as S
from app.core import store, tasks
from app.core import textcfg as T
from app.core.paths import absp
from app.views.common import header, job_box, pick, save_upload, upload_errors, upload_rule

# A check() 실패 이유 문장 → 규칙 이름 (21·13 검사와 같은 규칙)
RULES = [('형식 (소개 2문장 · SNS 1문장 · JSON)', ('JSON', '문장이어야')), ('꼭 넣을 문구 (글자 그대로, 문장 안)', ('꼭 넣을 문구',)),
         ('판촉 표현·지어낸 숫자 없음', ('판촉',)), ('상투 구절 없음', ('쓰지 말라는',))]


def rule_table(probs, need_must=True):
    rows = []
    for name, marks in RULES:
        if '꼭 넣을' in name and not need_must:
            continue
        hit = [p for p in probs if any(m in p for m in marks)]
        rows.append({'규칙': name, '결과': '실패' if hit else '통과', '이유': ' / '.join(hit)})
    return pd.DataFrame(rows)


def history(job, item):
    # 생성 회차별 글과 검사 결과 (21과 같은 순서: 첫 생성 → 후보 n개 → 구체적 재요청)
    p = job['params']
    texts = item['texts_all']
    rows = []
    for i, t in enumerate(texts):
        if i == 0:
            how = '첫 생성 (탐욕적 디코딩)'
        elif i <= S.N_CAND and len(texts) > 1:
            how = f'후보 {i}/{S.N_CAND} (샘플링)'
        else:
            how = '구체적 재요청 (고치는 방법 첨부)'
        pr = T.check(t, p['must'], ' '.join(p['points'] + ([p['must']] if p['must'] else [])), T.BANNED_PROMO, T.BANNED_CLICHE,
                     bool(p['must']))
        d = T.parse_json(t) or {}
        rows.append({'회차': i + 1, '방식': how, '결과': '통과' if not pr else '실패', '실패 이유': ' / '.join(pr), 'SNS 문장': d.get('sns', '')})
    return pd.DataFrame(rows)


def show(job):
    p, item = job['params'], job['result']['copy']['intro']
    lines = item['lines']
    store_txt, sns = (' '.join(lines[:-1]), lines[-1]) if len(lines) > 1 else (lines[0], '')
    st.caption(f"요청 #{job['id']} · 생성 {item['n_gen']}회 (모델 호출 {item['n_calls']}번) · {item['sec']}초")
    st.text_area('스토어 소개 문구 (2문장, 고칠 수 있음)', store_txt, key=f'a_store_{job["id"]}', height=110)
    st.markdown('**SNS 문구** (1문장)')
    s = html.escape(sns)
    if p['must'] and p['must'] in sns:
        s = s.replace(html.escape(p['must']), f'<mark>{html.escape(p["must"])}</mark>')
    st.markdown(f'<div style="padding:10px;border:1px solid #4c6b99;border-radius:8px">{s}</div>', unsafe_allow_html=True)
    if p['must']:
        st.caption('강조 표시 = 꼭 넣을 문구가 들어간 자리')
    probs = item['problems']
    st.markdown(f"**규칙 검사** · {'전부 통과' if not probs else f'실패 {len(probs)}건 (최종 문구를 그대로 보여 줌)'}")
    st.dataframe(rule_table(probs, bool(p['must'])), hide_index=True, width='stretch')
    with st.expander(f"생성 기록 · {len(item['texts_all'])}회"):
        st.dataframe(history(job, item), hide_index=True, width='stretch')
        if item['fb_sent']:
            st.caption('보낸 재요청 문장')
            st.code(item['fb_sent'], language=None)
    c1, c2, c3 = st.columns(3)
    if c1.button('다시 생성', key=f'a_re_{job["id"]}'):
        submit(job['game_id'], p)
    if c2.button('상세 페이지 ②에 쓰기', key=f'a_pick_{job["id"]}'):
        pick('②', job['id'])
    c3.download_button('TXT 다운로드', f"{st.session_state.get(f'a_store_{job['id']}', store_txt)}\n\n{sns}\n",
                       file_name=f"copy_{job['id']}.txt", key=f'a_txt_{job["id"]}')


def submit(gid, params):
    jid = store.add_job(gid, 'a', 'A 홍보 문구', params, tasks.stages_of('a', params))
    st.session_state.setdefault('a_job', {})[gid] = jid
    st.rerun()


def render():
    g = header('A. 스크린샷 → 홍보 문구', '게임 스크린샷 한 장으로 스토어 소개 문구 2문장과 SNS 문구 1문장을 만들어요.')
    if not g:
        st.warning('먼저 게임을 등록해 주세요.')
        return
    left, right = st.columns([1, 1.3], gap='large')
    with left:
        st.subheader('입력')
        f = st.file_uploader('스크린샷 (PNG · JPG 한 장)', type=['png', 'jpg', 'jpeg'], key='a_shot')
        st.caption(f'스크린샷: {upload_rule("screenshot")}')
        bad = bool(f) and upload_errors([f], 'screenshot')
        if f:
            st.image(f, caption='업로드한 스크린샷', width='stretch')
        pts = st.text_area('판매 포인트 (한 줄에 하나, 최우선 반영)', key='a_points',
                           help='비워 두면 게임 등록 때 적은 기본 판매 포인트만 써요.')
        must = st.text_input('꼭 넣을 문구', key='a_must', help='글자를 바꾸지 않고 SNS 문장 안에 그대로 넣어요. 문장 끝에 쉼표로 붙이면 실패로 봐요.')
        st.caption(f'톤: {S.TONES["친근하게"]}')
        if st.button('문구 생성 요청', type='primary', disabled=not f or bad):
            submit(g['id'], dict(image=save_upload(f, 'screenshots'), points=[x.strip() for x in pts.splitlines() if x.strip()],
                                 must=must.strip(), tone='친근하게'))
        st.caption('요청은 작업 대기열의 ① 문구 단계에서 처리돼요.')
    with right:
        st.subheader('결과')
        jid = st.session_state.get('a_job', {}).get(g['id'])
        if jid is None:
            done = store.list_jobs(['done'], game_id=g['id'], kind='a', limit=1)
            jid = done[0]['id'] if done else None
        if jid is None:
            st.info('아직 만든 문구가 없어요.')
        else:
            job = store.get_job(jid)
            if job and job['params'].get('image') and absp(job['params']['image']).exists():
                st.image(str(absp(job['params']['image'])), width=240)
            job_box(jid, 'A 문구', show)
