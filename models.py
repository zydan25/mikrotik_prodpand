# models.py - نماذج قاعدة البيانات الكاملة لنظام PPPoE Manager
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# ==============================
# نموذج المستخدمين والموظفين
# ==============================
class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='employee')  # admin / supervisor / employee / readonly
    is_active = db.Column(db.Boolean, default=True)
    can_add = db.Column(db.Boolean, default=True)
    can_edit = db.Column(db.Boolean, default=True)
    can_delete = db.Column(db.Boolean, default=False)
    can_disconnect = db.Column(db.Boolean, default=False)
    can_view_password = db.Column(db.Boolean, default=False)
    can_view_finance = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, default='')

    subscriptions_created = db.relationship('PPPoESubscription', foreign_keys='PPPoESubscription.created_by_id', backref='created_by', lazy='dynamic')
    subscriptions_edited = db.relationship('PPPoESubscription', foreign_keys='PPPoESubscription.last_edited_by_id', backref='last_edited_by', lazy='dynamic')
    audit_logs = db.relationship('AuditLog', backref='user', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_supervisor(self):
        return self.role in ('admin', 'supervisor')

    def total_collected(self, start_date=None, end_date=None):
        """إجمالي المبالغ التي قام الموظف بتحصيلها من الاشتراكات"""
        from sqlalchemy import func
        q = Payment.query.filter_by(collected_by_id=self.id)
        if start_date:
            q = q.filter(Payment.paid_at >= start_date)
        if end_date:
            q = q.filter(Payment.paid_at <= end_date)
        val = q.with_entities(func.sum(Payment.amount)).scalar()
        return float(val or 0)

    def total_settled(self, start_date=None, end_date=None):
        """إجمالي سندات القبض والتسويات التي سلمها الموظف للمدير"""
        from sqlalchemy import func
        q = EmployeeSettlement.query.filter_by(user_id=self.id)
        if start_date:
            q = q.filter(EmployeeSettlement.settled_at >= start_date)
        if end_date:
            q = q.filter(EmployeeSettlement.settled_at <= end_date)
        val = q.with_entities(func.sum(EmployeeSettlement.amount)).scalar()
        return float(val or 0)

    @property
    def current_balance(self):
        """المبلغ المتبقي في ذمة الموظف (المحصل غير المسلم)"""
        return round(self.total_collected() - self.total_settled(), 2)

    def __repr__(self):
        return f'<User {self.username}>'


# ==============================
# نموذج جهاز MikroTik (الراوتر)
# ==============================
class MikroTikDevice(db.Model):
    __tablename__ = 'mikrotik_devices'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    host = db.Column(db.String(255), nullable=False)
    api_port = db.Column(db.Integer, default=8728)
    rest_port = db.Column(db.Integer, default=443)
    username = db.Column(db.String(120), nullable=False)
    password = db.Column(db.String(255), nullable=False)
    use_ssl = db.Column(db.Boolean, default=False)
    use_rest = db.Column(db.Boolean, default=False)
    location = db.Column(db.String(255), default='')
    notes = db.Column(db.Text, default='')
    is_active = db.Column(db.Boolean, default=True)
    last_seen = db.Column(db.DateTime, nullable=True)
    last_status = db.Column(db.String(20), default='unknown')
    ros_version = db.Column(db.String(50), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    profiles = db.relationship('PPPoEProfile', backref='device', lazy='dynamic', cascade='all, delete-orphan')
    subscriptions = db.relationship('PPPoESubscription', backref='device', lazy='dynamic', cascade='all, delete-orphan')
    connection_logs = db.relationship('DeviceLog', backref='device', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Device {self.name} @ {self.host}>'


# ==============================
# نموذج بروفايلات PPPoE (الباقات)
# ==============================
class PPPoEProfile(db.Model):
    __tablename__ = 'pppoe_profiles'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('mikrotik_devices.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(100), default='عام')
    quota_gb = db.Column(db.Numeric(10, 2), default=0)  # 0 = مفتوح
    validity_days = db.Column(db.Integer, default=30)   # مدة الصلاحية بالأيام  # فئة الباقة: منزلي، تجاري، VIP، ألعاب، برودباند...
    router_id = db.Column(db.String(64), default='')
    rate_limit = db.Column(db.String(64), default='')   # e.g. "5M/10M"
    local_address = db.Column(db.String(64), default='')
    remote_address = db.Column(db.String(128), default='')
    dns_server = db.Column(db.String(128), default='')
    session_timeout = db.Column(db.String(64), default='')
    idle_timeout = db.Column(db.String(64), default='')
    price = db.Column(db.Numeric(10, 2), default=0)
    price_currency = db.Column(db.String(10), default='IQD')
    is_active = db.Column(db.Boolean, default=True)
    synced_at = db.Column(db.DateTime, nullable=True)
    raw_payload = db.Column(db.JSON, default=dict)

    subscriptions = db.relationship('PPPoESubscription', backref='profile', lazy='dynamic')

    def __repr__(self):
        return f'<Profile {self.name}>'


# ==============================
# نموذج الاشتراكات (الحسابات PPP Secret)
# ==============================
class PPPoESubscription(db.Model):
    __tablename__ = 'pppoe_subscriptions'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('mikrotik_devices.id'), nullable=False, index=True)
    profile_id = db.Column(db.Integer, db.ForeignKey('pppoe_profiles.id'), nullable=True, index=True)

    # بيانات الحساب على الراوتر
    username = db.Column(db.String(120), nullable=False, index=True)
    password = db.Column(db.String(120), nullable=False)
    router_secret_id = db.Column(db.String(64), default='', index=True)
    service = db.Column(db.String(32), default='pppoe')
    caller_id = db.Column(db.String(64), default='')       # MAC Address lock
    static_ip = db.Column(db.String(64), default='')       # Remote address/IP
    disabled = db.Column(db.Boolean, default=False)

    # بيانات العميل الاختيارية (مربوطة مباشرة باليوزر)
    customer_name = db.Column(db.String(200), default='')
    customer_phone = db.Column(db.String(32), default='')
    customer_address = db.Column(db.String(255), default='')
    customer_notes = db.Column(db.Text, default='')

    # بيانات الاشتراك والمحاسبة
    price = db.Column(db.Numeric(10, 2), default=0)
    price_currency = db.Column(db.String(10), default='IQD')
    started_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    comment = db.Column(db.Text, default='')

    # حالة
    status = db.Column(db.String(20), default='active')
    # حركة البيانات وحالة الاتصال اللحظية
    total_bytes_in = db.Column(db.BigInteger, default=0)   # Upload RX
    total_bytes_out = db.Column(db.BigInteger, default=0)  # Download TX
    quota_limit_gb = db.Column(db.Numeric(10, 2), default=0)
    uptime = db.Column(db.String(64), default='')
    is_online = db.Column(db.Boolean, default=False)
    current_ip = db.Column(db.String(64), default='')
   # active / suspended / expired / cancelled
    last_logged_out = db.Column(db.String(64), default='')

    # تتبع الموظفين
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    last_edited_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # تتبع المزامنة
    synced_at = db.Column(db.DateTime, nullable=True)
    remote_exists = db.Column(db.Boolean, default=True)

    payments = db.relationship('Payment', backref='subscription', lazy='dynamic', cascade='all, delete-orphan')

    __table_args__ = (db.UniqueConstraint('device_id', 'username', name='uq_device_username'),)


    @property
    def total_bytes(self):
        return (self.total_bytes_in or 0) + (self.total_bytes_out or 0)

    @property
    def consumed_formatted(self):
        b = self.total_bytes
        if not b or b <= 0: return '0 MB'
        if b >= 1024**3: return f'{b / (1024**3):.2f} GB'
        return f'{b / (1024**2):.1f} MB'

    @property
    def rx_formatted(self):
        b = self.total_bytes_in or 0
        if not b or b <= 0: return '0 MB'
        if b >= 1024**3: return f'{b / (1024**3):.2f} GB'
        return f'{b / (1024**2):.1f} MB'

    @property
    def tx_formatted(self):
        b = self.total_bytes_out or 0
        if not b or b <= 0: return '0 MB'
        if b >= 1024**3: return f'{b / (1024**3):.2f} GB'
        return f'{b / (1024**2):.1f} MB'

    @property
    def quota_display(self):
        limit = float(self.quota_limit_gb or (self.profile.quota_gb if self.profile else 0) or 0)
        return f'{limit:.0f} GB' if limit > 0 else 'مفتوح (Unlimited)'

    @property
    def remaining_quota_display(self):
        limit = float(self.quota_limit_gb or (self.profile.quota_gb if self.profile else 0) or 0)
        if limit <= 0: return 'مفتوح'
        consumed_gb = self.total_bytes / (1024**3)
        rem = limit - consumed_gb
        return f'{round(rem if rem > 0 else 0, 2)} GB'

    @property
    def usage_percent(self):
        limit = float(self.quota_limit_gb or (self.profile.quota_gb if self.profile else 0) or 0)
        if limit <= 0:
            return 0
        consumed_gb = self.total_bytes / (1024**3)
        pct = (consumed_gb / limit) * 100
        return min(round(pct, 1), 100)

    @property
    def days_remaining(self):
        if not self.expires_at:
            return None
        delta = self.expires_at - datetime.utcnow()
        return delta.days

    def __repr__(self):
        return f'<Subscription {self.username}>'


# ==============================
# نموذج المدفوعات والمحاسبة (اشتراكات وتجديدات)
# ==============================
class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('pppoe_subscriptions.id'), nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(10), default='IQD')
    payment_type = db.Column(db.String(30), default='renewal')  # renewal / new / partial / refund
    months = db.Column(db.Integer, default=1)
    paid_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    collected_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    notes = db.Column(db.Text, default='')
    receipt_no = db.Column(db.String(64), nullable=True)
    collected_by = db.relationship('User', foreign_keys=[collected_by_id])

    def __repr__(self):
        return f'<Payment {self.amount} for sub {self.subscription_id}>'


# ==============================
# نموذج سندات وتسويات الموظفين (سندات القبض والتصفير)
# ==============================
class EmployeeSettlement(db.Model):
    __tablename__ = 'employee_settlements'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(10), default='IQD')
    settlement_type = db.Column(db.String(30), default='receipt')  # receipt (سند قبض) / zeroing (تصفير) / advance
    receipt_number = db.Column(db.String(64), nullable=True, index=True)
    settled_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    settled_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True) # المدير المستلم
    notes = db.Column(db.Text, default='')

    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('settlements', lazy='dynamic', cascade='all, delete-orphan'))
    settled_by = db.relationship('User', foreign_keys=[settled_by_id])

    def __repr__(self):
        return f'<Settlement {self.amount} for user {self.user_id}>'


# ==============================
# نموذج سجلات التدقيق
# ==============================
class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    action = db.Column(db.String(50), nullable=False)
    resource = db.Column(db.String(50), default='')
    resource_id = db.Column(db.Integer, nullable=True)
    description = db.Column(db.Text, default='')
    ip_address = db.Column(db.String(50), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    extra = db.Column(db.JSON, default=dict)

    def __repr__(self):
        return f'<Log {self.action} by user {self.user_id}>'


# ==============================
# نموذج سجلات الاتصال بالراوتر
# ==============================
class DeviceLog(db.Model):
    __tablename__ = 'device_logs'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('mikrotik_devices.id'), nullable=False, index=True)
    action = db.Column(db.String(64), default='check')
    ok = db.Column(db.Boolean, default=False)
    message = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<DeviceLog {self.device_id} {self.action}>'
