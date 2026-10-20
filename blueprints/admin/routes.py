# blueprints/admin/routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import db, User, MikroTikDevice, AuditLog, PPPoEProfile, PPPoESubscription
from blueprints.mikrotik.service import PPPoEService
from datetime import datetime
from functools import wraps

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('هذه الصفحة للمسؤول فقط', 'danger')
            return redirect(url_for('pppoe.dashboard'))
        return f(*args, **kwargs)
    return decorated

def supervisor_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_supervisor:
            flash('لا تملك صلاحية الوصول', 'danger')
            return redirect(url_for('pppoe.dashboard'))
        return f(*args, **kwargs)
    return decorated

def log_audit(action, description='', resource='admin', resource_id=None):
    try:
        log = AuditLog(user_id=current_user.id, action=action, resource=resource,
                       resource_id=resource_id, description=description,
                       ip_address=request.remote_addr or '')
        db.session.add(log)
        db.session.commit()
    except Exception:
        pass

# ======== لوحة الإدارة ========
@admin_bp.route('/')
@login_required
@supervisor_required
def index():
    devices = MikroTikDevice.query.all()
    users = User.query.order_by(User.created_at.desc()).all()
    total_subs = PPPoESubscription.query.count()
    total_active = PPPoESubscription.query.filter_by(status='active').count()
    recent_logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(20).all()
    return render_template('admin/index.html',
        devices=devices, users=users,
        total_subs=total_subs, total_active=total_active,
        recent_logs=recent_logs)

# ======== إدارة الأجهزة ========
@admin_bp.route('/devices')
@login_required
@admin_required
def devices():
    devices = MikroTikDevice.query.order_by(MikroTikDevice.name).all()
    return render_template('admin/devices.html', devices=devices)

