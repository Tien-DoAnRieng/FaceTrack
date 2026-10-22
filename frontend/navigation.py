"""Cookie authentication and navigation for the individual UI pages."""
from html import escape
import jwt
import httpx
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from .pages import PAGES

COOKIE = 'faceid_session'
STYLE = '''body{margin:0;background:#f5f7fb;color:#17233c;font:16px system-ui}*{box-sizing:border-box}a{color:#2558c8;text-decoration:none}header{background:white;border-bottom:1px solid #dde3ed;padding:18px 28px;display:flex;align-items:center;justify-content:space-between}button{cursor:pointer;background:#2558c8;color:white;border:0;border-radius:8px;padding:12px 18px;font:inherit}nav{padding:20px;display:flex;flex-direction:column;gap:8px;width:245px;background:white}nav a{padding:12px;border-radius:8px;color:#374760}nav a.active{background:#eaf0ff;color:#2558c8;font-weight:600}.layout{display:flex;min-height:calc(100vh - 80px)}main{flex:1;min-width:0;padding:24px}iframe{width:100%;height:calc(100vh - 160px);min-height:640px;border:0;border-radius:12px;background:white}.card{max-width:430px;margin:70px auto;background:white;padding:32px;border-radius:16px;box-shadow:0 8px 40px #182e5110}label{display:block;margin-top:18px}input{width:100%;padding:12px;border:1px solid #c8d2e2;border-radius:8px;margin:8px 0}form p{color:#b42318}.card button{width:100%;margin-top:20px}@media(max-width:760px){.layout{display:block}nav{width:auto;flex-direction:row;overflow:auto}nav a{white-space:nowrap}main{padding:12px}header{padding:14px}.card{margin:30px 15px}}'''


FRAME_SCRIPT = '''<script>
function fitPageFrame(frame) {
    if (frame.pageObserver) frame.pageObserver.disconnect();
    const doc = frame.contentDocument;
    if (!doc) return;
    const fit = () => {
        const content = doc.querySelector('.gradio-container') || doc.body;
        frame.style.height = Math.max(640, Math.ceil(content.getBoundingClientRect().height), content.scrollHeight) + 'px';
    };
    const observer = new ResizeObserver(fit);
    frame.pageObserver = observer;
    observer.observe(doc.body);
    const content = doc.querySelector('.gradio-container');
    if (content) observer.observe(content);
    fit();
}
</script>'''


def document(title, body):
    return f'<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)} · FaceID</title><style>{STYLE}</style>{FRAME_SCRIPT}</head><body>{body}</body></html>'


def current_user(request):
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    try:
        payload = jwt.decode(token, request.app.state.secret, algorithms=['HS256'], issuer='faceid-api', audience='faceid-clients')
        rows = request.app.state.db.all('SELECT id,username,fullName,role FROM users WHERE id=?', [int(payload['sub'])])
        return rows[0] if rows else None
    except (jwt.InvalidTokenError, ValueError, KeyError, TypeError):
        return None


