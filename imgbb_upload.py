import requests
import base64
import secrets

def upload_image_imgbb(file_storage):
    """
    Sobe a imagem FileStorage (do Flask) para o imgbb e retorna a URL direta.
    """
    IMGBB_API_KEY = "6ac382cc95c4e42f2f42847421c6c496"
    random_name = secrets.token_hex(16)
    ext = file_storage.filename.rsplit('.', 1)[-1].lower()
    filename = f"{random_name}.{ext}"
    img_bytes = file_storage.read()
    encoded_image = base64.b64encode(img_bytes)
    url = "https://api.imgbb.com/1/upload"
    payload = {
        "key": IMGBB_API_KEY,
        "image": encoded_image,
        "name": filename
    }
    response = requests.post(url, data=payload)
    if response.status_code == 200:
        data = response.json()
        return data["data"]["url"]
    else:
        raise Exception(f"Erro ao enviar imagem para imgbb: {response.text}")
