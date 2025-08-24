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
import json
import requests
from datetime import datetime, timedelta
from elevenlabs.client import ElevenLabs  # NEW
from itertools import cycle

import imageio_ffmpeg

AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()


from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=True)


def _get_my_voice_ids():
    api_key = (
        st.secrets.get("ELEVENLABS_API_KEY") if "st" in globals() else None
    ) or os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        return set()
    try:
        client = ElevenLabs(api_key=api_key)
        voices = client.voices.get_all()
        return {v.voice_id for v in voices.voices}
    except Exception:
        return set()


MY_VOICE_IDS = _get_my_voice_ids()  # 시작 시 1회 로드
FALLBACK_VOICE_ID = os.getenv("ELEVEN_FALLBACK_VOICE_ID", "")


# KINDS API 키
KINDS_API_KEY = "6baa0f25-4695-4a66-aff8-4389931c6521"
# 뉴스 검색 API URL (OpenAPI_사용자치침서_V1.5.pdf 6페이지 참조)
NEWS_SEARCH_URL = "https://tools.kinds.or.kr/search/news"

# 뉴스 통합 분류체계 코드 (PDF 38-40페이지 참조)
CATEGORY_CODES = {
    "전체": "",
    "정치": "001000000",
    "경제": "002000000",
    "사회": "003000000",
    "문화": "004000000",
    "국제": "005000000",
    "스포츠": "007000000",
    "IT": "008000000",
}


def fetch_news_articles(query: str, category: str, num_articles: int = 6) -> str | None:
    """
    KINDS 뉴스 검색 API를 호출하여 관련 뉴스 기사 내용을 가져오는 함수
    """
    category_code = CATEGORY_CODES.get(category)

    # 검색 기간을 최근 1달로 동적으로 설정
    until_date = datetime.now()
    from_date = until_date - timedelta(days=30)

    request_body = {
        "access_key": KINDS_API_KEY,
        "argument": {
            "query": query,
            "published_at": {
                "from": from_date.strftime("%Y-%m-%d"),
                "until": until_date.strftime("%Y-%m-%d"),
            },
            "provider": [],
            "category": [category_code] if category_code else [],
            "sort": [
                {"_score": "desc"},  # 1순위: 정확도 높은 순
                {"date": "desc"},  # 2순위: 최신순
            ],
            "return_from": 0,
            "return_size": num_articles,
            "fields": ["title", "content", "provider", "published_at", "hilight"],
        },
    }

    try:
        response = requests.post(NEWS_SEARCH_URL, data=json.dumps(request_body))
        response.raise_for_status()

        data = response.json()
        if data.get("return_object", {}).get("total_hits", 0) == 0:
            st.warning("검색된 뉴스 기사가 없습니다. 다른 키워드로 시도해보세요.")
            return None

        articles = data.get("return_object", {}).get("documents", [])
        context = ""
        for i, article in enumerate(articles):
            context += f"--- 뉴스{i+1} ---\n"
            context += f"제목: {article.get('title', 'N/A')}\n"
            # hilight 필드는 검색어 주변을 강조해서 보여주므로 content보다 유용합니다.
            content_summary = (
                article.get("hilight", "내용 없음")
                .replace("<b>", "")
                .replace("</b>", "")
            )
            context += f"본문: {content_summary}\n\n"
        return context

    except requests.exceptions.RequestException as e:
        st.error(f"뉴스 API 요청에 실패했습니다: {e}")
        return None
    except Exception as e:
        st.error(f"뉴스 데이터를 처리하는 중 오류가 발생했습니다: {e}")
        return None


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


