import streamlit as st
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os
import re
import io
from pydub import AudioSegment

from core import (
    run_host_agent,
    run_guest_agents,
    run_writer_agent,
    generate_clova_speech,
)

load_dotenv(dotenv_path=".env")

# --- 상수 정의 ---
# 'mp3.mp3' 파일을 직접 참조하므로 BGM_FILE_PATH 상수는 이제 불필요
# try:
#     BASE_DIR = os.path.dirname(os.path.abspath(__file__))
#     BGM_FILE_PATH = os.path.join(BASE_DIR, "mp3.mp3")
# except NameError:
#     BGM_FILE_PATH = "mp3.mp3"

LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")

# title
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


# --- 1. 뉴스 카테고리 선택 섹션 ---
st.write("")
st.subheader("1. 뉴스 카테고리 선택")

category_options = {
    "전체": "🌐 전체", "경제": "📈 경제", "IT": "💻 IT/과학", "정치": "🏛️ 정치",
    "사회": "👥 사회", "생활/문화": "🎨 생활/문화", "스포츠": "⚽ 스포츠", "세계": "🌍 세계",
}

num_cols_per_row = 4
cols = st.columns(num_cols_per_row)
col_idx = 0

for i, (cat_key, cat_label) in enumerate(category_options.items()):
    with cols[col_idx]:
        button_type = "primary" if st.session_state.selected_category == cat_key else "secondary"
        if st.button(
            cat_label,
            key=f"cat_btn_{cat_key}",
            use_container_width=True,
            type=button_type,
        ):
            if st.session_state.selected_category != cat_key:
                st.session_state.selected_category = cat_key
                st.rerun()
    col_idx = (col_idx + 1) % num_cols_per_row


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

mood_options = {
    "차분한": "🧘‍♀️ 차분한", "신나는": "🥳 신나는", "전문적인": "👨‍🏫 전문적인", "유머러스한": "😂 유머러스한",
}
cols = st.columns(len(mood_options))


for i, (mood_key, mood_label) in enumerate(mood_options.items()):
    with cols[i]:
        button_type = "primary" if st.session_state.podcast_mood == mood_key else "secondary"
        if st.button(
            mood_label,
            key=f"mood_btn_{mood_key}",
            use_container_width=True,
            type=button_type,
        ):
            st.session_state.podcast_mood = mood_key

# --- 4. 팟캐스트 언어 선택 섹션 ---
st.write("")
st.subheader("4. 팟캐스트 언어 선택")

language_options = {"한국어": "🇰🇷 한국어", "영어": "🇺🇸 영어", "중국어": "Ch 중국어"}
lang_cols = st.columns(len(language_options))

for i, (lang_key, lang_label) in enumerate(language_options.items()):
    with lang_cols[i]:
        button_type = "primary" if st.session_state.selected_language == lang_key else "secondary"
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

if st.button("✨ 팟캐스트 대본 생성 및 음성 만들기", use_container_width=True, type="primary"):
    if not query:
        st.error("뉴스 검색 키워드를 입력해주세요!")
    else:
        try:
            llm = ChatOpenAI(model_name="gpt-4o", temperature=0.7)
            with st.spinner("1/3단계: Host-Agent가 게스트를 섭외하고 질문지를 작성 중입니다..."):
                host_response = run_host_agent(llm, query)
                guests = host_response["guests"]
                interview_outline = host_response["interview_outline"]
            with st.spinner("2/3단계: Guest-Agents가 각자의 전문 분야에 맞춰 답변을 준비 중입니다..."):
                guest_answers = run_guest_agents(llm, query, guests, interview_outline)
            with st.spinner("3/3단계: Writer-Agent가 수집된 답변들을 맛깔나는 대화 대본으로 다듬고 있습니다..."):
                final_script = run_writer_agent(
                    llm, query, st.session_state.podcast_mood,
                    st.session_state.selected_language, guests, guest_answers,
                )
                st.session_state.script = final_script
        except Exception as e:
            st.error(f"대본 생성 중 오류가 발생했습니다: {e}")

# --- 6. 생성된 팟캐스트 대본 및 음성 생성 UI ---
st.write("")
st.subheader("6. 생성된 팟캐스트 대본 및 음성")

