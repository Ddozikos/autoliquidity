from fastapi import FastAPI,UploadFile,File,Form,HTTPException,Header
from fastapi.responses import FileResponse,StreamingResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from datetime import datetime,timezone
import tempfile,os,asyncio,io,re,unicodedata,logging,json
from .database import Base,engine,SessionLocal
from .models import User,Report,Car
from .schemas import LoginIn,RenameIn,MarketSearchIn
from bs4 import BeautifulSoup
from .services.ocr import extract_pdf_with_ocr
from .services.llm import extract
from .services.html_parser import parse_html
from .services.price import PriceService
from .services.vin import VinService
from .services.filtering import prioritize

Path('data').mkdir(exist_ok=True); Base.metadata.create_all(bind=engine)
# Additive migration for existing local SQLite databases.
from sqlalchemy import inspect
if engine.dialect.name=='sqlite':
 existing={col['name'] for col in inspect(engine).get_columns('cars')}
 migrations={
  'market_sources':"TEXT DEFAULT '[]'",'market_error':"TEXT DEFAULT ''",
  'market_status':"TEXT DEFAULT 'not_configured'",'market_checked_at':'TEXT',
  'demand_sources':"TEXT DEFAULT '[]'",'vin_source':'TEXT',
  'vin_checked_at':'TEXT','vin_error':"TEXT DEFAULT ''",
 }
 with engine.begin() as conn:
  for name,definition in migrations.items():
   if name not in existing:conn.exec_driver_sql(f'ALTER TABLE cars ADD COLUMN {name} {definition}')
app=FastAPI(title='АвтоЛиквидность ФССП',version='0.1.0')
app.mount('/static',StaticFiles(directory='app/static' if Path('app/static').exists() else 'static'),name='static')
logger=logging.getLogger(__name__)
MAX_UPLOAD_BYTES=25*1024*1024
FILE_WORKERS=max(1,int(os.getenv('MAX_CONCURRENT_FILES','5')))
processing_queue:asyncio.Queue=asyncio.Queue()
_queue_worker_task=None
def user_from(token,db):
 try: uid=int(token.removeprefix('Bearer ').split(':')[0])
 except: raise HTTPException(401,'Требуется вход')
 u=db.get(User,uid)
 if not u:raise HTTPException(401,'Требуется вход')
 return u
def timestamp_iso(value):
 # SQLite drops tzinfo for DateTime columns; persisted values are written in UTC.
 if value.tzinfo is None:value=value.replace(tzinfo=timezone.utc)
 return value.isoformat()
@app.get('/api/health')
def health(): return {'ok':True}
@app.get('/')
def home():return FileResponse('static/index.html')
@app.on_event('startup')
async def start_processing_worker():
 global _queue_worker_task
 _queue_worker_task=asyncio.create_task(_processing_worker())
@app.on_event('shutdown')
async def stop_processing_worker():
 global _queue_worker_task
 if _queue_worker_task:
  _queue_worker_task.cancel()
  try:await _queue_worker_task
  except asyncio.CancelledError:pass
  _queue_worker_task=None
 while not processing_queue.empty():
  try:rid,files=processing_queue.get_nowait()
  except asyncio.QueueEmpty:break
  for path,_,_ in files:
   try:os.unlink(path)
   except OSError:pass
  db=SessionLocal()
  try:
   report=db.get(Report,rid)
   if report and report.status=='processing':report.status='failed';report.error_text='Сервер остановлен до обработки пакета';db.commit()
  finally:db.close()
  processing_queue.task_done()
@app.post('/api/login')
def login(data:LoginIn):
 db=SessionLocal()
 try:
  u=db.query(User).filter_by(email=data.email).first()
  if not u:u=User(email=data.email,name=data.email.split('@')[0]);db.add(u);db.commit();db.refresh(u)
  return {'access_token':f'{u.id}:mock','user':{'id':u.id,'email':u.email,'name':u.name}}
 finally:db.close()
@app.get('/api/me')
def me(authorization:str=Header(...)):
 db=SessionLocal()
 try:u=user_from(authorization,db);return {'id':u.id,'email':u.email,'name':u.name}
 finally:db.close()
