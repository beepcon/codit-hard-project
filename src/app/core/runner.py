# 앱에서 워커 프로세스를 자동으로 띄우고 상태를 읽음
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from .paths import OUT, ROOT, STATE_PATH, WORKER_LOG

WORKER = Path(__file__).resolve().parent / 'worker.py'
STALE_SEC = 20
_START_MARK = OUT / 'worker_starting'


def state():
    try:
        return json.loads(STATE_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def alive(st=None):
    st = st if st is not None else state()
    return bool(st) and time.time() - st.get('heartbeat', 0) < STALE_SEC


def ensure_worker():
    # 심장 박동이 20초 넘게 없으면 워커를 새로 띄움 (여러 화면이 동시에 띄우지 않게 시작 표시를 20초 둠)
    if alive():
        return False
    try:
        if time.time() - _START_MARK.stat().st_mtime < STALE_SEC:
            return False
    except OSError:
        pass
    _START_MARK.write_text(str(time.time()), encoding='utf-8')
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    with open(WORKER_LOG, 'a', encoding='utf-8') as f:
        subprocess.Popen([sys.executable, str(WORKER)], cwd=str(ROOT), stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         creationflags=flags, start_new_session=os.name != 'nt',
                         # 앱(Streamlit 서버) 프로세스 번호: 앱 창을 닫으면 워커가 이 번호로 알아채고 스스로 꺼짐 (11/05 결정)
                         env={**os.environ, 'PYTHONIOENCODING': 'utf-8', 'APP_PID': str(os.getpid())})
    return True
