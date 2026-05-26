from pathlib import Path
import os
from dotenv import load_dotenv
load_dotenv('.env')
os.environ['OCR_IMAGE_PROVIDER'] = 'openai'
from services.ocr import extract_text_pdf, extract_bl_fields
p = Path(r'C:\Users\cwakh\Downloads\COPY OF BL - DXB25-1748 (1).pdf')
print('exists=', p.exists())
text = extract_text_pdf(p)
print('embedded_text_chars=', len(text.strip()))
print('openai_key_loaded=', bool(os.getenv('OPENAI_API_KEY')))
result = extract_bl_fields(str(p))
keys = ['ocr_provider','ocr_mode','ocr_error','bl_number','doc_type','route_type','transport_mode','zra_regime','shipper_name','carrier_name','vessel_vehicle_no','origin','destination','consignee_name','consignee_tin','gross_weight','no_containers','cargo_description','hs_code','gn83_category']
for key in keys:
    value = result.get(key)
    if value not in (None, ''):
        print(f'{key}={value}')
raw = result.get('raw_text') or ''
print('raw_text_chars=', len(raw))
print('raw_text_preview=', raw[:1800].replace('\n', ' | '))
