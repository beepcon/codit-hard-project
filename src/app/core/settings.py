# 모델·생성 설정. 값은 모두 실험 노트북(07·12·14·15·16·17·18·20·21·22)에서 정한 것을 그대로 씀
import json

from . import textcfg as T
from .paths import ROOT

# ---- 문구 (A·B·C 요청 변환·상세 페이지 섹션): Qwen3-VL-8B, 13 ③ + 19 조사 수정 (21과 같음) ----
QWEN_REPO = 'Qwen/Qwen3-VL-8B-Instruct'
MAX_NEW_TOKENS = 512
COPY_SEED = 0
# 샘플링 후보 수: 13 ③ = 4개 (23 "후보 4개 → 8개" 결과에 따라 바꿀 수 있음)
N_CAND = T.N_CAND
# B 요청 변환 재요청: 07 R3 (가) 실패 이유를 알려 주고 샘플링으로 다시 요청, 최대 2번 (B 페이지 10/26 결정)
B_MAX_EXTRA = 2
B_FB = '아래 문제를 고쳐서 다시 써줘. 나머지 규칙도 그대로 지키고, JSON 형식으로만 답해줘.\n'
# A 톤: Qwen 실험(08~13·19·21)에서 쓴 "밝고 친근한 톤" 하나만 씀 (02는 Claude로 톤 3개를 비교함)
TONES = {'친근하게': T.TONE}

# ---- 그림 (B 배너·C 그림체): 12 c_config.json (07 B 결정 + rating 태그) + 18 냥기사 LoRA ----
C12 = json.loads((ROOT / 'outputs' / 'promo_c' / 'c_config.json').read_text(encoding='utf-8'))
C_MODEL, C_IPA, C_GEN = C12['model'], C12['ip_adapter'], C12['gen']
C_SEED = 0
# B 배너 크기: 채택 조합(07 F·12·18)을 확인한 가로형 1216×832만 씀
BANNER_SIZES = {'가로형 1216×832': (1216, 832)}
QUALITY = 'masterpiece, high score, great score, absurdres'
NEGATIVE_BASE = 'text, letters, words, watermark, signature, logo, lowres, worst quality, bad quality'
# 그림체 설정에서 고를 수 있는 값: 실험에서 쓴 값만 둔다
# 장면 강조 가중치 1.3: 07 "배너 문제 수정 실험" X (0x72 Compel 1.3)
SCENE_WEIGHT = 1.3
# IP-Adapter 전체 층 강도: 05 (0.5·0.8·1.0), 07 X (0.3)
IPA_SCALES = [0.3, 0.5, 0.8, 1.0]
# IP-Adapter 그림체 블록: 07·12 KayKit 설정과 같은 블록 가중치
STYLE_ONLY_IPA = C12['games']['kaykit']['ipa']


def build_style(tags='', neg_extra='', scene_weight=False, ipa_name='all_layers', ipa_scale=0.5):
    # 12 c_config.json 게임별 설정과 같은 틀: "그림체 태그, safe, 장면(가중치), 품질 태그" / "기본 부정, 빼는 태그, nsfw"
    tags, neg_extra = tags.strip().strip(','), neg_extra.strip().strip(',')
    scene = f'({{scene}}){SCENE_WEIGHT}' if scene_weight else '{scene}'
    return dict(prompt_example=(f'{tags}, ' if tags else '') + f'safe, {scene}, {QUALITY}',
                negative=NEGATIVE_BASE + (f', {neg_extra}' if neg_extra else '') + ', nsfw',
                ipa=STYLE_ONLY_IPA if ipa_name == 'style_only' else ipa_scale, ipa_name=ipa_name, compel=bool(scene_weight),
                tags=tags, neg_extra=neg_extra, scene_weight=bool(scene_weight), ipa_scale=ipa_scale)


