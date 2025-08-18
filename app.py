# 기존 코드를 Main 탭과 Info 탭으로 분리한 구조입니다.

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
    generate_audio_segments,
    process_podcast_audio,
    fetch_news_articles,
)

load_dotenv(dotenv_path=".env")
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")

st.set_page_config(page_title="🎤 AI 뉴스 팟캐스트 스튜디오", layout="centered")
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
            # 뉴스 기사 검색(API 호출)
            final_content = ""
            with st.spinner("1/4: KINDS API에서 최신 뉴스를 검색하고 있습니다..."):
                content = fetch_news_articles(query, st.session_state.selected_category)

            try:
                llm = ChatOpenAI(model_name="gpt-4o", temperature=0.7)

                with st.spinner("1/3: Host-Agent가 게스트를 섭외하고 있습니다..."):
                    host_response = run_host_agent(
                        llm, query, content, st.session_state.podcast_mode
                    )
                with st.spinner("2/3: Guest-Agents가 답변을 준비하고 있습니다..."):
                    guest_answers = run_guest_agents(
                        llm,
                        query,
                        host_response["guests"],
                        host_response["interview_outline"],
                        content,
                        st.session_state.podcast_mode,
                    )
                with st.spinner("3/3: Writer-Agent가 대본을 작성하고 있습니다..."):
                    final_script = run_writer_agent(
                        llm,
                        query,
                        st.session_state.podcast_mood,
                        st.session_state.selected_language,
                        host_response["guests"],
                        guest_answers,
                    )
                    st.session_state.script = final_script
            except Exception as e:
                st.error(f"대본 생성 중 오류: {e}")

    # --- 7. 음성 생성 섹션 ---
    if st.session_state.script:
        st.subheader("🎉 생성된 팟캐스트 대본")
        st.text_area("대본", st.session_state.script, height=300)

        if st.button(
            "🎧 이 대본으로 음성 생성하기", use_container_width=True, type="primary"
        ):
            with st.spinner(
                "음성을 생성하고 BGM을 편집하고 있습니다... 잠시만 기다려주세요."
            ):
                try:
                    parsed_lines, speakers = parse_script(st.session_state.script)
                    if not speakers:
                        st.error(
                            "대본에서 화자를 찾을 수 없습니다. 대본 형식을 확인해주세요. (예: **이름:**)"
                        )
                    else:
                        voice_map = assign_voices(
                            speakers, st.session_state.selected_language
                        )
                        st.write("#### 🎤 목소리 배정 결과")
                        for speaker, voice in voice_map.items():
                            st.write(f"**{speaker}** → **{voice}**")

                        st.write("#### 🎧 음성 조각 생성 중...")
                        audio_segments = generate_audio_segments(
                            parsed_lines, voice_map, speakers
                        )
                        st.write(
                            f"총 {len(audio_segments)}개의 음성 조각을 생성했습니다."
                        )

                        st.write("#### 🎶 BGM 편집 및 최종 결합 중...")
                        final_podcast_io = process_podcast_audio(
                            audio_segments, "mp3.mp3"
                        )

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


with OptionsTab:
    st.subheader("팟캐스트 생성 옵션")

    st.markdown("**팟캐스트 분위기 선택**")
    mood_options = {
        "차분한": "🧘‍♀️ 차분한",
        "신나는": "🥳 신나는",
        "전문적인": "👨‍🏫 전문적인",
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
