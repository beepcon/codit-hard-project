# 대기열 워커: 기다리는 요청을 모델 단계별로 모아, 단계마다 별도 프로세스에서 모델을 한 번 불러 처리 (21 단계별 묶음 처리와 같음)
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

# python src/app/core/worker.py 로 실행해도 app 패키지를 찾게 함
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd

from app.core import children as CH
from app.core import settings as S
from app.core import store, tasks
from app.core.paths import CHILD_DIR, LOCK_PATH, STAGE_CSV, STATE_PATH

CHILD_CODE = {'copy': CH.CHILD_COPY, 'c_image': CH.CHILD_C, 'sdxl_bg': CH.CHILD_SDXL, 'mask': CH.CHILD_MASK, 'y': CH.CHILD_Y,
              'iclight': CH.CHILD_IC}
HEARTBEAT_SEC = 2
STALE_SEC = 20
APP_PID = int(os.environ.get('APP_PID', '0') or 0)  # 앱이 띄운 워커만 앱이 꺼지면 같이 꺼짐 (직접 실행하면 0)
CUR = {'proc': None}  # 지금 돌고 있는 모델 프로세스 (워커가 꺼질 때 같이 끄려고 둠)
STATE = dict(pid=os.getpid(), started=time.time(), heartbeat=time.time(), stage=None, job_ids=[], done=0, total=0,
             stage_started=None, log=[])


_LOCK = threading.Lock()


SAVE_TRIES = 5
SAVE_WAIT_SEC = 0.1


def save_state(**kw):
    # 상태 파일을 다른 프로세스가 잡고 있으면 Windows에서 os.replace가 PermissionError(WinError 5)를 내고,
    # 예전에는 이 오류로 워커가 꺼졌다(11/04 worker.log, 시연 중 A 요청이 142초 밀림).
    # 조금씩 더 기다리며 다시 해 보고, 그래도 안 되면 이번 기록만 건너뛴다. 다음 기록 때 최신 상태가 다시 쓰인다
    with _LOCK:
        STATE.update(kw, heartbeat=time.time())
        tmp = STATE_PATH.with_suffix(f'.{os.getpid()}.tmp')
        for k in range(SAVE_TRIES):
            try:
                tmp.write_text(json.dumps(STATE, ensure_ascii=False), encoding='utf-8')
                os.replace(tmp, STATE_PATH)
                return True
            except OSError:
                time.sleep(SAVE_WAIT_SEC * (k + 1))
        STATE['save_fail'] = STATE.get('save_fail', 0) + 1
        # log()를 쓰면 다시 save_state를 부르므로 print만 한다
        print(f'[{time.strftime("%H:%M:%S")}] 상태 파일 저장 {SAVE_TRIES}번 실패 (누적 {STATE["save_fail"]}번), 이번 기록은 건너뜀', flush=True)
        return False


def app_alive(pid):
    if os.name != 'nt':
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    # Windows에서는 os.kill(pid, 0)이 Ctrl+C를 보내므로 쓰지 않고, 프로세스 핸들로 아직 실행 중인지 본다
    import ctypes
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.OpenProcess.restype = ctypes.c_void_p
    k.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    h = k.OpenProcess(0x00100000 | 0x1000, False, pid)  # SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ctypes.get_last_error() == 5  # 접근 거부는 프로세스가 있다는 뜻, 그 밖(없는 번호)은 꺼진 것
    try:
        return k.WaitForSingleObject(h, 0) == 0x102  # WAIT_TIMEOUT = 아직 실행 중
    finally:
        k.CloseHandle(h)


def stop_if_app_gone():
    # 앱 창을 닫으면 워커와 모델 프로세스를 끈다. 처리 중이던 요청은 상태가 그대로라 다음 실행 때 그 단계부터 다시 한다
    if not APP_PID or app_alive(APP_PID):
        return
    p = CUR['proc']
    if p is not None and p.poll() is None:
        p.kill()
    print(f'[{time.strftime("%H:%M:%S")}] 앱(pid {APP_PID})이 꺼져 워커를 끔. 처리 중이던 단계는 다음 실행 때 다시 함', flush=True)
    try:
        # 다음에 앱을 켜면 20초를 기다리지 않고 바로 새 워커를 띄우도록 심장 박동을 0으로 남김
        STATE_PATH.write_text(json.dumps(dict(STATE, heartbeat=0, stage=None), ensure_ascii=False), encoding='utf-8')
    except OSError:
        pass
    os._exit(0)


