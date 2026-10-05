"""Real HTTPS, auth, job, report and persistence smoke checks. No secrets printed."""
import base64
import hashlib
import json
from pathlib import Path
import ssl
import time
import urllib.error
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parents[1]
code=(ROOT/'.kotoba/pairing.txt').read_text().strip().split('.',1)[1]
pair=json.loads(base64.urlsafe_b64decode(code+'='*(-len(code)%4)))
context=ssl.create_default_context(cadata=pair['certificate'])
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))

def request(path,body=None,auth=True,binary=False):
    headers={'Content-Type':'application/json'}
    if auth:headers['Authorization']='Bearer '+pair['token']
    req=urllib.request.Request('https://127.0.0.1:48736'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    with opener.open(req,timeout=60) as response:
        raw=response.read()
        return raw if binary else json.loads(raw)

def expect_status(status,path,body=None,auth=True):
    try:request(path,body,auth)
    except urllib.error.HTTPError as error:assert error.code==status,(error.code,status)
    else:raise AssertionError('Expected HTTP failure')

if __name__=='__main__':
    checks=[]
    expect_status(401,'/v1/health',auth=False);checks.append('unauthenticated denied')
    status=request('/v1/health');assert status['ollama'] and status['model_ready'];checks.append('real model available')
    data=(ROOT/'examples/game.ja.json').read_bytes()
    submission={'request_id':str(uuid.uuid4()),'filename':'game.ja.json','data':base64.b64encode(data).decode(),
                'options':{'target':'en','include':['/dialogues/*/text'],'exclude':[],'strict_tokens':False}}
    inspect=request('/v1/preview',submission);assert inspect['total']==5;checks.append('real JSON preview filtered')
    invalid={**submission,'data':base64.b64encode(b'{bad JSON').decode()}
    expect_status(400,'/v1/preview',invalid);checks.append('invalid JSON rejected')
    invalid={**submission,'options':{'target':'--model'}}
    expect_status(400,'/v1/preview',invalid);checks.append('unapproved options rejected')
    job=request('/v1/jobs',submission)
    duplicate=request('/v1/jobs',submission);assert duplicate['id']==job['id'];checks.append('submission idempotent')
    for _ in range(180):
        job=request('/v1/jobs/'+job['id'])
        if job['status'] not in ('queued','running'):break
        time.sleep(2)
    assert job['status']=='completed',job
    result=request('/v1/jobs/'+job['id']+'/result',binary=True)
    output=json.loads(result);original=json.loads(data)
    assert output['id']==original['id'] and output['path']==original['path'] and output['menu']==original['menu']
    assert output['dialogues'][0]['text']!=original['dialogues'][0]['text']
    assert '\\C[2]' in output['dialogues'][3]['text']
    assert (ROOT/'.kotoba/jobs'/job['id']/'input.json').read_bytes()==data
    checks.extend(['real GPU job completed','source immutable','result downloadable with codes preserved'])
    report=request('/v1/jobs/'+job['id']+'/report');assert not report['errors'];checks.append('report available')
    result_path=ROOT/'outputs/companion-live-result.json';result_path.write_bytes(result)
    evidence={'checks':checks,'job_id':job['id'],'translated':job['done'],'reviews':len(job['reviews']),
              'result_sha256':hashlib.sha256(result).hexdigest(),'status':'PASS'}
    (ROOT/'outputs/companion-checks.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(json.dumps(evidence,indent=2))
