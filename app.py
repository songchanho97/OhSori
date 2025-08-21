# 기존 코드를 Main 탭과 Info 탭으로 분리한 구조입니다.
import base64
from streamlit.components.v1 import html as html_component


def make_video_data_url(filepath: str) -> str:
    with open(filepath, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:video/mp4;base64,{b64}"


def render_ad_video(title, desc, cta_text, link, video_src, video_width=500):
    return f"""
    <div style="box-sizing:border-box; width:100%; max-width:1380px; margin:12px auto 0 0 0;
                border:1px solid #E5E7EB; border-radius:16px; padding:14px 16px; background:#fff;">
      <div style="display:flex; gap:40px; align-items:center; flex-wrap:wrap;">
        <video src="{video_src}" type="video/mp4"
               autoplay muted loop playsinline controls preload="metadata"
               style="width:{video_width}px; height:auto; aspect-ratio:16/9; object-fit:cover; border-radius:12px;"></video>
        <div style="flex:1">
          <div style="font-weight:700; font-size:20px;">{title}</div>
          <div style="color:#6B7280; font-size:16px; margin-top:4px;">{desc}</div>
          <a href="{link}" target="_blank" rel="noopener"
             style="display:inline-block; margin-top:8px; padding:6px 10px; border:1px solid #111827; border-radius:10px;">
            {cta_text} →
          </a>
        </div>
      </div>
      <div style="margin-top:8px; color:#9CA3AF; font-size:12px;">광고</div>
    </div>
"""


import streamlit as st
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os
from core import (
    clean_text_for_tts,
    run_host_agent,
    run_guest_agents,
    run_writer_agent,
    parse_script,
    assign_voices,
    #generate_audio_segments,
    process_podcast_audio,
    fetch_news_articles,
    generate_audio_segments_elevenlabs,  # ⬅️ 추가
    get_voice_settings_for_mood,          # ✅ 분위기 → voice_settings
)

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)


LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")


st.set_page_config(page_title="🎤 AI 뉴스 팟캐스트 스튜디오", layout="wide")
if not (os.getenv("ELEVENLABS_API_KEY") or st.secrets.get("ELEVENLABS_API_KEY")):
    st.warning("ELEVENLABS_API_KEY가 설정되지 않았습니다. .env 또는 .streamlit/secrets.toml에 추가하세요.")
    # 키 없으면 아예 진행 막고 싶으면 ↓ 주석 해제
    # st.stop()
st.title("🎤 AI 뉴스 팟캐스트 스튜디오")
st.markdown(
    "관심 있는 뉴스 기사를 검색하고, AI가 자동으로 대본을 작성하여 팟캐스트 음성까지 생성해 드립니다."
)

# --- 세션 상태 초기화 ---
if "script" not in st.session_state:
    st.session_state.script = ""
if "podcast_mood" not in st.session_state:
    st.session_state.podcast_mood = "차분한"
if "podcast_mode" not in st.session_state:
    st.session_state.podcast_mode = "팩트 브리핑"
if "selected_category" not in st.session_state:
    st.session_state.selected_category = "전체"
if "selected_language" not in st.session_state:
    st.session_state.selected_language = "한국어"

# 탭 UI 생성
MainTab, OptionsTab = st.tabs(["Main", "Options"])

