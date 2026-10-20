# blueprints/accounting/routes.py - نظام المحاسبة وسندات الموظفين والتقارير
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import db, PPPoESubscription, Payment, User, MikroTikDevice, PPPoEProfile, EmployeeSettlement, AuditLog
from datetime import datetime, timedelta
from sqlalchemy import func, extract
import calendar

accounting_bp = Blueprint('accounting', __name__, url_prefix='/accounting')

def check_finance_access():
    return current_user.is_admin or current_user.can_view_finance or getattr(current_user, 'role', '') in ('admin', 'supervisor')

def log_audit(action, description='', resource='accounting', resource_id=None, extra=None):
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

# ======================================================
# لوحة المحاسبة العامة
# ======================================================
@accounting_bp.route('/')
@login_required
def index():
    if not check_finance_access():
        flash('لا تملك صلاحية عرض البيانات المالية', 'danger')
        return redirect(url_for('pppoe.dashboard'))
    
    devices = MikroTikDevice.query.filter_by(is_active=True).all()
    selected_id = request.args.get('device_id', type=int)
    
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    query = Payment.query
    if selected_id:
        query = query.join(PPPoESubscription).filter(PPPoESubscription.device_id == selected_id)
    
    total_revenue = query.with_entities(func.sum(Payment.amount)).scalar() or 0
    monthly_revenue = query.filter(Payment.paid_at >= month_start).with_entities(func.sum(Payment.amount)).scalar() or 0
    total_payments = query.count()
    monthly_payments = query.filter(Payment.paid_at >= month_start).count()

    # إجمالي المبالغ في ذمم الموظفين حالياً
    employees = User.query.filter_by(is_active=True).all()
    total_in_custody = sum(e.current_balance for e in employees if e.current_balance > 0)

    # الاشتراكات المنتهية قريباً
    expiring_soon = PPPoESubscription.query.filter(
        PPPoESubscription.expires_at != None,
        PPPoESubscription.expires_at <= now + timedelta(days=7),
        PPPoESubscription.expires_at >= now,
        PPPoESubscription.status == 'active'
    ).order_by(PPPoESubscription.expires_at).limit(10).all()

    # آخر العمليات
    recent_payments = Payment.query.order_by(Payment.paid_at.desc()).limit(10).all()

    return render_template('accounting/index.html',
        devices=devices, selected_id=selected_id,
        total_revenue=float(total_revenue), monthly_revenue=float(monthly_revenue),
        total_payments=total_payments, monthly_payments=monthly_payments,
        total_in_custody=round(total_in_custody, 2),
        expiring_soon=expiring_soon, recent_payments=recent_payments)

# ======================================================
# صفحة سندات وأرصدة الموظفين (كم عليه + إضافة تسوية + تصفير)
# ======================================================
@accounting_bp.route('/employees')
@login_required
def employees():
    if not check_finance_access():
        flash('لا تملك صلاحية عرض سندات الموظفين', 'danger')
        return redirect(url_for('pppoe.dashboard'))

    users = User.query.filter_by(is_active=True).all()
    employees_data = []

    for u in users:
        collected = u.total_collected()
        settled = u.total_settled()
        balance = u.current_balance
        last_settlement = EmployeeSettlement.query.filter_by(user_id=u.id).order_by(EmployeeSettlement.settled_at.desc()).first()
        recent_payments_count = Payment.query.filter_by(collected_by_id=u.id).count()

        employees_data.append({
            'user': u,
            'collected': collected,
            'settled': settled,
            'balance': balance,
            'last_settlement': last_settlement,
            'payments_count': recent_payments_count
        })

    # آخر سندات تم تسجيلها في النظام
    recent_settlements = EmployeeSettlement.query.order_by(EmployeeSettlement.settled_at.desc()).limit(15).all()

    return render_template('accounting/employees.html',
        employees_data=employees_data,
        recent_settlements=recent_settlements)

