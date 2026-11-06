# 실험 노트북(07·19·21·22)의 채택 코드를 글자 그대로 옮긴 파일. 노트북과 같은 결과가 나오도록 직접 고치지 않는다.
import json
import re

# ---- 19 "설정"·"후보 지시문·재요청 문구" 셀 (13 ③ + 19 조사 수정) ----
TONE = '밝고 친근한 톤'
SYSTEM_A = '너는 1인 인디게임 개발사의 마케팅 카피라이터다.'

# 08 "규칙 적용 지시문"과 같은 판매 포인트·사용자 입력·금지 표현·지시문
# 게임 기본 판매 포인트 (각 게임 데이터 파일에 있는 요소만 사용)
GAME_POINTS = {
    'nai': ['빨간 모자의 검은 고양이 기사가 칼과 방패로 싸우는 횡스크롤 액션', '개 기사·부엉이 마법사·토끼 상인 동료',
            '떠다니는 풀섬, 숲, 선술집, 성문을 넘나드는 스테이지', '동화책 같은 손그림 색감'],
    'x72': ['위에서 내려다보는 16비트 픽셀 던전', '기사·엘프·마법사·드워프 중 골라 플레이',
            '오크·해골·좀비·네크로맨서 등 몬스터', '금화·물약·보물상자(미믹 포함) 수집'],
    'kaykit': ['바바리안·기사·마법사·로그 등 5명의 로우폴리 영웅', '한손·양손 무기, 석궁, 지팡이를 쓰는 전투',
               '회피·막기·연속 공격 액션'],
}
# 사용자 입력 예시 (게임마다 1개). 냥기사는 판촉 표현이 사용자 입력에 있을 때 허용되는지 보려고 할인 문구를 넣음
USER_POINTS = {
    'nai': dict(points='11월 업데이트로 신규 동료 추가', must='11월 업데이트 기념 30% 할인'),
    'x72': dict(points='4인 로컬 협동 플레이 지원', must='스팀 찜하기'),
    'kaykit': dict(points='영웅마다 다른 전용 스킬', must='신규 영웅 로그 추가'),
}
BANNED_PROMO = ['할인', '특가', '무료', '이벤트', '출시', '사전예약', '선물']
BANNED_CLICHE = ['모험을 떠나', '떠나보세요', '떠나볼까요', '함께 떠나', '기다리고 있어요', '귀여운 친구들']

INSTRUCTION_A2 = '''게임 정보: {info}
{user_block}
게임 기본 판매 포인트 (사용자 입력이 없거나 부족할 때만 참고):
{points}
요청 사항: {tone}

이 게임 스크린샷을 보고 한국어 홍보 문구를 작성해줘.
규칙
1. 사용자 입력이 있으면 그 내용을 가장 먼저 반드시 반영하고, "꼭 넣을 문구"는 글자 그대로 넣어줘.
2. 사용자 입력에 없는 할인, 특가, 무료, 이벤트, 출시, 사전예약, 선물, 가격·기간 숫자는 쓰지 마.
3. 다음 표현은 쓰지 마: {cliche}
4. 이미지에 보이는 구체적인 요소(색, 사물, 장소, 행동)를 1개 이상 넣어줘.
- store: 인디게임 스토어 소개 문구, 정확히 2문장
- sns: SNS 홍보 문구, 정확히 1문장
아래 JSON 형식으로만 답해줘. 다른 설명은 쓰지 마.
{{"store": ["문장1", "문장2"], "sns": "문장"}}'''


# 08 "꼭 넣을 문구 처리 방식 비교"와 같은 검증 규칙·지시문 보강