def get_voice_settings_for_mood(mood: str):
    """
    ElevenLabs voice_settings 매핑.
    값 범위는 보통 0.0~1.0 (style은 일부 보이스에서만 의미 있을 수 있음)
    """
    if mood == "차분한":
        return {
            "stability": 0.75,
            "similarity_boost": 0.7,
            "style": 0.1,
            "use_speaker_boost": True,
        }
    elif mood == "신나는":
        return {
            "stability": 0.45,
            "similarity_boost": 0.85,
            "style": 0.7,
            "use_speaker_boost": True,
        }
    elif mood == "전문적인":
        return {
            "stability": 0.85,
            "similarity_boost": 0.6,
            "style": 0.2,
            "use_speaker_boost": True,
        }
    elif mood == "유머러스한":
        return {
            "stability": 0.5,
            "similarity_boost": 0.8,
            "style": 0.6,
            "use_speaker_boost": True,
        }
    else:  # 기본
        return {
            "stability": 0.6,
            "similarity_boost": 0.7,
            "style": 0.3,
            "use_speaker_boost": True,
        }


# >>clova에서만 해당 되는 거니 수정 해야함
# def generate_eleven_speech(
#     text,
#     speaker="nara",
#     speed=0,
#     pitch=0,
#     emotion=None,
#     emotion_strength=None,
#     alpha=None,
#     end_pitch=None,
# ):
#     """Naver CLOVA Voice API를 호출하여 음성을 생성하는 함수"""
#     client_id = st.secrets.get("NCP_CLIENT_ID") or os.getenv("NCP_CLIENT_ID")
#     client_secret = st.secrets.get("NCP_CLIENT_SECRET") or os.getenv(
#         "NCP_CLIENT_SECRET"
#     )
#     if not client_id or not client_secret:
#         return None, "CLOVA Voice API 인증 정보를 .env 파일에 설정해주세요."

#     url = "https://naveropenapi.apigw.ntruss.com/tts-premium/v1/tts"
#     headers = {
#         "X-NCP-APIGW-API-KEY-ID": client_id,
#         "X-NCP-APIGW-API-KEY": client_secret,
#         "Content-Type": "application/x-www-form-urlencoded",
#     }

#     # ▼▼▼ 파라미터를 동적으로 구성하는 부분 ▼▼▼
#     # 필수 파라미터
#     params = {
#         "speaker": speaker,
#         "text": text,
#         "format": "mp3",
#     }
#     # 선택적 파라미터 (값이 있을 때만 추가)
#     if emotion is not None:
#         params["emotion"] = emotion
#     if emotion_strength is not None:
#         params["emotion-strength"] = emotion_strength  # API 명세에 맞게 하이픈 사용
#     if alpha is not None:
#         params["alpha"] = alpha
#     if end_pitch is not None:
#         params["end-pitch"] = end_pitch  # API 명세에 맞게 하이픈 사용

#     # URL 인코딩을 적용하여 data 생성
#     # requests.utils.quote가 text에만 적용되도록 수정
#     encoded_params = [
#         f"{key}={requests.utils.quote(str(value)) if key == 'text' else value}"
#         for key, value in params.items()
#     ]
#     data = "&".join(encoded_params)

#     try:
#         response = requests.post(url, headers=headers, data=data.encode("utf-8"))
#         if response.status_code == 200:
#             return response.content, None
#         else:
#             return (
#                 None,
#                 f"CLOVA Voice API 오류: {response.status_code} - {response.text}",
#             )
#     except Exception as e:
#         return None, f"CLOVA Voice API 요청 중 예외 발생: {e}"


