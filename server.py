"""Live team quiz server. Run with: uvicorn server:app --host 0.0.0.0 --port 8000"""
import asyncio, csv, io, json, os, secrets, time
from pathlib import Path
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, StreamingResponse, Response
from pydantic import BaseModel

BASE=Path(__file__).parent
DATA=BASE/'rooms.json'
HOST_PIN=os.environ.get('HACKATHON_HOST_PIN','')
if not HOST_PIN:
    # Local initial setup; configure a secret PIN for public deployment.
    HOST_PIN='246824'
app=FastAPI(title='هاكاثون الطلاب القادة من أجل الدمج')

QUESTIONS=[
 ('الوعي بالدمج','ما التصرف الأفضل عندما يريد طالب من أصحاب الهمم المشاركة في نشاط جماعي؟',['نطلب منه أن يراقب فقط','نستمع إلى تفضيلاته ونهيئ فرص المشاركة المتكافئة','نختار له المهمة دون سؤاله','نلغي النشاط للجميع'],1),
 ('الوعي بالدمج','ما معنى التيسيرات المعقولة في البيئة المدرسية؟',['خفض جميع التوقعات تلقائياً','إعفاء الطالب من جميع الأنشطة','تعديلات مناسبة تزيل الحواجز دون عبء غير متناسب','عزل الطالب في مجموعة مستقلة'],2),
 ('الوعي بالدمج','أي عبارة تعبّر عن القيادة الطلابية الدامجة؟',['نقرر نيابة عن الآخرين','نجعل الجميع يتبع أسلوباً واحداً','نطلب من الطلبة المختلفين عدم المشاركة','نشرك أصحاب العلاقة في اتخاذ القرار'],3),
 ('الوعي بالدمج','ما الأسلوب الأنسب للتواصل مع زميل يستخدم وسيلة تواصل بديلة؟',['نعطيه وقتاً كافياً ونسأله عن أسلوبه المفضل','نرفع صوتنا دائماً','نتحدث مع مرافقه فقط','نجيب عنه بسرعة'],0),
 ('الوعي بالدمج','كيف نعرف أن المبادرة الدامجة نجحت؟',['بعدد الصور المنشورة فقط','بعدد الضيوف فقط','بقياس المشاركة وتجربة المستفيدين ونتائج واضحة','بجمال الشعار'],2),
 ('المواقف الذكية','طالب لا يستطيع الوصول إلى المسرح بسبب الدرج. ما الحل الأفضل؟',['نمنعه من العرض','نوفر مسار وصول آمن أو نعدل مكان الفقرة','نطلب من أصدقائه حمله دون تقييم السلامة','نؤجل مشاركته إلى العام المقبل'],1),
 ('المواقف الذكية','زميلة تتعرض للسخرية بسبب طريقة كلامها. ماذا يفعل القائد الطلابي؟',['يتجاهل الموقف','يشارك في المزاح','يدعم الزميلة ويتدخل بأمان ويبلغ المسؤول عند الحاجة','ينشر الفيديو للتوعية'],2),
 ('المواقف الذكية','أثناء مسابقة، لم يفهم أحد المشاركين السؤال المكتوب. ما الإجراء العادل؟',['نشرح المحتوى بصيغة ميسّرة دون كشف الإجابة','نمنحه إجابة صحيحة فوراً','نمنعه من إكمال الجولة','نختصر وقته'],0),
 ('المواقف الذكية','طالب لديه حساسية من الضوضاء في فعالية مزدحمة. ما التصرف الأفضل؟',['زيادة الصوت حتى يعتاد','توفير مكان هادئ وخيارات مشاركة مرنة','إجباره على الاستمرار','استبعاده من الحدث'],1),
 ('المواقف الذكية','طلب فريق نشر صورة لزميل من أصحاب الهمم دون موافقته. ما القرار الصحيح؟',['ننشرها لأن الهدف جيد','ننشرها بعد قص الصورة','نطلب الموافقة المناسبة ونحترم الخصوصية','ننشرها في مجموعة خاصة فقط'],2),
 ('التقنية والابتكار','أي تقنية تساعد الطالب الذي يصعب عليه قراءة النصوص الصغيرة؟',['واجهة تكبير النص وقارئ الشاشة عند الحاجة','تصغير الخط أكثر','الاعتماد على اللون وحده','إيقاف الصوت'],0),
 ('التقنية والابتكار','كيف نجعل نموذج التسجيل الرقمي أكثر إتاحة؟',['نجعل إكماله بالمؤشر فقط','نوفر تسميات واضحة ويدعم لوحة المفاتيح','نمنع التكبير','نستخدم صوراً بلا وصف'],1),
 ('التقنية والابتكار','ما الاستخدام المسؤول للذكاء الاصطناعي في خدمة الدمج؟',['الاعتماد الكامل على مخرجاته دون مراجعة','جمع البيانات الشخصية دون إذن','اختبار الحل مع المستفيدين ومراجعة الدقة والخصوصية','إلغاء دور المعلمين'],2),
 ('التقنية والابتكار','عند تصميم تطبيق مدرسي، ما أفضل طريقة لاختيار ميزاته الدامجة؟',['استشارة المستخدمين ذوي الاحتياجات المتنوعة وتجريب النموذج','تقليد تطبيق مشهور فقط','الاعتماد على رأي المصمم وحده','إضافة مؤثرات كثيرة دون اختبار'],0),
 ('التقنية والابتكار','أي خيار يساعد طالباً لديه صعوبة سمعية في متابعة فيديو تعليمي؟',['رفع الصوت فقط','إضافة ترجمة نصية دقيقة وإتاحة نص المحتوى','إزالة الفيديو','إخفاء التوضيحات'],1),
 ('التحدي السريع','لماذا لا تكفي إزالة الحواجز المادية وحدها لتحقيق الدمج؟',['لأن الدمج يحتاج أيضاً وصولاً رقمياً وتواصلاً ومشاركة فعلية','لأن الحواجز المادية غير مهمة','لأن التقنية تعوض كل شيء','لأن الدمج مسؤولية الطلاب فقط'],0),
 ('التحدي السريع','فريق يقترح مساراً مدرسياً ميسّراً. ما أفضل مؤشر أولي لنجاح المشروع؟',['عدد الملصقات','عدد الاجتماعات','قدرة الطلاب المستهدفين على التنقل بأمان واستقلالية أكبر','تكلفة الإعلان'],2),
 ('التحدي السريع','عند ظهور فجوة بين نتائج المسابقة ومستوى مشاركة فئات مختلفة، ماذا نفعل؟',['نتجاهل البيانات','نحلل الأسباب ونحسن إمكانية الوصول وعدالة التصميم','نلغي التقييم','نخفي النتائج'],1),
 ('التحدي السريع','أي فكرة تجعل المكتبة المدرسية أكثر دمجاً؟',['توفير صيغ قراءة متعددة ومسارات وصول واضحة','تخصيص جميع الكتب لمجموعة واحدة','تقليل ساعات عمل المكتبة','إلغاء الاستعارة الإلكترونية'],0),
 ('التحدي السريع','ما الخطوة الأولى عند تصميم حل ابتكاري لمشكلة تواجه أصحاب الهمم؟',['شراء أجهزة مباشرة','إطلاق إعلان','تحديد الاحتياج بمشاركة المستفيدين وفهم الحواجز','اختيار اسم المشروع'],2),
]

