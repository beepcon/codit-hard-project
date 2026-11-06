import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
# 프로젝트 폴더 (src/app의 두 단계 위). 시험할 때만 환경 변수로 바꿈
ROOT = Path(os.environ.get('ADSTUDIO_ROOT', APP_DIR.parents[1])).resolve()
RAW = ROOT / 'data' / 'raw'
OUT = ROOT / 'outputs' / 'app'
DB_PATH = OUT / 'app.db'
JOBS_DIR = OUT / 'jobs'
UPLOAD_DIR = OUT / 'uploads'
CHILD_DIR = OUT / '_child'
BG_DIR = OUT / 'bg'
STATE_PATH = OUT / 'worker_state.json'
LOCK_PATH = OUT / 'worker.lock'
WORKER_LOG = OUT / 'worker.log'
STAGE_CSV = OUT / 'stage_times.csv'
for _d in [OUT, JOBS_DIR, UPLOAD_DIR, CHILD_DIR, BG_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# 상세 페이지 가로 860px (21과 같음, https://clobe.ai/blog/online-shopping-mall-product-image-size)
PAGE_W = 860
# 07·21과 같은 Windows 기본 한글 글꼴(맑은 고딕). Windows가 아닌 시험 환경에서만 Noto CJK를 씀
_FONTS = [Path('C:/Windows/Fonts/malgun.ttf'), Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')]
_FONTS_BOLD = [Path('C:/Windows/Fonts/malgunbd.ttf'), Path('C:/Windows/Fonts/malgun.ttf'),
               Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc')]
FONT = next((p for p in _FONTS if p.exists()), None)
FONT_BOLD = next((p for p in _FONTS_BOLD if p.exists()), None)
assert FONT is not None and FONT_BOLD is not None, '한글 글꼴(맑은 고딕 malgun.ttf)이 없음'


def job_dir(job_id):
    d = JOBS_DIR / f'{int(job_id):05d}'
    d.mkdir(parents=True, exist_ok=True)
    return d


def rel(p):
    # 기록에는 프로젝트 폴더 기준 경로로 남김
    p = Path(p).resolve()
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


def absp(p):
    p = Path(p)
    return p if p.is_absolute() else ROOT / p
