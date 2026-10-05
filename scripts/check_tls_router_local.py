import base64,hashlib,json,socket,ssl,argparse
from urllib.parse import urlsplit
parser=argparse.ArgumentParser();parser.add_argument("--lan",required=True);parser.add_argument("--public",action="store_true");args=parser.parse_args()
from pathlib import Path
root=Path.cwd(); code=(root/'.kotoba/pairing.txt').read_text().strip().split('.',1)[1]; k=json.loads(base64.urlsafe_b64decode(code+'='*(-len(code)%4)))
m=json.loads((Path.home()/'.mochi/pc/pairing-public.json').read_text())
def check(address,name,pair,path,expected=200,auth=True):
 ctx=ssl.create_default_context(cadata=pair['certificate'])
 with socket.create_connection((address,8189),timeout=8) as raw:
  with ctx.wrap_socket(raw,server_hostname=name) as s:
   cert=s.getpeercert(binary_form=True)
   assert hashlib.sha256(cert).digest()==hashlib.sha256(ssl.PEM_cert_to_DER_cert(pair['certificate'])).digest()
   token=('Authorization: Bearer '+pair['token']+'\r\n') if auth else ''
   s.sendall(f'GET {path} HTTP/1.1\r\nHost: {name}:8189\r\n{token}Connection: close\r\n\r\n'.encode())
   head=s.recv(8192).split(b'\r\n',1)[0].decode()
   assert int(head.split()[1])==expected,head
 return head
results=[]
kotoba_host=urlsplit(k['endpoint']).hostname
mochi_host=urlsplit(m['url']).hostname
for address in [args.lan]+([mochi_host] if args.public else []):
 for name,pair,path in [(kotoba_host,k,'/v1/health'),(mochi_host,m,'/bridge/info')]:
  try:
   status=check(address,name,pair,path);results.append({'address':address,'service':'Kotoba' if pair is k else 'Mochi','status':status,'original_certificate':True});print(results[-1])
  except Exception as e:print(type(e).__name__,str(e));results.append({'address':address,'service':name,'error':str(e)})
print('Unauthorized Kotoba:',check(args.lan,kotoba_host,k,'/v1/health',401,False))
Path('outputs/tls-router-checks.json').write_text(json.dumps(results,indent=2))

if any("error" in result for result in results):
 raise SystemExit(1)