def parse_script(script_text):
    """대본 텍스트를 파싱하여 화자별 대사 리스트와 전체 화자 리스트를 반환합니다."""
    try:
        import re

        lines = [ln.strip() for ln in script_text.splitlines()]
        parsed_lines = []

        # 1) 헤더(예: **[본론]**, [본론]) → 무시
        p_header = re.compile(r"^\s*(\*\*)?\[\s*.+?\s*\](\*\*)?\s*$")

        # ▼▼ 헤더 제거한 텍스트로 재구성 (핵심 포인트 1) ▼▼
        script_wo_headers = "\n".join(ln for ln in lines if not p_header.match(ln))

        # 2) **이름:** 내용
        pattern = re.compile(r"\*\*(.*?):\*\*\s*(.*)")
        matches = pattern.findall(
            script_wo_headers
        )  # ← 핵심 포인트 2: script_text → script_wo_headers

        # ✅ 추가: **...**: 형식 (콜론이 볼드 밖)

        if not matches:
            pattern_outside = re.compile(r"\*\*(.*?)\*\*:\s*(.*)")
            matches = pattern_outside.findall(script_wo_headers)  # ← 동일하게 교체

        parsed_lines = [
            {"speaker": speaker.strip(), "text": text.strip()}
            for speaker, text in matches
        ]

        # 4) 기본 형식 "이름: 내용" (fallback)
        if not parsed_lines:
            # 헤더 제거된 텍스트 기준으로 split
            lines2 = re.split(r"\n(?=[\w\s.-]+:)", script_wo_headers.strip())
            parsed_lines = []
            for line in lines2:
                if ":" in line:
                    speaker, text = line.split(":", 1)
                    # 혹시 헤더 패턴이 끼어들면 건너뜀(이론상 여긴 안 옴)
                    if p_header.match(line):
                        continue
                    parsed_lines.append(
                        {"speaker": speaker.strip(), "text": text.strip()}
                    )

        speakers = sorted(list(set([line["speaker"] for line in parsed_lines])))
        return parsed_lines, speakers

    except Exception as e:
        print(f"스크립트 파싱 오류: {e}")
        return [], []


# 일레븐랩스 보이스 풀 (네가 준 ID 그대로)
ELEVEN_VOICE_POOLS = {
    "한국어": {
        "host": "gSIFuVFiNs1RkrhPg3G7",  # 교수(남)
        "pool": [
            # "ZJCNdZEjYwkOElxugmW2",  # 혁이(남)
            "uyVNoMrnUku1dZyVEXwD",  # 김안나(여)
            "1W00IGEmNmwmsDeYy7ag",  # kkc(남)
        ],
    },
    "영어": {
        "host": "RexqLjNzkCjWogguKyff",  # bradely(남)
        "pool": [
            # "RexqLjNzkCjWogguKyff",  # bradely(남)
            "iCrDUkL56s3C8sCRl7wb",  # hope(여)
            "L1aJrPa7pLJEyYlh3Ilq",  # oliver(남)
        ],
    },
    "일본어": {
        "host": "sRYzP8TwEiiqAWebdYPJ",  # Voiceactor(남)
        "pool": [
            # "sRYzP8TwEiiqAWebdYPJ",  # bradely(남)
            "hBWDuZMNs32sP5dKzMuc",  # Ken(여)
            "WQz3clzUdMqvBf0jswZQ",  # Shizuka(여)
        ],
    },
    "중국어": {
        "host": "fQj4gJSexpu8RDE2Ii5m",  # Yu(남)
        "pool": [
            # "fQj4gJSexpu8RDE2Ii5m",  # Yu(남)
            "hkfHEbBvdQFNX4uWHqR",  # Stacy(여)
            "WuLq5z7nEcrhppO0ZQJw",  # Martin(남) 아아 피곤합니다아
        ],
    },
}


def _norm_name(s: str) -> str:
    # '**이름:**' 같은 형식 대비해서 기호/공백 제거
    return s.strip().strip("*").strip(":").strip()


def assign_voices(speakers, language: str):
    """
    언어에 맞춰 화자에게 ElevenLabs voice_id를 배정.
    - 진행자(Host/진행자/Alex/主持人)는 언어별 host 고정 보이스
    - 게스트는 해당 언어 풀에서 라운드로빈(결정적) 배정
    """
    # 언어가 없거나 키가 틀리면 한국어 풀로 폴백
    conf = ELEVEN_VOICE_POOLS.get(language, ELEVEN_VOICE_POOLS["한국어"])
    host_voice = conf["host"]
    # host를 pool에서 제거(중복 배정 방지). 비면 host만이라도 사용
    pool = (
        [v for v in conf.get("pool", []) if v != host_voice]
        or conf.get("pool", [])
        or [host_voice]
    )

    host_keywords = {"Host", "진행자", "Alex", "主持人"}

    # 진행자/게스트 분리
    host_speakers = [s for s in speakers if _norm_name(s) in host_keywords]
    guest_speakers = [s for s in speakers if s not in host_speakers]

    # 진행자 없으면 첫 화자를 진행자로 폴백(원치 않으면 이 블록 제거)
    if not host_speakers and speakers:
        host_speakers = [speakers[0]]
        guest_speakers = speakers[1:]

    voice_map = {h: host_voice for h in host_speakers}

    # 게스트는 라운드로빈(매 실행 동일 결과). 랜덤 원하면 cycle 대신 random.choice 써도 됨
    picker = cycle(pool)
    for spk in guest_speakers:
        voice_map[spk] = next(picker)

    return voice_map


