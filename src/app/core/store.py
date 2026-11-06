# 게임 등록과 요청(대기열) 저장: SQLite 한 파일 (outputs/app/app.db). 앱과 워커 프로세스가 같이 씀
import json
import sqlite3
import time
from pathlib import Path

from . import settings as S
from . import textcfg as T
from .paths import DB_PATH, JOBS_DIR, ROOT, rel

SCHEMA = '''
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY, name TEXT, label TEXT, info TEXT, points TEXT, style TEXT, refs TEXT,
    lora TEXT, trigger TEXT, created REAL);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY, game_id INTEGER, kind TEXT, title TEXT, params TEXT, stages TEXT, stage_idx INTEGER,
    status TEXT, result TEXT, error TEXT, created REAL, started REAL, ended REAL);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value INTEGER);
'''
JSON_COLS = {'points', 'style', 'refs', 'params', 'stages', 'result'}


def conn():
    c = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    return c


def _row(r):
    if r is None:
        return None
    d = dict(r)
    for k in JSON_COLS & d.keys():
        d[k] = json.loads(d[k]) if d[k] else ({} if k in ('params', 'result', 'style') else [])
    return d


def init():
    with conn() as c:
        c.executescript(SCHEMA)
        if c.execute('SELECT COUNT(*) FROM games').fetchone()[0] == 0:
            for g in default_games():
                c.execute('INSERT INTO games (name, label, info, points, style, refs, lora, trigger, created) VALUES (?,?,?,?,?,?,?,?,?)',
                          (g['name'], g['label'], g['info'], json.dumps(g['points'], ensure_ascii=False),
                           json.dumps(g['style'], ensure_ascii=False), json.dumps(g['refs']), g['lora'], g['trigger'], time.time()))


def default_games():
    # 예시로 등록하는 게임 3개: 소개는 13 GAMES info, 판매 포인트는 13 GAME_POINTS, 그림체는 12 c_config.json,
    # 레퍼런스 아트는 12 refs(03 EDA 대표성 1위), 냥기사 LoRA는 18 결정(zero_trigger_n50, 트리거 nyang_knight_style)
    info = {'nai': '냥기사의 여행 — 검은 고양이 기사가 주인공인 2D 횡스크롤 어드벤처 게임',
            'kaykit': '로우폴리 3D 판타지 어드벤처 게임', 'x72': '픽셀 아트 던전 탐험 게임'}
    names = {'nai': ('냥기사의 여행', '2D 애니풍 횡스크롤'), 'kaykit': ('KayKit', '3D 로우폴리 판타지'), 'x72': ('0x72', '픽셀 아트 던전')}
    lora = ROOT / 'models' / 'lora' / 'sweep' / 'zero_trigger_n50' / 'pytorch_lora_weights.safetensors'
    out = []
    for g in ['nai', 'kaykit', 'x72']:
        ref = ROOT / Path(S.C12['refs'][g].replace('\\', '/')).relative_to('..')
        out.append(dict(name=names[g][0], label=names[g][1], info=info[g], points=T.GAME_POINTS[g], style=S.C12['games'][g],
                        refs=[rel(ref)], lora=rel(lora) if g == 'nai' and lora.exists() else '',
                        trigger='nyang_knight_style' if g == 'nai' and lora.exists() else ''))
    return out


def list_games():
    with conn() as c:
        return [_row(r) for r in c.execute('SELECT * FROM games ORDER BY id')]


def get_game(gid):
    with conn() as c:
        return _row(c.execute('SELECT * FROM games WHERE id=?', (gid,)).fetchone())


def add_game(name, label, info, points, refs, lora='', trigger='', style=None):
    with conn() as c:
        cur = c.execute('INSERT INTO games (name, label, info, points, style, refs, lora, trigger, created) VALUES (?,?,?,?,?,?,?,?,?)',
                        (name, label, info, json.dumps(points, ensure_ascii=False),
                         json.dumps(style or S.NEW_GAME_STYLE, ensure_ascii=False), json.dumps(refs), lora, trigger, time.time()))
        return cur.lastrowid


def update_game(gid, **kw):
    sets = ', '.join(f'{k}=?' for k in kw)
    vals = [json.dumps(v, ensure_ascii=False) if k in JSON_COLS else v for k, v in kw.items()]
    with conn() as c:
        c.execute(f'UPDATE games SET {sets} WHERE id=?', (*vals, gid))


def delete_game(gid):
    with conn() as c:
        c.execute('DELETE FROM games WHERE id=?', (gid,))


def _next_job_id(c):
    # 끝난 요청을 지우면 SQLite가 지운 번호를 다시 쓰고, 그 번호의 결과 폴더(outputs/app/jobs/000NN)를 덮어쓴다.
    # 그래서 DB 최대 번호, 지금까지 쓴 마지막 번호(meta), 결과 폴더 최대 번호 중 가장 큰 것 다음을 쓴다
    db_max = c.execute('SELECT COALESCE(MAX(id), 0) FROM jobs').fetchone()[0]
    last = c.execute("SELECT value FROM meta WHERE key='last_job_id'").fetchone()
    dir_max = max((int(p.name) for p in JOBS_DIR.iterdir() if p.name.isdigit()), default=0) if JOBS_DIR.exists() else 0
    return max(db_max, last[0] if last else 0, dir_max) + 1


def add_job(game_id, kind, title, params, stages):
    with conn() as c:
        jid = _next_job_id(c)
        c.execute('INSERT INTO jobs (id, game_id, kind, title, params, stages, stage_idx, status, result, error, created) '
                  'VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                  (jid, game_id, kind, title, json.dumps(params, ensure_ascii=False), json.dumps(stages), 0,
                   'queued' if stages else 'done', '{}', '', time.time()))
        c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('last_job_id', ?)", (jid,))
        return jid


def get_job(jid):
    with conn() as c:
        return _row(c.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone())


def list_jobs(statuses=None, game_id=None, kind=None, limit=200):
    q, args = 'SELECT * FROM jobs WHERE 1=1', []
    if statuses:
        q += f' AND status IN ({",".join("?" * len(statuses))})'
        args += list(statuses)
    if game_id is not None:
        q += ' AND game_id=?'
        args.append(game_id)
    if kind:
        q += ' AND kind=?'
        args.append(kind)
    q += ' ORDER BY id DESC LIMIT ?'
    args.append(limit)
    with conn() as c:
        return [_row(r) for r in c.execute(q, args)]


def set_job(jid, **kw):
    sets = ', '.join(f'{k}=?' for k in kw)
    vals = [json.dumps(v, ensure_ascii=False) if k in JSON_COLS else v for k, v in kw.items()]
    with conn() as c:
        c.execute(f'UPDATE jobs SET {sets} WHERE id=?', (*vals, jid))


def cancel_job(jid):
    # 처리 중인 단계는 끝까지 돌고, 그 뒤 단계로 넘어가지 않음
    with conn() as c:
        c.execute("UPDATE jobs SET status='cancelled', ended=? WHERE id=? AND status IN ('queued', 'running')", (time.time(), jid))


def delete_finished_jobs():
    # 완료·오류·취소 요청만 지움(대기·진행 중은 워커가 처리 중이라 남김). 결과 파일(outputs/app/jobs)은 지우지 않음
    with conn() as c:
        return c.execute("DELETE FROM jobs WHERE status IN ('done', 'error', 'cancelled')").rowcount


def current_stage(job):
    st = job['stages']
    return st[job['stage_idx']] if job['status'] in ('queued', 'running') and job['stage_idx'] < len(st) else None
