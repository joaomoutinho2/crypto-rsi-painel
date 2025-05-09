import firebase_admin
from firebase_admin import credentials, firestore
import os, json

def iniciar_firebase(usando_secrets=False, secrets=None):
    if not firebase_admin._apps:
        if usando_secrets and secrets:
            firebase_dict = dict(secrets["firebase"])
            if "\\n" in firebase_dict["private_key"]:
                firebase_dict["private_key"] = firebase_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(firebase_dict)
        else:
            firebase_json = os.environ["FIREBASE_JSON"]  # ← VEM DA ENV DO RENDER
            firebase_dict = json.loads(firebase_json)
            if "\\n" in firebase_dict["private_key"]:
                firebase_dict["private_key"] = firebase_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(firebase_dict)

        firebase_admin.initialize_app(cred)

    return firestore.client()