def generate_audio_segments(
    parsed_lines, voice_map, mood, model_id=None, voice_settings=None
):  # 1. mood 인자 받기
    """
    파싱된 대본 라인들을 순회하며 각 라인에 대한 음성 조각(AudioSegment)을 생성합니다.
    팟캐스트 분위기(mood)에 맞는 스타일을 적용합니다.
    """
    audio_segments = []

    # 2. 현재 분위기에 맞는 스타일 프리셋을 가져옵니다.
    # style_params = get_speech_style_for_mood(mood)
    if voice_settings is None:
        # core.py에 이미 만들어둔 ElevenLabs용 매핑을 사용
        # 없으면 간단한 기본값으로 대체
        try:
            settings = get_voice_settings_for_mood(mood)
        except NameError:
            settings = {
                "stability": 0.6,
                "similarity_boost": 0.7,
                "style": 0.3,
                "use_speaker_boost": True,
            }
    else:
        settings = voice_settings

    if model_id is None:
        model_id = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")

    progress_bar = st.progress(0, text="음성 조각 생성 시작...")

    total = len(parsed_lines)
    for i, line in enumerate(parsed_lines):
        speaker = line["speaker"]
        cleaned_text = clean_text_for_tts(line["text"])
        progress_bar.progress(
            (i + 1) / max(total, 1),
            text=f"'{speaker}'의 대사 생성 중... ({i+1}/{total})",
        )

        if not cleaned_text:
            continue

        # ▼ CLOVA의 clova_speaker 대신 ElevenLabs voice_id 사용
        voice_id = voice_map.get(speaker)
        if not voice_id:
            # 화자 매핑이 없으면 첫 보이스로 폴백
            voice_id = next(iter(voice_map.values()))

        # 안정성 위해 1000자 단위 분할
        chunks = [cleaned_text[j : j + 1000] for j in range(0, len(cleaned_text), 1000)]

        for chunk in chunks:
            # ▼ CLOVA 호출 삭제: generate_clova_speech(...)  ❌
            # ▼ ElevenLabs 호출로 교체
            audio_bytes, err = generate_elevenlabs_speech(
                text=chunk,
                voice_id=voice_id,
                model_id=model_id,
                voice_settings=settings,
            )

            if err:
                st.error(f"'{speaker}' 음성 생성 오류: {err}")
                progress_bar.empty()
                return None

            seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
            audio_segments.append(seg)

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


def process_podcast_audio(audio_segments, bgm_file):
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
    final_podcast_io = io.BytesIO()
    final_podcast.export(final_podcast_io, format="mp3", bitrate="192k")
    final_podcast_io.seek(0)
    return final_podcast_io

    # 수정된 부분: AudioSegment 객체를 바로 반환
    # return final_podcast


