import pandas as pd
import streamlit as st

from app.core import settings as S
from app.core import store
from app.core.paths import absp
from app.views.common import save_upload, upload_errors, upload_rule


def _points_editor(key, values):
    df = pd.DataFrame({'판매 포인트': values or ['']})
    out = st.data_editor(df, num_rows='dynamic', key=key, width='stretch', hide_index=True)
    return [str(x).strip() for x in out['판매 포인트'] if str(x).strip() and str(x) != 'nan']


def _style_editor(key, style):
    # 그림체 설정: 12 게임별 설정과 같은 틀(그림체 태그, 빼는 태그, 장면 강조, IP-Adapter)로 고친다. 고를 수 있는 값은 실험에서 쓴 값만 둔다
    f = S.style_fields(style)
    tags = st.text_area('그림체 태그 (영어, 장면 앞에 붙음)', f['tags'], key=f'{key}_tags', height=80,
                        help='캐릭터와 그림체를 영어 태그로 적어 주세요. 비우면 태그 없이 레퍼런스 아트만으로 그려요.')
    neg = st.text_input('빼고 싶은 요소 (영어 태그)', f['neg_extra'], key=f'{key}_neg', help='예: KayKit은 anime, 1girl')
    weight = st.checkbox(f'장면 강조 (장면 태그 가중치 {S.SCENE_WEIGHT})', f['scene_weight'], key=f'{key}_w',
                         help='장면이 잘 드러나지 않을 때 써요 (07 0x72 용암).')
    mode = st.radio('IP-Adapter 적용 범위', ['all_layers', 'style_only'], index=0 if f['ipa_name'] == 'all_layers' else 1,
                    format_func=lambda m: '전체 층' if m == 'all_layers' else '그림체 블록', key=f'{key}_mode', horizontal=True)
    scale = st.select_slider('IP-Adapter 강도 (전체 층일 때)', S.IPA_SCALES, value=f['ipa_scale'] if f['ipa_scale'] in S.IPA_SCALES else 0.5,
                             key=f'{key}_scale')
    return S.build_style(tags, neg, weight, mode, scale)


def _style_examples():
    rows = []
    for g in store.list_games():
        if g['name'] in EXAMPLE_NAMES:
            f = S.style_fields(g['style'])
            rows.append({'예시 게임': g['name'], '그림체 태그': f['tags'], '빼는 태그': f['neg_extra'] or '-',
                         '장면 강조': '예' if f['scene_weight'] else '-',
                         'IP-Adapter': '그림체 블록' if f['ipa_name'] == 'style_only' else f"전체 층 {f['ipa_scale']}"})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')


EXAMPLE_NAMES = [g['name'] for g in store.default_games()]


