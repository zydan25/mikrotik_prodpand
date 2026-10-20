# app.py - Flask Main Application
import os
import sys
from flask import Flask, redirect, url_for, render_template
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from models import db, User
from config import config
from datetime import datetime

def _ensure_schema():
    from models import db
    try:
        with db.engine.connect() as conn:
            # 1. pppoe_subscriptions
            res = conn.execute(db.text("PRAGMA table_info(pppoe_subscriptions)")).fetchall()
            cols = [r[1] for r in res]
            if cols:
                needed = [
                    ('raw_payload', 'JSON'),
                    ('last_logged_out', "VARCHAR(64) DEFAULT ''"),
                    ('total_bytes_in', 'BIGINT DEFAULT 0'),
                    ('total_bytes_out', 'BIGINT DEFAULT 0'),
                    ('quota_limit_gb', 'NUMERIC(10, 2) DEFAULT 0'),
                    ('uptime', "VARCHAR(64) DEFAULT ''"),
                    ('is_online', 'BOOLEAN DEFAULT 0'),
                    ('current_ip', "VARCHAR(64) DEFAULT ''")
                ]
                for col_name, col_type in needed:
                    if col_name not in cols:
                        conn.execute(db.text(f"ALTER TABLE pppoe_subscriptions ADD COLUMN {col_name} {col_type}"))
                        conn.commit()

            # 2. mikrotik_devices
            res_dev = conn.execute(db.text("PRAGMA table_info(mikrotik_devices)")).fetchall()
            dev_cols = [r[1] for r in res_dev]
            if dev_cols and 'last_sync_raw' not in dev_cols:
                conn.execute(db.text("ALTER TABLE mikrotik_devices ADD COLUMN last_sync_raw JSON"))
                conn.commit()

            # 3. pppoe_profiles
            res_prof = conn.execute(db.text("PRAGMA table_info(pppoe_profiles)")).fetchall()
            prof_cols = [r[1] for r in res_prof]
            if prof_cols:
                prof_needed = [
                    ('category', "VARCHAR(100) DEFAULT 'عام'"),
                    ('quota_gb', "NUMERIC(10, 2) DEFAULT 0"),
                    ('validity_days', "INTEGER DEFAULT 30"),
                    ('raw_payload', "JSON")
                ]
                for col_name, col_type in prof_needed:
                    if col_name not in prof_cols:
                        conn.execute(db.text(f"ALTER TABLE pppoe_profiles ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
    except Exception as e:
        sys.stderr.write(f"[WARN] _ensure_schema: {e}\n")
        sys.stderr.flush()

def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    migrate = Migrate(app, db)
    csrf = CSRFProtect(app)

    login_manager = LoginManager(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'login_required'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from blueprints.auth.routes import auth_bp
    from blueprints.admin.routes import admin_bp
    from blueprints.pppoe.routes import pppoe_bp
    from blueprints.accounting.routes import accounting_bp
    from blueprints.broadband_lab import lab_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(pppoe_bp)
    app.register_blueprint(accounting_bp)
    app.register_blueprint(lab_bp)

    
    @app.errorhandler(400)
    def bad_request(e):
        return render_template('errors/400.html'), 400
    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

    @app.context_processor
    def inject_globals():
        from models import MikroTikDevice, PPPoEProfile
        try:
            devs = MikroTikDevice.query.filter_by(is_active=True).all()
            profs = PPPoEProfile.query.filter_by(is_active=True).order_by(PPPoEProfile.category, PPPoEProfile.name).all()
            cats = sorted(list({p.category or 'عام' for p in profs})) if profs else ['عام']
        except Exception:
            devs, profs, cats = [], [], ['عام']
        return {
            'app_name': 'PPPoE Manager',
            'now': datetime.utcnow(),
            'devices': devs,
            'profiles': profs,
            'categories': cats,
            'global_devices': devs,
            'global_profiles': profs,
            'global_categories': cats
        }

    with app.app_context():
        db.create_all()
        _ensure_schema()
        _ensure_admin()

    return app

def _ensure_admin():
    from models import User
    if not User.query.filter_by(username='admin').first():
        admin = User(
            username='admin', full_name='Admin',
            role='admin', is_active=True,
            can_add=True, can_edit=True, can_delete=True,
            can_disconnect=True, can_view_password=True, can_view_finance=True
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        sys.stdout.write('[OK] Admin created: admin / admin123\n')
        sys.stdout.flush()

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

