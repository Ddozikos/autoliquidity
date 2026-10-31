import os
from dotenv import load_dotenv
load_dotenv()
DATABASE_URL=os.getenv('DATABASE_URL','sqlite:///./data/app.db')
GIGACHAT_API_KEY=os.getenv('GIGACHAT_API_KEY','')
GIGACHAT_MODEL=os.getenv('GIGACHAT_MODEL','GigaChat-3-Ultra')
GIGACHAT_BASE_URL=os.getenv('GIGACHAT_BASE_URL','https://api.giga.chat/v1')
GIGACHAT_SCOPE=os.getenv('GIGACHAT_SCOPE','GIGACHAT_API_PERS')
GIGACHAT_VERIFY_SSL_CERTS=os.getenv('GIGACHAT_VERIFY_SSL_CERTS','false').lower()=='true'
