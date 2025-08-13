import streamlit as st
from langchain_openai import ChatOpenAI
from langchain_core.messages.chat import ChatMessage
from dotenv import load_dotenv
from langchain_teddynote.prompts import load_prompt
import os

load_dotenv(dotenv_path=".env")

LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")

# title
st.title("🎤 AI 뉴스 팟캐스트 스튜디오")
st.markdown(
    "관심 있는 뉴스 기사를 검색하고, AI가 자동으로 대본을 작성하여 팟캐스트 음성까지 생성해 드립니다."
)

# 세션 상태 초기화
if "podcast_mood" not in st.session_state:
    st.session_state.podcast_mood = "차분한"  # 팟캐스트 분위기 기본값 설정
if "selected_category" not in st.session_state:
    st.session_state.selected_category = "전체"  # 뉴스 카테고리 기본값 설정
if "selected_language" not in st.session_state:  # 새로운 언어 선택 기본값 설정
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

generate_button = st.button(
    "✨ 팟캐스트 대본 생성 및 음성 만들기", use_container_width=True
)


# 이전 대화를 출력
def print_messages():
    """대화기록을 출력하는 함수"""
    for message in st.session_state["messages"]:
        st.chat_message(message.role).write(message.content)


# 새로운 메시지를 추가
def add_message(role, message):
    """대화기록을 추가하는 함수"""
    st.session_state["messages"].append(ChatMessage(role=role, content=message))

    # 체인 생성
    prompt = load_prompt("prompts/podcast.yaml", encoding="utf-8")

    # LLM 모델
    llm = ChatOpenAI(model_name="gpt-4o", temperature=0.0)

    # 출력 파서
    output_parser = StrOutputParser()

    # 체인 생성
    chain = prompt | llm | output_parser
    return chain