class CreateRequest(BaseModel): pin:str
class JoinRequest(BaseModel): room:str; name:str
class ActionRequest(BaseModel): token:str; action:str; choice:int|None=None

rooms={}
connections={}
locks={}

def stamp():return int(time.time()*1000)
def persist():
    safe={k:{**r,'timer_deadline':None if r['phase']=='question' else r['timer_deadline']} for k,r in rooms.items()}
    tmp=DATA.with_suffix('.tmp');tmp.write_text(json.dumps(safe,ensure_ascii=False),encoding='utf-8');tmp.replace(DATA)

def load():
    if DATA.exists():
        try:
            for k,r in json.loads(DATA.read_text(encoding='utf-8')).items():
                if r.get('phase')=='question':r['phase']='results';r['timer_deadline']=None;r['last_notice']='انقطعت الجولة أثناء إعادة التشغيل؛ أعاد المنظم إظهار النتائج.'
                rooms[k]=r
        except Exception as exc:print('Unable to load rooms:',exc)
load()

def role(r, token):
    if secrets.compare_digest(str(token),r['host_token']):return ('host',None)
    for i,t in enumerate(r['teams']):
        if secrets.compare_digest(str(token),t['token']):return ('team',i)
    return (None,None)

def state(r,what,team_index=None):
    idx=r['index'];q=QUESTIONS[idx] if 0<=idx<len(QUESTIONS) else None
    scores=sorted([{'name':t['name'],'score':t['score'],'answered':str(i) in r['answers']} for i,t in enumerate(r['teams'])],key=lambda t:(-t['score'],t['name']))
    base={'type':'state','room':r['code'],'phase':r['phase'],'index':idx,'total':len(QUESTIONS),'teams_count':len(r['teams']),'max_teams':8,'joined':[t['name'] for t in r['teams']],'deadline':r['timer_deadline'],'server_time':stamp(),'round':q[0] if q else None,'notice':r.get('last_notice',''),'answered_count':len(r['answers'])}
    if r['phase'] in ('question','results') and q:
        base['question']=q[1];base['choices']=q[2]
    if r['phase']=='results' and q:
        base['correct']=q[3];base['leaderboard']=scores; base['answers_count']=[sum(1 for v in r['answers'].values() if v==j) for j in range(4)]
    if r['phase']=='ended':base['leaderboard']=scores
    if what=='host':
        base['leaderboard']=scores if r['phase']!='question' else None
        base['selected_answers']={r['teams'][int(i)]['name']:v for i,v in r['answers'].items()}
    if what=='team' and team_index is not None:
        base['your_name']=r['teams'][team_index]['name'];base['your_score']=r['teams'][team_index]['score'];base['submitted']=str(team_index) in r['answers'];base['your_choice']=r['answers'].get(str(team_index))
        if r['phase']=='question':base.pop('leaderboard',None)
    return base

