import re

import streamlit as st


st.set_page_config(
    page_title="OncoNote Explorer",
    page_icon="🩺",
    layout="wide",
)

st.title("🩺 OncoNote Explorer")
st.write("Onkoloji notlarını incelemek ve not içinden soru sormak için başlangıç ekranı.")

st.info("Şimdilik örnek veya anonimleştirilmiş metin kullan.")


def find_relevant_sentences(note: str, question: str) -> list[str]:
    """Sorudaki kelimelerle eşleşen not cümlelerini bulur."""
    sentences = re.split(r"(?<=[.!?])\s+", note.strip())
    question_words = {
        word.lower()
        for word in re.findall(r"\w+", question)
        if len(word) > 2
    }

    scored_sentences = []

    for sentence in sentences:
        sentence_words = {
            word.lower()
            for word in re.findall(r"\w+", sentence)
        }
        score = len(question_words & sentence_words)

        if score > 0:
            scored_sentences.append((score, sentence))

    scored_sentences.sort(key=lambda item: item[0], reverse=True)
    return [sentence for _, sentence in scored_sentences[:3]]


left, right = st.columns([1, 1])

with left:
    st.subheader("Notu ekle")

    uploaded_file = st.file_uploader(
        "Bir .txt dosyası yükle",
        type=["txt"],
    )

    uploaded_text = ""
    if uploaded_file is not None:
        uploaded_text = uploaded_file.getvalue().decode(
            "utf-8",
            errors="replace",
        )

    note_text = st.text_area(
        "Ya da notu buraya yapıştır",
        value=uploaded_text,
        height=300,
        placeholder="Not metnini buraya ekle...",
    )

with right:
    st.subheader("Not özeti")

    if note_text.strip():
        words = re.findall(r"\b\w+\b", note_text)
        paragraphs = [
            part for part in note_text.splitlines()
            if part.strip()
        ]

        metric1, metric2 = st.columns(2)
        metric1.metric("Kelime sayısı", len(words))
        metric2.metric("Metin bölümü", len(paragraphs))

        st.write("**İlk bölüm:**")
        st.write(paragraphs[0] if paragraphs else "Metin bulunamadı.")
    else:
        st.write("Özet panelini görmek için önce bir not ekle.")

st.divider()
st.subheader("Not hakkında soru sor")

question = st.text_input(
    "Sorun",
    placeholder="Örnek: Hangi ilaçtan bahsediliyor?",
)

if st.button("Notta ara"):
    if not note_text.strip():
        st.warning("Önce bir not ekle.")
    elif not question.strip():
        st.warning("Önce bir soru yaz.")
    else:
        matches = find_relevant_sentences(note_text, question)

        if matches:
            st.write("Notta soruyla eşleşen cümleler:")
            for sentence in matches:
                st.write(f"- {sentence}")
        else:
            st.write("Sorudaki kelimelerle eşleşen bir cümle bulamadım.")