@app.post('/api/market/search')
def market_search(data:MarketSearchIn,authorization:str=Header(...)):
 db=SessionLocal()
 try:user_from(authorization,db)
 finally:db.close()
 result=PriceService().lookup(data.make.strip(),data.model.strip(),str(data.year) if data.year else None,None)
 configured=result.get('configured_sources',[])
 status=result.get('status','not_configured')
 messages={'not_configured':'Источники объявлений не подключены. Настройте разрешённый API в .env.','not_applicable':'Поиск не применим к этому запросу.','no_results':'Подключённые источники не вернули объявления для этого автомобиля.','error':'Не удалось получить данные ни от одного источника.','partial':'Получены предложения не от всех источников.','found':'Найдены объявления. Средняя цена рассчитана по полученным предложениям.'}
 message=messages.get(status,'Статус источников неизвестен.')
 def slug(value):
  chars='абвгдеёжзийклмнопрстуфхцчшщъыьэюя'
  sounds=['a','b','v','g','d','e','yo','zh','z','i','y','k','l','m','n','o','p','r','s','t','u','f','kh','ts','ch','sh','shch','','y','','e','yu','ya']
  translit=dict(zip(chars,sounds))
  value=''.join(translit.get(char,char) for char in value.strip().lower())
  return re.sub(r'[^a-z0-9]+','-',value).strip('-')
 search_url=f'https://auto.drom.ru/{slug(data.make)}/{slug(data.model)}/'+(f'year-{data.year}/' if data.year else '')
 return {'status':status,'message':message,'checked_at':result.get('checked_at'),'demand':result.get('demand'),'demand_sources':result.get('demand_sources',[]),'vehicle':{'make':data.make,'model':data.model,'year':data.year},'average_price':result.get('price'),'representative_link':result.get('link'),'offers':result.get('sources',[]),'searched_sources':configured,'source_errors':result.get('errors',[]),'drom_search_url':search_url}
@app.post('/api/process')
async def process(files:list[UploadFile]=File(...),min_price:int=Form(300000),min_demand:int=Form(70),authorization:str=Header(...)):
 if not files or len(files)>50:raise HTTPException(400,'Загрузите от 1 до 50 файлов')
 for f in files:
  if Path(f.filename).suffix.lower() not in ('.pdf','.html','.htm'):raise HTTPException(400,f'Неподдерживаемый формат: {f.filename}')
 saved=[]
 try:
  db=SessionLocal()
  try:u=user_from(authorization,db)
  finally:db.close()
  for f in files:
   ext=Path(f.filename).suffix.lower()
   if f.size is not None and f.size>MAX_UPLOAD_BYTES:raise HTTPException(413,f'Файл больше 25 МБ: {f.filename}')
   tmp=tempfile.NamedTemporaryFile(delete=False,suffix=ext);size=0
   try:
    while chunk:=await f.read(1024*1024):
     size+=len(chunk)
     if size>MAX_UPLOAD_BYTES:raise HTTPException(413,f'Файл больше 25 МБ: {f.filename}')
     tmp.write(chunk)
   except Exception:
    tmp.close()
    try:os.unlink(tmp.name)
    except OSError:pass
    raise
   else:tmp.close()
   saved.append((tmp.name,f.filename,ext))
  db=SessionLocal()
  try:
   report=Report(user_id=u.id,name=f'Пакет {datetime.now().strftime("%d.%m.%Y %H:%M")}',min_price=min_price,min_demand=min_demand,status='processing')
   db.add(report);db.commit();rid=report.id
  finally:db.close()
  await processing_queue.put((rid,saved))
  return {'report_id':rid,'queue_position':processing_queue.qsize()}
 except HTTPException:
  for path,_,_ in saved:
   try:os.unlink(path)
   except OSError:pass
  raise
 except Exception as exc:
  for path,_,_ in saved:
   try:os.unlink(path)
   except OSError:pass
  logger.warning('Could not enqueue upload: %s',type(exc).__name__)
  raise HTTPException(500,'Не удалось поставить пакет в очередь') from exc
async def _processing_worker():
 while True:
  rid,files=await processing_queue.get()
  try:await process_batch(rid,files)
  except Exception as exc:
   logger.error('Report %s worker failed: %s',rid,type(exc).__name__)
   db=SessionLocal()
   try:
    report=db.get(Report,rid)
    if report:report.status='failed';report.error_text='Внутренняя ошибка фоновой обработки';db.commit()
   finally:db.close()
  finally:processing_queue.task_done()