# ======================================================
# إضافة سند تسوية / قبض لموظف (AJAX)
# ======================================================
@accounting_bp.route('/settlements/add', methods=['POST'])
@login_required
def add_settlement():
    if not (current_user.is_admin or current_user.can_view_finance):
        return jsonify({'ok': False, 'message': 'لا تملك صلاحية تسجيل السندات'}), 403

    data = request.get_json() or request.form
    user_id = int(data.get('user_id', 0) or 0)
    emp = User.query.get(user_id)
    if not emp:
        return jsonify({'ok': False, 'message': 'الموظف غير موجود'})

    amount = float(data.get('amount', 0) or 0)
    if amount <= 0:
        return jsonify({'ok': False, 'message': 'يرجى إدخال مبلغ صحيح أكبر من صفر'})

    # رقم إيصال تلقائي إذا لم يتم إدخاله
    receipt_no = str(data.get('receipt_number', '')).strip()
    if not receipt_no:
        receipt_no = f"REC-{datetime.utcnow().strftime('%y%m%d')}-{emp.id}-{int(datetime.utcnow().timestamp()) % 10000}"

    settlement = EmployeeSettlement(
        user_id=emp.id,
        amount=amount,
        currency=str(data.get('currency', 'IQD')),
        settlement_type=str(data.get('settlement_type', 'receipt')),
        receipt_number=receipt_no,
        settled_at=datetime.utcnow(),
        settled_by_id=current_user.id,
        notes=str(data.get('notes', ''))
    )
    db.session.add(settlement)
    db.session.commit()

    log_audit('create_settlement', f'تسجيل سند قبض رقم {receipt_no} بمبلغ {amount} من الموظف {emp.full_name}', 'settlement', settlement.id)

    return jsonify({
        'ok': True,
        'message': f'تم تسجيل السند بنجاح بمبلغ {amount} للموظف {emp.full_name}',
        'settlement_id': settlement.id,
        'new_balance': emp.current_balance
    })

# ======================================================
# تصفير حساب الموظف بالكامل (AJAX)
# ======================================================
@accounting_bp.route('/settlements/zero/<int:user_id>', methods=['POST'])
@login_required
def zero_balance(user_id):
    if not current_user.is_admin:
        return jsonify({'ok': False, 'message': 'تصفير الحسابات يتطلب صلاحية المدير العام'}), 403

    emp = User.query.get_or_404(user_id)
    balance = emp.current_balance
    if balance <= 0:
        return jsonify({'ok': False, 'message': f'رصيد الموظف {emp.full_name} مسوى مسبقاً ولا توجد مبالغ في ذمته'})

    receipt_no = f"ZERO-{datetime.utcnow().strftime('%y%m%d')}-{emp.id}"
    settlement = EmployeeSettlement(
        user_id=emp.id,
        amount=balance,
        currency='IQD',
        settlement_type='zeroing',
        receipt_number=receipt_no,
        settled_at=datetime.utcnow(),
        settled_by_id=current_user.id,
        notes=f'تصفير شامل للرصيد المتبقي بواسطة المدير {current_user.full_name}'
    )
    db.session.add(settlement)
    db.session.commit()

    log_audit('zero_balance', f'تصفير رصيد الموظف {emp.full_name} بمبلغ {balance}', 'settlement', settlement.id)

    return jsonify({
        'ok': True,
        'message': f'تم تصفير حساب الموظف {emp.full_name} بنجاح بمبلغ {balance}',
        'settlement_id': settlement.id,
        'new_balance': emp.current_balance
    })

