# .streamlit/secrets.toml
# ⚠️ NO subas este archivo a GitHub. Agrega .streamlit/secrets.toml a tu .gitignore
# Estos valores los configurás directamente en Streamlit Cloud (Settings → Secrets)

# ID del archivo Excel en Google Drive
# (está en la URL cuando abrís el archivo: drive.google.com/file/d/ESTE_ES_EL_ID/view)
EXCEL_FILE_ID = "TU_FILE_ID_AQUI"

# Credenciales del Service Account de Google
# Pegá aquí el contenido completo del archivo JSON que descargaste de Google Cloud
GOOGLE_CREDENTIALS = '''
{
  "type": "service_account",
  "project_id": "tu-proyecto",
  "private_key_id": "...",
  "private_key": "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n",
  "client_email": "rio-veggi-app@tu-proyecto.iam.gserviceaccount.com",
  "client_id": "...",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token"
}
'''
