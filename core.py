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


def clean_text_for_tts(script):
    """
    TTS 음성 합성을 위해 텍스트를 전처리하는 함수.
    '**이름**', '[질문...]' 등 발음에는 불필요한 요소를 제거합니다.
    ('#'으로 시작하는 줄은 이제 제거하지 않습니다.)
    """
    # 1단계: '#'으로 시작하는 줄 제거 로직을 사용자의 요청에 따라 주석 처리하여 비활성화합니다.
    # cleaned_script = re.sub(r"^#.*\n?", "", script, flags=re.MULTILINE)

    # 2단계: 나머지 불필요한 패턴들을 제거
    # 이제 원본 'script'에 직접 정제 로직을 적용합니다.
    cleaned_script = re.sub(
        r"\*\*.*?\*\*|\[질문\s*\d+\s*:.*?\]\n?|[*\[\]]|클로징|오프닝",
        "",
        script,  # 원본 스크립트를 직접 사용
    )

    return cleaned_script.strip()  # 최종적으로 시작과 끝의 공백을 제거합니다.


def run_host_agent(llm, topic):
    """Host-Agent를 실행하여 게스트 정보와 인터뷰 개요를 반환"""
    prompt = load_prompt("./prompts/host_agent.yaml", encoding="utf-8")
    host_chain = prompt | llm | JsonOutputParser()
    return host_chain.invoke({"topic": topic})


def run_guest_agents(llm, topic, guests, interview_outline):
    """Guest-Agent들을 실행하여 각 게스트의 답변을 반환"""
    guest_answers = []
    prompt = load_prompt("./prompts/guest_agent.yaml", encoding="utf-8")
    guest_chain = prompt | llm | StrOutputParser()
    for guest in guests:
        answer = guest_chain.invoke(
            {
                "guest_name": guest["name"],
                "guest_description": guest["description"],
                "topic": topic,
                "questions": "\n- ".join(interview_outline),
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
        # Markdown 형식(**이름:**) 우선 파싱
        pattern = re.compile(r"\*\*([A-Za-z가-힣\s]+):\*\*\s*(.*)")
        matches = pattern.findall(script_text)
        parsed_lines = [
            {"speaker": speaker.strip(), "text": text.strip()}
            for speaker, text in matches
        ]

        # 파싱 실패 시, 기본 형식(:)으로 재시도
        if not parsed_lines:
            lines = re.split(r"\n(?=[\w\s]+:)", script_text.strip())
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
    else:  # 기본값: 한국어
        available_voices = [
            "nara",
            "dara",
            "jinho",
            "nhajun",
            "nsujin",
            "nsiyun",
            "njihun",
        ]
        host_voice = "nara"

    voice_map = {}
    host_speakers = [s for s in speakers if "Host" in s or "진행자" in s or "Alex" in s]
    guest_speakers = [s for s in speakers if s not in host_speakers]

    for host in host_speakers:
        voice_map[host] = host_voice

    guest_voice_pool = [v for v in available_voices if v != host_voice]
    if len(guest_speakers) > len(guest_voice_pool):
        selected_guest_voices = random.choices(guest_voice_pool, k=len(guest_speakers))
    else:
        selected_guest_voices = random.sample(guest_voice_pool, len(guest_speakers))

    for guest, voice in zip(guest_speakers, selected_guest_voices):
        voice_map[guest] = voice

    return voice_map


def generate_audio_segments(parsed_lines, voice_map):
    """파싱된 대본과 목소리 맵을 기반으로 음성 조각 리스트를 생성합니다."""
    audio_segments = []
    for line in parsed_lines:
        speaker = line["speaker"]
        text = line["text"].strip()
        clova_speaker = voice_map.get(speaker, "nara")

        if not text:
            continue

        text_chunks = [text[i : i + 1000] for i in range(0, len(text), 1000)]
        for chunk in text_chunks:
            audio_content, error = generate_clova_speech(
                text=chunk, speaker=clova_speaker
            )
            if error:
                # Streamlit UI가 없는 core.py에서는 에러를 반환하거나 로깅 처리합니다.
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
