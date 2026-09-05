import streamlit as st
from google import genai
import datetime
from PIL import Image

st.set_page_config(page_title="Black Jack - Sécurisé", page_icon="🤖")

client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])

# Initialisation des états
if "connecte" not in st.session_state:
    st.session_state.connecte = False

if "messages" not in st.session_state:
    st.session_state.messages = []

# --- ÉCRAN D'ACCUEIL AVEC MOT DE PASSE ---
if not st.session_state.connecte:
    st.title("🔒 Accès Restreint - Black Jack")
    st.write("Entre l'une des clés d'accès autorisées pour lancer ton tuteur personnel.")

    # Liste de tes 3 clés secrètes (tu peux les changer ici !)
    cles_valides = ["2026", "2025", "2027"]

    # Utilisation d'un champ de texte masqué pour le mot de passe
    code_entre = st.text_input("Entre ta clé d'accès :", type="password")

    if st.button("Valider la clé 🚀"):
        # On vérifie si le code entré fait partie de tes clés valides
        if code_entre in cles_valides:
            st.session_state.connecte = True
            st.success("Accès autorisé ! Bienvenue.")
            st.rerun()
        else:
            st.error("❌ Clé incorrecte. Demande la bonne clé ou réessaie.")

# --- ÉCRAN DU CHAT (Une fois connecté avec la bonne clé) ---
else:
    st.title("🤖 Black Jack - Ton Tuteur Scolaire")
    st.write("Pose tes questions ou envoie une photo de ton exercice.")

    # Bouton pour se déconnecter et retourner à l'accueil sécurisé
    if st.sidebar.button("🔒 Verrouiller / Accueil"):
        st.session_state.connecte = False
        st.rerun()

    uploaded_file = st.sidebar.file_uploader("Ajouter une photo d'exercice", type=["jpg", "jpeg", "png"])

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Discuter avec Black Jack..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
            if uploaded_file:
                st.image(uploaded_file, width=300)

        with st.chat_message("assistant"):
            try:
                maintenant = datetime.datetime.now().strftime("%d/%m/%Y à %H:%M")
                
                system_instruction = (
                    f"Tu t'appelles Black Jack, une IA personnelle ultra-sympathique, "
                    f"un peu comme un grand frère ou un pote calé pour l'école. "
                    f"Nous sommes exactement le {maintenant}. "
                    "Tu es un tuteur scolaire multidisciplinaire expert : français, "
                    "mathématiques, anglais, espagnol, histoire-géo. "
                    "Ton ton est naturel, chaleureux, encourageant et direct."
                )

                contents = []
                if uploaded_file:
                    image = Image.open(uploaded_file)
                    contents.append(image)

                full_prompt = f"{system_instruction}\n\nQuestion de l'utilisateur : {prompt}"
                contents.append(full_prompt)

                response = client.models.generate_content(
                    model='gemini-3.6-flash',
                    contents=contents,
                )
                st.markdown(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
            except Exception as e:
                st.error(f"Erreur : {e}")