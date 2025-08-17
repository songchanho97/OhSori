import os
import json
import random
import requests
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import load_prompt
import streamlit as st
import re
from pydub import AudioSegment
import io


def clean_text_for_tts(text):
    """
    TTS 음성 합성을 위해 대사 텍스트를 최종 전처리하는 함수.
    - '#', '*', '[]' 등 발음이 불필요한 특수기호를 제거합니다.
    - (대사 안에 있는 사람 이름은 제거하지 않습니다.)
    """
    # 불필요한 특수 기호 및 단어를 제거합니다.
    # 콜론(:)은 문장 중간에 나올 수 있으므로 제거 목록에서 제외하는 것이 좋습니다.
    cleaned_text = re.sub(r"[#*\[\]]|클로징|오프닝", "", text)

    # 여러 공백을 하나로 축소하고 양 끝 공백을 최종적으로 제거합니다.
    cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()

    return cleaned_text

def clean_text_for_tts(text):
    """
    TTS 음성 합성을 위해 대사 텍스트를 최종 전처리하는 함수.
    - '#', '*', '[]' 등 발음이 불필요한 특수기호를 제거합니다.
    - (대사 안에 있는 사람 이름은 제거하지 않습니다.)
    """
    # 불필요한 특수 기호 및 단어를 제거합니다.
    # 콜론(:)은 문장 중간에 나올 수 있으므로 제거 목록에서 제외하는 것이 좋습니다.
    cleaned_text = re.sub(r"[#*\[\]]|클로징|오프닝", "", text)

    # 여러 공백을 하나로 축소하고 양 끝 공백을 최종적으로 제거합니다.
    cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()

    return cleaned_text


# core.py 파일의 run_host_agent 함수를 아래 코드로 교체해주세요.

def run_host_agent(llm, topic, content, mode):
    """Host-Agent를 실행하여 게스트 정보와 인터뷰 개요를 반환"""

    # mode 값에 따라 사용할 프롬프트 파일을 결정합니다.
    if mode == "팩트 브리핑":
        prompt_path = "./prompts/host_agent_fact.yaml"
    else:  # '균형 토의' 또는 다른 모든 경우
        prompt_path = "./prompts/host_agent_discussion.yaml"

    # 결정된 경로의 프롬프트 파일을 로드
    prompt = load_prompt(prompt_path, encoding="utf-8")

    host_chain = prompt | llm | JsonOutputParser()
    return host_chain.invoke({"topic": topic, "content": content})


def run_guest_agents(llm, topic, guests, interview_outline, content, mode):
    """Guest-Agent들을 실행하여 각 게스트의 답변을 반환"""
    guest_answers = []

    # mode 값에 따라 사용할 프롬프트 파일을 결정합니다.
    if mode == "팩트 브리핑":
        prompt_path = "./prompts/guest_agent_fact.yaml"
    else:  # '균형 토의' 또는 다른 모든 경우
        prompt_path = "./prompts/guest_agent_discussion.yaml"

    # 결정된 경로의 프롬프트 파일을 로드
    prompt = load_prompt(prompt_path, encoding="utf-8")

    guest_chain = prompt | llm | StrOutputParser()
    for guest in guests:
        answer = guest_chain.invoke(
            {
                "guest_name": guest["name"],
                "guest_description": guest["description"],
                "topic": topic,
                "questions": "\n- ".join(interview_outline),
                "content": content,
            }
        )
        guest_answers.append({"name": guest["name"], "answer": answer})
    return guest_answers


def run_writer_agent(llm, topic, mood, language, guests, guest_answers):
    """Writer-Agent를 실행하여 최종 팟캐스트 대본을 반환"""
    prompt = load_prompt("./prompts/writer_agent.yaml", encoding="utf-8")
    writer_chain = prompt | llm | StrOutputParser()
    return writer_chain.invoke(
        {
            "topic": topic,
            "mood": mood,
            "language": language,
            "guests_info": json.dumps(guests, ensure_ascii=False),
            "guest_raw_answers": "\n\n".join(
                [
                    f"--- {ga['name']}님의 답변 ---\n{ga['answer']}"
                    for ga in guest_answers
                ]
            ),
        }
    )


