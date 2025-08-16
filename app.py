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
import random

from core import (
    run_host_agent,
    run_guest_agents,
    run_writer_agent,
    generate_clova_speech,
    clean_text_for_tts,
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

# app.py 파일에 추가될 내용

st.write("")
# --- 6. 생성된 팟캐스트 대본 및 음성 생성 UI ---
st.subheader("6. 생성된 팟캐스트 대본 및 음성")

if "script" in st.session_state and st.session_state.script:
    final_script = st.session_state.script

    st.text_area("생성된 팟캐스트 대본", final_script, height=300)

    # --- 1. 대본에서 모든 화자 목록을 미리 추출 (새로운 로직) ---
    try:
        # Markdown 형식(**이름:**)에 맞춰 화자와 대사를 한 번에 추출하는 정규표현식
        # **(영어 또는 한글 이름):** (대사 내용)
        pattern = re.compile(r"\*\*([A-Za-z가-힣]+):\*\*\s*(.*)")
        matches = pattern.findall(final_script)

        parsed_lines = [
            {"speaker": speaker, "text": text.strip()} for speaker, text in matches
        ]

        if not parsed_lines:
            # 만약 위 패턴으로 아무것도 찾지 못했을 경우, 기존의 단순 ": " 기준으로 다시 시도합니다.
            lines = re.split(r"\n(?=[\w\s]+:)", final_script.strip())
            parsed_lines = []
            for line in lines:
                if ":" in line:
                    speaker, text = line.split(":", 1)
                    parsed_lines.append(
                        {"speaker": speaker.strip(), "text": text.strip()}
                    )

        # 고유 화자 목록을 확정합니다.
        speakers = sorted(list(set([line["speaker"] for line in parsed_lines])))
    except Exception as e:
        st.error(f"대본에서 화자를 분석하는 중 오류가 발생했습니다: {e}")
        speakers = []  # 오류 발생 시 화자 목록을 비웁니다.

    st.write("---")

    # 디버깅을 위해 실제 변수 값을 화면에 출력합니다.
    st.info(f"분석된 화자 목록: {speakers}")
    # st.info(f"인식된 화자 수: {len(speakers)}")

    # --- 2. '음성 만들기' 버튼 ---
    # 화자가 2명 이상일 때만 버튼이 활성화되도록 할 수 있습니다.
    if len(speakers) >= 2:
        if st.button(
            "이 대본으로 팟캐스트 음성 만들기 🎧",
            use_container_width=True,
            type="primary",
        ):
            with st.spinner("🎧 팟캐스트 음성을 생성 중입니다..."):
                try:
                    # --- 3. (핵심) 버튼 클릭 시, 목소리 자동 배정 ---
                    st.info("대본의 화자들에게 목소리를 자동으로 배정합니다.")

                    available_voices = [
                        "nara",
                        "dara",
                        "jinho",
                        "nhajun",
                        "nsujin",
                        "nsiyun",
                        "njihun",
                    ]
                    voice_map = {}

                    # 진행자와 게스트를 분리합니다.
                    host_speakers = [
                        s for s in speakers if "Host" in s or "진행자" in s
                    ]
                    guest_speakers = [s for s in speakers if s not in host_speakers]

                    # 3-1. 진행자에게는 고정 목소리를 할당합니다 (예: 'nara').
                    host_voice = "nara"
                    for host in host_speakers:
                        voice_map[host] = host_voice

                    # 3-2. 게스트에게 할당할 목소리 풀을 준비합니다.
                    # 진행자가 사용한 목소리와 사용 가능한 전체 목소리를 고려합니다.
                    guest_voice_pool = [v for v in available_voices if v != host_voice]

                    # 3-3. 게스트 수만큼 랜덤으로, 겹치지 않게 목소리를 할당합니다.
                    if len(guest_speakers) > len(guest_voice_pool):
                        st.warning(
                            "게스트가 너무 많아 일부 목소리가 중복될 수 있습니다."
                        )
                        # 목소리가 부족할 경우, 중복을 허용하여 배정
                        selected_guest_voices = random.choices(
                            guest_voice_pool, k=len(guest_speakers)
                        )
                    else:
                        selected_guest_voices = random.sample(
                            guest_voice_pool, len(guest_speakers)
                        )

                    for guest, voice in zip(guest_speakers, selected_guest_voices):
                        voice_map[guest] = voice

                    # 사용자에게 배정 결과를 명확히 보여줍니다.
                    for speaker, voice in voice_map.items():
                        st.write(f"✅ **{speaker}** → **{voice}** 목소리로 배정")

                        # --- 4. 음성 생성 및 병합 ---
                        audio_segments = []
                        for line in parsed_lines:
                            speaker = line["speaker"]
                            text = line["text"].strip()
                            clova_speaker = voice_map.get(
                                speaker, "nara"
                            )  # 맵에서 목소리 조회

                            if not text:
                                continue

                            # 긴 텍스트 분할 (API 제한 대응)
                            text_chunks = [
                                text[i : i + 1000] for i in range(0, len(text), 1000)
                            ]

                            for chunk in text_chunks:
                                audio_content, error = generate_clova_speech(
                                    text=chunk, speaker=clova_speaker
                                )
                                if error:
                                    st.error(
                                        f"'{speaker}'의 음성 생성 중 오류: {error}"
                                    )
                                    st.stop()

                                segment = AudioSegment.from_file(
                                    io.BytesIO(audio_content), format="mp3"
                                )
                                audio_segments.append(segment)

                        # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
                        # 모든 음성 조각을 합치는 수정된 로직
                        final_podcast = AudioSegment.empty()
                        pause = AudioSegment.silent(duration=500)  # 500ms 쉼

                        for i, segment in enumerate(audio_segments):
                            final_podcast += segment
                            # 마지막 오디오 조각 뒤에는 쉼을 추가하지 않습니다.
                            if i < len(audio_segments) - 1:
                                final_podcast += pause
                        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

                        # 최종 결과물 출력
                        final_podcast_io = io.BytesIO()
                        final_podcast.export(final_podcast_io, format="mp3")

                        st.success("🎉 팟캐스트 음성 생성이 완료되었습니다!")
                        st.audio(final_podcast_io, format="audio/mp3")
                        st.download_button(
                            label="🎧 MP3 파일 다운로드",
                            data=final_podcast_io,
                            file_name="podcast.mp3",
                            mime="audio/mpeg",
                        )

                except Exception as e:
                    st.error(f"음성 생성 과정에서 예상치 못한 오류가 발생했습니다: {e}")
    elif speakers:
        # 화자가 1명만 있을 경우 안내 메시지를 표시합니다.
        st.warning("팟캐스트를 생성하려면 대본에 최소 2명 이상의 화자가 필요합니다.")
