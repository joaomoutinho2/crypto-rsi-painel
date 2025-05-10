import firebase_admin
from firebase_admin import credentials, firestore
import os
import json

def iniciar_firebase(usando_secrets=False, secrets=None):
    # Verifica se o Firebase já foi inicializado
    if not firebase_admin._apps:
        if usando_secrets and secrets:
            # 🔐 Modo Streamlit (secrets.toml)
            firebase_dict = dict(secrets["firebase"])
            if "\\n" in firebase_dict["private_key"]:
                firebase_dict["private_key"] = firebase_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(firebase_dict)
        else:
            # 🔐 Modo Render (usando variável de ambiente FIREBASE_JSON)
            firebase_json = os.environ["FIREBASE_JSON"]
            firebase_dict = json.loads(firebase_json)
            if "\\n" in firebase_dict["private_key"]:
                firebase_dict["private_key"] = firebase_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(firebase_dict)

        # Inicializa a app Firebase
        firebase_admin.initialize_app(cred)

    # Retorna o cliente Firestore
    return firestore.client()
