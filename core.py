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
from pydub.effects import speedup


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


def get_speech_style_for_mood(mood):
    """선택된 분위기에 맞는 음성 스타일 파라미터 딕셔너리를 반환합니다."""
    if mood == "차분한":
        return {"speed": 0, "pitch": 1, "emotion": 0}
    elif mood == "신나는":
        return {"speed": -2, "pitch": -1, "emotion": 2}
    elif mood == "전문적인":
        return {"speed": 0, "pitch": 1, "emotion": 0}
    elif mood == "유머러스한":
        return {"speed": -2, "pitch": -2, "emotion": 2}
    else:  # 기본값
        return {}


def generate_clova_speech(
    text,
    speaker="nara",
    speed=0,
    pitch=0,
    emotion=None,
    emotion_strength=None,
    alpha=None,
    end_pitch=None,
):
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

    # ▼▼▼ 파라미터를 동적으로 구성하는 부분 ▼▼▼
    # 필수 파라미터
    params = {
        "speaker": speaker,
        "text": text,
        "format": "mp3",
    }
    # 선택적 파라미터 (값이 있을 때만 추가)
    if emotion is not None:
        params["emotion"] = emotion
    if emotion_strength is not None:
        params["emotion-strength"] = emotion_strength  # API 명세에 맞게 하이픈 사용
    if alpha is not None:
        params["alpha"] = alpha
    if end_pitch is not None:
        params["end-pitch"] = end_pitch  # API 명세에 맞게 하이픈 사용

    # URL 인코딩을 적용하여 data 생성
    # requests.utils.quote가 text에만 적용되도록 수정
    encoded_params = [
        f"{key}={requests.utils.quote(str(value)) if key == 'text' else value}"
        for key, value in params.items()
    ]
    data = "&".join(encoded_params)

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
    elif language == "일본어":
        available_voices = [
            "dayumu",
            "ddaiki",
            "deriko",
            "dhajime",
            "dmio",
            "dnaomi",
            "driko",
        ]
        host_voice = "ddaiki"
    elif language == "중국어":  # ▼▼▼ 중국어 분기 추가 ▼▼▼
        available_voices = ["meimei", "liangliang", "chiahua"]
        host_voice = "liangliang"  # 중국어 진행자 목소리 (예시)
    else:  # 기본값: 한국어
        available_voices = ["vdaeseong", "vmikyung"]
        host_voice = "vgoeun"

    voice_map = {}
    # 'Host', '진행자' 등 언어별 진행자 키워드를 리스트로 관리
    host_keywords = ["Host", "진행자", "Alex", "主持人"]
    host_speakers = [s for s in speakers if s.strip("* ") in host_keywords]
    guest_speakers = [s for s in speakers if s not in host_speakers]

    for host in host_speakers:
        voice_map[host] = host_voice

    # 진행자 목소리를 제외한 나머지 목소리 풀
    guest_voice_pool = [v for v in available_voices if v != host_voice]
    if not guest_voice_pool:  # 만약 게스트 목소리 풀이 비었다면 전체 목소리 사용
        guest_voice_pool = available_voices

    selected_guest_voices = []
    # 게스트 수에 맞게 목소리 배정 (중복 허용 또는 샘플링)
    if guest_speakers:
        if len(guest_speakers) > len(guest_voice_pool):
            selected_guest_voices = random.choices(
                guest_voice_pool, k=len(guest_speakers)
            )
        else:
            selected_guest_voices = random.sample(guest_voice_pool, len(guest_speakers))

    for guest, voice in zip(guest_speakers, selected_guest_voices):
        voice_map[guest] = voice

    return voice_map


def generate_audio_segments(parsed_lines, voice_map, mood):  # 1. mood 인자 받기
    """
    파싱된 대본 라인들을 순회하며 각 라인에 대한 음성 조각(AudioSegment)을 생성합니다.
    팟캐스트 분위기(mood)에 맞는 스타일을 적용합니다.
    """
    audio_segments = []

    # 2. 현재 분위기에 맞는 스타일 프리셋을 가져옵니다.
    style_params = get_speech_style_for_mood(mood)

    progress_bar = st.progress(0, "음성 조각 생성 시작...")

    for i, line in enumerate(parsed_lines):
        speaker = line["speaker"]
        cleaned_text = clean_text_for_tts(line["text"])

        progress_text = f"'{speaker}'의 대사 생성 중... ({i+1}/{len(parsed_lines)})"
        progress_bar.progress((i + 1) / len(parsed_lines), text=progress_text)

        if not cleaned_text:
            continue

        clova_speaker = voice_map.get(speaker, "nara")

        # API는 최대 5000자까지 가능하지만, 안정성을 위해 1000자 단위로 분할
        text_chunks = [
            cleaned_text[i : i + 1000] for i in range(0, len(cleaned_text), 1000)
        ]

        for chunk in text_chunks:
            # 3. TTS API 호출 시, `**style_params`로 분위기 프리셋을 적용합니다.
            audio_content, error = generate_clova_speech(
                text=chunk, speaker=clova_speaker, **style_params
            )

            if error:
                # 앱을 멈추는 대신 사용자에게 오류를 알리고 중단
                st.error(f"'{speaker}'의 음성 생성 중 오류가 발생했습니다: {error}")
                progress_bar.empty()
                return None  # 오류 발생 시 None 반환

            segment = AudioSegment.from_file(io.BytesIO(audio_content), format="mp3")
            audio_segments.append(segment)

    progress_bar.empty()
    return audio_segments


def change_audio_speed(audio_segment, speed=1.0):
    """
    pydub.effects.speedup을 사용하여 오디오의 재생 속도를 변경합니다.
    """
    if speed == 1.0:
        return audio_segment
    return speedup(audio_segment, playback_speed=speed)


# core.py에 있는 기존 함수를 이렇게 수정합니다.


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

    # 4. 메모리로 내보내기 (이 부분을 수정합니다.)
    # final_podcast_io = io.BytesIO()
    # final_podcast.export(final_podcast_io, format="mp3", bitrate="192k")
    # final_podcast_io.seek(0)
    # return final_podcast_io

    # 수정된 부분: AudioSegment 객체를 바로 반환
    return final_podcast
