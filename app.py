import streamlit as st
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from langchain_teddynote.prompts import load_prompt
import os
import re
from pydub import AudioSegment
from openai import OpenAI
import io
import re

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
        button_type = (
            "primary" if st.session_state.selected_category == cat_key else "secondary"
        )

        if st.button(
            cat_label,
            key=f"cat_btn_{cat_key}",
            use_container_width=True,
            type=button_type,
        ):

            if st.session_state.selected_category != cat_key:
                st.session_state.selected_category = cat_key
                # 세션 상태를 업데이트한 후 앱을 다시 실행하여 UI를 즉시 갱신
                st.rerun()
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
             if st.session_state.podcast_mood != mood_key:
                st.session_state.podcast_mood = mood_key
                st.rerun()
           

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
            if st.session_state.selected_language != lang_key:
                st.session_state.selected_language = lang_key
                st.rerun()

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

# app.py 파일에 추가될 내용

st.write("")
# --- 6. 생성된 팟캐스트 대본 및 음성 생성 UI ---
st.subheader("6. 생성된 팟캐스트 대본 및 음성")

# st.session_state에 'script'가 생성되었다고 가정합니다.
if "script" in st.session_state and st.session_state.script:
    final_script = st.session_state.script

    # 생성된 대본을 UI에 표시
    st.text_area("생성된 팟캐스트 대본", final_script, height=300)

    # --- 1단계 (준비): 대본에서 화자 목록 추출 ---
    lines = re.split(r"\n(?=[\w\s]+:)", final_script.strip())
    parsed_lines = []
    for line in lines:
        if ":" in line:
            speaker, text = line.split(":", 1)
            parsed_lines.append({"speaker": speaker.strip(), "text": text.strip()})

    # 고유한 화자 목록을 순서대로 정렬하여 추출
    speakers = sorted(list(set([line["speaker"] for line in parsed_lines])))

    # --- 2단계 (UI): 화자별 목소리 선택 UI 표시 ---
    st.write("---")
    st.subheader("🎤 화자별 목소리 설정")

    # 사용 가능한 목소리 목록
    available_voices = [
        "nara",
        "dara",
        "jinho",
        "nhajun",
        "nsujin",
        "nsiyun",
        "njihun",
    ]  # 예시 목록

    # 각 화자에 대한 목소리 선택 메뉴를 생성
    # st.columns를 사용해 2열로 깔끔하게 배치
    cols = st.columns(2)
    for i, speaker in enumerate(speakers):
        with cols[i % 2]:
            st.selectbox(
                label=f"**{speaker}**의 목소리 선택",
                options=available_voices,
                key=f"voice_select_{speaker}",  # 각 메뉴를 구분하기 위한 고유 키
            )

    st.write("---")

    # --- 3단계 (실행): '음성 만들기' 버튼 및 로직 ---
    if st.button(
        "이 대본과 설정으로 팟캐스트 음성 만들기 🎧",
        use_container_width=True,
        type="primary",
    ):
        with st.spinner(
            "🎧 팟캐스트 음성을 생성 중입니다... (긴 대사는 분할 처리됩니다)"
        ):
            # '이 대본과 설정으로 팟캐스트 음성 만들기 🎧' 버튼 로직 전체
            try:
                # --- (이전 코드와 동일) 사용자 선택으로 voice_map 생성 ---
                voice_map = {}
                for speaker in speakers:
                    voice_map[speaker] = st.session_state[f"voice_select_{speaker}"]

                # --- 1. 모든 음성 조각을 생성해서 'audio_segments' 리스트에 모으기 ---
                audio_segments = []
                for line in parsed_lines:
                    speaker = line["speaker"]
                    full_text = line["text"]
                    clova_speaker = voice_map.get(speaker, "nara")

                    if not full_text.strip():
                        continue

                    # 텍스트 분할(Chunking) 로직
                    text_chunks = []
                    if len(full_text) > 2000:
                        sentences = re.split(r"(?<=[.!?])\s+", full_text)
                        current_chunk = ""
                        for sentence in sentences:
                            if len(current_chunk) + len(sentence) + 1 < 2000:
                                current_chunk += sentence + " "
                            else:
                                text_chunks.append(current_chunk.strip())
                                current_chunk = sentence + " "
                        if current_chunk:
                            text_chunks.append(current_chunk.strip())
                    else:
                        text_chunks.append(full_text)

                    # 각 텍스트 조각에 대해 음성을 생성하고 리스트에 추가
                    for text in text_chunks:
                        audio_content, error = generate_clova_speech(
                            text=text, speaker=clova_speaker
                        )

                        if error:
                            st.error(error)
                            st.stop()

                        audio_bytes = io.BytesIO(audio_content)
                        segment = AudioSegment.from_file(audio_bytes, format="mp3")
                        audio_segments.append(segment)

                # ======================================================================
                # ▼▼▼ 2. 모든 for 루프가 끝난 후에, 딱 한 번만 음성 병합 및 출력! ▼▼▼

                # 음성 파일 병합
                pause = AudioSegment.silent(duration=500)
                final_podcast = AudioSegment.empty()
                for segment in audio_segments:
                    final_podcast += segment + pause

                # 최종 파일 출력
                final_podcast_io = io.BytesIO()
                final_podcast.export(final_podcast_io, format="mp3")
                final_podcast_io.seek(0)

                st.success("🎉 팟캐스트 음성 생성이 완료되었습니다!")
                st.audio(final_podcast_io, format="audio/mp3")

                st.download_button(
                    label="🎧 MP3 파일 다운로드",
                    data=final_podcast_io,
                    file_name="podcast.mp3",
                    mime="audio/mpeg",
                )
                # ▲▲▲ 이 로직이 루프 바깥으로 이동했습니다 ▲▲▲
                # ======================================================================

            except Exception as e:
                st.error(f"음성 생성 중 오류가 발생했습니다: {e}")
