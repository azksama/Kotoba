"""Android SDK UI snapshot, with pairing codes redacted from console output."""
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding='utf-8')
result=subprocess.run(['adb','-s','emulator-5554','shell','uiautomator','dump','/sdcard/kotoba-ui.xml'],check=True,capture_output=True,text=True)
if 'ERROR' in result.stdout+result.stderr:
    raise RuntimeError('Android UI snapshot unavailable; no stale snapshot used.')
subprocess.run(['adb','-s','emulator-5554','pull','/sdcard/kotoba-ui.xml',str(root/'outputs/kotoba-ui.xml')],check=True,stdout=subprocess.DEVNULL)
for node in ET.parse(root/'outputs/kotoba-ui.xml').iter('node'):
    label=node.get('text') or node.get('content-desc')
    if label:
        if 'KTB1.' in label and len(label)>100:label='[private pairing code]'
        print(node.get('class'),node.get('bounds'),label)
