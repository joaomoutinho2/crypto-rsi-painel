import firebase_admin
from firebase_admin import credentials, firestore
import os
import json

print("🧪 [firebase_config] Ficheiro importado.")

def iniciar_firebase(usando_secrets=False, secrets=None):
    print("🧪 [firebase_config] iniciar_firebase() chamado.")

    if not firebase_admin._apps:
        try:
            if usando_secrets and secrets:
                print("🔐 A usar secrets.toml")
                firebase_dict = dict(secrets["firebase"])
                if "\\n" in firebase_dict["private_key"]:
                    firebase_dict["private_key"] = firebase_dict["private_key"].replace("\\n", "\n")
                cred = credentials.Certificate(firebase_dict)
            else:
                print("🔐 A tentar usar FIREBASE_JSON do ambiente...")
                firebase_json = os.environ.get("FIREBASE_JSON")

                if firebase_json:
                    print("🧪 JSON bruto obtido do ambiente.")
                    firebase_dict = json.loads(firebase_json)

                    if "\\n" in firebase_dict["private_key"]:
                        firebase_dict["private_key"] = firebase_dict["private_key"].replace("\\n", "\n")

                    print("🧪 JSON carregado com sucesso.")
                    cred = credentials.Certificate(firebase_dict)
                else:
                    print("📁 A usar firebase_key.json local")
                    with open("firebase_key.json") as f:
                        firebase_dict = json.load(f)
                    cred = credentials.Certificate(firebase_dict)

            firebase_admin.initialize_app(cred)
            print("✅ Firebase inicializado.")

        except Exception as e:
            print(f"❌ Erro ao inicializar o Firebase: {e}")
            import traceback
            traceback.print_exc()
            raise

    return firestore.client()
