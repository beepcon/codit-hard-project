import io
import time
from pathlib import Path

import streamlit as st
from PIL import Image

from app.core import runner, store
from app.core import settings as S
from app.core.paths import UPLOAD_DIR, absp, rel


def game():
    return store.get_game(st.session_state.get('game_id'))


def header(title, caption):
    st.title(title)
    st.caption(caption)
    g = game()
    if g:
        st.markdown(f'대상 게임 **{g["name"]}** · 사이드바에서 바꿀 수 있어요')
    return g


def save_upload(f, sub):
    d = UPLOAD_DIR / sub
    d.mkdir(parents=True, exist_ok=True)
    p = d / f'{int(time.time() * 1000)}_{Path(f.name).name}'
    p.write_bytes(f.getvalue())
    return rel(p)


def upload_rule(kind):
    return f'긴 변 {S.UPLOAD_MIN_LONG[kind]}px 이상, {S.UPLOAD_RATIO_TEXT}'


def check_upload(f, kind):
    # 올린 그림 하나의 크기·비율이 기준 밖이면 고칠 방법을 담은 문장 목록, 기준 안이면 빈 목록
    try:
        w, h = Image.open(io.BytesIO(f.getvalue())).size
    except Exception:
        return [f'{f.name}: 그림 파일로 열 수 없어요.']
    out, need = [], S.UPLOAD_MIN_LONG[kind]
    lo, hi = S.UPLOAD_RATIO
    if max(w, h) < need:
        out.append(f'{f.name} ({w}×{h}px): 긴 변이 {need}px보다 작아요. 긴 변 {need}px 이상인 원본으로 다시 올려 주세요.')
    if w / h < lo:
        out.append(f'{f.name} ({w}×{h}px): 세로로 너무 길어요(가로:세로 {w / h:.2f}:1). 세로를 {int(w / lo)}px 이하로 잘라 3:4보다 넓게 만든 뒤 다시 올려 주세요.')
    elif w / h > hi:
        out.append(f'{f.name} ({w}×{h}px): 가로로 너무 길어요(가로:세로 {w / h:.2f}:1). 가로를 {int(h * hi)}px 이하로 잘라 3:1보다 좁게 만든 뒤 다시 올려 주세요.')
    return out


def upload_errors(files, kind):
    # 기준 밖 그림이 있으면 화면에 안내를 띄우고 True
    probs = [m for f in files for m in check_upload(f, kind)]
    if probs:
        st.error(f'{S.UPLOAD_KIND_KO[kind]} 기준({upload_rule(kind)})에 맞지 않아 올릴 수 없어요.\n\n' + '\n\n'.join('- ' + m for m in probs))
    return bool(probs)


def fmt_sec(sec):
    sec = int(max(sec or 0, 0))
    return f'{sec // 60:02d}:{sec % 60:02d}'


def elapsed(job):
    end = job.get('ended') or time.time()
    return end - job['created']


def stage_text(job):
    cur = store.current_stage(job)
    names = ' → '.join(S.STAGE_INFO[s][0] for s in job['stages'])
    if job['status'] == 'done':
        return f'완료 · {names}'
    if job['status'] == 'error':
        return f'오류 · {job["error"][:200]}'
    if job['status'] == 'cancelled':
        return '취소됨'
    st_ = runner.state()
    now = cur and st_.get('stage') == cur and job['id'] in st_.get('job_ids', [])
    return f"{S.STAGE_INFO[cur][0]} {'처리 중' if now else '대기'} · {names}"


def job_box(jid, label, on_done):
    # 요청 상태: 처리 중이면 2초마다 다시 읽고, 끝나면 결과를 그림
    @st.fragment(run_every=2)
    def _poll():
        job = store.get_job(jid)
        if job is None:
            return
        if job['status'] in ('queued', 'running'):
            with st.status(f"요청 #{jid} · {stage_text(job)} · 경과 {fmt_sec(elapsed(job))}", state='running'):
                st.write('작업 대기열에서 처리 중이에요. 다른 화면으로 가도 계속 처리돼요.')
                st.page_link(st.session_state['pages']['queue'], label='대기열 보기 →')
            st.session_state[f'_running_{jid}'] = True
        elif st.session_state.pop(f'_running_{jid}', False):
            st.rerun()
    job = store.get_job(jid)
    if job is None:
        return
    if job['status'] in ('queued', 'running'):
        _poll()
    elif job['status'] == 'done':
        st.status(f'{label} 완료 · 요청 #{jid} · {fmt_sec(elapsed(job))}', state='complete')
        on_done(job)
    elif job['status'] == 'error':
        st.status(f'요청 #{jid} 오류', state='error').write(job['error'])
    else:
        st.info(f'요청 #{jid}은 취소됐어요.')


def download(path, label, key):
    p = absp(path)
    if p.exists():
        st.download_button(label, p.read_bytes(), file_name=p.name, mime='image/png', key=key)


def pick(sec, value):
    # 상세 페이지에 쓸 결과를 게임별로 기억 (화면을 옮겨도 유지)
    st.session_state.setdefault('page_pick', {}).setdefault(st.session_state['game_id'], {})[sec] = value
    st.toast(f'상세 페이지 {sec}에 넣었어요.')


def picked(sec):
    return st.session_state.get('page_pick', {}).get(st.session_state.get('game_id'), {}).get(sec)
