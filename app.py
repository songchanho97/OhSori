import streamlit as st
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os

# core.py에서 모든 함수를 가져옵니다.
from core import (
    run_host_agent,
    run_guest_agents,
    run_writer_agent,
    parse_script,
    assign_voices,
    generate_audio_segments,
    process_podcast_audio,
)

load_dotenv(dotenv_path=".env")
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")

# --- UI 섹션 ---
st.title("🎤 AI 뉴스 팟캐스트 스튜디오")
st.markdown(
    "관심 있는 뉴스 기사를 검색하고, AI가 자동으로 대본을 작성하여 팟캐스트 음성까지 생성해 드립니다."
)

# --- 세션 상태 초기화 ---
if "script" not in st.session_state:
    st.session_state.script = ""
if "podcast_mood" not in st.session_state:
    st.session_state.podcast_mood = "차분한"
if "selected_category" not in st.session_state:
    st.session_state.selected_category = "전체"
if "selected_language" not in st.session_state:
    st.session_state.selected_language = "한국어"

# --- 1. 뉴스 카테고리 선택 섹션 (복구) ---
st.subheader("1. 뉴스 카테고리 선택")
category_options = {
    "전체": "🌐 전체",
    "경제": "📈 경제",
    "IT": "💻 IT/과학",
    "정치": "🏛️ 정치",
    "사회": "👥 사회",
    "생활/문화": "🎨 생활/문화",
    "스포츠": "⚽ 스포츠",
    "세계": "🌍 세계",
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

# --- 2. 뉴스 검색 조건 입력 섹션 ---
st.subheader("2. 뉴스 검색 조건 입력")
query = st.text_input(
    "검색할 뉴스 키워드를 입력하세요", placeholder="예: '챗GPT', '경제 침체'"
)

# --- 3. 팟캐스트 분위기 선택 섹션 ---
st.subheader("3. 팟캐스트 분위기 선택")
mood_options = {
    "차분한": "🧘‍♀️ 차분한",
    "신나는": "🥳 신나는",
    "전문적인": "👨‍🏫 전문적인",
    "유머러스한": "😂 유머러스한",
}
cols_mood = st.columns(len(mood_options))
for i, (mood_key, mood_label) in enumerate(mood_options.items()):
    with cols_mood[i]:
        if st.button(
            mood_label,
            key=f"mood_{mood_key}",
            use_container_width=True,
            type=(
                "primary" if st.session_state.podcast_mood == mood_key else "secondary"
            ),
        ):
            if st.session_state.podcast_mood != mood_key:
                st.session_state.podcast_mood = mood_key
                st.rerun()

# --- 4. 팟캐스트 언어 선택 섹션 ---
st.subheader("4. 팟캐스트 언어 선택")
language_options = {"한국어": "🇰🇷 한국어", "영어": "🇺🇸 영어"}
cols_lang = st.columns(len(language_options))
for i, (lang_key, lang_label) in enumerate(language_options.items()):
    with cols_lang[i]:
        if st.button(
            lang_label,
            key=f"lang_{lang_key}",
            use_container_width=True,
            type=(
                "primary"
                if st.session_state.selected_language == lang_key
                else "secondary"
            ),
        ):
            st.session_state.selected_language = lang_key

# --- 5. 대본 생성 버튼 섹션 ---
st.subheader("5. 팟캐스트 생성")
if st.button("✨ 팟캐스트 대본 생성하기", use_container_width=True, type="primary"):
    if not query:
        st.error("뉴스 검색 키워드를 입력해주세요!")
    else:
        try:
            llm = ChatOpenAI(model_name="gpt-4o", temperature=0.7)
            with st.spinner("1/3: Host-Agent가 게스트를 섭외하고 있습니다..."):
                host_response = run_host_agent(llm, query)
            with st.spinner("2/3: Guest-Agents가 답변을 준비하고 있습니다..."):
                guest_answers = run_guest_agents(
                    llm,
                    query,
                    host_response["guests"],
                    host_response["interview_outline"],
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

# --- 6. 음성 생성 섹션 ---
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
                # 1. 스크립트 파싱
                parsed_lines, speakers = parse_script(st.session_state.script)

                # 2. 목소리 배정
                voice_map = assign_voices(speakers, st.session_state.selected_language)
                st.write("#### 🎤 목소리 배정 결과")
                for speaker, voice in voice_map.items():
                    st.write(f"**{speaker}** → **{voice}**")

                # 3. 음성 조각 생성
                audio_segments = generate_audio_segments(parsed_lines, voice_map)

                # 4. BGM과 함께 최종 팟캐스트 오디오 처리
                final_podcast_io = process_podcast_audio(audio_segments, "mp3.mp3")

                # 5. 결과 출력
                st.success("🎉 팟캐스트 음성 생성이 완료되었습니다!")
                st.audio(final_podcast_io, format="audio/mp3")
                st.download_button(
                    label="📥 MP3 파일 다운로드",
                    data=final_podcast_io,
                    file_name="podcast_with_intro.mp3",
                    mime="audio/mpeg",
                )
            except Exception as e:
                st.error(f"음성 생성 또는 후반 작업 중 오류: {e}")