with MainTab:
    # --- 1. 뉴스 카테고리 선택 ---
    st.subheader("뉴스 카테고리 선택")
    category_options = {
        "전체": "🌐 전체",
        "정치": "🏛️ 정치",
        "경제": "📈 경제",
        "사회": "👥 사회",
        "문화": "🎨 문화",
        "국제": "🌍 국제",
        "스포츠": "⚽ 스포츠",
        "IT": "💻 IT/과학",
    }
    num_cols_per_row = 4
    cols_cat = st.columns(num_cols_per_row)
    col_idx = 0
    for i, (cat_key, cat_label) in enumerate(category_options.items()):
        with cols_cat[col_idx]:
            if st.button(
                cat_label,
                key=f"cat_{cat_key}",
                use_container_width=True,
                type=(
                    "primary"
                    if st.session_state.selected_category == cat_key
                    else "secondary"
                ),
            ):
                if st.session_state.selected_category != cat_key:
                    st.session_state.selected_category = cat_key
                    st.rerun()
        col_idx = (col_idx + 1) % num_cols_per_row

    # --- 2. 뉴스 검색 조건 입력 ---
    st.subheader("뉴스 검색 조건 입력")
    query = st.text_input(
        "검색할 뉴스 키워드를 입력하세요", placeholder="예: '챗GPT', '경제 침체'"
    )

    # --- 6. 대본 생성 버튼 ---
    st.subheader("팟캐스트 생성")

    if st.button("✨ 팟캐스트 대본 생성하기", use_container_width=True, type="primary"):
        if not query:
            st.error("뉴스 검색 키워드를 입력해주세요!")
        else:
            # 0) 먼저 LLM 초기화

            # 뉴스 기사 검색(API 호출)
            final_content = ""
            with st.spinner("1/4: KINDS API에서 최신 뉴스를 검색하고 있습니다..."):
                content = fetch_news_articles(query, st.session_state.selected_category)
            try:
                llm = ChatOpenAI(model_name="gpt-4o", temperature=0.7)
            except Exception as e:
                st.error(f"LLM 초기화 실패: {e}")
                llm = None

            # 1) 뉴스 데이터 불러오기
            content = fetch_news_articles(query, st.session_state.selected_category)
            if not content:
                st.warning("뉴스 데이터를 불러올 수 없습니다.")
            else:
                loading_area = st.container()
                ad_area = st.container()

                # 2) 광고 배너
                # 파일은 저장소에: OhSori/static/ads/adv.mp4
                data_url = make_video_data_url("static/ads/adv.mp4")

                ad_html = render_ad_video(
                    title="실종아동 찾기 · 112 신고",
                    desc="잠깐의 관심이 큰 기적이 됩니다.",
                    cta_text="자세히 보기",
                    link="https://www.safe182.go.kr",
                    video_src=data_url,  # ← data URL 전달!
                )
                html_component(ad_html, height=380, scrolling=False)

                # 3) 실제 Agent 실행
                try:
                    with loading_area:
                        with st.spinner(
                            "1/3: Host-Agent가 게스트를 섭외하고 있습니다..."
                        ):
                            host_response = run_host_agent(
                                llm, query, content, st.session_state.podcast_mode
                            )

                        with st.spinner(
                            "2/3: Guest-Agents가 답변을 준비하고 있습니다..."
                        ):
                            guest_answers = run_guest_agents(
                                llm,
                                query,
                                host_response["guests"],
                                host_response["interview_outline"],
                                content,
                                st.session_state.podcast_mode,
                            )

                        with st.spinner(
                            "3/3: Writer-Agent가 대본을 작성하고 있습니다..."
                        ):
                            final_script = run_writer_agent(
                                llm,
                                query,
                                st.session_state.podcast_mood,
                                st.session_state.selected_language,
                                host_response["guests"],
                                guest_answers,
                            )
                            st.session_state.script = final_script

                    st.success("대본 생성 완료!")

                except Exception as e:
                    st.error(f"대본 생성 중 오류: {e}")

   
