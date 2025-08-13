import streamlit as st
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from langchain_teddynote.prompts import load_prompt
import os

from core import (
    run_host_agent,
    run_guest_agents,
    run_writer_agent,
    generate_clova_speech,
)

load_dotenv(dotenv_path=".env")

LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")

# title
st.title("🎤 AI 뉴스 팟캐스트 스튜디오")
st.markdown(
    "관심 있는 뉴스 기사를 검색하고, AI가 자동으로 대본을 작성하여 팟캐스트 음성까지 생성해 드립니다."
)
# --- 세션 상태 초기화 ---
# 대본을 저장할 세션 상태 추가
if "script" not in st.session_state:
    st.session_state.script = ""
if "podcast_mood" not in st.session_state:
    st.session_state.podcast_mood = "차분한"
if "selected_category" not in st.session_state:
    st.session_state.selected_category = "전체"
if "selected_language" not in st.session_state:
    st.session_state.selected_language = "한국어"


# --- 1. 뉴스 카테고리 선택 섹션 ---
st.write("")
st.subheader("1. 뉴스 카테고리 선택")

# 뉴스 카테고리 선택 버튼 (네모 버튼 형태로 가로 배치 + 이모지)
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
cols = st.columns(num_cols_per_row)
col_idx = 0

for i, (cat_key, cat_label) in enumerate(category_options.items()):
    with cols[col_idx]:
        # 선택된 카테고리 버튼은 primary type으로 표시
        button_type = (
            "primary" if st.session_state.selected_category == cat_key else "secondary"
        )
        if st.button(
            cat_label,  # 이모지와 텍스트를 직접 전달
            key=f"cat_btn_{cat_key}",
            use_container_width=True,
            type=button_type,
        ):
            st.session_state.selected_category = cat_key  # 클릭 시 세션 상태 업데이트
    col_idx = (col_idx + 1) % num_cols_per_row

# 사이드바 생성

# --- 2. 뉴스 검색 조건 입력 섹션 ---
st.write("")
st.subheader("2. 뉴스 검색 조건 입력")
query = st.text_input(
    "검색할 뉴스 키워드를 입력하세요 (예: '인공지능 AND 일자리', '기후변화 OR 탄소중립')",
    placeholder="예: '챗GPT', '경제 침체'",
)

# --- 3. 팟캐스트 분위기 선택 섹션 ---
st.write("")
st.subheader("3. 팟캐스트 분위기 선택")

# 팟캐스트 분위기 선택 버튼 (네모 버튼 형태로 가로 배치 + 이모지)
mood_options = {
    "차분한": "🧘‍♀️ 차분한",
    "신나는": "🥳 신나는",
    "전문적인": "👨‍🏫 전문적인",
    "유머러스한": "😂 유머러스한",
}
cols = st.columns(len(mood_options))


for i, (mood_key, mood_label) in enumerate(mood_options.items()):
    with cols[i]:
        # 선택된 분위기 버튼은 primary type으로 표시
        button_type = (
            "primary" if st.session_state.podcast_mood == mood_key else "secondary"
        )
        if st.button(
            mood_label,  # 이모지와 텍스트를 직접 전달
            key=f"mood_btn_{mood_key}",
            use_container_width=True,
            type=button_type,
        ):
            st.session_state.podcast_mood = mood_key

# --- 4. 팟캐스트 언어 선택 섹션 (새로 추가) ---
st.write("")
st.subheader("4. 팟캐스트 언어 선택")

language_options = {"한국어": "🇰🇷 한국어", "영어": "🇺🇸 영어", "중국어": "Ch 중국어"}
lang_cols = st.columns(len(language_options))

for i, (lang_key, lang_label) in enumerate(language_options.items()):
    with lang_cols[i]:
        button_type = (
            "primary" if st.session_state.selected_language == lang_key else "secondary"
        )
        if st.button(
            lang_label,
            key=f"lang_btn_{lang_key}",
            use_container_width=True,
            type=button_type,
        ):
            st.session_state.selected_language = lang_key

# --- 5. 팟캐스트 생성 버튼 섹션 ---
st.write("")
st.subheader("5. 팟캐스트 생성")

if st.button(
    "✨ 팟캐스트 대본 생성 및 음성 만들기", use_container_width=True, type="primary"
):
    if not query:
        st.error("뉴스 검색 키워드를 입력해주세요!")
    else:
        try:
            llm = ChatOpenAI(model_name="gpt-4o", temperature=0.7)

            with st.spinner(
                "1/3단계: Host-Agent가 게스트를 섭외하고 질문지를 작성 중입니다..."
            ):
                host_response = run_host_agent(llm, query)
                guests = host_response["guests"]
                interview_outline = host_response["interview_outline"]
                st.session_state.guests = guests  # 세션에 게스트 정보 저장

            with st.spinner(
                "2/3단계: Guest-Agents가 각자의 전문 분야에 맞춰 답변을 준비 중입니다..."
            ):
                guest_answers = run_guest_agents(llm, query, guests, interview_outline)

            with st.spinner(
                "3/3단계: Writer-Agent가 수집된 답변들을 맛깔나는 대화 대본으로 다듬고 있습니다..."
            ):
                final_script = run_writer_agent(
                    llm,
                    query,
                    st.session_state.podcast_mood,
                    st.session_state.selected_language,
                    guests,
                    guest_answers,
                )
                st.session_state.script = final_script

        except Exception as e:
            st.error(f"대본 생성 중 오류가 발생했습니다: {e}")

# --- 6. 생성된 팟캐스트 대본 및 음성 생성 UI ---
if st.session_state.get("script"):
    st.write("")
    st.subheader("🎉 생성된 팟캐스트 대본")
    st.markdown(st.session_state.script)

    st.subheader("🎧 팟캐스트 음성 생성 (TTS)")
    if st.button("🎵 이 대본으로 음성 생성하기"):
        with st.spinner(
            "대본을 분석하고, 각 성우의 목소리로 음성을 만들고 있습니다..."
        ):
            guests = st.session_state.get("guests", [])
            if not guests:
                st.error("게스트 정보가 없습니다. 대본을 다시 생성해주세요.")
            else:
                voice_map = {
                    "Alex": "nara",
                    guests[0]["name"]: "dara",
                    guests[1]["name"]: "jinho",
                }
                lines = st.session_state.script.strip().split("\n")
                st.success("음성 생성이 완료되었습니다! 아래에서 확인해보세요. 👇")
                for line in lines:
                    line = line.strip()
                    if not line or ":" not in line:
                        continue

                    speaker_name, speech_text = line.split(":", 1)
                    speaker_name = speaker_name.strip()
                    speech_text = speech_text.strip()

                    if speaker_name in voice_map:
                        st.write(
                            f"**{speaker_name}** ({voice_map[speaker_name]} 목소리)"
                        )
                        audio_content, error_msg = generate_clova_speech(
                            speech_text, speaker=voice_map[speaker_name]
                        )
                        if error_msg:
                            st.error(error_msg)
                        if audio_content:
                            st.audio(audio_content, format="audio/mp3")
                    else:
                        st.write(line)
