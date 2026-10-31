import asyncio, json, os, re
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from ..config import GIGACHAT_API_KEY, GIGACHAT_MODEL, GIGACHAT_BASE_URL, GIGACHAT_SCOPE, GIGACHAT_VERIFY_SSL_CERTS

_sem = asyncio.Semaphore(int(os.getenv('MAX_CONCURRENT_LLM_CALLS', '5')))
PROMPT = '''Ты извлекаешь данные из постановлений ФССП. Верни только валидный JSON-массив объектов, по одной записи на каждый автомобиль. Учитывай все постановления в документе. Поля: doc_type (строго ban или removal), debtor_name, inn, debt_amount (число в рублях или null), vin, make, model, year, plate, doc_number, doc_date, vzyskatel, ip_id, confidence (0..1). Не используй контрольные примеры/оценки из нижней части документа. Не додумывай значения: неизвестное — null. Кириллические буквы в VIN транслитерируй в латиницу, если это однозначно.'''

def _parse_response(text):
 text=text.strip()
 text=re.sub(r'^```(?:json)?\s*|\s*```$', '', text, flags=re.I)
 data=json.loads(text)
 if isinstance(data,dict): data=data.get('cars', data.get('items', [data]))
 if not isinstance(data,list): raise ValueError('GigaChat returned a non-array result')
 result=[]
 for row in data:
  if not isinstance(row,dict): continue
  row['doc_type']='removal' if str(row.get('doc_type','')).lower()=='removal' else 'ban'
  row['confidence']=max(0,min(1,float(row.get('confidence') or .5)))
  result.append(row)
 return result

async def extract(text, filename):
 if not GIGACHAT_API_KEY: raise RuntimeError('GIGACHAT_API_KEY is not configured')
 if not text.strip(): raise RuntimeError(f'No readable text in {filename}')
 async with _sem:
  def call():
   with GigaChat(base_url=GIGACHAT_BASE_URL, credentials=GIGACHAT_API_KEY, scope=GIGACHAT_SCOPE, model=GIGACHAT_MODEL, verify_ssl_certs=GIGACHAT_VERIFY_SSL_CERTS, timeout=30) as client:
    chat=Chat(messages=[Messages(role=MessagesRole.SYSTEM,content=PROMPT),Messages(role=MessagesRole.USER,content=text[:45000])],temperature=0.1)
    response=client.chat(chat)
    return _parse_response(response.choices[0].message.content)
  return await asyncio.wait_for(asyncio.to_thread(call), timeout=35)
