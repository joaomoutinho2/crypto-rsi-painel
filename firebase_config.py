import firebase_admin
from firebase_admin import credentials, firestore
import os
import json

def iniciar_firebase(usando_secrets=False, secrets=None):
    if not firebase_admin._apps:
        if usando_secrets and secrets:
            # 🔐 Modo Streamlit (secrets.toml)
            firebase_dict = dict(secrets["firebase"])
            if "\\n" in firebase_dict["private_key"]:
                firebase_dict["private_key"] = firebase_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(firebase_dict)
        else:
            # 🔐 Modo Render (usando FIREBASE_JSON no ambiente)
            firebase_json = os.environ.get("FIREBASE_JSON")
            if not firebase_json:
                raise RuntimeError("⚠️ FIREBASE_JSON não está definida no ambiente!")
            firebase_dict = json.loads(firebase_json)
            if "\\n" in firebase_dict["private_key"]:
                firebase_dict["private_key"] = firebase_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(firebase_dict)

        firebase_admin.initialize_app(cred)

    return firestore.client()