VALIDATOR = r"""
import json, re
from difflib import SequenceMatcher

# 11/04: 앱 A 작업 1(리치의 모험)에서 sns가 store 첫 문장과 똑같은데 규칙 통과로 나옴 → sns가 store 문장과 겹치면 실패.
# 기준 유사도 0.9: 이전 A 후보 2,255개에서 0.9 근처 값이 드물고, 0.9 이상은 한두 단어만 다른 문장이었음
DUP_SIM = 0.9


def dup_sim(sns, store):
    # 공백·문장부호를 뺀 sns와 가장 비슷한 store 문장의 유사도
    norm = lambda s: re.sub(r'[\s.!?…,~]+', '', str(s))
    return max((SequenceMatcher(None, norm(x), norm(sns)).ratio() for x in store), default=0.0)


def parse_json(text):
    m = re.search(r'\{.*\}', str(text), re.S)
    try:
        d = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        d = None
    return d if isinstance(d, dict) else None


def _josa(word, with_final, without_final):
    # 마지막 글자에 받침이 있으면 with_final(이·을), 없으면 without_final(가·를). 한글이 아니면 without_final
    ch = word.strip()[-1:] or ' '
    if '가' <= ch <= '힣' and (ord(ch) - 0xAC00) % 28:
        return with_final
    return without_final


def n_sentences(s):
    # 글자가 없는 조각(문장 끝 이모지·기호)은 문장으로 세지 않음 (02와 같은 기준)
    return len([x for x in re.split(r'(?<=[.!?…])\s+', s.strip()) if re.search(r'[가-힣A-Za-z一-鿿]', x)])


def integrated(sns, must):
    if must not in sns or n_sentences(sns) != 1:
        return False
    if len(re.findall(r'[가-힣]', sns.replace(must, ' '))) < 8:
        return False
    p = re.escape(must)
    if re.search(r'[.!?…,:;~\-—]\s*' + p + r'\s*[.!?…~]*\s*$', sns) or re.match(r'^\s*' + p + r'\s*[.!?…,:;~\-—]', sns):
        return False
    return True


def check(text, must, allowed, banned_promo, banned_cliche, need_must):
    d = parse_json(text)
    if not (d and isinstance(d.get('store'), list) and isinstance(d.get('sns'), str)):
        return ['JSON 형식이 아니다. {"store": ["문장1", "문장2"], "sns": "문장"} 형식으로만 써야 한다.']
    store = [str(x) for x in d['store']]
    sns = d['sns']
    probs = []
    n_store, n_sns = sum(n_sentences(x) for x in store), n_sentences(sns)
    if n_store != 2:
        probs.append(f'store는 정확히 2문장이어야 하는데 {n_store}문장이다.')
    if n_sns != 1:
        probs.append(f'sns는 정확히 1문장이어야 하는데 {n_sns}문장이다.')
    if need_must:
        if must not in sns:
            probs.append(f'꼭 넣을 문구 "{must}"{_josa(must, "이", "가")} sns 문장에 글자 그대로 들어 있지 않다.')
        elif not integrated(sns, must):
            probs.append(f'꼭 넣을 문구 "{must}"{_josa(must, "이", "가")} 문장 앞이나 뒤에 따로 붙어 있다. sns 문장의 일부로 자연스럽게 넣어야 한다.')
    sim = dup_sim(sns, store)
    if sim >= DUP_SIM:
        probs.append(f'sns 문장이 store 문장과 거의 같다(유사도 {sim:.2f}). sns는 store와 다른 문장으로 써야 한다.')
    body = ' '.join(store) + ' ' + sns
    words = [w for w in banned_promo if w in body and w not in allowed]
    nums = [n for n in re.findall(r'\d+\s*%|\d+\s*월|\d+\s*일', body) if n.replace(' ', '') not in allowed.replace(' ', '')]
    if words or nums:
        probs.append(f'사용자 입력에 없는 판촉 표현을 썼다: {", ".join(words + nums)}')
    cl = [c for c in banned_cliche if c in body]
    if cl:
        probs.append(f'쓰지 말라는 표현을 썼다: {", ".join(cl)}')
    return probs
"""
exec(VALIDATOR)