@admin_bp.route('/devices/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_device():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        host = request.form.get('host', '').strip()
        api_port = int(request.form.get('api_port', 8728) or 8728)
        rest_port = int(request.form.get('rest_port', 443) or 443)
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        use_ssl = bool(request.form.get('use_ssl'))
        use_rest = bool(request.form.get('use_rest'))
        location = request.form.get('location', '').strip()
        notes = request.form.get('notes', '').strip()

        if not all([name, host, username, password]):
            flash('يرجى تعبئة جميع الحقول المطلوبة', 'danger')
            return render_template('admin/device_form.html', device=None)

        device = MikroTikDevice(
            name=name, host=host, api_port=api_port, rest_port=rest_port,
            username=username, password=password, use_ssl=use_ssl,
            use_rest=use_rest, location=location, notes=notes
        )
        db.session.add(device)
        db.session.commit()
        log_audit('create', f'إضافة جهاز جديد: {name}', 'device', device.id)
        flash(f'تمت إضافة الجهاز "{name}" بنجاح', 'success')
        return redirect(url_for('admin.devices'))
    return render_template('admin/device_form.html', device=None)

@admin_bp.route('/devices/<int:device_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_device(device_id):
    device = MikroTikDevice.query.get_or_404(device_id)
    if request.method == 'POST':
        device.name = request.form.get('name', device.name).strip()
        device.host = request.form.get('host', device.host).strip()
        device.api_port = int(request.form.get('api_port', device.api_port) or 8728)
        device.rest_port = int(request.form.get('rest_port', device.rest_port) or 443)
        device.username = request.form.get('username', device.username).strip()
        new_pass = request.form.get('password', '').strip()
        if new_pass:
            device.password = new_pass
        device.use_ssl = bool(request.form.get('use_ssl'))
        device.use_rest = bool(request.form.get('use_rest'))
        device.location = request.form.get('location', '').strip()
        device.notes = request.form.get('notes', '').strip()
        db.session.commit()
        log_audit('update', f'تعديل الجهاز: {device.name}', 'device', device.id)
        flash('تم تحديث بيانات الجهاز بنجاح', 'success')
        return redirect(url_for('admin.devices'))
    return render_template('admin/device_form.html', device=device)

@admin_bp.route('/devices/<int:device_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_device(device_id):
    device = MikroTikDevice.query.get_or_404(device_id)
    name = device.name
    db.session.delete(device)
    db.session.commit()
    log_audit('delete', f'حذف الجهاز: {name}', 'device', device_id)
    return jsonify({'ok': True, 'message': f'تم حذف الجهاز "{name}" بنجاح'})

@admin_bp.route('/devices/<int:device_id>/test', methods=['POST'])
@login_required
@admin_required
def test_device(device_id):
    device = MikroTikDevice.query.get_or_404(device_id)
    svc = PPPoEService(device)
    result = svc.test_connection()
    if result.ok:
        ver = result.data.get('version', '') if isinstance(result.data, dict) else ''
        if ver:
            device.ros_version = ver
        device.last_seen = datetime.utcnow()
        device.last_status = 'online'
        db.session.commit()
    else:
        device.last_status = 'offline'
        db.session.commit()
    return jsonify(result.to_dict())

# ======== إدارة المستخدمين ========
@admin_bp.route('/users')
@login_required
@admin_required
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=all_users)

@admin_bp.route('/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip() or None
        password = request.form.get('password', '')
        role = request.form.get('role', 'employee')
        
        if not all([username, full_name, password]):
            flash('يرجى تعبئة جميع الحقول المطلوبة', 'danger')
            return render_template('admin/user_form.html', user=None)
        
        if User.query.filter_by(username=username).first():
            flash('اسم المستخدم موجود مسبقاً', 'danger')
            return render_template('admin/user_form.html', user=None)
        
        user = User(
            username=username, full_name=full_name, email=email, role=role,
            can_add=bool(request.form.get('can_add')),
            can_edit=bool(request.form.get('can_edit')),
            can_delete=bool(request.form.get('can_delete')),
            can_disconnect=bool(request.form.get('can_disconnect')),
            can_view_password=bool(request.form.get('can_view_password')),
            can_view_finance=bool(request.form.get('can_view_finance')),
            notes=request.form.get('notes', '').strip()
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        log_audit('create', f'إضافة موظف جديد: {username}', 'user', user.id)
        flash(f'تمت إضافة الموظف "{full_name}" بنجاح', 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/user_form.html', user=None)

@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        user.full_name = request.form.get('full_name', user.full_name).strip()
        user.email = request.form.get('email', '').strip() or None
        user.role = request.form.get('role', user.role)
        user.is_active = bool(request.form.get('is_active'))
        user.can_add = bool(request.form.get('can_add'))
        user.can_edit = bool(request.form.get('can_edit'))
        user.can_delete = bool(request.form.get('can_delete'))
        user.can_disconnect = bool(request.form.get('can_disconnect'))
        user.can_view_password = bool(request.form.get('can_view_password'))
        user.can_view_finance = bool(request.form.get('can_view_finance'))
        user.notes = request.form.get('notes', '').strip()
        new_pass = request.form.get('password', '').strip()
        if new_pass:
            user.set_password(new_pass)
        db.session.commit()
        log_audit('update', f'تعديل الموظف: {user.username}', 'user', user.id)
        flash('تم تحديث بيانات الموظف بنجاح', 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/user_form.html', user=user)

@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        return jsonify({'ok': False, 'message': 'لا يمكنك تعطيل حسابك الخاص'})
    user.is_active = not user.is_active
    db.session.commit()
    status = 'تفعيل' if user.is_active else 'تعطيل'
    log_audit('update', f'{status} الموظف: {user.username}', 'user', user.id)
    return jsonify({'ok': True, 'message': f'تم {status} الحساب', 'is_active': user.is_active})

@admin_bp.route('/logs')
@login_required
@supervisor_required
def audit_logs():
    page = request.args.get('page', 1, type=int)
    per_page = 50
    q = request.args.get('q', '').strip()
    query = AuditLog.query
    if q:
        query = query.filter(AuditLog.description.contains(q))
    logs = query.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return render_template('admin/logs.html', logs=logs, q=q)