# --- 7. 음성 생성 섹션 ---
if st.session_state.script:
    st.subheader("🎉 생성된 팟캐스트 대본")
    st.text_area("대본", st.session_state.script, height=300)

    if st.button("🎧 이 대본으로 음성 생성하기", use_container_width=True, type="primary"):
        with st.spinner("음성을 생성하고 BGM을 편집하고 있습니다... 잠시만 기다려주세요."):
            try:
                # 1) 대본 파싱
                parsed_lines, speakers = parse_script(st.session_state.script)
                if not speakers:
                    st.error("대본에서 화자를 찾을 수 없습니다. (예: **이름:** 형식)")
                    st.stop()

                # 2) 언어별 보이스 매핑 (ElevenLabs voice_id)
                voice_map = assign_voices(speakers, st.session_state.selected_language)
                st.write("#### 🎤 목소리 배정 결과 (ElevenLabs)")
                for spk, vid in voice_map.items():
                    st.write(f"**{spk}** → **{vid}**")

                # 3) 분위기 프리셋 → ElevenLabs voice_settings
                settings = get_voice_settings_for_mood(st.session_state.podcast_mood)

                # 4) ElevenLabs로 음성 조각 생성
                audio_segments = generate_audio_segments_elevenlabs(
                    parsed_lines,
                    eleven_voice_map=voice_map,
                    model_id=os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"),
                    voice_settings=settings,
                )
                if not audio_segments:
                    st.error("ElevenLabs 음성 생성에 실패했습니다. 로그를 확인해주세요.")
                    st.stop()

                # 5) BGM 결합 및 출력
                final_podcast_io = process_podcast_audio(audio_segments, "mp3.mp3")
                st.success("🎉 팟캐스트 음성 생성이 완료되었습니다!")
                st.audio(final_podcast_io, format="audio/mp3")
                st.download_button(
                    "📥 MP3 파일 다운로드",
                    final_podcast_io,
                    file_name="podcast_with_intro.mp3",
                    mime="audio/mpeg",
                )
            except Exception as e:
                st.error(f"음성 생성 또는 후반 작업 중 오류: {e}")



# if st.session_state.script:
#     st.subheader("🎉 생성된 팟캐스트 대본")
#     st.text_area("대본", st.session_state.script, height=300)

#     if st.button("🎧 이 대본으로 음성 생성하기", use_container_width=True, type="primary"):
#         with st.spinner("음성을 생성하고 BGM을 편집하고 있습니다... 잠시만 기다려주세요."):
#             try:
#                 # 1) 대본 파싱
#                 parsed_lines, speakers = parse_script(st.session_state.script)
#                 if not speakers:
#                     st.error("대본에서 화자를 찾을 수 없습니다. 대본 형식을 확인해주세요. (예: **이름:**)")
#                     st.stop()

#                 # 2) 한국어 전용 보이스 풀 (호스트 고정 + 나머지 랜덤)
#                 HOST_NAME = "Alex"  # 대본에 Host/진행자 대신 Alex를 쓰는 현재 패턴
#                 HOST_VOICE_ID = "ZJCNdZEjYwkOElxugmW2"  # 혁이(남) - 고정

#                 korean_voice_pool = [
#                     "ZJCNdZEjYwkOElxugmW2",  # 혁이(남)
#                     "uyVNoMrnUku1dZyVEXwD",  # 김안나(여)
#                     "1W00IGEmNmwmsDeYy7ag",  # kkc(남)
#                 ]

#                 import random

#                 # 2-1) 호스트/게스트 분리
#                 host_speakers = [s for s in speakers if s.strip() in [HOST_NAME, "Host", "진행자"]]
#                 guest_speakers = [s for s in speakers if s not in host_speakers]

#                 # 2-2) 맵 초기화 + 호스트 고정 배정
#                 eleven_voice_map = {}
#                 for h in host_speakers:
#                     eleven_voice_map[h] = HOST_VOICE_ID

#                 # 2-3) 게스트 랜덤 배정 (가능하면 중복 없이, 부족하면 섞어서 순환)
#                 guest_pool = [v for v in korean_voice_pool if v != HOST_VOICE_ID] or korean_voice_pool

#                 if len(guest_speakers) <= len(guest_pool):
#                     assigned = random.sample(guest_pool, len(guest_speakers))  # 중복 없이
#                 else:
#                     reps = (len(guest_speakers) + len(guest_pool) - 1) // len(guest_pool)
#                     extended = (guest_pool * reps)[:len(guest_speakers)]
#                     random.shuffle(extended)
#                     assigned = extended

#                 eleven_voice_map.update({spk: assigned[i] for i, spk in enumerate(guest_speakers)})

#                 # 결과 표시 (중복 출력 방지: 이 블록만 남겨둬)
#                 st.write("#### 🎤 목소리 배정 결과 (ElevenLabs)")
#                 for spk, v in eleven_voice_map.items():
#                     st.write(f"**{spk}** → **{v}**")