async def broadcast(code):
    r=rooms.get(code)
    if not r:return
    for ws,metadata in list(connections.get(code,{}).items()):
        try:await ws.send_json(state(r,*metadata))
        except Exception:connections.get(code,{}).pop(ws,None)

def finalize(r):
    if r['phase']!='question':return
    correct=QUESTIONS[r['index']][3]
    for ix,t in enumerate(r['teams']):
        if r['answers'].get(str(ix))==correct:t['score']+=100
    r['phase']='results';r['timer_deadline']=None;r['last_notice']='انتهى السؤال، والنتائج أمامكم الآن.';persist()

async def ticker(code,idx,deadline):
    await asyncio.sleep(max(0,(deadline-stamp())/1000))
    r=rooms.get(code)
    if r and r['phase']=='question' and r['index']==idx and r['timer_deadline']==deadline:
        finalize(r);await broadcast(code)

def question_start(r):
    if r['phase']=='question':raise HTTPException(409,'السؤال الجاري لم ينته')
    if len(r['teams'])==0:raise HTTPException(409,'لا توجد فرق مسجلة')
    if r['phase']=='lobby':r['index']=0
    elif r['phase']=='results':r['index']+=1
    else:raise HTTPException(409,'لا يمكن بدء سؤال في هذه المرحلة')
    if r['index']>=len(QUESTIONS):r['phase']='ended';r['timer_deadline']=None
    else:
        r['phase']='question';r['answers']={};r['timer_deadline']=stamp()+30000;r['last_notice']='ابدأوا التشاور: أمامكم 30 ثانية.'
        asyncio.create_task(ticker(r['code'],r['index'],r['timer_deadline']))
    persist()

@app.get('/')
async def home():return FileResponse(BASE/'static'/'index.html')
@app.get('/health')
async def health():return {'status':'ok','rooms':len(rooms)}
@app.post('/api/create')
async def create(body:CreateRequest):
    if not secrets.compare_digest(body.pin,HOST_PIN):raise HTTPException(403,'الرمز السري للمنظم غير صحيح')
    code=''.join(str(secrets.randbelow(10)) for _ in range(6))
    while code in rooms:code=''.join(str(secrets.randbelow(10)) for _ in range(6))
    token=secrets.token_urlsafe(36)
    r={'code':code,'host_token':token,'phase':'lobby','index':-1,'timer_deadline':None,'teams':[],'answers':{},'last_notice':'الغرفة جاهزة لاستقبال الفرق.'}
    rooms[code]=r;persist();return {'room':code,'token':token}