def style_fields(style):
    # 저장된 그림체 설정을 화면 입력값으로 되돌림. 예시 게임(12 c_config.json)은 틀에 맞춰 나눔
    if 'tags' in style:
        return {k: style[k] for k in ('tags', 'neg_extra', 'scene_weight', 'ipa_name', 'ipa_scale')}
    head, rest = style['prompt_example'].split('safe, ', 1)
    neg = style['negative'][len(NEGATIVE_BASE):]
    neg = neg[:-len(', nsfw')] if neg.endswith(', nsfw') else neg
    return dict(tags=head.rstrip(', '), neg_extra=neg.lstrip(', '), scene_weight=rest.startswith('({scene})'),
                ipa_name=style['ipa_name'], ipa_scale=style['ipa'] if not isinstance(style['ipa'], dict) else 0.5)


# 새로 등록한 게임의 기본 그림체 설정: 05 IP-Adapter 기본(전체 층 0.5), 07 rating 태그(safe / nsfw).
# 24에서 이 기본 설정은 주인공·그림체를 유지하지 못해, 이용자가 게임에 맞게 고친다
NEW_GAME_STYLE = build_style()

# ---- D 빈 배경·F 목업 크기: 14 f_config.json ----
F14 = json.loads((ROOT / 'outputs' / 'mockup_f' / 'f_config.json').read_text(encoding='utf-8'))
SDXL_BASE = F14['F0']['model']
NEGATIVE_F = F14['negative']
MAX_SIDE = F14['max_side']

# ---- D 장면: 15·16 SCENES (desk는 16·17·20·21에서 씀) ----
SCENES = {'desk': 'on a wooden desk next to a game controller and small figures, warm desk lamp light, cozy room',
          'studio': 'on a pastel color studio backdrop, soft shadow, clean background',
          'cafe': 'on a cafe table by the window, morning sunlight, shallow depth of field'}
SCENE_LABEL = {'desk': '책상', 'studio': '스튜디오', 'cafe': '카페'}
# 상세 페이지 ④ 문구 요청에 넣는 장면 설명 (desk는 21 SCENE_KO, 나머지는 위 영어 장면 문구를 옮김)
SCENE_KO = {'desk': '따뜻한 스탠드 조명이 비추는 나무 책상 위, 게임 컨트롤러와 작은 피규어 옆에',
            'studio': '부드러운 그림자가 지는 파스텔색 스튜디오 배경 위에',
            'cafe': '아침 햇살이 드는 창가 카페 테이블 위에'}
KIND_EN = {'tshirt': 't-shirt', 'hoodie': 'hoodie', 'tote': 'tote bag', 'mug': 'mug'}
KIND_KO = {'tshirt': '티셔츠', 'mug': '머그컵', 'tote': '에코백', 'hoodie': '후드티'}


def bg_args(scene):
    # R1n의 IC-Light 배경 조건: 15 D2 빈 배경과 같은 설정 (SDXL base, 1024, 30스텝, CFG 7, seed 0)
    return dict(size=1024, steps=30, cfg=7.0, seed=0, prompt=f'{SCENES[scene]}, empty scene, no objects',
                negative=NEGATIVE_F + ', product, object in center')


def scene_prompt(kind, scene):
    return f'product photography of a {KIND_EN[kind]} {SCENES[scene]}'


# Y: 16·20 설정
Y_REPO = 'yahoo-inc/photo-background-generation'
Y_ARGS = dict(size=512, steps=20, cond_scale=1.0, guess_mode=False)
Y_SEEDS = [0, 1, 2]
DARK, EDGE_PX = 20, 16
# IC-Light: 15·17 설정
SD15 = 'stablediffusionapi/realistic-vision-v51'
ICLIGHT = dict(repo='lllyasviel/ic-light', file='iclight_sd15_fbc.safetensors', code_commit='bcf3f29ca85be8a4686215f477b546f5030be8b7')
D2_ARGS = dict(steps=20, cfg=7.0, highres_scale=1.5, highres_denoise=0.5, max_side=640, a_prompt='best quality',
               n_prompt='lowres, bad anatomy, bad hands, cropped, worst quality')
