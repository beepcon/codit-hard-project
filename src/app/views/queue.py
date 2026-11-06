import time

import pandas as pd
import streamlit as st

from app.core import runner, store
from app.core import settings as S
from app.core.paths import STAGE_CSV
from app.views.common import elapsed, fmt_sec


def stage_marks(job):
    cur = store.current_stage(job)
    out = []
    for i, s in enumerate(job['stages']):
        no = S.STAGE_INFO[s][0].split()[0]
        if job['status'] == 'done' or i < job['stage_idx']:
            out.append(f'{no}✓')
        elif s == cur and job['status'] == 'running':
            out.append(f'{no}▶')
        else:
            out.append(no)
    return ' '.join(out)


def service_time():
    if S.SERVICE_CSV.exists():
        sv = pd.read_csv(S.SERVICE_CSV)
        return sv.batched_sec.mean(), sv.per_page_sec.mean()
    return None, None


def render():
    st.title('작업 대기열·진행 상황')
    st.markdown('모든 요청은 모델별 단계로 묶여 차례로 처리돼요. 같은 모델이 필요한 요청을 모아 모델을 한 번만 올려요.')

    @st.fragment(run_every=2)
    def live():
        stt = runner.state()
        jobs = store.list_jobs(limit=300)
        games = {g['id']: g['name'] for g in store.list_games()}
        waiting = [j for j in jobs if j['status'] in ('queued', 'running')]
        done_n = sum(j['status'] == 'done' for j in jobs)
        cur = stt.get('stage') if runner.alive(stt) else None
        m1, m2, m3, m4 = st.columns(4)
        m1.metric('대기 중인 요청', f'{len(waiting)}건')
        m1.markdown(f'완료 {done_n}건')
        m2.metric('현재 단계', S.STAGE_INFO[cur][0] if cur else '없음')
        m2.markdown(f"요청 {len(stt.get('job_ids', []))}건 · {stt.get('done', 0)}/{stt.get('total', 0)}" if cur else '처리할 요청 없음')
        m3.metric('경과 시간', fmt_sec(time.time() - stt['stage_started']) if cur and stt.get('stage_started') else '-')
        m3.markdown('현재 단계')
        b, p = service_time()
        m4.metric('상세 페이지 1장 처리 (21 측정)', f'약 {b:.0f}초' if b else '-')
        m4.markdown(f'요청마다 모델을 올리면 약 {p:.0f}초' if p else '')
        if not runner.alive(stt):
            st.warning('워커가 응답하지 않아요. 앱이 다시 띄워요 (outputs/app/worker.log 참고).')
            runner.ensure_worker()

        st.markdown('**단계 파이프라인**')
        cols = st.columns(len(S.STAGES))
        for c, s in zip(cols, S.STAGES):
            n = sum(store.current_stage(j) == s for j in waiting)
            state = '진행 중' if s == cur else ('대기' if n else '쉼')
            with c.container(border=True):
                st.markdown(f"**{S.STAGE_INFO[s][0]}** · {state}")
                st.markdown(S.STAGE_INFO[s][1])
                st.markdown(S.STAGE_INFO[s][2])
                st.markdown(f'{n}건' if s != cur else f"{stt.get('done', 0)} / {stt.get('total', 0)}건")
        if cur:
            st.progress(min(stt.get('done', 0) / max(stt.get('total', 1), 1), 1.0),
                        text=f"{S.STAGE_INFO[cur][0]} · 요청 {', '.join('#' + str(i) for i in stt.get('job_ids', []))}")

        st.markdown('**요청 목록**')
        rows = [{'번호': f"#{j['id']}", '게임': games.get(j['game_id'], '(지움)'), '기능': j['title'], '필요한 단계': stage_marks(j),
                 '상태': {'queued': '대기', 'running': '진행 중', 'done': '완료', 'error': '오류', 'cancelled': '취소'}[j['status']],
                 '경과': fmt_sec(elapsed(j)), '오류': j['error'][:120]} for j in jobs if j['stages']]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch', height=320)
        st.markdown('숫자 = 그 요청이 거치는 단계. ✓ 완료 · ▶ 진행 중 · 표시 없음 대기')
        with st.status('단계 기록', expanded=True, state='running' if cur else 'complete'):
            st.code('\n'.join(stt.get('log', [])[-25:]) or '(기록 없음)', language=None)

    live()
    with st.popover('끝난 요청 기록 지우기'):
        st.markdown('완료·오류·취소된 요청을 모두 지워요. 지운 완료 결과는 상세 페이지·C·F·D 화면의 선택지에서도 사라져요. '
                    '대기·진행 중인 요청과 결과 파일(outputs/app/jobs)은 그대로 남아요.')
        if st.button('지우기', type='primary'):
            st.success(f'끝난 요청 {store.delete_finished_jobs()}건을 지웠어요.')
    waiting = store.list_jobs(['queued', 'running'], limit=300)
    if waiting:
        c1, c2 = st.columns([3, 1], vertical_alignment='bottom')
        jid = c1.selectbox('취소할 요청', [j['id'] for j in waiting], format_func=lambda i: f'#{i}')
        if c2.button('취소'):
            store.cancel_job(jid)
            st.rerun()
        st.markdown('처리 중인 단계는 끝까지 돌고, 그 뒤 단계로 넘어가지 않아요.')
    b, p = service_time()
    st.info('왜 바로 나오지 않나요? GPU 24GB에 모델을 모두 함께 올릴 수 없어요(Qwen 최대 18.23GB + animagine 13.0GB, 21). '
            '그래서 요청을 모아 문구 → 그림 → SDXL → 마스크 → Y → IC-Light → 합성 순서로 단계마다 모델을 한 번만 올려 처리해요. '
            + (f'상세 페이지 1장 기준 묶음 처리 약 {b:.0f}초, 요청마다 모든 모델을 올리면 약 {p:.0f}초가 걸렸어요(21).' if b else ''))
    if STAGE_CSV.exists():
        with st.expander('단계별 처리 시간 기록 (최근 20번)'):
            st.dataframe(pd.read_csv(STAGE_CSV).tail(20), hide_index=True, width='stretch')