RULE1 = '1. 사용자 입력이 있으면 그 내용을 가장 먼저 반드시 반영하고, "꼭 넣을 문구"는 글자 그대로 넣어줘.'
assert INSTRUCTION_A2.count(RULE1) == 1
INSTRUCTION_A3 = INSTRUCTION_A2.replace(RULE1, '\n'.join([
    RULE1,
    '   "꼭 넣을 문구"는 sns 문장 안에 문장의 일부로 넣고, 문장 앞이나 뒤에 따로 붙이지 마.',
    '   좋은 예 (다른 게임, 꼭 넣을 문구 "데모 플레이 가능"): "눈 덮인 마을의 여우 기사 이야기, 데모 플레이 가능 소식을 지금 확인해 보세요."',
    '   나쁜 예: "눈 덮인 마을의 여우 기사 이야기를 만나 보세요. 데모 플레이 가능"']))

N_CAND = 4

# ① 지시문 예시 추가: 09 지시문(INSTRUCTION_A3)의 나쁜 예 줄 다음에 명사로 끝나는 문구의 예를 더함
BAD_LINE = '   나쁜 예: "눈 덮인 마을의 여우 기사 이야기를 만나 보세요. 데모 플레이 가능"'
assert INSTRUCTION_A3.count(BAD_LINE) == 1
INSTRUCTION_EX = INSTRUCTION_A3.replace(BAD_LINE, '\n'.join([
    BAD_LINE,
    '   꼭 넣을 문구가 명사로 끝나면 단어를 바꾸지 말고 뒤에 조사를 붙여 넣어줘.',
    '   좋은 예 (다른 게임, 꼭 넣을 문구 "신규 맵 사막 추가"): "모래바람이 부는 협곡을 달리는 기사단, 신규 맵 사막 추가로 더 넓어진 세계를 만나 보세요."',
    '   나쁜 예: "신규 맵으로 사막이 추가되어 모래바람 협곡을 달릴 수 있어요." (문구를 바꿔 씀)']))

# ② 구체적 재요청: 09 (가) 재요청 문구 + 실패 이유별 고치는 방법
FB_HEAD = '아래 문제를 고쳐서 다시 써줘. 나머지 규칙도 그대로 지키고, JSON 형식으로만 답해줘.\n'
FB_HINTS = {
    'missing': '- 고치는 방법: "{must}"의 단어를 바꾸거나 나누거나 순서를 바꾸지 말고 글자 그대로 sns 문장에 넣어. 바로 뒤에 조사를 붙여도 된다 (예: "{must_ro}", "{must} 소식과 함께").',
    'attached': '- 고치는 방법: "{must}"{eul} 문장 끝이나 앞에 쉼표로 붙이지 말고 문장 가운데에 넣어 (예: "…, {must_ro} 더 다채로워진 전투를 만나 보세요.").',
}
# 실패 이유 문장(VALIDATOR check)에서 어떤 고치는 방법을 붙일지 고르는 표시
FB_KEYS = {'missing': '글자 그대로 들어 있지 않다', 'attached': '따로 붙어 있다', 'polite': '존댓말(~요, ~니다)로 끝나지 않은', 'dup': 'store 문장과 거의 같다'}

# ---- 25 "후보 지시문·재요청 문구" 셀: 후보 3 fb_edit (고칠 문장을 지시하는 재요청) ----
# 25에서 재요청 단계만 바꿨을 때 세 게임 0.889 → 0.956, 0x72 0.800 → 1.000, 표현 다양성은 ③과 같음 (m25_by_game.csv, m25_scored.csv)
FB_HINTS_EDIT = {
    'missing': '- 고치는 방법: sns 문장을 "{must_ro} …"로 시작하도록 다시 써. "{must}"는 글자 그대로 쓰고, store는 그대로 둬.',
    'attached': '- 고치는 방법: sns 문장을 "{must_ro} …"로 시작하도록 다시 써. "{must}"는 글자 그대로 쓰고, store는 그대로 둬.',
    # 11/04 polite (③④)
    'polite': '- 고치는 방법: 위 문장을 존댓말(~요, ~니다)로 끝나게 고쳐 써. 내용과 문장 수는 그대로 둬.',
    # 11/04 dup (② sns·store 겹침)
    'dup': '- 고치는 방법: sns 문장을 store 문장과 다른 내용으로 다시 써. store는 그대로 둬.',
}


