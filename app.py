import streamlit as st
from langchain_openai import ChatOpenAI
from langchain_core.messages.chat import ChatMessage
from dotenv import load_dotenv
from langchain_teddynote.prompts import load_prompt
import os
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

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
    # 🚨 여기서부터 들여쓰기 시작! (Tab 또는 스페이스 4칸)
    if not query:
        st.error("뉴스 검색 키워드를 입력해주세요!")
    else:
        with st.spinner(
            "AI가 열심히 팟캐스트 대본을 작성하고 있습니다... 잠시만 기다려주세요! 🤖"
        ):
            try:
                prompt = load_prompt("prompts/podcast.yaml", encoding="utf-8")

                llm = ChatOpenAI(model_name="gpt-4o", temperature=0.7)
                output_parser = StrOutputParser()
                chain = prompt | llm | output_parser

                st.session_state.script = chain.invoke(
                    {
                        "category": st.session_state.selected_category,
                        "query": query,
                        "mood": st.session_state.podcast_mood,
                        "language": st.session_state.selected_language,
                    }
                )

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