#                 # 3) ElevenLabs로 음성 생성
#                 # st.write("#### 🎧 ElevenLabs로 음성 조각 생성 중...")
#                 # audio_segments = generate_audio_segments_elevenlabs(
#                 #     parsed_lines,
#                 #     eleven_voice_map=eleven_voice_map,
#                 #     model_id=os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"),
#                 # )
#                 # if not audio_segments:
#                 #     st.error("ElevenLabs 음성 생성에 실패했습니다. 로그 메시지를 확인해주세요.")
#                 #     st.stop()

#                 # st.write(f"총 {len(audio_segments)}개의 음성 조각을 생성했습니다.")

#             #     # 4) BGM 결합
#             #     st.write("#### 🎶 BGM 편집 및 최종 결합 중...")
#             #     final_podcast_io = process_podcast_audio(audio_segments, "mp3.mp3")

#             #     # 5) 재생/다운로드
#             #     st.success("🎉 팟캐스트 음성 생성이 완료되었습니다!")
#             #     st.audio(final_podcast_io, format="audio/mp3")
#             #     st.download_button(
#             #         "📥 MP3 파일 다운로드",
#             #         final_podcast_io,
#             #         file_name="podcast_with_intro.mp3",
#             #         mime="audio/mpeg",
#             #     )

#             except Exception as e:
#                 st.error(f"음성 생성 또는 후반 작업 중 오류: {e}")
=======
    # --- 7. 음성 생성 섹션 ---
    if st.session_state.script:
        st.subheader("🎉 생성된 팟캐스트 대본")
        st.text_area("대본", st.session_state.script, height=300)



with OptionsTab:
    st.subheader("팟캐스트 생성 옵션")

    st.markdown("**팟캐스트 분위기 선택**")
    mood_options = {
        "차분한": "🌿 차분한",
        "신나는": "💃 신나는",
        "전문적인": "🧑‍💼 전문적인",
    }
    cols_mood = st.columns(len(mood_options))
    for i, (mood_key, mood_label) in enumerate(mood_options.items()):
        with cols_mood[i]:
            if st.button(
                mood_label,
                key=f"mood_{mood_key}",
                use_container_width=True,
                type=(
                    "primary"
                    if st.session_state.podcast_mood == mood_key
                    else "secondary"
                ),
            ):
                if st.session_state.podcast_mood != mood_key:
                    st.session_state.podcast_mood = mood_key
                    st.rerun()

    st.markdown("**팟캐스트 모드 선택**")
    mode_options = {"팩트 브리핑": "팩트 브리핑", "균형 토의": "균형 토의"}
    cols_mode = st.columns(len(mode_options))
    for i, (mode_key, mode_label) in enumerate(mode_options.items()):
        with cols_mode[i]:
            if st.button(
                mode_label,
                key=f"mode_{mode_key}",
                use_container_width=True,
                type=(
                    "primary"
                    if st.session_state.podcast_mode == mode_key
                    else "secondary"
                ),
            ):
                if st.session_state.podcast_mode != mode_key:
                    st.session_state.podcast_mode = mode_key
                    st.rerun()

    st.markdown("**팟캐스트 언어 선택**")
    language_options = {
        "한국어": "🇰🇷 한국어",
        "영어": "🇺🇸 영어",
        "일본어": "🇯🇵 일본어",
        "중국어": "🇨🇳 중국어",
    }

    lang_cols = st.columns(len(language_options))
    for i, (lang_key, lang_label) in enumerate(language_options.items()):
        with lang_cols[i]:
            button_type = (
                "primary"
                if st.session_state.selected_language == lang_key
                else "secondary"
            )
            if st.button(
                lang_label,
                key=f"lang_btn_{lang_key}",  # 키 값을 다른 섹션과 겹치지 않게 수정
                use_container_width=True,
                type=button_type,
            ):
                # 상태가 실제로 변경되었을 때만 rerun을 호출합니다. (이 부분이 핵심!)
                if st.session_state.selected_language != lang_key:
                    st.session_state.selected_language = lang_key
                    st.rerun()