def install_navigation(app):
    def home(user):
        return '/ui/' + ('schedule' if user['role'] == 'student' else 'camera')

    @app.middleware('http')
    async def protect_pages(request, call_next):
        path = request.url.path
        if path.startswith('/_pages/'):
            name = path.split('/')[2]
            user = current_user(request)
            if not user:
                return HTMLResponse('Phiên đăng nhập đã hết hạn. <a href="/login" target="_top">Đăng nhập lại</a>', status_code=401)
            if name not in PAGES or user['role'] not in PAGES[name][1]:
                return HTMLResponse('Bạn không có quyền truy cập trang này.', status_code=403)
        response = await call_next(request)
        if path.startswith(('/ui', '/_pages/', '/login')):
            response.headers['Cache-Control'] = 'no-store'
        return response

    def login_page(message=''):
        return HTMLResponse(document('Đăng nhập', f'''<section class="card"><h1>FaceID</h1><p>Đăng nhập để quản lý và điểm danh khuôn mặt.</p><form method="post" action="/login"><label>Tên đăng nhập<input name="username" autocomplete="username" required></label><label>Mật khẩu<input name="password" type="password" autocomplete="current-password" required></label><p>{escape(message)}</p><button>Đăng nhập</button></form><p><a href="/register">Tạo tài khoản giáo viên</a></p></section>'''))

    def same_origin(request):
        origin = request.headers.get('origin')
        return origin is None or origin.rstrip('/') == str(request.base_url).rstrip('/')

    @app.get('/login', response_class=HTMLResponse)
    def login_get(request: Request):
        user = current_user(request)
        return RedirectResponse(home(user), status_code=303) if user else login_page()

    @app.post('/login')
    async def login_post(request: Request):
        if not same_origin(request):
            return HTMLResponse('Invalid origin', status_code=403)
        form = await request.form()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://internal') as client:
            response = await client.post('/auth/login', json={'username': form.get('username'), 'password': form.get('password')})
        if response.status_code != 200:
            return login_page('Tên đăng nhập hoặc mật khẩu không đúng.')
        data = response.json()
        result = RedirectResponse(home(data['user']), status_code=303)
        result.set_cookie(COOKIE, data['accessToken'], httponly=True, samesite='lax', secure=request.url.scheme == 'https', max_age=data['expiresIn'], path='/')
        return result

    @app.get('/register', response_class=HTMLResponse)
    def register_get():
        return HTMLResponse(document('Tạo tài khoản', '''<section class="card"><h1>Tạo tài khoản giáo viên</h1><form method="post" action="/register"><label>Họ và tên<input name="fullName" required></label><label>Tên đăng nhập<input name="username" required></label><label>Mật khẩu<input name="password" type="password" minlength="8" required></label><button>Tạo tài khoản</button></form><p><a href="/login">Về đăng nhập</a></p></section>'''))

    @app.post('/register')
    async def register_post(request: Request):
        if not same_origin(request):
            return HTMLResponse('Invalid origin', status_code=403)
        form = await request.form()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://internal') as client:
            response = await client.post('/auth/register', json={key: form.get(key) for key in ('username', 'password', 'fullName')})
        if response.status_code == 201:
            return login_page('Đã tạo tài khoản. Bạn có thể đăng nhập.')
        return HTMLResponse(document('Lỗi tạo tài khoản', '<section class="card"><p>' + escape(str(response.json().get('message', 'Dữ liệu không hợp lệ'))) + '</p><a href="/register">Thử lại</a></section>'), status_code=400)

    @app.post('/logout')
    def logout(request: Request):
        if not same_origin(request):
            return HTMLResponse('Invalid origin', status_code=403)
        response = RedirectResponse('/login', status_code=303)
        response.delete_cookie(COOKIE, path='/')
        return response

    @app.get('/ui')
    @app.get('/ui/')
    def index(request: Request):
        user = current_user(request)
        return RedirectResponse(home(user) if user else '/login', status_code=303)

    @app.get('/ui/{name}', response_class=HTMLResponse)
    def screen(name: str, request: Request):
        user = current_user(request)
        if not user:
            return RedirectResponse('/login', status_code=303)
        if name not in PAGES:
            return HTMLResponse('Không tìm thấy trang.', status_code=404)
        if user['role'] not in PAGES[name][1]:
            return HTMLResponse('Bạn không có quyền truy cập trang này.', status_code=403)
        links = ''.join(f'<a class="{"active" if key == name else ""}" href="/ui/{key}">{title}</a>' for key, (title, roles) in PAGES.items() if user['role'] in roles)
        body = f'''<header><strong>FaceID</strong><span>{escape(user['fullName'])}</span><form method="post" action="/logout"><button>Đăng xuất</button></form></header><div class="layout"><nav>{links}</nav><main><iframe title="{PAGES[name][0]}" src="/_pages/{name}/" onload="fitPageFrame(this)"></iframe></main></div>'''
        return HTMLResponse(document(PAGES[name][0], body))