def heartbeat():
    # 모델 로드처럼 출력이 없는 동안에도 앱이 워커가 살아 있음을 알 수 있게 2초마다 기록
    while True:
        time.sleep(HEARTBEAT_SEC)
        stop_if_app_gone()
        try:
            save_state()
        except OSError:
            pass


def log(msg):
    line = f'[{time.strftime("%H:%M:%S")}] {msg}'
    print(line, flush=True)
    save_state(log=(STATE['log'] + [line])[-60:])


def read_state():
    try:
        return json.loads(STATE_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def acquire_lock():
    # 다른 워커가 살아 있으면(심장 박동이 최근) 이 워커는 끝냄
    st = read_state()
    if st.get('pid') and st.get('pid') != os.getpid() and time.time() - st.get('heartbeat', 0) < STALE_SEC:
        return False
    LOCK_PATH.write_text(str(os.getpid()), encoding='utf-8')
    return True


def run_child(stage, args):
    # 21 run_stage와 같음: 별도 프로세스 실행, 진행 출력을 줄마다 받아 상태 파일에 남김
    csv_p, js_p = CHILD_DIR / f'{stage}.csv', CHILD_DIR / f'{stage}.json'
    csv_p.unlink(missing_ok=True)
    js_p.unlink(missing_ok=True)
    started, t0 = time.strftime('%Y-%m-%d %H:%M:%S'), time.perf_counter()
    proc = subprocess.Popen([sys.executable, '-c', CH.CHILD_HEAD + CHILD_CODE[stage]], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    CUR['proc'] = proc
    proc.stdin.write(json.dumps(dict(args, csv=str(csv_p.resolve()), stage_json=str(js_p.resolve())), ensure_ascii=False))
    proc.stdin.close()
    tail = []
    for line in proc.stdout:
        line = line.rstrip('\n')
        tail = (tail + [line])[-30:]
        m = re.search(r' (\d+)/(\d+) ', line)
        if m:
            save_state(done=int(m.group(1)), total=int(m.group(2)))
        if line.strip():
            log(line[:300])
    rc = proc.wait()
    CUR['proc'] = None
    wall = round(time.perf_counter() - t0, 2)
    got = pd.read_csv(csv_p, keep_default_na=False).to_dict('records') if csv_p.exists() else []
    st = json.loads(js_p.read_text(encoding='utf-8')) if js_p.exists() else {}
    return got, dict(started=started, ended=time.strftime('%Y-%m-%d %H:%M:%S'), wall_sec=wall, returncode=rc, tail='\n'.join(tail), **st)


def num(x):
    v = pd.to_numeric(x, errors='coerce')
    return 0.0 if pd.isna(v) else float(v)


def stage_row(stage, n_items, n_ok, items, st, job_ids):
    # 21 finish_stage와 같은 단계 기록 (고정 시간 = 전체 − 항목 시간 합)
    row = dict(stage=stage, model=tasks.STAGE_MODEL[stage], started=st['started'], ended=st['ended'], n_items=n_items, n_ok=n_ok,
               wall_sec=st['wall_sec'], import_sec=st.get('import_sec'), load_sec=st.get('load_sec'),
               extra_load_sec=st.get('extra_load_sec', 0.0), items_sec=round(items, 2), fixed_sec=round(st['wall_sec'] - items, 2),
               item_sec_mean=round(items / n_ok, 2) if n_ok else None, peak_vram_gb=st.get('peak_vram_gb'),
               returncode=st['returncode'], job_ids=json.dumps(job_ids))
    pd.DataFrame([row]).to_csv(STAGE_CSV, mode='a', header=not STAGE_CSV.exists(), index=False, encoding='utf-8-sig')


def advance(job, result, error=''):
    now = time.time()
    if error:
        store.set_job(job['id'], status='error', error=error[:1000], result=result, ended=now)
        return
    idx = job['stage_idx'] + 1
    done = idx >= len(job['stages'])
    cur = store.get_job(job['id'])
    if cur['status'] == 'cancelled':
        store.set_job(job['id'], result=result, stage_idx=idx)
        return
    store.set_job(job['id'], result=result, stage_idx=idx, status='done' if done else 'running', ended=now if done else None)


def run_compose(jobs, games):
    started, t0 = time.strftime('%Y-%m-%d %H:%M:%S'), time.perf_counter()
    items, n_ok = 0.0, 0
    for k, job in enumerate(jobs, 1):
        try:
            res = tasks.compose_job(job, games[job['game_id']])
            items += res['compose_sec']
            n_ok += 1
            advance(job, res)
        except Exception as e:
            advance(job, job['result'], f'{type(e).__name__}: {e}')
        log(f"합성 {k}/{len(jobs)} 요청 #{job['id']}")
    st = dict(started=started, ended=time.strftime('%Y-%m-%d %H:%M:%S'), wall_sec=round(time.perf_counter() - t0, 2), returncode=0,
              import_sec=0.0, load_sec=0.0, peak_vram_gb=0.0)
    stage_row('compose', len(jobs), n_ok, items, st, [j['id'] for j in jobs])


def run_stage(stage, jobs, games):
    # 요청마다 작업을 만들고, 같은 파일(같은 장면의 빈 배경 등)은 한 번만 만듦
    per_job, todo = {}, {}
    for job in jobs:
        try:
            ts = tasks.tasks_for(stage, job, games[job['game_id']])
        except Exception as e:
            advance(job, job['result'], f'작업 만들기 실패 ({stage}): {type(e).__name__}: {e}')
            continue
        # 결과 열쇠: 문구 작업은 id, 나머지는 file (21 별도 프로세스 코드와 같음)
        keys = [t.get('file', t.get('id')) for t in ts]
        per_job[job['id']] = (job, keys)
        for k, t in zip(keys, ts):
            todo.setdefault(k, t)
    by = {}
    if todo:
        got, st = run_child(stage, dict(STAGE_ARGS_CACHE[stage](), tasks=list(todo.values())))
        by = {x['file']: x for x in got}
        items = sum(num(x.get('sec')) + num(x.get('extra_sec')) for x in got if x.get('error', '') == '')
        n_ok = sum(1 for x in got if x.get('error', '') == '')
        stage_row(stage, len(todo), n_ok, items, st, list(per_job))
        if st['returncode'] != 0:
            log(f'{stage} 프로세스 종료 코드 {st["returncode"]}')
    for jid, (job, files) in per_job.items():
        recs = [by.get(f, dict(file=f, error='프로세스가 결과를 남기지 않음 (위 단계 기록 참고)')) for f in files]
        errs = [r['error'] for r in recs if r.get('error', '')]
        if errs:
            advance(job, job['result'], f'{S.STAGE_INFO[stage][0]} 단계 오류: {errs[0]}')
            continue
        try:
            advance(job, tasks.apply(stage, job, recs))
        except Exception as e:
            advance(job, job['result'], f'결과 정리 실패 ({stage}): {type(e).__name__}: {e}')


STAGE_ARGS_CACHE = tasks.STAGE_ARGS


def loop_once():
    jobs = store.list_jobs(['queued', 'running'], limit=1000)
    if not jobs:
        save_state(stage=None, job_ids=[], done=0, total=0)
        return False
    games = {g['id']: g for g in store.list_games()}
    for j in jobs:
        if j['game_id'] not in games:
            advance(j, j['result'], '등록된 게임이 지워짐')
    jobs = [j for j in jobs if j['game_id'] in games]
    stage = next((s for s in S.STAGES if any(store.current_stage(j) == s for j in jobs)), None)
    if stage is None:
        return False
    batch = sorted([j for j in jobs if store.current_stage(j) == stage], key=lambda j: j['id'])
    now = time.time()
    for j in batch:
        if j['status'] == 'queued':
            store.set_job(j['id'], status='running', started=now)
    batch = [store.get_job(j['id']) for j in batch]
    save_state(stage=stage, job_ids=[j['id'] for j in batch], done=0, total=len(batch), stage_started=now)
    log(f"{S.STAGE_INFO[stage][0]} 단계 시작 · 요청 {', '.join('#' + str(j['id']) for j in batch)}")
    if stage == 'compose':
        run_compose(batch, games)
    else:
        run_stage(stage, batch, games)
    log(f"{S.STAGE_INFO[stage][0]} 단계 끝")
    return True


def main():
    store.init()
    if not acquire_lock():
        print('다른 워커가 실행 중이라 종료', flush=True)
        return
    save_state(stage=None)
    threading.Thread(target=heartbeat, daemon=True).start()
    log(f'워커 시작 (pid {os.getpid()})')
    while True:
        try:
            busy = loop_once()
        except Exception:
            log('워커 오류: ' + traceback.format_exc()[-800:])
            busy = False
        if not busy:
            save_state()
            time.sleep(HEARTBEAT_SEC)


if __name__ == '__main__':
    main()
