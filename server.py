import os, sqlite3, secrets, io, time, json, hmac
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import qrcode

ROOT = Path(__file__).resolve().parent
DB = os.environ.get('CHARTER_DB_PATH', str(ROOT/'charter.sqlite3'))
ADMIN_PIN = os.environ.get('CHARTER_ADMIN_PIN', '')
MAXLEN = 1000
app = FastAPI(title='ميثاق الابتكار من أجل الدمج', docs_url=None, redoc_url=None)
app.mount('/assets', StaticFiles(directory=ROOT/'static'/'assets'), name='assets')

def conn():
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA busy_timeout=15000')
    return c

@app.on_event('startup')
def start():
    Path(DB).parent.mkdir(parents=True,exist_ok=True)
    with conn() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('CREATE TABLE IF NOT EXISTS signatures (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, category TEXT NOT NULL, created TEXT NOT NULL, feedback TEXT DEFAULT NULL, idea TEXT DEFAULT NULL, feedback_status TEXT NOT NULL DEFAULT "none")')
        c.execute('CREATE INDEX IF NOT EXISTS idx_feedback ON signatures(feedback_status, id)')
        columns={x[1] for x in c.execute('PRAGMA table_info(signatures)').fetchall()}
        if 'publish_name' not in columns:
            c.execute('ALTER TABLE signatures ADD COLUMN publish_name INTEGER NOT NULL DEFAULT 0')

