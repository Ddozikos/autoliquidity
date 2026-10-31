import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / 'samples' / 'fssp_100_dokumentov' / 'html' / '099_Toyota_Avensis.html'


class PersistenceTests(unittest.TestCase):
    def test_completed_report_and_cars_survive_application_restart(self):
        if not REFERENCE.exists():
            self.skipTest('user-provided reference documents are not included in the distributable archive')
        with tempfile.TemporaryDirectory(prefix='autoliquidity-restart-') as directory:
            database = Path(directory) / 'app.db'
            environment = os.environ.copy()
            environment.update({
                'DATABASE_URL': f'sqlite:///{database}',
                'APIAD_ENABLED': 'false',
                'GIGACHAT_API_KEY': '',
                'AVITO_PRICE_API_URL': '',
                'AUTORU_PRICE_API_URL': '',
                'DROM_PRICE_API_URL': '',
                'SBERAUTO_PRICE_API_URL': '',
                'VIN_API_URL': '',
            })
            upload_script = r'''
import sys, time
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    token=client.post('/api/login',json={'email':'restart-test@example.invalid','password':'x'}).json()['access_token']
    headers={'Authorization':'Bearer '+token}
    with open(sys.argv[1],'rb') as document:
        response=client.post('/api/process',headers=headers,data={'min_price':'300000','min_demand':'70'},files=[('files',('reference.html',document,'text/html'))])
    assert response.status_code==200,response.text
    report_id=response.json()['report_id']
    for _ in range(200):
        result=client.get(f'/api/reports/{report_id}',headers=headers).json()
        if result['status']!='processing': break
        time.sleep(.05)
    assert result['status']=='ready',result
    assert len(result['cars'])==1,result
    print(report_id)
'''
            first = subprocess.run(
                [sys.executable, '-c', upload_script, str(REFERENCE)],
                cwd=ROOT, env=environment, text=True, capture_output=True, timeout=45,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            report_id = int(first.stdout.strip().splitlines()[-1])

            restart_script = r'''
import sys
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    token=client.post('/api/login',json={'email':'restart-test@example.invalid','password':'x'}).json()['access_token']
    headers={'Authorization':'Bearer '+token}
    reports=client.get('/api/reports',headers=headers).json()
    report=next(item for item in reports if item['id']==int(sys.argv[1]))
    assert report['status']=='ready',report
    detail=client.get(f"/api/reports/{report['id']}",headers=headers).json()
    assert len(detail['cars'])==1,detail
    assert detail['cars'][0]['vin']=='JTNBE46KX73123456',detail
'''
            restarted = subprocess.run(
                [sys.executable, '-c', restart_script, str(report_id)],
                cwd=ROOT, env=environment, text=True, capture_output=True, timeout=20,
            )
            self.assertEqual(restarted.returncode, 0, restarted.stderr)


if __name__ == '__main__':
    unittest.main()