if "script" in st.session_state and st.session_state.script:
    final_script = st.session_state.script
    st.text_area("생성된 팟캐스트 대본", final_script, height=300)

    lines = re.split(r"\n(?=[\w\s]+:)", final_script.strip())
    parsed_lines = []
    for line in lines:
        if ":" in line:
            speaker, text = line.split(":", 1)
            parsed_lines.append({"speaker": speaker.strip(), "text": text.strip()})

    speakers = sorted(list(set([line["speaker"] for line in parsed_lines])))

    st.write("---")
    st.subheader("🎤 화자별 목소리 설정")
    available_voices = ["nara", "dara", "jinho", "nhajun", "nsujin", "nsiyun", "njihun"]
    cols = st.columns(2)
    for i, speaker in enumerate(speakers):
        with cols[i % 2]:
            st.selectbox(
                label=f"**{speaker}**의 목소리 선택",
                options=available_voices,
                key=f"voice_select_{speaker}",
            )

    st.write("---")
    if st.button("이 대본과 설정으로 팟캐스트 음성 만들기 🎧", use_container_width=True, type="primary"):
        with st.spinner("🎧 팟캐스트 음성을 생성하고 인트로를 편집하고 있습니다..."):
            try:
                voice_map = {speaker: st.session_state[f"voice_select_{speaker}"] for speaker in speakers}
                
                audio_segments = []
                for line in parsed_lines:
                    speaker, full_text = line["speaker"], line["text"]
                    clova_speaker = voice_map.get(speaker, "nara")
                    if not full_text.strip(): continue
                    
                    text_chunks = [full_text[i:i + 2000] for i in range(0, len(full_text), 2000)]
                    for text in text_chunks:
                        audio_content, error = generate_clova_speech(text=text, speaker=clova_speaker)
                        if error: st.error(error); st.stop()
                        audio_segments.append(AudioSegment.from_file(io.BytesIO(audio_content), format="mp3"))

                # ▼▼▼▼▼ 오디오 처리 로직 시작 (수정됨) ▼▼▼▼▼
                
                # 1. 생성된 음성 조각들을 하나로 병합
                pause = AudioSegment.silent(duration=500)
                final_podcast_voice = AudioSegment.empty()
                for segment in audio_segments:
                    final_podcast_voice += segment + pause
                
                # 2. BGM 파일 로드
                bgm_audio = AudioSegment.from_file("mp3.mp3", format="mp3")

                # 3. BGM 인트로 및 페이드 아웃 효과 생성 (더 자연스럽게 수정)
                intro_duration = 3000  # 3초 인트로
                fade_duration = 6000   # [수정] 페이드 시간을 4초 -> 6초로 늘려 더 부드럽게

                # 3-1. 3초 인트로 부분은 볼륨을 6dB 키웁니다.
                loud_intro = bgm_audio[:intro_duration] + 6

                # 3-2. 목소리와 겹치며 사라질 부분은 원본 BGM 볼륨에서 바로 페이드 아웃을 시작합니다.
                # [수정] 급격한 볼륨 감소를 막기 위해 '- 15' 부분을 제거했습니다.
                fading_part = bgm_audio[intro_duration : intro_duration + fade_duration].fade_out(fade_duration)

                # 3-3. 인트로와 페이드 아웃 BGM을 합칩니다.
                final_bgm_track = loud_intro + fading_part

                # 4. 최종 팟캐스트 결합
                # 최종 길이는 (인트로 길이 + 목소리 길이)로 설정
                final_duration = intro_duration + len(final_podcast_voice)
                final_podcast = AudioSegment.silent(duration=final_duration)

                # 4-1. BGM 트랙을 처음에 덮어씌웁니다.
                final_podcast = final_podcast.overlay(final_bgm_track)
                # 4-2. 3초 지점부터 목소리 트랙을 덮어씌웁니다.
                final_podcast = final_podcast.overlay(final_podcast_voice, position=intro_duration)

                # 5. 최종 결과물을 메모리로 내보내기
                final_podcast_io = io.BytesIO()
                final_podcast.export(final_podcast_io, format="mp3", bitrate="192k")

                # 6. 최종 파일 출력 및 다운로드
                st.success("🎉 팟캐스트 음성 생성이 완료되었습니다!")
                
                final_podcast_io.seek(0)
                st.audio(final_podcast_io, format="audio/mp3")

                final_podcast_io.seek(0)
                st.download_button(label="🎧 MP 파일 다운로드", data=final_podcast_io, file_name="podcast_with_intro.mp3", mime="audio/mpeg")

                # ▲▲▲▲▲ 오디오 처리 로직 끝 ▲▲▲▲▲


            except Exception as e:
                st.error(f"음성 생성 또는 후반 작업 중 오류가 발생했습니다: {e}")