IC_SEED = 0
FILL_DILATE_PX = 12
RATIO_CLIP = (0.25, 4.0)
# (a) 16 R1n_s32_ic, (b) 17 YR1n_s8_fill_y
D_CFG = {'R1n': dict(sigma=32, cond='SDXL 빈 배경 (15 D2와 같음)', base='ic'),
         'YR1n': dict(sigma=8, cond='fill (Y 배경의 굿즈 자리 메움)', base='y')}
# D 입력 마스크: 14·15와 같은 BiRefNet
BIREFNET = 'ZhengPeng7/BiRefNet'

# ---- F 목업 후보: 22 (21과 같음) ----
MOCK_CANDS = {'mug': {'F1': {}, 'F1curve': dict(curve=True), 'F1spec': dict(spec=True)},
              'fabric': {'F1': {}, 'F1cloth': dict(cloth=True)}}
MOCK_LABEL = {'F1': ('기본 합성', '사진의 밝기·주름을 따라 살짝 휨'), 'F1curve': ('위아래 휨', '머그 몸통 윤곽을 따라 그림 위아래가 휨'),
              'F1spec': ('반사광', '머그의 반사광 띠를 그림 위에 다시 얹음'), 'F1cloth': ('천 질감', '주름을 더 따르고 천 결이 그림에 비침')}

# ---- 대기열 단계 (모델마다 별도 프로세스에서 한 번 로드, 21과 같은 순서) ----
STAGES = ['copy', 'c_image', 'sdxl_bg', 'mask', 'y', 'iclight', 'compose']
STAGE_INFO = {
    'copy': ('① 문구', 'Qwen3-VL-8B', 'A 문구 · B·C 변환 · 상세 문구'),
    'c_image': ('② 그림', 'animagine-xl-4.0 + IP-Adapter', 'B 배너 · C 그림 (LoRA 있는 게임은 LoRA 추가)'),
    'sdxl_bg': ('③ SDXL', 'SDXL base', 'R1n 빈 배경'),
    'mask': ('④ 마스크', 'BiRefNet', 'F 새 굿즈 사진 · D 입력'),
    'y': ('⑤ Y 배경', 'photo-background-generation', 'D 배경 생성 · 검은 띠면 seed 다시'),
    'iclight': ('⑥ IC-Light', 'realistic-vision-v51 + IC-Light', 'D 조명 옮기기 (R1n · YR1n)'),
    'compose': ('⑦ 합성', 'Pillow · Chromium', '배너 글자(Pillow) · 상세 페이지(HTML → PNG, 26)'),
}
JOB_LABEL = {'a': 'A 홍보 문구', 'b_convert': 'B 장면·문구 변환', 'b_banner': 'B 이벤트 배너', 'c_convert': 'C 장면 변환',
             'c_image': 'C 그림체 이미지', 'f_mask': 'F 굿즈 마스크', 'f_pick': 'F 고른 목업', 'd': 'D 굿즈 배경',
             'page': '상세 페이지'}
# 올리는 그림 기준 (27 등록 그림 크기·비율 기준, 11/04 사용자 결정). 기준 밖이면 올리지 못하게 막고 필요한 크기·비율을 안내함
# 27: 긴 변 256px는 게임 화면·굿즈 칸에서 2.4~3.5배로 늘어남, 512px는 1.2~1.8배. 세로로 3:4보다 길면 게임 화면 칸 채움 0.85 이하
UPLOAD_MIN_LONG = {'screenshot': 512, 'ref': 256, 'goods': 512}
UPLOAD_KIND_KO = {'screenshot': 'A 스크린샷', 'ref': '레퍼런스 아트', 'goods': '굿즈 사진'}
UPLOAD_RATIO = (3 / 4, 3.0)  # 가로 ÷ 세로 허용 범위: 3:4(세로가 긴 쪽 끝) ~ 3:1(가로가 긴 쪽 끝)
UPLOAD_RATIO_TEXT = '가로:세로 3:1 ~ 3:4 (예: 16:9, 4:3, 1:1, 3:4)'

# 상세 페이지 1장 서비스 시간 (21 dp_service_time.csv 평균): 대기열 화면 표시용
SERVICE_CSV = ROOT / 'outputs' / 'detail_page' / 'dp_service_time.csv'