def generate_clova_speech(text, speaker="nara", speed=0, pitch=0):
    """Naver CLOVA Voice API를 호출하여 음성을 생성하는 함수"""
    client_id = st.secrets.get("NCP_CLIENT_ID") or os.getenv("NCP_CLIENT_ID")
    client_secret = st.secrets.get("NCP_CLIENT_SECRET") or os.getenv(
        "NCP_CLIENT_SECRET"
    )
    if not client_id or not client_secret:
        return None, "CLOVA Voice API 인증 정보를 .env 파일에 설정해주세요."

    url = "https://naveropenapi.apigw.ntruss.com/tts-premium/v1/tts"
    headers = {
        "X-NCP-APIGW-API-KEY-ID": client_id,
        "X-NCP-APIGW-API-KEY": client_secret,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = f"speaker={speaker}&text={requests.utils.quote(text)}&speed={speed}&pitch={pitch}&format=mp3"
    try:
        response = requests.post(url, headers=headers, data=data.encode("utf-8"))
        if response.status_code == 200:
            return response.content, None
        else:
            return (
                None,
                f"CLOVA Voice API 오류: {response.status_code} - {response.text}",
            )
    except Exception as e:
        return None, f"CLOVA Voice API 요청 중 예외 발생: {e}"


def parse_script(script_text):
    """대본 텍스트를 파싱하여 화자별 대사 리스트와 전체 화자 리스트를 반환합니다."""
    try:

        # **...:** 형식으로 된 화자를 모두 인식하도록 수정
        pattern = re.compile(r"\*\*(.*?):\*\*\s*(.*)")
        matches = pattern.findall(script_text)
        parsed_lines = [
            {"speaker": speaker.strip(), "text": text.strip()}
            for speaker, text in matches
        ]

        if not parsed_lines:
            # 기본 형식(:)으로 재시도
            lines = re.split(r"\n(?=[\w\s.-]+:)", script_text.strip())
            parsed_lines = []
            for line in lines:
                if ":" in line:
                    speaker, text = line.split(":", 1)
                    parsed_lines.append(
                        {"speaker": speaker.strip(), "text": text.strip()}
                    )

        speakers = sorted(list(set([line["speaker"] for line in parsed_lines])))
        return parsed_lines, speakers
    except Exception as e:
        print(f"스크립트 파싱 오류: {e}")
        return [], []


def assign_voices(speakers, language):
    """언어 설정에 따라 화자들에게 목소리를 자동으로 배정합니다."""
    if language == "영어":
        available_voices = ["clara", "danna", "djoey", "matt"]
        host_voice = "matt"
    elif language == "일본어":  # ▼▼▼ 일본어 분기 추가 ▼▼▼
        available_voices = [
            "dayumu",
            "ddaiki",
            "deriko",
            "dhajime",
            "dmio",
            "dnaomi",
            "driko",
        ]
        host_voice = "ddaiki"  # 일본어 진행자 목소리 (예시)

    else:  # 기본값: 한국어
        available_voices = [
            "nara",
            "dara",
            "jinho",
            "nhajun",
            "nsujin",
        ]
        host_voice = "nara"

    voice_map = {}

    host_speakers = [s for s in speakers if "Host" in s or "진행자" in s or "Alex" in s]
    guest_speakers = [s for s in speakers if s not in host_speakers]

    for host in host_speakers:
        voice_map[host] = host_voice

    guest_voice_pool = [v for v in available_voices if v != host_voice]
    if not guest_voice_pool:
        guest_voice_pool = available_voices

    if len(guest_speakers) > len(guest_voice_pool):
        selected_guest_voices = random.choices(guest_voice_pool, k=len(guest_speakers))
    elif guest_speakers:
        selected_guest_voices = random.sample(guest_voice_pool, len(guest_speakers))
    else:
        selected_guest_voices = []

    for guest, voice in zip(guest_speakers, selected_guest_voices):
        voice_map[guest] = voice

    return voice_map


def generate_audio_segments(parsed_lines, voice_map, speakers):
    """파싱된 대본과 목소리 맵을 기반으로 음성 조각 리스트를 생성합니다."""
    audio_segments = []
    for line in parsed_lines:
        speaker = line["speaker"]

        # ▼▼▼ 텍스트 정제 로직을 여기서 호출합니다 ▼▼▼
        cleaned_text = clean_text_for_tts(line["text"])

        # 정제 후 텍스트가 비어있으면 건너뜁니다.
        if not cleaned_text:
            continue

        clova_speaker = voice_map.get(speaker, "nara")

        text_chunks = [
            cleaned_text[i : i + 1000] for i in range(0, len(cleaned_text), 1000)
        ]
        for chunk in text_chunks:
            audio_content, error = generate_clova_speech(
                text=chunk, speaker=clova_speaker
            )
            if error:
                raise Exception(f"'{speaker}'의 음성 생성 중 오류: {error}")

            segment = AudioSegment.from_file(io.BytesIO(audio_content), format="mp3")
            audio_segments.append(segment)

    return audio_segments


def process_podcast_audio(audio_segments, bgm_file="mp3.mp3"):
    """음성 조각들에 BGM을 입히고 최종 팟캐스트 파일을 생성합니다."""
    # 1. 음성 조각 병합
    pause = AudioSegment.silent(duration=500)
    final_podcast_voice = AudioSegment.empty()
    for i, segment in enumerate(audio_segments):
        final_podcast_voice += segment
        if i < len(audio_segments) - 1:
            final_podcast_voice += pause

    # 2. BGM 처리
    bgm_audio = AudioSegment.from_file(bgm_file, format="mp3")
    intro_duration = 3000
    fade_duration = 6000
    loud_intro = bgm_audio[:intro_duration] + 6
    fading_part = bgm_audio[intro_duration : intro_duration + fade_duration].fade_out(
        fade_duration
    )
    final_bgm_track = loud_intro + fading_part

    # 3. 최종 결합
    final_duration = intro_duration + len(final_podcast_voice)
    final_podcast = AudioSegment.silent(duration=final_duration)
    final_podcast = final_podcast.overlay(final_bgm_track)
    final_podcast = final_podcast.overlay(final_podcast_voice, position=intro_duration)

    # 4. 메모리로 내보내기
    final_podcast_io = io.BytesIO()
    final_podcast.export(final_podcast_io, format="mp3", bitrate="192k")
    final_podcast_io.seek(0)
    return final_podcast_io
