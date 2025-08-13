import os
import json
import requests
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import load_prompt


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
    client_id = os.getenv("NCP_CLIENT_ID")
    client_secret = os.getenv("NCP_CLIENT_SECRET")
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
