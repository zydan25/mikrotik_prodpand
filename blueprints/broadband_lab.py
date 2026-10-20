"""مختبر مستقل لاختبار مصادر اشتراكات وباقات البرودباند على MikroTik."""
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from models import db, MikroTikDevice, DeviceLog, AuditLog
from blueprints.mikrotik.service import PPPoEService
from datetime import datetime
import json

lab_bp = Blueprint('broadband_lab', __name__, url_prefix='/admin/broadband-lab')

SOURCES = {
    'ppp_secrets': {'label': 'اشتراكات PPPoE (PPP Secrets)', 'path': '/ppp/secret', 'props': '.id,name,profile,service,caller-id,remote-address,disabled,comment,limit-bytes-in,limit-bytes-out,last-logged-out'},
    'ppp_profiles': {'label': 'بروفايلات PPP', 'path': '/ppp/profile', 'props': '.id,name,rate-limit,local-address,remote-address,dns-server,session-timeout,idle-timeout'},
    'um_profiles': {'label': 'باقات User Manager', 'path': '/user-manager/profile', 'legacy_path': '/tool/user-manager/profile', 'props': '.id,name,name-for-users,price,validity,starts-when,override-shared-users'},
    'um_limitations': {'label': 'قيود User Manager', 'path': '/user-manager/limitation', 'legacy_path': '/tool/user-manager/profile/limitation', 'props': '.id,name,transfer-limit,upload-limit,download-limit,uptime-limit,rate-limit'},
    'um_profile_limitations': {'label': 'ربط الباقات بالقيود', 'path': '/user-manager/profile-limitation', 'legacy_path': '/tool/user-manager/profile/profile-limitation', 'props': '.id,profile,limitation,from-time,till-time,weekdays'},
    'um_users': {'label': 'مستخدمو User Manager مباشرة', 'path': '/user-manager/user', 'legacy_paths': ['/tool/user-manager/user'], 'props': '.id,name,disabled,group,shared-users,caller-id,attributes,last-logged-in'},
    'um_user_profiles': {'label': 'باقات المستخدمين المسندة (User Profiles)', 'path': '/user-manager/user-profile', 'legacy_paths': ['/tool/user-manager/user/profile', '/tool/user-manager/user-profile'], 'props': '.id,user,profile,state,end-time'},
}

def _read_source(service, source):
    """يقرأ مصدر User Manager مع تجربة المسارات الحديثة والقديمة عبر Binary API."""
    paths = [source['path']]
    if not service._use_rest:
        paths.extend(source.get('legacy_paths', []))

    last_error = None
    for path in paths:
        try:
            if service._use_rest:
                data = service._rest().get(path, params={'.proplist': source['props']})
                if isinstance(data, dict):
                    data = [data] if data else []
                rows = data if isinstance(data, list) else []
            else:
                client = service._binary()
                try:
                    resource_path = path.lstrip('/')
                    resource, _api = client.get_resource([path, resource_path])
                    data = resource.call('print', {'.proplist': source['props']})
                    rows = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
                finally:
                    client.disconnect()
            return rows, path
        except Exception as exc:
            last_error = exc
            error_text = str(exc).lower()
            if len(paths) > 1 and ('no such command prefix' in error_text or 'unknown command' in error_text):
                continue
            raise

    if last_error:
        raise last_error
    return [], source['path']

@lab_bp.route('/', methods=['GET'])
@login_required
def index():
    if not (current_user.is_admin or current_user.is_supervisor):
        return 'غير مصرح', 403
    devices = MikroTikDevice.query.filter_by(is_active=True).order_by(MikroTikDevice.name).all()
    logs = DeviceLog.query.filter(DeviceLog.action.like('broadband-lab:%')).order_by(DeviceLog.created_at.desc()).limit(30).all()
    return render_template('broadband_lab/index.html', devices=devices, logs=logs, sources=SOURCES)

@lab_bp.route('/fetch', methods=['POST'])
@login_required
def fetch_source():
    if not (current_user.is_admin or current_user.is_supervisor):
        return jsonify({'ok': False, 'message': 'غير مصرح'}), 403
    payload = request.get_json(silent=True) or request.form
    try:
        device_id = int(payload.get('device_id', 0))
    except (TypeError, ValueError):
        device_id = 0
    key = str(payload.get('source', ''))
    device = db.session.get(MikroTikDevice, device_id)
    if not device or not device.is_active:
        return jsonify({'ok': False, 'message': 'اختر جهاز MikroTik فعالاً'}), 400
    source = SOURCES.get(key)
    if not source:
        return jsonify({'ok': False, 'message': 'مصدر غير معروف'}), 400

    ok, message, rows = False, '', []
    used_path = source['path']
    try:
        service = PPPoEService(device)
        rows, used_path = _read_source(service, source)
        ok = True
        message = f'تمت قراءة المصدر بنجاح؛ عدد السجلات: {len(rows)}'
    except Exception as exc:
        message = f'{type(exc).__name__}: {exc}'
    try:
        db.session.add(DeviceLog(device_id=device.id, action=f'broadband-lab:{key}', ok=ok, message=f"{used_path} | {message}"[:4000]))
        db.session.add(AuditLog(user_id=current_user.id, action='broadband_lab_fetch', resource='mikrotik_source', resource_id=device.id,
            description=f"اختبار {source['label']} من {device.name}: {message}"[:4000],
            ip_address=request.headers.get('X-Forwarded-For', request.remote_addr or ''),
            extra={'source': key, 'path': used_path, 'ok': ok, 'count': len(rows), 'sample': rows[:5]}))
        db.session.commit()
    except Exception:
        db.session.rollback()

    return jsonify({'ok': ok, 'source': key, 'label': source['label'], 'path': used_path,
                    'device': device.name, 'count': len(rows), 'message': message, 'data': rows[:500],
                    'truncated': len(rows) > 500, 'checked_at': datetime.utcnow().isoformat()})