@app.post('/api/join')
async def join(body:JoinRequest):
    code=body.room.strip();name=body.name.strip()
    r=rooms.get(code)
    if not r:raise HTTPException(404,'لم يتم العثور على الغرفة')
    if r['phase']!='lobby':raise HTTPException(409,'تم إغلاق الانضمام بعد بدء المسابقة')
    if len(name)<2 or len(name)>36:raise HTTPException(400,'اكتب اسم فريق من حرفين حتى 36 حرفاً')
    if len(r['teams'])>=8:raise HTTPException(409,'الغرفة اكتملت: ثمانية فرق')
    if any(x['name'].casefold()==name.casefold() for x in r['teams']):raise HTTPException(409,'اسم الفريق مستخدم بالفعل')
    token=secrets.token_urlsafe(36)
    r['teams'].append({'name':name,'token':token,'score':0});persist();await broadcast(code)
    return {'room':code,'token':token,'name':name}
@app.get('/api/state/{code}')
async def read_state(code:str,token:str=''):
    r=rooms.get(code)
    if not r:raise HTTPException(404,'الغرفة غير موجودة')
    role_name,ix=role(r,token) if token else ('screen',None)
    return state(r,role_name,ix)
@app.post('/api/action/{code}')
async def action(code:str,body:ActionRequest):
    r=rooms.get(code)
    if not r:raise HTTPException(404,'الغرفة غير موجودة')
    typ,ix=role(r,body.token)
    if not typ:raise HTTPException(403,'غير مصرح')
    act=body.action
    if typ=='host' and act=='start':question_start(r)
    elif typ=='host' and act=='finish':finalize(r)
    elif typ=='host' and act=='reset':
        r['phase']='lobby';r['index']=-1;r['answers']={};r['timer_deadline']=None
        for t in r['teams']:t['score']=0
        r['last_notice']='أعيد بدء المسابقة وتصفير النقاط';persist()
    elif typ=='team' and act=='answer':
        if r['phase']!='question' or stamp()>=r['timer_deadline']:raise HTTPException(409,'انتهت مهلة الإجابة')
        if str(ix) in r['answers']:raise HTTPException(409,'تم تسجيل إجابة فريقك بالفعل')
        if body.choice not in (0,1,2,3):raise HTTPException(400,'خيار غير صالح')
        r['answers'][str(ix)]=body.choice;persist()
    else:raise HTTPException(403,'هذا الإجراء غير مسموح لدورك')
    await broadcast(code)
    return {'ok':True}
@app.get('/api/results/{code}.csv')
async def results(code:str,token:str):
    r=rooms.get(code)
    if not r or not secrets.compare_digest(token,r['host_token']):raise HTTPException(403,'غير مصرح')
    f=io.StringIO();w=csv.writer(f);w.writerow(['الترتيب','اسم الفريق','النقاط'])
    for i,t in enumerate(sorted(r['teams'],key=lambda x:-x['score']),1):w.writerow([i,t['name'],t['score']])
    f.seek(0);return StreamingResponse(iter(["\ufeff",f.getvalue()]),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="results_{code}.csv"'})
@app.websocket('/ws/{code}')
async def websocket(ws:WebSocket,code:str,token:str=''):
    r=rooms.get(code)
    if not r:await ws.close(code=4404);return
    typ,ix=role(r,token) if token else ('screen',None)
    if not typ:await ws.close(code=4403);return
    await ws.accept();connections.setdefault(code,{})[ws]=(typ,ix)
    await ws.send_json(state(r,typ,ix))
    try:
        while True:
            await ws.receive_text() # heartbeat from client
    except WebSocketDisconnect:pass
    finally:connections.get(code,{}).pop(ws,None)

@app.get('/api/qr/{code}')
async def qr(code:str,request:Request):
    if code not in rooms:raise HTTPException(404,'الغرفة غير موجودة')
    import qrcode
    from urllib.parse import quote
    proto=request.headers.get('x-forwarded-proto',request.url.scheme)
    host=request.headers.get('host','localhost:8000')
    url=f"{proto}://{host}/?room={quote(code)}&view=team"
    qr=qrcode.QRCode(box_size=9,border=2);qr.add_data(url);qr.make(fit=True)
    out=io.BytesIO();qr.make_image(fill_color='#0A2C5B',back_color='white').save(out,'PNG')
    return Response(out.getvalue(),media_type='image/png')