# ======================================================
# التقرير الشهري وكشف حساب الموظف مع فرز حسب الشهر والسنة
# ======================================================
@accounting_bp.route('/employees/<int:user_id>/report')
@login_required
def employee_report(user_id):
    if not check_finance_access():
        flash('لا تملك صلاحية عرض تقارير الموظفين', 'danger')
        return redirect(url_for('pppoe.dashboard'))

    emp = User.query.get_or_404(user_id)
    now = datetime.utcnow()

    # استخراج الشهر والسنة المحددين
    selected_year = request.args.get('year', now.year, type=int)
    selected_month = request.args.get('month', now.month, type=int)

    # حساب بداية ونهاية الشهر المختار
    _, num_days = calendar.monthrange(selected_year, selected_month)
    month_start = datetime(selected_year, selected_month, 1, 0, 0, 0)
    month_end = datetime(selected_year, selected_month, num_days, 23, 59, 59)

    # الاشتراكات والتجديدات المحصلة في هذا الشهر
    month_payments = Payment.query.filter(
        Payment.collected_by_id == emp.id,
        Payment.paid_at >= month_start,
        Payment.paid_at <= month_end
    ).order_by(Payment.paid_at.desc()).all()

    # السندات والتسويات المسلمة في هذا الشهر
    month_settlements = EmployeeSettlement.query.filter(
        EmployeeSettlement.user_id == emp.id,
        EmployeeSettlement.settled_at >= month_start,
        EmployeeSettlement.settled_at <= month_end
    ).order_by(EmployeeSettlement.settled_at.desc()).all()

    month_collected = sum(float(p.amount) for p in month_payments)
    month_settled = sum(float(s.amount) for s in month_settlements)
    month_net = round(month_collected - month_settled, 2)

    # الإجماليات التراكمية الكلية
    total_collected_all = emp.total_collected()
    total_settled_all = emp.total_settled()
    current_balance = emp.current_balance

    # قائمة السنوات المتاحة للاختيار (من العام الماضي للعام القادم)
    years = [now.year - 1, now.year, now.year + 1]
    months = [
        (1, 'يناير / كانون الثاني'), (2, 'فبراير / شباط'), (3, 'مارس / آذار'),
        (4, 'أبريل / نيسان'), (5, 'مايو / أيار'), (6, 'يونيو / حزيران'),
        (7, 'يوليو / تموز'), (8, 'أغسطس / آب'), (9, 'سبتمبر / أيلول'),
        (10, 'أكتوبر / تشرين الأول'), (11, 'نوفمبر / تشرين الثاني'), (12, 'ديسمبر / كانون الأول')
    ]

    return render_template('accounting/employee_report.html',
        emp=emp,
        selected_year=selected_year,
        selected_month=selected_month,
        years=years,
        months=months,
        month_payments=month_payments,
        month_settlements=month_settlements,
        month_collected=month_collected,
        month_settled=month_settled,
        month_net=month_net,
        total_collected_all=total_collected_all,
        total_settled_all=total_settled_all,
        current_balance=current_balance)

# ======================================================
# طباعة سند قبض / تسوية
# ======================================================
@accounting_bp.route('/settlements/<int:settlement_id>/print')
@login_required
def print_settlement(settlement_id):
    if not check_finance_access():
        flash('لا تملك صلاحية عرض هذا السند', 'danger')
        return redirect(url_for('pppoe.dashboard'))

    settlement = EmployeeSettlement.query.get_or_404(settlement_id)
    return render_template('accounting/settlement_print.html', s=settlement)

# ======================================================
# تسجيل دفعة تجديد لاشتراك
# ======================================================
@accounting_bp.route('/add-payment/<int:sub_id>', methods=['POST'])
@login_required
def add_payment(sub_id):
    if not check_finance_access():
        return jsonify({'ok': False, 'message': 'لا تملك صلاحية إضافة دفعات'})
    
    sub = PPPoESubscription.query.get_or_404(sub_id)
    data = request.get_json()
    amount = float(data.get('amount', 0) or 0)
    if amount <= 0:
        return jsonify({'ok': False, 'message': 'المبلغ يجب أن يكون أكبر من صفر'})
    
    months = int(data.get('months', 1) or 1)
    payment = Payment(
        subscription_id=sub.id,
        amount=amount,
        currency=str(data.get('currency', 'IQD')),
        payment_type=str(data.get('payment_type', 'renewal')),
        months=months,
        notes=str(data.get('notes', '')),
        collected_by_id=current_user.id
    )
    db.session.add(payment)
    
    if months > 0:
        base = sub.expires_at if sub.expires_at and sub.expires_at > datetime.utcnow() else datetime.utcnow()
        sub.expires_at = base + timedelta(days=30 * months)
        sub.status = 'active'
        sub.disabled = False
    
    db.session.commit()
    return jsonify({
        'ok': True,
        'message': f'تم تسجيل الدفعة ({amount} {payment.currency}) لحساب {current_user.full_name}',
        'new_expires': sub.expires_at.strftime('%Y-%m-%d') if sub.expires_at else ''
    })

# ======================================================
# التقارير الإجمالية
# ======================================================
@accounting_bp.route('/reports')
@login_required
def reports():
    if not check_finance_access():
        flash('لا تملك صلاحية عرض التقارير', 'danger')
        return redirect(url_for('pppoe.dashboard'))
    
    employee_stats = db.session.query(
        User.id,
        User.full_name,
        User.username,
        func.count(PPPoESubscription.id).label('subs_created'),
        func.sum(Payment.amount).label('total_collected')
    ).outerjoin(PPPoESubscription, PPPoESubscription.created_by_id == User.id
    ).outerjoin(Payment, Payment.collected_by_id == User.id
    ).group_by(User.id).all()

    return render_template('accounting/reports.html', employee_stats=employee_stats)