def with_ro(must):
    # 10은 "{문구}로" 고정 → 받침(ㄹ 제외) 뒤에는 "으로"
    c = must[-1]
    if '가' <= c <= '힣' and (ord(c) - 0xAC00) % 28 not in (0, 8):
        return must + '으로'
    return must + '로'


assert with_ro('신규 영웅 로그 추가') == '신규 영웅 로그 추가로'  # 10과 같음
assert with_ro('11월 업데이트 기념 30% 할인') == '11월 업데이트 기념 30% 할인으로'
assert with_ro('스팀 찜하기') == '스팀 찜하기로'

# ---- 21 "설정: 문구" 셀 (상세 페이지 섹션 요청·검증) ----
# 섹션별 요청: A 지시문(INSTRUCTION_EX)의 요청 문장·출력 형식 줄만 바꿈
REQ_LINE = '이 게임 스크린샷을 보고 한국어 홍보 문구를 작성해줘.'
FMT_A = ('- store: 인디게임 스토어 소개 문구, 정확히 2문장\n- sns: SNS 홍보 문구, 정확히 1문장\n'
         '아래 JSON 형식으로만 답해줘. 다른 설명은 쓰지 마.\n{{"store": ["문장1", "문장2"], "sns": "문장"}}')
assert INSTRUCTION_EX.count(REQ_LINE) == 1 and INSTRUCTION_EX.endswith(FMT_A)
JSON_LINE = '아래 JSON 형식으로만 답해줘. 다른 설명은 쓰지 마.'
SECTIONS = {
    # 08 기능 B 제목 규칙 "20자 이내"
    # 제목은 문장 수 대신 한 줄인지만 봄(n_sent=None): 느낌표가 든 제목을 2문장으로 세지 않게 (11/03)
    'title': dict(no='①', key='title', n_sent=None, max_chars=20, need_must=False, json_fmt='{"title": "제목"}',
                  req='이 게임 스크린샷을 보고 굿즈 상세페이지 맨 위 대표 이미지에 올릴 한국어 제목을 작성해줘.',
                  fmt=f'- title: 상세페이지 제목, 한국어, 20자 이내, 한 줄\n{JSON_LINE}\n{{{{"title": "제목"}}}}'),
    'intro': dict(no='②', key='store+sns', n_sent=None, max_chars=None, need_must=True,
                  json_fmt='{"store": ["문장1", "문장2"], "sns": "문장"}', req=REQ_LINE, fmt=FMT_A),
    # A store와 같은 문장 수
    # 11/04 polite: ③④가 반말("…있어.")로 끝나 존댓말인 ②와 한 페이지에서 섞임(21 냥기사·KayKit ④, 0x72 ③, 앱 작업 18 ④)
    # → 존댓말 줄을 지시문에 넣고 check_section에서 존댓말 어미로 끝나는지 검사
    'mockup': dict(no='③', key='copy', n_sent=2, max_chars=None, need_must=False, json_fmt='{"copy": ["문장1", "문장2"]}', polite=True,
                   req='이 게임 그림을 인쇄한 {goods} 굿즈의 목업 사진 아래에 들어갈 한국어 소개 문구를 작성해줘.',
                   fmt=f'- copy: 굿즈 상세페이지 소개 문구, 정확히 2문장\n- 모든 문장은 존댓말(~요, ~니다)로 끝내줘.\n{JSON_LINE}\n{{{{"copy": ["문장1", "문장2"]}}}}'),
    'staging': dict(no='④', key='copy', n_sent=2, max_chars=None, need_must=False, json_fmt='{"copy": ["문장1", "문장2"]}', polite=True,
                    req='{goods} 굿즈를 {scene} 놓고 찍은 연출 사진 아래에 들어갈 한국어 문구를 작성해줘.',
                    fmt=f'- copy: 굿즈 연출 사진 설명 문구, 정확히 2문장\n- 모든 문장은 존댓말(~요, ~니다)로 끝내줘.\n{JSON_LINE}\n{{{{"copy": ["문장1", "문장2"]}}}}'),
}