async def _extract_file(path,name,ext):
 ocr_confidence=None
 if ext in ('.html','.htm'):
  raw=await asyncio.to_thread(Path(path).read_bytes)
  items=await asyncio.to_thread(parse_html,raw)
  if items:return items,None
  soup=BeautifulSoup(raw,'lxml')
  for node in soup(['script','style']):node.decompose()
  text=soup.get_text(' ',strip=True)
  if not text.strip():raise RuntimeError('В HTML не найден текст постановления')
 else:
  text,ocr_confidence=await asyncio.to_thread(extract_pdf_with_ocr,path)
 if not text.strip():raise RuntimeError('Не удалось извлечь текст из PDF')
 items=await extract(text,name)
 if ocr_confidence is not None and ocr_confidence<.7:
  for item in items:item['confidence']=.5
 if not items:raise RuntimeError('В документе не найдены записи об автомобилях')
 return items,ocr_confidence

async def _enrich_item(item,name,rid,market_slots):
 typ=item.get('doc_type') or 'ban';make=item.get('make');model=item.get('model');vin=item.get('vin')
 market={'status':'not_applicable' if typ!='ban' or not (make or model) else 'not_configured','checked_at':None,'price':None,'demand':None,'demand_sources':[],'link':None,'sources':[],'errors':[]}
 status='Не проверен'
 vin_source=None;vin_checked_at=None;vin_error='';provider_errors=[]
 async with market_slots:
  if typ=='ban' and (make or model):
   try:market=await asyncio.to_thread(PriceService().lookup,make,model,item.get('year'),vin)
   except Exception as exc:market.update(status='error',errors=[{'source':'market','error':type(exc).__name__}])
  provider_errors.extend(f"{error.get('source','Источник')}: {error.get('error','ошибка')}" for error in market.get('errors',[]))
  if vin:
   try:
    vin_result=await asyncio.to_thread(VinService().enrich,vin)
    status=vin_result.get('status','Не проверен');vin_source=vin_result.get('source');vin_checked_at=vin_result.get('checked_at')
   except Exception as exc:
    logger.warning('VIN lookup failed for report %s (%s)',rid,type(exc).__name__)
    status='Ошибка проверки'
    vin_error=type(exc).__name__;provider_errors.append(f'VIN: {vin_error}')
 debt=item.get('debt_amount')
 try:
  if isinstance(debt,str):
   debt=re.sub(r'[^\d,.\-]','',debt).replace(',','.')
   if debt.count('.')>1:debt=debt.replace('.','',debt.count('.')-1)
  debt=float(debt) if debt is not None else None
 except (TypeError,ValueError):debt=None
 # Demand is a provider metric. Do not infer it from asking-price bands.
 demand=market.get('demand')
 try:confidence=max(0.0,min(1.0,float(item.get('confidence') or .5)))
 except (TypeError,ValueError):confidence=.5
 return Car(report_id=rid,source_doc=name,doc_number=item.get('doc_number'),doc_date=item.get('doc_date'),doc_type=typ,debtor_name=item.get('debtor_name') or 'Неизвестный должник',inn=item.get('inn'),debt_amount=debt if debt is not None else 0,vin=vin,make=make,model=model,year=str(item['year']) if item.get('year') is not None else None,plate=item.get('plate'),price=market.get('price'),demand=demand,status=status,vin_source=vin_source,vin_checked_at=vin_checked_at,vin_error=vin_error,market_status=market.get('status','not_configured'),market_checked_at=market.get('checked_at'),demand_sources=json.dumps(market.get('demand_sources',[]),ensure_ascii=False),link=market.get('link'),motivation_index=round(market['price']/debt,2) if market.get('price') and debt else None,vzyskatel=item.get('vzyskatel'),ip_id=item.get('ip_id'),confidence=confidence,market_sources=json.dumps(market.get('sources',[]),ensure_ascii=False),market_error='; '.join(provider_errors))

async def process_batch(rid,files):
 file_slots=asyncio.Semaphore(FILE_WORKERS);market_slots=asyncio.Semaphore(FILE_WORKERS)
 async def process_file(entry):
  path,name,ext=entry
  try:
   async with file_slots:
    items,_=await asyncio.wait_for(_extract_file(path,name,ext),timeout=60)
   cars=await asyncio.gather(*(_enrich_item(item,name,rid,market_slots) for item in items))
   return cars,None
  except asyncio.TimeoutError:return [],f'{name}: превышено время обработки 60 секунд'
  except Exception as exc:
   logger.warning('Document processing failed (%s)',type(exc).__name__)
   return [],f'{name}: обработка не удалась ({type(exc).__name__})'
  finally:
   try:os.unlink(path)
   except OSError:pass
 results=await asyncio.gather(*(process_file(entry) for entry in files))
 cars=[car for group,_ in results for car in group]
 errors=[error for _,error in results if error]
 db=SessionLocal()
 try:
  report=db.get(Report,rid)
  if not report:return
  db.add_all(cars)
  report.error_text='; '.join(errors)[:2000]
  report.status='ready' if cars else 'failed'
  if not cars and not report.error_text:report.error_text='В пакете не найдено записей об автомобилях'
  db.commit()
 except Exception as e:
  db.rollback()
  report=db.get(Report,rid)
  if report:report.status='failed';report.error_text=f'Не удалось сохранить результат ({type(e).__name__})'[:2000];db.commit()
 finally:db.close()