def generate_elevenlabs_speech(
    text: str,
    voice_id: str | None = None,
    model_id: str | None = None,
    output_format: str = "mp3_44100_128",
    voice_settings: dict | None = None,
):
    """
    ElevenLabs Text-to-Speech.
    반환: (audio_bytes | None, error_message | None)
    """
    try:
        # .env 또는 Streamlit secrets에서 읽음
        api_key = (
            st.secrets.get("ELEVENLABS_API_KEY") if "st" in globals() else None
        ) or os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            return None, "ELEVENLABS_API_KEY가 설정되어 있지 않습니다."

        client = ElevenLabs(api_key=api_key)

        # 기본값: .env에 없으면 문서 예시값 사용
        voice_id = (
            voice_id or os.getenv("ELEVENLABS_VOICE_ID") or "JBFqnCBsd6RMkjVDRZzb"
        )
        model_id = (
            model_id or os.getenv("ELEVENLABS_MODEL_ID") or "eleven_multilingual_v2"
        )

        audio = client.text_to_speech.convert(
            text=text,
            voice_id=voice_id,
            model_id=model_id,
            output_format=output_format,
            voice_settings=voice_settings
            or {
                "stability": 0.6,
                "similarity_boost": 0.7,
                "style": 0.3,
                "use_speaker_boost": True,
            },
        )
        audio_bytes = (
            b"".join(audio)
            if hasattr(audio, "__iter__") and not isinstance(audio, (bytes, bytearray))
            else audio
        )
        return audio_bytes, None

        # SDK가 generator를 줄 수도 있어 안전하게 통합
        if hasattr(audio, "__iter__") and not isinstance(audio, (bytes, bytearray)):
            audio_bytes = b"".join(audio)
        else:
            audio_bytes = audio

        return audio_bytes, None
    except Exception as e:
        msg = str(e)
        # 🔽 슬롯 초과/보이스 미보유 시 폴백 보이스로 1회 재시도
        if (
            "voice_limit_reached" in msg or "voice_not_found" in msg
        ) and FALLBACK_VOICE_ID:
            try:
                audio = client.text_to_speech.convert(
                    text=text,
                    voice_id=FALLBACK_VOICE_ID,
                    model_id=model_id
                    or os.getenv("ELEVENLABS_MODEL_ID")
                    or "eleven_multilingual_v2",
                    output_format=output_format,
                    voice_settings=voice_settings
                    or {
                        "stability": 0.6,
                        "similarity_boost": 0.7,
                        "style": 0.3,
                        "use_speaker_boost": True,
                    },
                )
                audio_bytes = (
                    b"".join(audio)
                    if hasattr(audio, "__iter__")
                    and not isinstance(audio, (bytes, bytearray))
                    else audio
                )
                return audio_bytes, None
            except Exception as e2:
                return None, f"ElevenLabs 폴백 실패: {e2}"
        # 기본 에러 리턴
        return None, f"ElevenLabs API 요청 오류: {e}"


def generate_audio_segments_elevenlabs(
    parsed_lines,
    eleven_voice_map: dict | None = None,  # speaker -> voice_id 매핑
    model_id: str | None = None,
    voice_settings: dict | None = None,
):
    """
    파싱된 대본을 순회하며 ElevenLabs로 MP3 AudioSegment 리스트 생성.
    반환: [AudioSegment] | None
    """
    audio_segments = []
    progress_bar = (
        st.progress(0, "ElevenLabs 음성 생성 시작...") if "st" in globals() else None
    )

    for i, line in enumerate(parsed_lines):
        speaker = line.get("speaker", "Narrator")
        text = (line.get("text") or "").strip()
        if not text:
            continue

        # 긴 문장 안정화를 위해 1000자 단위로 분할
        chunks = [text[j : j + 1000] for j in range(0, len(text), 1000)]
        if progress_bar:
            progress_bar.progress(
                (i + 1) / max(1, len(parsed_lines)),
                text=f"'{speaker}' 생성 중... ({i+1}/{len(parsed_lines)})",
            )

        # 스피커별 voice_id 매핑(없으면 .env 기본 사용)
        voice_id = (eleven_voice_map or {}).get(speaker)

        for c in chunks:
            audio_bytes, err = generate_elevenlabs_speech(
                text=c,
                voice_id=voice_id,
                model_id=model_id,
                voice_settings=voice_settings,
            )
            if err:
                if progress_bar:
                    progress_bar.empty()
                (
                    st.error(f"'{speaker}' 음성 생성 오류: {err}")
                    if "st" in globals()
                    else None
                )
                return None
            seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
            audio_segments.append(seg)

    if progress_bar:
        progress_bar.empty()
    return audio_segments