class Sign(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    category: str = Field(default='فرد',max_length=30)
    accepted: bool
    honeypot: str = ''

class Feedback(BaseModel):
    code: str
    opinion: str = Field(min_length=1,max_length=50)
    idea: str = Field(min_length=3,max_length=500)
    publish_name: bool = False
    honeypot: str = ''

def clean(s): return ' '.join(s.strip().split())

@app.get('/', response_class=HTMLResponse)
def home(): return (ROOT/'static'/'index.html').read_text(encoding='utf8')

@app.get('/api/stats')
def stats():
    with conn() as c:
        count = c.execute('SELECT count(*) FROM signatures').fetchone()[0]
        ideas = c.execute('SELECT count(*) FROM signatures WHERE feedback_status = "approved"').fetchone()[0]
    return {'signatures':count,'ideas':ideas}

@app.post('/api/sign')
def sign(item: Sign):
    if item.honeypot: raise HTTPException(400,'تعذّر التسجيل')
    name=clean(item.name)
    if len(name)<2 or not item.accepted: raise HTTPException(400,'الاسم والموافقة على الميثاق مطلوبان')
    if item.category not in ('فرد','طالب','ولي أمر','معلم','موظف','مشارك مجتمعي','أخرى'):
        raise HTTPException(400,'الفئة غير صحيحة')
    code='IC-'+datetime.now(timezone.utc).strftime('%Y')+'-'+secrets.token_hex(5).upper()
    now=datetime.now(timezone.utc).isoformat()
    with conn() as c:
        c.execute('INSERT INTO signatures (code,name,category,created) VALUES (?,?,?,?)',(code,name,item.category,now))
    return {'code':code,'name':name,'created':now}

@app.post('/api/feedback')
def feedback(item:Feedback):
    if item.honeypot: raise HTTPException(400,'تعذّر الإرسال')
    if item.opinion not in ('مبادرة مميزة','مبادرة مهمة','أرغب في تطويرها','اقتراح آخر'):
        raise HTTPException(400,'يرجى اختيار رأيك')
    idea=clean(item.idea)
    if len(idea)<3: raise HTTPException(400,'اكتب فكرة بسيطة لدعم الدمج')
    if not item.publish_name: raise HTTPException(400,'يرجى الموافقة على عرض اسمك مع فكرتك قبل الإرسال')
    with conn() as c:
        r=c.execute('SELECT feedback_status FROM signatures WHERE code=?',(item.code,)).fetchone()
        if not r: raise HTTPException(404,'الشهادة غير موجودة')
        if r['feedback_status']!='none': raise HTTPException(409,'تم إرسال مشاركتك مسبقاً')
        c.execute('UPDATE signatures SET feedback=?, idea=?, publish_name=?, feedback_status="pending" WHERE code=?',(item.opinion,idea,1 if item.publish_name else 0,item.code))
    return {'success':True,'message':'شكراً لك! وصلت فكرتك وستُنشر بعد المراجعة.'}

@app.get('/api/certificate/{code}')
def certificate(code:str):
    with conn() as c:
        r=c.execute('SELECT code,name,category,created FROM signatures WHERE code=?',(code,)).fetchone()
        if not r: raise HTTPException(404,'لم يتم العثور على الشهادة')
    return dict(r)

@app.get('/verify/{code}',response_class=HTMLResponse)
def verify(code:str):
    with conn() as c:
        r=c.execute('SELECT code,name,created FROM signatures WHERE code=?',(code,)).fetchone()
    import html
    if not r: return HTMLResponse('<html lang="ar" dir="rtl"><meta charset="utf-8"><body style="font-family:Arial;text-align:center;padding:60px"><h1>الشهادة غير موجودة</h1><p>تحقق من الرقم المدخل</p></body></html>',status_code=404)
    return HTMLResponse(f'<html lang="ar" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><body style="background:#f4f7fb;font-family:Arial;text-align:center;padding:50px;color:#102e53"><h1>✓ شهادة مشاركة موثقة</h1><h2>ميثاق الابتكار من أجل الدمج</h2><p>الاسم: <b>{html.escape(r["name"])}</b></p><p>رقم الشهادة: <b>{html.escape(r["code"])}</b></p><p>تاريخ التسجيل: {html.escape(r["created"][:10])}</p><small>تأكيد تسجيل المشاركة في الميثاق، وليس شهادة اعتماد مهني أو مؤسسي.</small></body></html>')

@app.get('/api/qr/{code}')
def qr(code:str,request:Request):
    with conn() as c:
        exists=c.execute('SELECT 1 FROM signatures WHERE code=?',(code,)).fetchone()
    if not exists: raise HTTPException(404,'لم يتم العثور على الشهادة')
    origin=str(request.base_url).rstrip('/')
    image=qrcode.make(origin+'/verify/'+code)
    bio=io.BytesIO();image.save(bio,format='PNG');bio.seek(0)
    return StreamingResponse(bio,media_type='image/png')

@app.get('/api/ideas')
def ideas():
    with conn() as c:
        rows=c.execute('SELECT feedback,idea,CASE WHEN publish_name=1 THEN name ELSE NULL END AS name FROM signatures WHERE feedback_status="approved" ORDER BY id DESC LIMIT 30').fetchall()
    return {'items':[dict(r) for r in rows]}

def authorize(pin):
    if not ADMIN_PIN: raise HTTPException(503,'حدد CHARTER_ADMIN_PIN على الخادم أولاً')
    if not hmac.compare_digest(pin or '',ADMIN_PIN):raise HTTPException(401,'رمز الإدارة غير صحيح')

@app.get('/admin',response_class=HTMLResponse)
def admin_page():return (ROOT/'static'/'admin.html').read_text(encoding='utf8')

@app.get('/api/admin/feedback')
def moderation(x_admin_pin: str=Header(default='')):
    authorize(x_admin_pin)
    with conn() as c:
        rows=c.execute('SELECT id,code,name,publish_name,feedback,idea,created FROM signatures WHERE feedback_status="pending" ORDER BY id DESC LIMIT 200').fetchall()
    return {'items':[dict(x) for x in rows]}

class Moderate(BaseModel):
    status: str

@app.post('/api/admin/feedback/{id}')
def moderate(id:int,item:Moderate,x_admin_pin:str=Header(default='')):
    authorize(x_admin_pin)
    if item.status not in ('approved','rejected'):raise HTTPException(400,'حالة غير صحيحة')
    with conn() as c:
        cur=c.execute('UPDATE signatures SET feedback_status=? WHERE id=? AND feedback_status="pending"',(item.status,id))
    return {'ok':cur.rowcount>0}

@app.get('/health')
def health():return {'ok':True}

