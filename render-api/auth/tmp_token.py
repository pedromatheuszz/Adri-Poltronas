# tmp_token.py
# tmp_token.py  –  dentro de render-api\auth
from .jwt import generate_token          # <-- import relativo

if __name__ == "__main__":
    print(generate_token("adri-render-admin", role="admin", expires_minutes=15))
