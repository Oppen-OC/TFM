import os

import requests
import streamlit as st

API_URL = f"http://{os.getenv('API_HOST', '127.0.0.1')}:{os.getenv('API_PORT', '8000')}"

st.title("TFM")

if st.button("Check API health"):
    try:
        response = requests.get(f"{API_URL}/health", timeout=5)
        st.json(response.json())
    except requests.ConnectionError:
        st.error(f"API no disponible en {API_URL}")
