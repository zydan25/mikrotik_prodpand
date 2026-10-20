import re
# blueprints/pppoe/routes.py - إدارة اشتراكات PPPoE والتجديد السريع والباقات
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import db, MikroTikDevice, PPPoEProfile, PPPoESubscription, Payment, AuditLog
from blueprints.mikrotik.service import PPPoEService
from datetime import datetime, timedelta
from functools import wraps

pppoe_bp = Blueprint('pppoe', __name__, url_prefix='')

def require_permission(perm):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if not current_user.is_admin and not getattr(current_user, perm, False):
                return jsonify({'ok': False, 'message': 'لا تملك صلاحية هذا الإجراء'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

def log_audit(action, description='', resource='subscription', resource_id=None, extra=None):
    try:
        log = AuditLog(
            user_id=current_user.id, action=action, resource=resource,
            resource_id=resource_id, description=description,
            ip_address=request.remote_addr or '', extra=extra or {}
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        pass

def _get_device_or_first(device_id=None):
    if device_id:
        return MikroTikDevice.query.get(device_id)
    return MikroTikDevice.query.filter_by(is_active=True).first()

# ======================================================
# لوحة التحكم الرئيسية - Dashboard
# ======================================================
@pppoe_bp.route('/')
@login_required
def dashboard():
    devices = MikroTikDevice.query.filter_by(is_active=True).all()
    selected_id = request.args.get('device_id', type=int)
    selected = _get_device_or_first(selected_id)

    stats = {
        'total': 0, 'active': 0, 'disabled': 0, 'expired': 0,
        'online': 0, 'devices': len(devices), 'today_renewals': 0,
        'today_sales': 0, 'expiring_soon': 0
    }

    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if selected:
        subs = PPPoESubscription.query.filter_by(device_id=selected.id)
        stats['total'] = subs.count()
        stats['active'] = subs.filter(PPPoESubscription.disabled == False, (PPPoESubscription.expires_at == None) | (PPPoESubscription.expires_at >= now)).count()
        stats['disabled'] = subs.filter_by(disabled=True).count()
        stats['expired'] = subs.filter(PPPoESubscription.expires_at != None, PPPoESubscription.expires_at < now).count()
        stats['expiring_soon'] = subs.filter(
            PPPoESubscription.expires_at != None,
            PPPoESubscription.expires_at >= now,
            PPPoESubscription.expires_at <= now + timedelta(days=5)
        ).count()

        # تجديدات ومبيعات اليوم على هذا الجهاز
        today_payments = Payment.query.join(PPPoESubscription).filter(
            PPPoESubscription.device_id == selected.id,
            Payment.paid_at >= today_start
        ).all()
        stats['today_renewals'] = len(today_payments)
        stats['today_sales'] = sum(float(p.amount) for p in today_payments)

    # آخر العمليات وحالة الاتصال اللحظية
    recent_subs = PPPoESubscription.query.filter_by(device_id=selected.id).order_by(PPPoESubscription.updated_at.desc()).limit(8).all() if selected else []
    if selected:
        try:
            svc = PPPoEService(selected)
            live_map = svc.get_live_sessions_and_traffic()
            stats['online'] = len(live_map)
            for s in recent_subs:
                if s.username in live_map:
                    s.is_online = True
                    s.uptime = live_map[s.username]['uptime']
                    s.current_ip = live_map[s.username]['address']
                    s.total_bytes_in = live_map[s.username]['rx']
                    s.total_bytes_out = live_map[s.username]['tx']
                else:
                    s.is_online = False
        except Exception:
            pass

    # الباقات والفئات للتجديد السريع
    profiles = PPPoEProfile.query.filter_by(device_id=selected.id, is_active=True).all() if selected else []
    categories = sorted(list(set(p.category or 'عام' for p in profiles))) if profiles else ['عام']

    return render_template('pppoe/dashboard.html',
        devices=devices, selected=selected, stats=stats,
        recent_subs=recent_subs, profiles=profiles, categories=categories)

# ======================================================
# قائمة الاشتراكات (مع دعم بطاقات الهاتف المتجاوبة)
# ======================================================
@pppoe_bp.route('/subscriptions')
@login_required
def subscriptions():
    devices = MikroTikDevice.query.filter_by(is_active=True).all()
    selected_id = request.args.get('device_id', type=int)
    selected = _get_device_or_first(selected_id)

    page = request.args.get('page', 1, type=int)
    per_page = 30
    q = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '')
    profile_filter = request.args.get('profile_id', type=int)
    category_filter = request.args.get('category', '').strip()

    query = PPPoESubscription.query
    if selected:
        query = query.filter_by(device_id=selected.id)
    if q:
        query = query.filter(
            db.or_(
                PPPoESubscription.username.ilike(f'%{q}%'),
                PPPoESubscription.customer_name.ilike(f'%{q}%'),
                PPPoESubscription.customer_phone.ilike(f'%{q}%'),
                PPPoESubscription.comment.ilike(f'%{q}%')
            )
        )

    now = datetime.utcnow()
    if status_filter == 'active':
        query = query.filter(PPPoESubscription.disabled == False, (PPPoESubscription.expires_at == None) | (PPPoESubscription.expires_at >= now))
    elif status_filter == 'disabled':
        query = query.filter_by(disabled=True)
    elif status_filter == 'expired':
        query = query.filter(PPPoESubscription.expires_at != None, PPPoESubscription.expires_at < now)

    if profile_filter:
        query = query.filter(PPPoESubscription.profile_id == profile_filter)
    if category_filter:
        query = query.join(PPPoEProfile).filter(PPPoEProfile.category == category_filter)

    subs = query.order_by(PPPoESubscription.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)

    profiles = PPPoEProfile.query.filter_by(device_id=selected.id).all() if selected else []
    categories = sorted(list(set(p.category or 'عام' for p in profiles))) if profiles else ['عام']

    # دمج بيانات الجلسات النشطة وحركة البيانات اللحظية
    if selected:
        try:
            svc = PPPoEService(selected)
            live_map = svc.get_live_sessions_and_traffic()
            for s in subs.items:
                if s.username in live_map:
                    s.is_online = True
                    s.uptime = live_map[s.username]['uptime']
                    s.current_ip = live_map[s.username]['address']
                    s.total_bytes_in = live_map[s.username]['rx']
                    s.total_bytes_out = live_map[s.username]['tx']
                else:
                    s.is_online = False
        except Exception:
            pass

    return render_template('pppoe/subscriptions.html',
        devices=devices, selected=selected, subs=subs,
        profiles=profiles, categories=categories, q=q,
        status_filter=status_filter, profile_filter=profile_filter,
        category_filter=category_filter)

# ======================================================
# API البحث وجلب بيانات المشترك للتعبئة التلقائية
# ======================================================
@pppoe_bp.route('/api/sub-lookup')
@login_required
def api_sub_lookup():
    device_id = request.args.get('device_id', type=int)
    q = request.args.get('q', '').strip()

    query = PPPoESubscription.query
    if device_id:
        query = query.filter_by(device_id=device_id)
    if q:
        query = query.filter(
            db.or_(
                PPPoESubscription.username.ilike(f'%{q}%'),
                PPPoESubscription.customer_name.ilike(f'%{q}%'),
                PPPoESubscription.customer_phone.ilike(f'%{q}%')
            )
        )
    
    subs = query.order_by(PPPoESubscription.username).limit(50).all()
    res = []
    for s in subs:
        res.append({
            'id': s.id,
            'username': s.username,
            'customer_name': s.customer_name or '',
            'customer_phone': s.customer_phone or '',
            'profile_id': s.profile_id,
            'profile_name': s.profile.name if s.profile else '',
            'category': s.profile.category if s.profile else 'عام',
            'price': float(s.price or (s.profile.price if s.profile else 0)),
            'currency': s.price_currency or 'IQD',
            'expires_at': s.expires_at.strftime('%Y-%m-%d') if s.expires_at else '',
            'days_remaining': s.days_remaining,
            'disabled': s.disabled,
            'comment': s.comment or ''
        })
    return jsonify({'ok': True, 'subs': res})

# ======================================================
# API جلب الباقات حسب الفئة
# ======================================================
@pppoe_bp.route('/api/profiles-by-category')
@login_required
def api_profiles_by_category():
    device_id = request.args.get('device_id', type=int)
    category = request.args.get('category', '').strip()

    query = PPPoEProfile.query.filter_by(is_active=True)
    if device_id:
        query = query.filter_by(device_id=device_id)
    if category and category != 'all':
        query = query.filter_by(category=category)

    profiles = query.order_by(PPPoEProfile.name).all()
    res = []
    for p in profiles:
        res.append({
            'id': p.id,
            'name': p.name,
            'category': p.category or 'عام',
            'rate_limit': p.rate_limit or '',
            'price': float(p.price or 0),
            'currency': p.price_currency or 'IQD'
        })
    return jsonify({'ok': True, 'profiles': res})

# ======================================================
# تجديد وحفظ الاشتراك السريع (Quick Renewal & Subscription)
# ======================================================
@pppoe_bp.route('/subscriptions/quick-renew', methods=['POST'])
@login_required
def quick_renew():
    if not (current_user.is_admin or current_user.can_add or current_user.can_edit):
        return jsonify({'ok': False, 'message': 'لا تملك صلاحية إضافة أو تجديد الاشتراكات'}), 403

    data = request.get_json() or request.form
    mode = str(data.get('mode', 'existing')) # 'existing' (تجديد ليوزر سابق) أو 'new' (يوزر جديد)
    device_id = int(data.get('device_id', 0) or 0)
    device = MikroTikDevice.query.get(device_id)
    if not device:
        return jsonify({'ok': False, 'message': 'يرجى تحديد جهاز الراوتر'})

    profile_id = int(data.get('profile_id', 0) or 0)
    profile = PPPoEProfile.query.get(profile_id) if profile_id else None
    if not profile:
        return jsonify({'ok': False, 'message': 'يرجى اختيار الباقة المراد الاشتراك بها'})

    months = int(data.get('months', 1) or 1)
    if months <= 0:
        months = 1

    price = float(data.get('price', profile.price or 0) or 0)
    currency = str(data.get('currency', profile.price_currency or 'IQD'))
    now = datetime.utcnow()

    # 1. حالة: تجديد ليوزر سابق موجود
    if mode == 'existing':
        sub_id = int(data.get('sub_id', 0) or 0)
        username = str(data.get('username', '')).strip()

        sub = None
        if sub_id:
            sub = PPPoESubscription.query.get(sub_id)
        elif username:
            sub = PPPoESubscription.query.filter_by(device_id=device.id, username=username).first()

        if not sub:
            return jsonify({'ok': False, 'message': 'لم يتم العثور على اسم المستخدم السابق للتجديد'})

        # تحديث المايكروتك إذا تم تغيير الباقة أو كان الحساب معطلاً
        svc = PPPoEService(device)
        need_update = {}
        if sub.profile_id != profile.id:
            need_update['profile'] = profile.name
        if sub.disabled:
            need_update['disabled'] = 'no'

        if need_update and sub.router_secret_id:
            res = svc.update_secret(sub.router_secret_id, need_update)
            if not res.ok:
                return jsonify({'ok': False, 'message': f'فشل التحديث في الراوتر: {res.message}'})

        # تمديد التاريخ بالاعتماد على صلاحية الباقة الحقيقية
        val_days = profile.validity_days if profile.validity_days else 30
        if not sub.expires_at or sub.expires_at <= now:
            sub.started_at = now
            base_date = now
        else:
            base_date = sub.expires_at
        sub.expires_at = base_date + timedelta(days=val_days * months)
        sub.profile_id = profile.id
        sub.price = price
        sub.price_currency = currency
        sub.disabled = False
        sub.status = 'active'
        sub.last_edited_by_id = current_user.id
        sub.updated_at = now

        # تحديث بيانات العميل الاختيارية إن وجدت
        if data.get('customer_name'): sub.customer_name = str(data.get('customer_name'))
        if data.get('customer_phone'): sub.customer_phone = str(data.get('customer_phone'))
        if data.get('comment'): sub.comment = str(data.get('comment'))

        # تسجيل السند / الدفعة لحساب الموظف المحصل
        payment = Payment(
            subscription_id=sub.id,
            amount=price,
            currency=currency,
            payment_type='renewal',
            months=months,
            paid_at=now,
            collected_by_id=current_user.id,
            notes=f'تجديد باقة {profile.name} لمدة {months} شهر'
        )
        db.session.add(payment)
        db.session.commit()

        log_audit('renew', f'تجديد اشتراك {sub.username} باقة {profile.name} بمبلغ {price}', 'subscription', sub.id)

        return jsonify({
            'ok': True,
            'message': f'تم تجديد اشتراك "{sub.username}" بنجاح وتمديده إلى {sub.expires_at.strftime("%Y-%m-%d")}',
            'sub_id': sub.id,
            'expires_at': sub.expires_at.strftime('%Y-%m-%d'),
            'amount_collected': price
        })

    # 2. حالة: مشترك / يوزر جديد
    else:
        username = str(data.get('username', '')).strip()
        password = str(data.get('password', '')).strip()
        if not username or not password:
            return jsonify({'ok': False, 'message': 'يرجى إدخال اسم المستخدم وكلمة المرور للحساب الجديد'})

        if PPPoESubscription.query.filter_by(device_id=device.id, username=username).first():
            return jsonify({'ok': False, 'message': f'اسم المستخدم "{username}" موجود مسبقاً على هذا الراوتر!'})

        # إضافة في المايكروتك
        svc = PPPoEService(device)
        comment = str(data.get('comment', ''))
        result = svc.add_secret(
            username=username,
            password=password,
            profile=profile.name,
            comment=comment,
            static_ip=str(data.get('static_ip', '')),
            caller_id=str(data.get('caller_id', ''))
        )
        if not result.ok:
            return jsonify({'ok': False, 'message': f'خطأ من الراوتر: {result.message}'})

        router_id = result.data.get('router_id', '') if isinstance(result.data, dict) else ''
        val_days = profile.validity_days if profile.validity_days else 30
        sub_started = now
        if data.get('started_at'):
            try:
                sub_started = datetime.strptime(str(data.get('started_at')), '%Y-%m-%d')
            except Exception:
                pass
        expires_at = sub_started + timedelta(days=val_days * months)

        sub = PPPoESubscription(
            device_id=device.id,
            profile_id=profile.id,
            username=username,
            password=password,
            router_secret_id=router_id,
            service='pppoe',
            caller_id=str(data.get('caller_id', '')),
            static_ip=str(data.get('static_ip', '')),
            customer_name=str(data.get('customer_name', '')),
            customer_phone=str(data.get('customer_phone', '')),
            customer_address=str(data.get('customer_address', '')),
            price=price,
            price_currency=currency,
            started_at=now,
            expires_at=expires_at,
            comment=comment,
            status='active',
            created_by_id=current_user.id
        )
        db.session.add(sub)
        db.session.flush()

        if price > 0:
            pay = Payment(
                subscription_id=sub.id,
                amount=price,
                currency=currency,
                payment_type='new',
                months=months,
                paid_at=now,
                collected_by_id=current_user.id,
                notes=f'اشتراك جديد باقة {profile.name}'
            )
            db.session.add(pay)

        db.session.commit()
        log_audit('create', f'إنشاء اشتراك جديد: {username} باقة {profile.name}', 'subscription', sub.id)

        return jsonify({
            'ok': True,
            'message': f'تم إنشاء وتفعيل الاشتراك الجديد "{username}" بنجاح حتى {expires_at.strftime("%Y-%m-%d")}',
            'sub_id': sub.id,
            'expires_at': expires_at.strftime('%Y-%m-%d'),
            'amount_collected': price
        })

# ======================================================
# تفاصيل المشترك
# ======================================================
@pppoe_bp.route('/subscriptions/<int:sub_id>')
@login_required
def subscription_detail(sub_id):
    sub = PPPoESubscription.query.get_or_404(sub_id)
    payments = Payment.query.filter_by(subscription_id=sub.id).order_by(Payment.paid_at.desc()).all()
    return render_template('pppoe/subscription_detail.html', sub=sub, payments=payments)

# ======================================================
# إضافة مشترك (النموذج التقليدي الكامل)
# ======================================================
@pppoe_bp.route('/subscriptions/add', methods=['GET', 'POST'])
@login_required
def add_subscription():
    devices = MikroTikDevice.query.filter_by(is_active=True).all()
    if request.method == 'GET':
        selected_id = request.args.get('device_id', type=int)
        selected = _get_device_or_first(selected_id)
        profiles = PPPoEProfile.query.filter_by(device_id=selected.id, is_active=True).all() if selected else []
        categories = sorted(list(set(p.category or 'عام' for p in profiles))) if profiles else ['عام']
        return render_template('pppoe/subscription_form.html',
            devices=devices, selected=selected, profiles=profiles, categories=categories, sub=None)

    data = request.get_json() or request.form
    device_id = int(data.get('device_id', 0))
    device = MikroTikDevice.query.get(device_id)
    if not device:
        return jsonify({'ok': False, 'message': 'الجهاز غير موجود'})

    username = str(data.get('username', '')).strip()
    password = str(data.get('password', '')).strip()
    profile_id = int(data.get('profile_id', 0) or 0)

    if not username or not password:
        return jsonify({'ok': False, 'message': 'اسم المستخدم وكلمة المرور مطلوبة'})

    if PPPoESubscription.query.filter_by(device_id=device_id, username=username).first():
        return jsonify({'ok': False, 'message': 'اسم المستخدم موجود بالفعل بهذا الراوتر'})

    profile = PPPoEProfile.query.get(profile_id) if profile_id else None
    profile_name = profile.name if profile else str(data.get('profile_name', 'default'))

    svc = PPPoEService(device)
    result = svc.add_secret(
        username=username,
        password=password,
        profile=profile_name,
        comment=str(data.get('comment', '')),
        static_ip=str(data.get('static_ip', '')),
        caller_id=str(data.get('caller_id', ''))
    )
    if not result.ok:
        return jsonify({'ok': False, 'message': result.message})

    router_id = result.data.get('router_id', '') if isinstance(result.data, dict) else ''

    expires_raw = data.get('expires_at', '')
    expires_at = None
    if expires_raw:
        try:
            expires_at = datetime.strptime(str(expires_raw), '%Y-%m-%d')
        except Exception:
            pass
    if not expires_at:
        expires_at = datetime.utcnow() + timedelta(days=30)

    price = float(data.get('price', 0) or 0)
    sub = PPPoESubscription(
        device_id=device_id,
        profile_id=profile_id or None,
        username=username,
        password=password,
        router_secret_id=router_id,
        service='pppoe',
        caller_id=str(data.get('caller_id', '')),
        static_ip=str(data.get('static_ip', '')),
        customer_name=str(data.get('customer_name', '')),
        customer_phone=str(data.get('customer_phone', '')),
        customer_address=str(data.get('customer_address', '')),
        price=price,
        price_currency=str(data.get('currency', 'IQD')),
        started_at=datetime.utcnow(),
        expires_at=expires_at,
        comment=str(data.get('comment', '')),
        status='active',
        created_by_id=current_user.id
    )
    db.session.add(sub)
    db.session.flush()

    if price > 0:
        pay = Payment(
            subscription_id=sub.id,
            amount=price,
            currency=str(data.get('currency', 'IQD')),
            payment_type='new',
            months=1,
            collected_by_id=current_user.id
        )
        db.session.add(pay)

    db.session.commit()
    log_audit('create', f'إضافة مشترك جديد: {username} على {device.name}', 'subscription', sub.id, {'router_id': router_id})
    return jsonify({'ok': True, 'message': 'تم إضافة المشترك بنجاح', 'sub_id': sub.id})

# ======================================================
# تعديل الاشتراك
# ======================================================
@pppoe_bp.route('/subscriptions/<int:sub_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_subscription(sub_id):
    sub = PPPoESubscription.query.get_or_404(sub_id)
    devices = MikroTikDevice.query.filter_by(is_active=True).all()

    if request.method == 'GET':
        profiles = PPPoEProfile.query.filter_by(device_id=sub.device_id, is_active=True).all()
        categories = sorted(list(set(p.category or 'عام' for p in profiles))) if profiles else ['عام']
        return render_template('pppoe/subscription_form.html',
            devices=devices, selected=sub.device, profiles=profiles, categories=categories, sub=sub)

    if not (current_user.is_admin or current_user.can_edit):
        return jsonify({'ok': False, 'message': 'لا تملك صلاحية التعديل'}), 403

    data = request.get_json() or request.form
    new_password = str(data.get('password', '')).strip()
    profile_id = int(data.get('profile_id', 0) or 0)
    profile = PPPoEProfile.query.get(profile_id) if profile_id else None
    profile_name = profile.name if profile else str(data.get('profile_name', sub.profile.name if sub.profile else 'default'))

    fields = {'profile': profile_name}
    if new_password:
        fields['password'] = new_password
    caller_id = str(data.get('caller_id', sub.caller_id or ''))
    static_ip = str(data.get('static_ip', sub.static_ip or ''))
    if caller_id is not None:
        fields['caller-id'] = caller_id
    if static_ip is not None:
        fields['remote-address'] = static_ip
    comment = str(data.get('comment', sub.comment or ''))
    fields['comment'] = comment

    if sub.router_secret_id:
        svc = PPPoEService(sub.device)
        result = svc.update_secret(sub.router_secret_id, fields)
        if not result.ok:
            return jsonify({'ok': False, 'message': result.message})

    if new_password:
        sub.password = new_password
    sub.profile_id = profile_id or sub.profile_id
    sub.caller_id = caller_id
    sub.static_ip = static_ip
    sub.comment = comment
    sub.customer_name = str(data.get('customer_name', sub.customer_name or ''))
    sub.customer_phone = str(data.get('customer_phone', sub.customer_phone or ''))
    sub.customer_address = str(data.get('customer_address', sub.customer_address or ''))
    sub.customer_notes = str(data.get('customer_notes', sub.customer_notes or ''))
    
    started_raw = data.get('started_at', '')
    if started_raw:
        try:
            sub.started_at = datetime.strptime(str(started_raw), '%Y-%m-%d')
        except Exception:
            pass

    expires_raw = data.get('expires_at', '')
    if expires_raw:
        try:
            sub.expires_at = datetime.strptime(str(expires_raw), '%Y-%m-%d')
        except Exception:
            pass

    sub.updated_at = datetime.utcnow()
    sub.last_edited_by_id = current_user.id
    db.session.commit()
    log_audit('update', f'تعديل المشترك: {sub.username}', 'subscription', sub.id)
    return jsonify({'ok': True, 'message': 'تم حفظ التعديلات بنجاح'})

# ======================================================
# حذف الاشتراك
# ======================================================
@pppoe_bp.route('/subscriptions/<int:sub_id>/delete', methods=['POST'])
@login_required
def delete_subscription(sub_id):
    if not (current_user.is_admin or current_user.can_delete):
        return jsonify({'ok': False, 'message': 'لا تملك صلاحية الحذف'}), 403

    sub = PPPoESubscription.query.get_or_404(sub_id)
    username = sub.username

    if sub.router_secret_id:
        svc = PPPoEService(sub.device)
        result = svc.delete_secret(sub.router_secret_id, sub.username)
        if not result.ok:
            return jsonify({'ok': False, 'message': result.message})

    db.session.delete(sub)
    db.session.commit()
    log_audit('delete', f'حذف المشترك: {username}', 'subscription', sub_id)
    return jsonify({'ok': True, 'message': f'تم حذف المشترك "{username}" بنجاح'})

# ======================================================
# تفعيل / تعطيل المشترك
# ======================================================
@pppoe_bp.route('/subscriptions/<int:sub_id>/toggle-disable', methods=['POST'])
@login_required
def toggle_disable(sub_id):
    if not (current_user.is_admin or current_user.can_edit):
        return jsonify({'ok': False, 'message': 'لا تملك صلاحية هذا الإجراء'}), 403

    sub = PPPoESubscription.query.get_or_404(sub_id)
    new_disabled = not sub.disabled

    if sub.router_secret_id:
        svc = PPPoEService(sub.device)
        result = svc.set_disabled(sub.router_secret_id, new_disabled, sub.username)
        if not result.ok:
            return jsonify({'ok': False, 'message': result.message})

    sub.disabled = new_disabled
    sub.updated_at = datetime.utcnow()
    sub.last_edited_by_id = current_user.id
    db.session.commit()
    action = 'تعطيل' if new_disabled else 'تفعيل'
    log_audit('update', f'{action} المشترك: {sub.username}', 'subscription', sub.id)
    return jsonify({'ok': True, 'message': f'تم {action} المشترك بنجاح', 'disabled': new_disabled})

# ======================================================
# الجلسات النشطة (Active Sessions)
# ======================================================
@pppoe_bp.route('/api/active-sessions/<int:device_id>')
@login_required
def api_active_sessions(device_id):
    device = MikroTikDevice.query.get_or_404(device_id)
    svc = PPPoEService(device)
    result = svc.get_active_sessions()
    return jsonify(result.to_dict())

# ======================================================
# فصل جلسة نشطة
# ======================================================
@pppoe_bp.route('/api/disconnect-session', methods=['POST'])
@login_required
def api_disconnect_session():
    if not (current_user.is_admin or current_user.can_disconnect):
        return jsonify({'ok': False, 'message': 'لا تملك صلاحية فصل الاتصال'}), 403
    data = request.get_json()
    device_id = int(data.get('device_id', 0))
    session_id = str(data.get('session_id', ''))
    device = MikroTikDevice.query.get(device_id)
    if not device or not session_id:
        return jsonify({'ok': False, 'message': 'بيانات غير كاملة'})
    svc = PPPoEService(device)
    result = svc.disconnect_session(session_id)
    if result.ok:
        log_audit('disconnect', f'فصل جلسة {session_id} على {device.name}', 'session')
    return jsonify(result.to_dict())

# ======================================================
# بروفايلات / باقات PPPoE
# ======================================================
@pppoe_bp.route('/profiles')
@login_required
def profiles():
    devices = MikroTikDevice.query.filter_by(is_active=True).all()
    selected_id = request.args.get('device_id', type=int)
    selected = _get_device_or_first(selected_id)
    profiles_list = PPPoEProfile.query.filter_by(device_id=selected.id).all() if selected else []
    categories = sorted(list(set(p.category or 'عام' for p in profiles_list))) if profiles_list else ['عام']
    standard_categories = ['برودباند عام', 'برودباند منزلي', 'سرعات فائقة / VIP', 'ألعاب (Gaming)', 'تجاري / شركات', 'خدمات شبكات و VPN', 'باقات النظام', 'باقات التوقف والحد']
    db_categories = [p.category for p in profiles_list if p.category]
    available_categories = sorted(list(set(standard_categories + db_categories)))
    return render_template('pppoe/profiles.html',
        devices=devices, selected=selected, profiles=profiles_list, categories=categories,
        available_categories=available_categories)

# ======================================================
# تعديل فئة وسعر الباقة
# ======================================================
@pppoe_bp.route('/profiles/<int:profile_id>/edit-pricing', methods=['POST'])
@login_required
def edit_profile_pricing(profile_id):
    if not (current_user.is_admin or current_user.is_supervisor):
        return jsonify({'ok': False, 'message': 'لا تملك صلاحية تعديل الباقات'}), 403
    p = PPPoEProfile.query.get_or_404(profile_id)
    data = request.get_json() or request.form
    if 'category' in data:
        p.category = str(data.get('category', 'عام')).strip() or 'عام'
    if 'price' in data:
        p.price = float(data.get('price', 0) or 0)
    if 'currency' in data:
        p.price_currency = str(data.get('currency', 'IQD'))
    if 'quota_gb' in data:
        p.quota_gb = float(data.get('quota_gb', 0) or 0)
    if 'validity_days' in data:
        p.validity_days = int(data.get('validity_days', 30) or 30)
    db.session.commit()
    log_audit('update_profile', f'تعديل فئة/سعر/حجم باقة: {p.name}', 'profile', p.id)
    return jsonify({'ok': True, 'message': f'تم تحديث باقة "{p.name}" بنجاح'})

# ======================================================
# مزامنة الباقات من الراوتر
# ======================================================
@pppoe_bp.route('/api/sync-profiles/<int:device_id>', methods=['POST'])
@login_required
def api_sync_profiles(device_id):
    if not (current_user.is_admin or current_user.is_supervisor):
        return jsonify({'ok': False, 'message': 'لا تملك صلاحية المزامنة'}), 403
    device = MikroTikDevice.query.get_or_404(device_id)
    svc = PPPoEService(device)
    result = svc.get_profiles()
    if not result.ok:
        return jsonify(result.to_dict())

    created, updated = 0, 0
    for row in result.data:
        rid = str(row.get('.id', ''))
        name = str(row.get('name', '')).strip()
        if not name: continue
        existing = PPPoEProfile.query.filter_by(device_id=device_id, name=name).first()
        if existing:
            existing.router_id = rid
            existing.rate_limit = row.get('rate-limit', existing.rate_limit)
            existing.local_address = row.get('local-address', existing.local_address)
            existing.remote_address = row.get('remote-address', existing.remote_address)
            existing.dns_server = row.get('dns-server', existing.dns_server)
            existing.session_timeout = row.get('session-timeout', existing.session_timeout)
            existing.synced_at = datetime.utcnow()
            existing.raw_payload = row
            updated += 1
        else:
            p = PPPoEProfile(
                device_id=device_id,
                name=name,
                category=auto_detect_category(name, row.get('rate-limit', '')),
                router_id=rid,
                rate_limit=row.get('rate-limit', ''),
                local_address=row.get('local-address', ''),
                remote_address=row.get('remote-address', ''),
                dns_server=row.get('dns-server', ''),
                session_timeout=row.get('session-timeout', ''),
                synced_at=datetime.utcnow(),
                raw_payload=row
            )
            db.session.add(p)
            created += 1

    db.session.commit()
    log_audit('sync_profiles', f'مزامنة باقات الراوتر: تم إضافة {created} وتحديث {updated}', 'device', device.id)
    return jsonify({'ok': True, 'message': f'تمت المزامنة بنجاح: إضافة {created} وتحديث {updated} باقة'})


def decode_mikrotik_text(text):
    if not text:
        return ''
    if isinstance(text, bytes):
        try:
            return text.decode('utf-8')
        except UnicodeDecodeError:
            try:
                return text.decode('windows-1256')
            except Exception:
                return text.decode('latin1', errors='ignore')
    text_str = str(text)
    # Check if raw escaped bytes in string like \xd4\xc8
    if '\\x' in text_str:
        try:
            raw_b = text_str.encode('latin1').decode('unicode-escape').encode('latin1')
            return raw_b.decode('windows-1256')
        except Exception:
            pass
    return text_str

def auto_detect_category(profile_name, rate_limit):
    name_lower = (profile_name or '').lower()
    rate_lower = (rate_limit or '').lower()
    if 'vpn' in name_lower or 'iptv' in name_lower or 'pptp' in name_lower:
        return 'خدمات VPN و شبكات'
    if 'default' in name_lower:
        return 'باقات النظام'
    if 'cut' in name_lower:
        return 'باقات التوقف والحد'
    # Check speed
    m = re.search(r'(\d+)\s*[mk]', rate_lower)
    if m:
        speed = int(m.group(1))
        if 'm' in rate_lower and speed >= 20:
            return 'سرعات فائقة / VIP'
        return 'برودباند منزلي'
    return 'برودباند عام'

# ======================================================
# مزامنة واستيراد الاشتراكات من الراوتر (Sync Secrets)
# ======================================================
@pppoe_bp.route('/api/sync-subscriptions/<int:device_id>', methods=['POST'])
@login_required
def api_sync_subscriptions(device_id):
    if not (current_user.is_admin or current_user.can_add or current_user.is_supervisor):
        return jsonify({'ok': False, 'message': 'لا تملك صلاحية المزامنة'}), 403

    device = MikroTikDevice.query.get_or_404(device_id)
    svc = PPPoEService(device)
    result = svc.get_secrets()
    if not result.ok:
        return jsonify(result.to_dict())

    # Map profiles by name
    prof_map = {p.name: p.id for p in PPPoEProfile.query.filter_by(device_id=device_id).all()}

    created, updated = 0, 0
    now = datetime.utcnow()

    for row in result.data:
        username = str(row.get('name', '')).strip()
        if not username:
            continue

        rid = str(row.get('.id', ''))
        prof_name = str(row.get('profile', 'default'))
        profile_id = prof_map.get(prof_name)
        password = str(row.get('password', '')) or '1234'
        caller_id = str(row.get('caller-id', ''))
        static_ip = str(row.get('remote-address', ''))
        disabled = str(row.get('disabled', 'false')).lower() in ('true', 'yes')
        raw_comment = row.get('comment', '')
        comment = decode_mikrotik_text(raw_comment) if raw_comment else ''

        sub = PPPoESubscription.query.filter_by(device_id=device_id, username=username).first()
        if sub:
            sub.router_secret_id = rid
            if profile_id:
                sub.profile_id = profile_id
            sub.disabled = disabled
            if caller_id: sub.caller_id = caller_id
            if static_ip: sub.static_ip = static_ip
            if comment and not sub.comment: sub.comment = comment
            sub.remote_exists = True
            sub.synced_at = now
            updated += 1
        else:
            sub = PPPoESubscription(
                device_id=device_id,
                profile_id=profile_id,
                username=username,
                password=password,
                router_secret_id=rid,
                service=str(row.get('service', 'pppoe')),
                caller_id=caller_id,
                static_ip=static_ip,
                disabled=disabled,
                comment=comment,
                customer_name=comment if len(comment) < 50 and not comment.startswith('سوف') else '',
                status='disabled' if disabled else 'active',
                created_by_id=current_user.id,
                started_at=now,
                expires_at=now + timedelta(days=PPPoEProfile.query.get(profile_id).validity_days if profile_id and PPPoEProfile.query.get(profile_id) and PPPoEProfile.query.get(profile_id).validity_days else 30),
                synced_at=now,
                remote_exists=True
            )
            db.session.add(sub)
            created += 1

    db.session.commit()
    log_audit('sync_subs', f'مزامنة مشتركي الراوتر: استيراد {created} وتحديث {updated}', 'device', device.id)
    return jsonify({
        'ok': True,
        'message': f'تمت المزامنة بنجاح: تم استيراد {created} مشترك جديد وتحديث {updated} مشترك'
    })