@app.get('/api/reports')
def reports(authorization:str=Header(...)):
 db=SessionLocal()
 try:
  u=user_from(authorization,db); rs=db.query(Report).filter_by(user_id=u.id).order_by(Report.created_at.desc()).all()
  return [{'id':r.id,'name':r.name,'created_at':timestamp_iso(r.created_at),'cars_count':len(r.cars),'user':u.name,'status':r.status,'search_text':' '.join(value for c in r.cars for value in (c.debtor_name,c.vin,c.make,c.model,c.plate) if value)} for r in rs]
 finally:db.close()
def car_json(c):return {'id':c.id,'source_doc':c.source_doc,'doc_number':c.doc_number,'doc_date':c.doc_date,'doc_type':c.doc_type,'debtor_name':c.debtor_name,'inn':c.inn,'debt_amount':c.debt_amount,'vin':c.vin,'make':c.make,'model':c.model,'year':c.year,'plate':c.plate,'price':c.price,'demand':c.demand,'status':c.status,'vin_source':c.vin_source,'vin_checked_at':c.vin_checked_at,'vin_error':c.vin_error or '', 'market_status':c.market_status,'market_checked_at':c.market_checked_at,'demand_sources':json.loads(c.demand_sources or '[]'),'link':c.link,'motivation_index':c.motivation_index,'vzyskatel':c.vzyskatel,'ip_id':c.ip_id,'confidence':c.confidence,'market_sources':json.loads(c.market_sources or '[]'),'market_error':c.market_error or ''}
@app.get('/api/reports/{rid}')
def report_detail(rid:int,authorization:str=Header(...)):
 db=SessionLocal()
 try:
  u=user_from(authorization,db);r=db.get(Report,rid)
  if not r or r.user_id!=u.id:raise HTTPException(404,'Отчёт не найден')
  cars=list(r.cars) if r.status=='ready' else []
  priority=sorted((car for car in cars if prioritize(car,r.min_price,r.min_demand)),key=lambda car:car.motivation_index or 0,reverse=True)
  return {'id':r.id,'name':r.name,'created_at':timestamp_iso(r.created_at),'status':r.status,'error_text':r.error_text,'min_price':r.min_price,'min_demand':r.min_demand,'cars':[car_json(c) for c in cars],'prioritized_ids':[car.id for car in priority]}
 finally:db.close()
@app.patch('/api/reports/{rid}')
def rename(rid:int,data:RenameIn,authorization:str=Header(...)):
 db=SessionLocal()
 try:
  u=user_from(authorization,db);r=db.get(Report,rid)
  if not r or r.user_id!=u.id:raise HTTPException(404,'Отчёт не найден')
  r.name=data.name[:160];db.commit();return {'ok':True}
 finally:db.close()
@app.get('/api/reports/{rid}/export')
def export(rid:int,authorization:str=Header(...),ids:str=''):
 db=SessionLocal()
 try:
  u=user_from(authorization,db);r=db.get(Report,rid)
  if not r or r.user_id!=u.id:raise HTTPException(404,'Отчёт не найден')
  selected=set(map(int,ids.split(','))) if ids else set(); cars=[c for c in r.cars if c.doc_type=='ban' and c.id in selected and c.status!='В залоге']
  from openpyxl import Workbook
  wb=Workbook();ws=wb.active;ws.title='Авто';ws.append(['ФИО','ИНН','Сумма долга','VIN','Автомобиль','Год','Госномер','Цена рынка','Статус','Спрос','Ссылка','Confidence','Тип документа'])
  for c in cars:
   if c.status=='В залоге':continue
   ws.append([c.debtor_name,c.inn,c.debt_amount,c.vin,' '.join(filter(None,[c.make,c.model])),c.year,c.plate,c.price,c.status,c.demand,c.link,c.confidence,c.doc_type])
  b=io.BytesIO();wb.save(b);b.seek(0);return StreamingResponse(b,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename=report-{rid}.xlsx'})
 finally:db.close()
