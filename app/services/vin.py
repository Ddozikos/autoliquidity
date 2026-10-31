import os
from datetime import datetime,timezone
import httpx

class VinService:
    """Adapter for a user supplied VIN / encumbrance API; no fabricated clearance result."""
    def __init__(self):
        self.url=os.getenv('VIN_API_URL','').strip()
        self.key=os.getenv('VIN_API_KEY','').strip()
    def enrich(self,vin):
        if not self.url:return {'status':'Не проверен','source':None,'checked_at':None}
        headers={'Authorization':f'Bearer {self.key}'} if self.key else {}
        try:
            response=httpx.get(self.url,params={'vin':vin},headers=headers,timeout=15)
            response.raise_for_status(); data=response.json()
            return {'status':data.get('status','Неизвестно'),'source':data.get('source') or 'VIN_API_URL','checked_at':datetime.now(timezone.utc).isoformat()}
        except Exception as exc:
            raise RuntimeError(f'VIN provider error: {type(exc).__name__}') from exc
