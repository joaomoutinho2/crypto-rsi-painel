import firebase_admin
from firebase_admin import credentials, firestore
import os
import json

print("🧪 [firebase_config] Ficheiro importado.")

def iniciar_firebase(usando_secrets=False, secrets=None):
    print("🧪 [firebase_config] iniciar_firebase() chamado.")

    if not firebase_admin._apps:  # Verifica se o Firebase já foi inicializado
        try:
            if usando_secrets and secrets:
                print("🔐 A usar secrets.toml")
                firebase_dict = dict(secrets["firebase"])
                # Substituir "\\n" por "\n" na chave privada
                if "\\n" in firebase_dict["private_key"]:
                    firebase_dict["private_key"] = firebase_dict["private_key"].replace("\\n", "\n")
                cred = credentials.Certificate(firebase_dict)
            else:
                print("🔐 A usar FIREBASE_JSON do ambiente")
                firebase_json = os.environ.get("FIREBASE_JSON")
                if not firebase_json:
                    raise RuntimeError("FIREBASE_JSON não está definida!")

                print("🧪 JSON bruto obtido do ambiente.")
                firebase_dict = json.loads(firebase_json)

                # Substituir "\\n" por "\n" na chave privada
                if "\\n" in firebase_dict["private_key"]:
                    firebase_dict["private_key"] = firebase_dict["private_key"].replace("\\n", "\n")

                print("🧪 JSON carregado com sucesso.")
                cred = credentials.Certificate(firebase_dict)

            # Inicializar o Firebase
            firebase_admin.initialize_app(cred)
            print("✅ Firebase inicializado com sucesso.")

        except Exception as e:
            print(f"❌ Erro ao inicializar o Firebase: {e}")
            import traceback
            traceback.print_exc()
            raise

    return firestore.client()
