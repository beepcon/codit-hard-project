# start.bat이 실행함: 처음이면 .venv를 만들고 requirements-app.txt·Chromium을 설치한 뒤 앱을 켬, 다음부터는 바로 앱을 켬
# 지금 쓰는 conda 환경은 건드리지 않음. 모델은 앱에서 처음 쓸 때 Hugging Face에서 받음
import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / '.venv'
REQ = ROOT / 'requirements-app.txt'
MARK = VENV / 'install_ok.txt'      # 설치가 끝까지 됐을 때만 남김 (requirements-app.txt 내용 해시)
LOG = VENV / 'install_log.txt'
VPY = VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
T0 = time.perf_counter()


def say(msg):
    print(f"[{time.strftime('%H:%M:%S')} | {time.perf_counter() - T0:6.0f}초] {msg}", flush=True)


def stop(msg):
    say('설치를 멈췄어요: ' + msg)
    if os.name == 'nt':
        input('엔터를 누르면 창이 닫혀요.')
    sys.exit(1)


def run(args, title):
    # 진행 줄을 화면에 바로 보여 주고 같은 내용을 install_log.txt에 남김
    say(title)
    with open(LOG, 'a', encoding='utf-8') as log:
        log.write(f'\n===== {time.strftime("%Y-%m-%d %H:%M:%S")} {title}\n$ {" ".join(map(str, args))}\n')
        p = subprocess.Popen([str(a) for a in args], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             encoding='utf-8', errors='replace', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
        for line in p.stdout:
            print(line, end='', flush=True)
            log.write(line)
        p.wait()
    if p.returncode != 0:
        stop(f'{title} 단계에서 오류가 났어요 (종료 코드 {p.returncode}). 기록: {LOG}')


def req_hash():
    return hashlib.sha256(REQ.read_bytes()).hexdigest()


def install():
    say(f'설치가 아직 안 됐거나 requirements-app.txt가 바뀌어서 설치부터 해요. 설치 위치: {VENV}')
    if sys.version_info[:2] != (3, 12):
        stop(f'Python 3.12가 필요해요. 지금은 {sys.version.split()[0]}이에요.')
    if not shutil.which('git'):
        stop('git이 필요해요 (diffusers를 GitHub 커밋에서 받음). https://git-scm.com 에서 설치한 뒤 다시 실행해 주세요.')
    if not VPY.exists():
        VENV.mkdir(exist_ok=True)
        run([sys.executable, '-m', 'venv', VENV], '가상환경 만들기 (.venv)')
    run([VPY, '-m', 'pip', 'install', '--upgrade', 'pip'], 'pip 업데이트')
    run([VPY, '-m', 'pip', 'install', '-r', REQ], 'requirements-app.txt 설치 (torch 등, 처음에는 오래 걸려요)')
    run([VPY, '-m', 'playwright', 'install', 'chromium'], '상세 페이지 합성용 Chromium 받기')
    MARK.write_text(req_hash(), encoding='utf-8')
    say('설치가 끝났어요.')


def main():
    if not REQ.exists():
        stop(f'{REQ.name}이 프로젝트 폴더에 없어요.')
    if not (MARK.exists() and MARK.read_text(encoding='utf-8').strip() == req_hash()):
        install()
    if not shutil.which('nvidia-smi'):
        say('주의: NVIDIA GPU(nvidia-smi)를 찾지 못했어요. 앱 화면은 열리지만 생성 단계는 GPU(24GB) 없이는 돌지 않아요.')
    say('앱을 켜요. 브라우저가 열리지 않으면 아래에 나오는 Local URL을 열어 주세요. 끄려면 이 창에서 Ctrl+C를 눌러요.')
    say('모델은 처음 쓸 때 Hugging Face에서 받아서, 첫 요청은 오래 걸릴 수 있어요.')
    sys.exit(subprocess.call([str(VPY), '-m', 'streamlit', 'run', str(ROOT / 'src' / 'app' / 'streamlit_app.py')], cwd=ROOT))


if __name__ == '__main__':
    main()