# 규칙 1 블록: "1. 사용자 입력이 있으면"부터 규칙 2 앞까지 (꼭 넣을 문구 설명·예시 포함)
_lines = INSTRUCTION_EX.split('\n')
_i1 = next(i for i, l in enumerate(_lines) if l.startswith('1. 사용자 입력이 있으면'))
_i2 = next(i for i, l in enumerate(_lines) if i > _i1 and l.startswith('2. '))
RULE1_MUST = '\n'.join(_lines[_i1:_i2])
RULE1_NO_MUST = '1. 사용자 입력이 있으면 그 내용을 가장 먼저 반드시 반영해줘.'
assert INSTRUCTION_EX.count(RULE1_MUST) == 1 and '꼭 넣을 문구' in RULE1_MUST

# A check()와 같은 판촉·숫자·금지 표현 규칙에 섹션 형식(키 하나, 문장 수, 글자 수)만 바꾼 검증
VALIDATOR_SEC = r"""
POLITE_END = ('요', '니다', '니까', '죠', '시오')


def not_polite(v):
    # 문장 끝 기호·이모지를 떼고 존댓말 어미(POLITE_END)로 끝나지 않는 문장. 명사로 끝나는 문장도 걸림
    out = []
    for x in v:
        for s in re.split(r'(?<=[.!?…])\s+', x.strip()):
            if re.search(r'[가-힣A-Za-z一-鿿]', s) and not re.sub(r'[^가-힣A-Za-z0-9]+$', '', s).endswith(POLITE_END):
                out.append(s.strip())
    return out


def check_section(text, key, n_sent, max_chars, json_fmt, allowed, banned_promo, banned_cliche, polite=False):
    d = parse_json(text)
    v = d.get(key) if d else None
    if isinstance(v, str):
        v = [v]
    if not (isinstance(v, list) and v and all(isinstance(x, str) for x in v)):
        return [f'JSON 형식이 아니다. {json_fmt} 형식으로만 써야 한다.']
    probs = []
    if n_sent is None:
        n_lines = sum(len([l for l in x.split('\n') if l.strip()]) for x in v)
        if n_lines != 1:
            probs.append(f'{key}는 한 줄이어야 하는데 {n_lines}줄이다.')
    else:
        n = sum(n_sentences(x) for x in v)
        if n != n_sent:
            probs.append(f'{key}는 정확히 {n_sent}문장이어야 하는데 {n}문장이다.')
    n_chars = sum(len(x.strip()) for x in v)
    if max_chars and n_chars > max_chars:
        probs.append(f'{key}는 {max_chars}자 이내여야 하는데 {n_chars}자다.')
    body = ' '.join(v)
    words = [w for w in banned_promo if w in body and w not in allowed]
    nums = [m for m in re.findall(r'\d+\s*%|\d+\s*월|\d+\s*일', body) if m.replace(' ', '') not in allowed.replace(' ', '')]
    if words or nums:
        probs.append(f'사용자 입력에 없는 판촉 표현을 썼다: {", ".join(words + nums)}')
    cl = [c for c in banned_cliche if c in body]
    if cl:
        probs.append(f'쓰지 말라는 표현을 썼다: {", ".join(cl)}')
    if polite:
        bad = not_polite(v)
        if bad:
            probs.append(f'존댓말(~요, ~니다)로 끝나지 않은 문장이 있다: {" / ".join(bad)}')
    return probs
"""
exec(VALIDATOR_SEC)