def render():
    st.title('게임 등록·목록')
    st.caption('게임을 한 번 등록하면 모든 기능이 이 게임의 소개, 판매 포인트, 그림체를 불러와요.')
    left, right = st.columns([1, 1.25], gap='large')
    with left:
        st.subheader('새 게임 등록')
        # 근거: 18 냥기사 그림체 점수 IP-Adapter만 0.718 → LoRA + IP-Adapter 0.737 (README 주요 결과)
        st.info('스타일 LoRA를 함께 등록하면 그림체가 더 잘 유지돼요')
        with st.form('new_game', clear_on_submit=True):
            name = st.text_input('게임 이름')
            label = st.text_input('장르·그림체 (목록에 표시)', placeholder='예: 2D 애니풍 횡스크롤')
            info = st.text_input('한 줄 소개', help='홍보 문구와 상세 페이지 ② 게임 소개에 쓰여요.')
            st.markdown('판매 포인트')
            st.caption('A 홍보 문구에서 사용자가 판매 포인트를 따로 적지 않았을 때만 쓰는 기본값이에요.')
            points = _points_editor('new_points', [])
            refs = st.file_uploader('레퍼런스 아트 (여러 장 가능, 첫 장이 대표 아트)', type=['png', 'jpg', 'jpeg'], accept_multiple_files=True,
                                    help='B 배너, C 그림체 이미지에서 IP-Adapter가 그림체를 맞출 때 대표 아트(첫 장)를 써요.')
            st.caption(f'레퍼런스 아트: {upload_rule("ref")}')
            lora = st.file_uploader('스타일 LoRA (선택, .safetensors)', type=['safetensors'],
                                    help='없으면 IP-Adapter만으로 그림체를 맞춰요.')
            trigger = st.text_input('LoRA 트리거 단어 (선택)', help='LoRA를 학습할 때 캡션에 넣은 단어. 장면 태그 뒤에 붙여요.')
            with st.expander('그림체 설정 (기본값으로 시작, 게임에 맞게 고쳐 주세요)'):
                st.caption('기본값은 그림체 태그 없이 레퍼런스 아트와 IP-Adapter 전체 층 0.5만 써요. 24에서 이 기본 설정은 주인공·그림체를 '
                           '유지하지 못했고, 게임별로 정한 설정을 써야 그림체가 유지됐어요. 아래 예시 게임 설정을 참고해 고쳐 주세요.')
                _style_examples()
                new_style = _style_editor('new_style', S.NEW_GAME_STYLE)
            ok = st.form_submit_button('게임 등록', type='primary')
        if ok:
            if not (name.strip() and info.strip() and refs):
                st.error('게임 이름, 한 줄 소개, 레퍼런스 아트 1장 이상이 필요해요.')
            elif upload_errors(refs, 'ref'):
                pass
            else:
                ref_paths = [save_upload(f, 'refs') for f in refs]
                lora_path = save_upload(lora, 'lora') if lora else ''
                gid = store.add_game(name.strip(), label.strip(), info.strip(), points, ref_paths, lora_path, trigger.strip(), new_style)
                st.session_state['game_id_pending'] = gid
                st.success(f'{name} 등록 완료')
                st.rerun()
    with right:
        games = store.list_games()
        st.subheader(f'등록된 게임 · {len(games)}개')
        for g in games:
            with st.container(border=True):
                c1, c2 = st.columns([1, 2.2])
                if g['refs'] and absp(g['refs'][0]).exists():
                    c1.image(str(absp(g['refs'][0])), caption='대표 아트', width='stretch')
                c2.markdown(f"**{g['name']}**" + (f" · {g['label']}" if g['label'] else '') + (' · 작업 중' if g['id'] == st.session_state.get('game_id') else ''))
                c2.write(g['info'])
                if g['points']:
                    c2.markdown(' '.join(f':green-badge[{p}]' for p in g['points']))
                c2.caption(('LoRA + IP-Adapter' if g['lora'] else 'IP-Adapter만') + f" · 레퍼런스 아트 {len(g['refs'])}장")
                b1, b2 = c2.columns(2)
                if b1.button('수정', key=f'edit_{g["id"]}'):
                    st.session_state['editing'] = g['id']
                if b2.button('삭제', key=f'del_{g["id"]}'):
                    st.session_state['deleting'] = g['id']
                if st.session_state.get('deleting') == g['id']:
                    st.warning('이 게임을 목록에서 지워요. 만든 결과 파일은 남아요.')
                    if st.button('삭제 확인', key=f'delok_{g["id"]}', type='primary'):
                        store.delete_game(g['id'])
                        st.session_state.pop('deleting')
                        st.rerun()
                if st.session_state.get('editing') == g['id']:
                    with st.form(f'edit_form_{g["id"]}'):
                        info2 = st.text_input('한 줄 소개', g['info'])
                        label2 = st.text_input('장르·그림체', g['label'] or '')
                        pts2 = _points_editor(f'pts_{g["id"]}', g['points'])
                        st.markdown('그림체 설정')
                        style2 = _style_editor(f'style_{g["id"]}', g['style'])
                        if st.form_submit_button('저장'):
                            store.update_game(g['id'], info=info2, label=label2, points=pts2, style=style2)
                            st.session_state.pop('editing')
                            st.rerun()
