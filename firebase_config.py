import firebase_admin
from firebase_admin import credentials, firestore
import os

def iniciar_firebase(usando_secrets=False, secrets=None):
    if not firebase_admin._apps:
        if usando_secrets and secrets:
            firebase_dict = dict(secrets["firebase"])
            if "\\n" in firebase_dict["private_key"]:
                firebase_dict["private_key"] = firebase_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(firebase_dict)
        else:
            cred = credentials.Certificate("firebase_key.json")

        firebase_admin.initialize_app(cred)

    return firestore.client()
