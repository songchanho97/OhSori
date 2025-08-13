import streamlit as st
from langchain_openai import ChatOpenAI
from langchain_core.messages.chat import ChatMessage
from dotenv import load_dotenv
from langchain_teddynote.prompts import load_prompt
import os
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
import json


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
        # LLM 클라이언트 한 번만 정의
        llm = ChatOpenAI(model_name="gpt-4o", temperature=0.7)
        output_parser = StrOutputParser()

        try:
            # =================================================================
            # STEP 1: Host-Agent가 게스트 프로필과 인터뷰 개요 생성
            # =================================================================
            with st.spinner(
                "1/3단계: Host-Agent가 게스트를 섭외하고 질문지를 작성 중입니다... 섭외 전문가: 2명"
            ):
                host_prompt_template = """
                당신은 "{topic}" 주제를 다루는 팟캐스트 쇼의 유능한 PD입니다. 이 주제에 대해 깊이 있는 대화를 나눌 가상의 게스트 2명을 섭외하고, 인터뷰 질문 4개로 구성된 인터뷰 개요를 작성해주세요.

                # 출력 형식 (반드시 JSON 형식으로 응답해주세요):
                {{
                    "guests": [
                        {{"name": "게스트1 이름", "description": "게스트1의 직업 및 전문 분야에 대한 상세 설명"}},
                        {{"name": "게스트2 이름", "description": "게스트2의 직업 및 전문 분야에 대한 상세 설명"}}
                    ],
                    "interview_outline": [
                        "첫 번째 질문",
                        "두 번째 질문",
                        "세 번째 질문",
                        "네 번째 질문"
                    ]
                }}
                """
                host_chain = (
                    ChatPromptTemplate.from_template(host_prompt_template)
                    | llm
                    | JsonOutputParser()
                )
                host_response = host_chain.invoke({"topic": query})
                # host_response = json.loads(host_response_str)

                guests = host_response["guests"]
                interview_outline = host_response["interview_outline"]

                st.session_state.guests = guests

            # =================================================================
            # STEP 2: 각 Guest-Agent가 인터뷰 개요에 대해 답변 생성 (병렬 처리)
            # =================================================================
            with st.spinner(
                "2/3단계: Guest-Agents가 각자의 전문 분야에 맞춰 답변을 준비 중입니다..."
            ):
                guest_answers = []
                guest_prompt_template = """
                당신은 {guest_description}인 "{guest_name}"입니다.
                팟캐스트 주제인 "{topic}"에 대해 아래의 인터뷰 질문들에 답변해주세요.
                당신의 전문성과 역할에 깊이 몰입하여, 심도 있고 독창적인 관점의 답변을 작성해주세요.

                # 인터뷰 질문:
                {questions}

                # 출력:
                각 질문에 대한 답변을 명확하게 작성해주세요.
                """
                guest_chain = (
                    ChatPromptTemplate.from_template(guest_prompt_template)
                    | llm
                    | output_parser
                )

                for guest in guests:
                    # 논문에 따르면 각 게스트는 병렬적으로 답변을 생성합니다.
                    answer = guest_chain.invoke(
                        {
                            "guest_name": guest["name"],
                            "guest_description": guest["description"],
                            "topic": query,
                            "questions": "\\n- ".join(interview_outline),
                        }
                    )
                    guest_answers.append({"name": guest["name"], "answer": answer})

            # =================================================================
            # STEP 3: Writer-Agent가 모든 정보를 종합하여 최종 대본 작성
            # =================================================================
            with st.spinner(
                "3/3단계: Writer-Agent가 수집된 답변들을 맛깔나는 대화 대본으로 다듬고 있습니다..."
            ):
                writer_prompt_template = """
                당신은 전문 팟캐스트 대본 작가입니다. 다음 정보를 바탕으로, 진행자와 게스트들이 자연스럽게 대화하는 최종 팟캐스트 대본을 작성해주세요.

                - 팟캐스트 주제: {topic}
                - 팟캐스트 분위기: {mood}
                - 언어: {language}

                - 진행자: Alex (호기심 많고 유쾌한 진행자)
                - 게스트 정보: {guests_info}

                - 게스트들이 제출한 답변 원본:
                {guest_raw_answers}

                # 지침:
                - 게스트들이 제출한 답변 원본의 핵심 내용을 바탕으로, 서로 의견을 주고받는 자연스러운 대화 형식으로 재구성해주세요.
                - 오프닝, 각 질문에 대한 대화, 클로징 멘트를 포함하여 완결성 있는 구조로 작성해주세요.
                - 딱딱한 질의응답이 아닌, 실제 사람들이 나누는 대화처럼 생동감 있게 만들어주세요.
                - {mood} 분위기를 전체 대본에 잘 녹여내 주세요.
                - 최종 대본은 반드시 {language}로 작성해주세요.
                """
                writer_chain = (
                    ChatPromptTemplate.from_template(writer_prompt_template)
                    | llm
                    | output_parser
                )

                final_script = writer_chain.invoke(
                    {
                        "topic": query,
                        "mood": st.session_state.podcast_mood,
                        "language": st.session_state.selected_language,
                        "guests_info": json.dumps(guests, ensure_ascii=False),
                        "guest_raw_answers": "\\n\\n".join(
                            [
                                f"--- {ga['name']}님의 답변 ---\\n{ga['answer']}"
                                for ga in guest_answers
                            ]
                        ),
                    }
                )
                st.session_state.script = final_script

        except Exception as e:
            st.error(f"대본 생성 중 오류가 발생했습니다: {e}")


# --- 6. 생성된 팟캐스트 대본 출력 ---
if st.session_state.script:
    st.write("")
    st.subheader("🎉 생성된 팟캐스트 대본")
    st.markdown(st.session_state.script)

    # 멘토의 조언: 대본이 생성된 후에야 음성 생성 버튼이 보이도록 하면 더 좋습니다.
    st.subheader("🎧 팟캐스트 음성 생성 (TTS)")
    if st.button("🎵 이 대본으로 음성 생성하기"):
        # TODO: 여기에 Text-to-Speech(TTS) 로직을 추가합니다.
        # 예를 들어 OpenAI의 TTS API나 gTTS 라이브러리를 사용할 수 있습니다.
        with st.spinner("음성을 생성하는 중입니다..."):
            # gTTS 예시 (프로토타입용)
            # from gtts import gTTS
            # import io
            # tts = gTTS(text=st.session_state.script, lang=st.session_state.selected_language[:2].lower())
            # fp = io.BytesIO()
            # tts.write_to_fp(fp)
            # st.audio(fp, format="audio/mp3")
            st.success("음성 생성이 완료되었습니다!")
            st.info(
                "음성 생성 기능은 여기에 연결될 예정입니다. 지금은 대본 생성까지 완성되었습니다!"
            )
