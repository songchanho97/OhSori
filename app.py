import streamlit as st
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from langchain_teddynote.prompts import load_prompt
import os
import io
import re
import tempfile
import subprocess

import imageio_ffmpeg  # ← ffmpeg 바이너리 제공(별도 brew 설치 불필요)

from core import (
    run_host_agent,
    run_guest_agents,
    run_writer_agent,
    generate_clova_speech,
)

# ─────────────────────────────────────────────────────────────────────────────
# ffmpeg 기반 MP3 병합 헬퍼 (pydub 없이)
# ─────────────────────────────────────────────────────────────────────────────
def concat_mp3_bytes(mp3_bytes_list, pause_sec=0.5, sr=24000, ch=1, quality=4) -> bytes:
    """
    MP3 바이트 리스트를 ffmpeg로 병합(+ 조각 사이 정적음)하여 최종 MP3 바이트 반환
    - pause_sec: 조각 사이 무음 초
    - sr: 출력 샘플레이트(Hz)
    - ch: 채널 수(1=mono, 2=stereo)
    - quality: libmp3lame VBR 품질(0~9, 낮을수록 고품질/용량↑)
    """
    if not mp3_bytes_list:
        raise ValueError("병합할 MP3 조각이 없습니다.")

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    channel_layout = "mono" if ch == 1 else "stereo"

    with tempfile.TemporaryDirectory() as td:
        # 1) 입력 mp3들을 임시파일로 저장
        seg_paths = []
        for i, b in enumerate(mp3_bytes_list):
            p = os.path.join(td, f"seg{i}.mp3")
            with open(p, "wb") as f:
                f.write(b)
            seg_paths.append(p)

        # 2) 정적음 mp3 생성 (pause_sec 길이)
        silence_path = os.path.join(td, "silence.mp3")
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f", "lavfi",
                "-t", str(pause_sec),
                "-i", f"anullsrc=r={sr}:cl={channel_layout}",
                "-q:a", str(quality),
                silence_path,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 3) concat 리스트 파일 작성 (세그먼트 사이에 정적음 삽입)
        list_path = os.path.join(td, "list.txt")
        with open(list_path, "w") as f:
            for i, p in enumerate(seg_paths):
                f.write(f"file '{p}'\n")
                if i != len(seg_paths) - 1:
                    f.write(f"file '{silence_path}'\n")

        # 4) concat + 통일 인코딩
        out_path = os.path.join(td, "out.mp3")
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", list_path,
                "-c:a", "libmp3lame",
                "-ar", str(sr),
                "-ac", str(ch),
                "-q:a", str(quality),
                out_path,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        with open(out_path, "rb") as f:
            return f.read()


# ─────────────────────────────────────────────────────────────────────────────

load_dotenv(dotenv_path=".env")
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")

# title
st.title("🎤 AI 뉴스 팟캐스트 스튜디오")
st.markdown("관심 있는 뉴스 기사를 검색하고, AI가 자동으로 대본을 작성하여 팟캐스트 음성까지 생성해 드립니다.")

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
    "차분한": "🧘‍♀️ 차분한",
    "신나는": "🥳 신나는",
    "전문적인": "👨‍🏫 전문적인",
    "유머러스한": "😂 유머러스한",
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
            # langchain-openai 0.3.x: model 파라미터 사용
            llm = ChatOpenAI(model="gpt-4o", temperature=0.7)

            with st.spinner("1/3단계: Host-Agent가 게스트를 섭외하고 질문지를 작성 중입니다..."):
                host_response = run_host_agent(llm, query)
                guests = host_response["guests"]
                interview_outline = host_response["interview_outline"]
                st.session_state.guests = guests

            with st.spinner("2/3단계: Guest-Agents가 각자의 전문 분야에 맞춰 답변을 준비 중입니다..."):
                guest_answers = run_guest_agents(llm, query, guests, interview_outline)

            with st.spinner("3/3단계: Writer-Agent가 수집된 답변들을 맛깔나는 대화 대본으로 다듬고 있습니다..."):
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
st.write("")
st.subheader("6. 생성된 팟캐스트 대본 및 음성")

if "script" in st.session_state and st.session_state.script:
    final_script = st.session_state.script

    # 생성된 대본 표시
    st.text_area("생성된 팟캐스트 대본", final_script, height=300)

    # 1) 화자/텍스트 파싱
    lines = re.split(r"\n(?=[\w\s]+:)", final_script.strip())
    parsed_lines = []
    for line in lines:
        if ":" in line:
            speaker, text = line.split(":", 1)
            parsed_lines.append({"speaker": speaker.strip(), "text": text.strip()})

    speakers = sorted(list(set([line["speaker"] for line in parsed_lines])))

    # 2) 화자별 목소리 선택
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

    # 3) 음성 만들기
    if st.button("이 대본과 설정으로 팟캐스트 음성 만들기 🎧", use_container_width=True, type="primary"):
        with st.spinner("🎧 팟캐스트 음성을 생성 중입니다... (긴 대사는 분할 처리됩니다)"):
            try:
                # 화자→목소리 매핑
                voice_map = {speaker: st.session_state[f"voice_select_{speaker}"] for speaker in speakers}

                # 1. 모든 음성 조각을 생성해서 'mp3_segments' 리스트에 모으기
                mp3_segments = []
                for line in parsed_lines:
                    speaker = line["speaker"]
                    full_text = line["text"]
                    clova_speaker = voice_map.get(speaker, "nara")

                    if not full_text.strip():
                        continue

                    # 텍스트 분할(Chunking)
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

                    # 각 조각에 대해 TTS → mp3 bytes 수집
                    for text in text_chunks:
                        audio_content, error = generate_clova_speech(text=text, speaker=clova_speaker)
                        if error:
                            st.error(error)
                            st.stop()
                        if not audio_content:
                            st.error("생성된 오디오가 비어 있습니다.")
                            st.stop()
                        mp3_segments.append(audio_content)

                if not mp3_segments:
                    st.error("생성된 오디오 세그먼트가 없습니다.")
                    st.stop()

                # 2. ffmpeg로 병합(+0.5s 무음)
                final_mp3 = concat_mp3_bytes(mp3_segments, pause_sec=0.5, sr=24000, ch=1, quality=4)

                # 3. 재생/다운로드 (bytes로 전달)
                st.success("🎉 팟캐스트 음성 생성이 완료되었습니다!")
                st.audio(final_mp3, format="audio/mpeg")
                st.download_button(
                    label="🎧 MP3 파일 다운로드",
                    data=final_mp3,
                    file_name="podcast.mp3",
                    mime="audio/mpeg",
                )

            except Exception as e:
                st.error(f"음성 생성 중 오류가 발생했습니다: {e}")
