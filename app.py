import streamlit as st
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from langchain_teddynote.prompts import load_prompt


load_dotenv(dotenv_path=".env")
