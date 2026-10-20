# blueprints/auth/routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, AuditLog
from datetime import datetime

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

def log_audit(action, description='', resource='auth', resource_id=None):
    try:
        log = AuditLog(
            user_id=current_user.id if current_user.is_authenticated else None,
            action=action,
            resource=resource,
            resource_id=resource_id,
            description=description,
            ip_address=request.remote_addr or ''
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        pass

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('pppoe.dashboard'))
    
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))
        
        if not username or not password:
            error = 'يرجى إدخال اسم المستخدم وكلمة المرور'
        else:
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                if not user.is_active:
                    error = 'هذا الحساب موقوف. يرجى التواصل مع المسؤول.'
                else:
                    login_user(user, remember=remember)
                    user.last_login = datetime.utcnow()
                    db.session.commit()
                    log_audit('login', f'تسجيل دخول ناجح للمستخدم {username}')
                    next_page = request.args.get('next')
                    return redirect(next_page or url_for('pppoe.dashboard'))
            else:
                error = 'اسم المستخدم أو كلمة المرور غير صحيحة'
    
    return render_template('auth/login.html', error=error)

@auth_bp.route('/logout')
@login_required
def logout():
    log_audit('logout', f'تسجيل خروج المستخدم {current_user.username}')
    logout_user()
    flash('تم تسجيل الخروج بنجاح', 'info')
    return redirect(url_for('auth.login'))
