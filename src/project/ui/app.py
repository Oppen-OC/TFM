import requests
import streamlit as st

from project.config import settings

# La UI habla con la API por HTTP y nada más: no importa `services/` ni carga el
# modelo. Si Streamlit necesita un dato nuevo, se añade un endpoint.
API_URL = settings.api_url

st.title("TFM")

if st.button("Check API health"):
    try:
        response = requests.get(f"{API_URL}/health", timeout=5)
        st.json(response.json())
    except requests.ConnectionError:
        st.error(f"API no disponible en {API_URL}")