# ---- 07 "배너 문제 수정 실험" 설정 셀 (B 요청 변환 지시문·검증) + 10/26 동의어 허용 ----
SYSTEM_B = '너는 게임 이벤트 배너 제작을 돕는 도우미다.'
INSTRUCTION_B2 = """게임 정보: {info}
요청: {request}

요청을 읽고 이미지 생성용 영어 장면 태그와 배너 문구를 만들어줘.
- scene: 배경과 장면을 묘사하는 영어 태그 5~10개, 쉼표로 구분. 글자·텍스트·로고 관련 태그는 넣지 마.
- title: 배너 제목, 한국어, 20자 이내
- sub: 기간·조건 등 부제, 한국어
규칙
1. 요청에 있는 숫자(할인율·날짜·버전)는 글자 그대로 넣고, 요청에 없는 날짜·기간·가격·숫자는 지어내지 마.
2. 요청에 없는 판촉 표현은 쓰지 마: {banned}
아래 JSON 형식으로만 답해줘. 다른 설명은 쓰지 마.
{{"scene": "tag1, tag2", "title": "제목", "sub": "부제"}}"""
VALIDATOR_B = r"""
import json, re

SYNONYMS = {'할인': ['세일'], '출시': ['나와'], '특가': ['할인']}


def parse_json(text):
    m = re.search(r'\{.*\}', str(text), re.S)
    try:
        d = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        d = None
    return d if isinstance(d, dict) else None


def check_b(text, request, banned):
    d = parse_json(text)
    if not (d and all(isinstance(d.get(k), str) for k in ['scene', 'title', 'sub'])):
        return ['JSON 형식이 아니다. {"scene": "...", "title": "...", "sub": "..."} 형식으로만 써야 한다.']
    probs = []
    tags = [x.strip() for x in d['scene'].split(',') if x.strip()]
    if not 5 <= len(tags) <= 10:
        probs.append(f'scene 태그는 5~10개여야 하는데 {len(tags)}개다.')
    if len(d['title']) > 20:
        probs.append(f'title은 20자 이내여야 하는데 {len(d["title"])}자다.')
    copy = d['title'] + ' ' + d['sub']
    req_nums = re.findall(r'\d+(?:\.\d+)?', request)
    missing = [n for n in req_nums if n not in copy]
    if missing:
        probs.append(f'요청에 있는 숫자가 빠졌다: {", ".join(missing)}')
    extra = [n for n in re.findall(r'\d+(?:\.\d+)?', copy) if n not in req_nums]
    if extra:
        probs.append(f'요청에 없는 숫자를 지어냈다: {", ".join(extra)}')
    # 10/26 결정: 요청에 동의어가 있으면 위반으로 보지 않음 (세일 → 할인, 나와 → 출시, 할인 → 특가)
    words = [w for w in banned if w in copy and w not in request and not any(x in request for x in SYNONYMS.get(w, []))]
    if words:
        probs.append(f'요청에 없는 판촉 표현을 썼다: {", ".join(words)}')
    return probs
"""
exec(VALIDATOR_B)

# C 장면 변환 검사: B 변환 지시문의 scene 형식만 봄 (C는 제목·부제를 쓰지 않음)
VALIDATOR_C = r"""
def check_c(text):
    d = parse_json(text)
    if not (d and isinstance(d.get('scene'), str)):
        return ['JSON 형식이 아니다. {"scene": "tag1, tag2", "title": "제목", "sub": "부제"} 형식으로만 써야 한다.']
    tags = [x.strip() for x in d['scene'].split(',') if x.strip()]
    if not 5 <= len(tags) <= 10:
        return [f'scene 태그는 5~10개여야 하는데 {len(tags)}개다.']
    return []
"""
exec(VALIDATOR_C)
