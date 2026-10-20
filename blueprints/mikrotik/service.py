# blueprints/mikrotik/service.py
# طبقة خدمة MikroTik - تدعم RouterOS v6 و v7 عبر Binary API و REST API
import socket
import re
from datetime import datetime, timezone
from typing import Optional
import requests
import routeros_api
from requests.auth import HTTPDigestAuth

# =========================================================
# نتيجة العملية الموحدة
# =========================================================
class MikroTikResult:
    def __init__(self, ok: bool, message: str = '', data=None):
        self.ok = ok
        self.message = message
        self.data = data or []

    def to_dict(self):
        return {'ok': self.ok, 'message': self.message, 'data': self.data}


# =========================================================
# كاشف إصدار RouterOS
# =========================================================
class VersionDetector:
    @staticmethod
    def parse_version(version_str: str) -> tuple:
        """استخرج أرقام الإصدار من نص مثل 7.12.1 أو 6.49.8"""
        m = re.match(r'(\d+)\.(\d+)', str(version_str))
        if m:
            return (int(m.group(1)), int(m.group(2)))
        return (0, 0)

    @staticmethod
    def is_v7(version_str: str) -> bool:
        major, _ = VersionDetector.parse_version(version_str)
        return major >= 7

    @staticmethod
    def is_v6(version_str: str) -> bool:
        major, _ = VersionDetector.parse_version(version_str)
        return major == 6

    @staticmethod
    def supports_rest(version_str: str) -> bool:
        """REST API متاح من RouterOS 7.1 فأعلى"""
        major, minor = VersionDetector.parse_version(version_str)
        return major >= 7


# =========================================================
# عميل Binary API (RouterOS v6 + v7)
# =========================================================
class BinaryAPIClient:
    def __init__(self, host, port, username, password, use_ssl=False, timeout=10):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.timeout = timeout
        self._pool = None

    def _connect(self):
        self._pool = routeros_api.RouterOsApiPool(
            self.host,
            username=self.username,
            password=self.password,
            port=self.port,
            use_ssl=self.use_ssl,
            plaintext_login=True
        )
        return self._pool.get_api()

    def disconnect(self):
        try:
            if self._pool:
                self._pool.disconnect()
        except Exception:
            pass

    def get_resource(self, path_options):
        """يحاول مسارات متعددة حتى ينجح"""
        api = self._connect()
        if isinstance(path_options, str):
            path_options = [path_options]
        last_exc = None
        for path in path_options:
            try:
                res = api.get_resource(path)
                return res, api
            except Exception as e:
                last_exc = e
        raise last_exc

    def call(self, resource, command, args=None):
        if args is None:
            args = {}
        return resource.call(command, args)

    def get_system_resource(self):
        api = self._connect()
        try:
            res = api.get_resource('/system/resource')
            data = res.get()
            return data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else {})
        finally:
            self.disconnect()

    def detect_version(self):
        try:
            info = self.get_system_resource()
            return str(info.get('version', ''))
        except Exception:
            return ''


# =========================================================
# عميل REST API (RouterOS v7.1+)
# =========================================================
class RESTAPIClient:
    def __init__(self, host, port=443, username='admin', password='', use_ssl=True, timeout=10):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.timeout = timeout
        scheme = 'https' if use_ssl else 'http'
        self.base_url = f'{scheme}://{host}:{port}/rest'

    def _request(self, method, path, payload=None, params=None):
        url = f'{self.base_url}{path}'
        auth = HTTPDigestAuth(self.username, self.password)
        headers = {'Content-Type': 'application/json'}
        kwargs = dict(auth=auth, headers=headers, timeout=self.timeout, verify=False, params=params)
        if payload is not None:
            kwargs['json'] = payload
        resp = getattr(requests, method)(url, **kwargs)
        resp.raise_for_status()
        if resp.content:
            return resp.json()
        return {}

    def get(self, path, params=None):
        return self._request('get', path, params=params)

    def post(self, path, payload):
        return self._request('post', path, payload=payload)

    def patch(self, path, payload):
        return self._request('patch', path, payload=payload)

    def delete(self, path):
        return self._request('delete', path)

    def detect_version(self):
        try:
            data = self.get('/system/resource')
            if isinstance(data, list):
                data = data[0] if data else {}
            return str(data.get('version', ''))
        except Exception:
            return ''


# =========================================================
# خدمة PPPoE الموحدة - تدعم جميع الإصدارات
# =========================================================
class PPPoEService:
    """خدمة إدارة اشتراكات PPPoE لأجهزة MikroTik
    تدعم RouterOS v6 و v7 عبر Binary API أو REST API"""

    def __init__(self, device_model):
        self.device = device_model
        self._ros_version = device_model.ros_version or ''
        self._use_rest = device_model.use_rest and VersionDetector.supports_rest(self._ros_version)

    def _binary(self):
        return BinaryAPIClient(
            host=self.device.host,
            port=self.device.api_port or 8728,
            username=self.device.username,
            password=self.device.password,
            use_ssl=self.device.use_ssl
        )

    def _rest(self):
        return RESTAPIClient(
            host=self.device.host,
            port=self.device.rest_port or 443,
            username=self.device.username,
            password=self.device.password,
            use_ssl=True
        )

    # ------------------------------------------
    # فحص الاتصال وكشف الإصدار
    # ------------------------------------------
    def test_connection(self) -> MikroTikResult:
        try:
            if self._use_rest:
                client = self._rest()
                data = client.get('/system/resource')
                if isinstance(data, list): data = data[0] if data else {}
                ver = data.get('version', '')
                board = data.get('board-name', '')
                return MikroTikResult(True,
                    f'متصل بنجاح | RouterOS {ver} | {board}',
                    {'version': ver, 'board': board})
            else:
                client = self._binary()
                info = client.get_system_resource()
                ver = info.get('version', '')
                board = info.get('board-name', '')
                cpu = info.get('cpu-load', '')
                free_mem = info.get('free-memory', '')
                return MikroTikResult(True,
                    f'متصل بنجاح | RouterOS {ver} | {board}',
                    {'version': ver, 'board': board, 'cpu_load': cpu, 'free_memory': free_mem})
        except routeros_api.exceptions.RouterOsApiCommunicationError as e:
            return MikroTikResult(False, f'خطأ بيانات الاعتماد أو المنفذ: {e}')
        except socket.timeout:
            return MikroTikResult(False, 'انتهت مهلة الاتصال - تحقق من العنوان والمنفذ')
        except ConnectionRefusedError:
            return MikroTikResult(False, 'الاتصال مرفوض - تحقق من أن API مفعّل على الراوتر')
        except Exception as e:
            return MikroTikResult(False, f'خطأ غير متوقع: {str(e)}')

    def detect_and_save_version(self, device_model) -> str:
        """يكشف الإصدار ويحدث نموذج قاعدة البيانات"""
        try:
            if device_model.use_rest:
                client = self._rest()
                info = client.get('/system/resource')
                if isinstance(info, list): info = info[0] if info else {}
            else:
                client = self._binary()
                info = client.get_system_resource()
            ver = str(info.get('version', ''))
            device_model.ros_version = ver
            device_model.last_seen = datetime.utcnow()
            device_model.last_status = 'online'
            return ver
        except Exception:
            device_model.last_status = 'offline'
            return ''


    def get_live_sessions_and_traffic(self):
        """جلب الجلسات النشطة وحركة البيانات الحية لكل مشترك من الراوتر"""
        active_map = {}
        try:
            client = self._binary()
            res_act, _ = client.get_resource(['/ppp/active', 'ppp/active'])
            actives = res_act.call('print')
            for a in actives:
                name = a.get('name')
                if name:
                    active_map[name] = {
                        'uptime': str(a.get('uptime', '')),
                        'address': str(a.get('address', '')),
                        'caller_id': str(a.get('caller-id', '')),
                        'rx': 0, 'tx': 0
                    }

            try:
                res_if, _ = client.get_resource(['/interface', 'interface'])
                ifaces = res_if.call('print', {'.proplist': 'name,rx-byte,tx-byte'})
                for iface in ifaces:
                    iname = str(iface.get('name', ''))
                    if iname.startswith('<') and iname.endswith('>'):
                        clean = iname[1:-1]
                        parts = clean.split('-', 1)
                        if len(parts) == 2:
                            user = parts[1]
                            for k in active_map:
                                if k == user or user.startswith(k):
                                    active_map[k]['rx'] = int(iface.get('rx-byte', 0) or 0)
                                    active_map[k]['tx'] = int(iface.get('tx-byte', 0) or 0)
            except Exception:
                pass
            client.disconnect()
        except Exception:
            pass
        return active_map

    # ------------------------------------------
    # جلب بروفايلات PPP (/ppp/profile)
    # ------------------------------------------
    def get_profiles(self) -> MikroTikResult:
        props = ['.id', 'name', 'rate-limit', 'local-address', 'remote-address',
                 'dns-server', 'session-timeout', 'idle-timeout']
        try:
            if self._use_rest:
                client = self._rest()
                data = client.get('/ppp/profile', params={'.proplist': ','.join(props)})
                return MikroTikResult(True, '', data if isinstance(data, list) else [data])
            else:
                client = self._binary()
                res, api = client.get_resource(['/ppp/profile', 'ppp/profile'])
                data = res.call('print', {'.proplist': ','.join(props)})
                client.disconnect()
                if not isinstance(data, list):
                    data = [data] if isinstance(data, dict) else []
                return MikroTikResult(True, '', data)
        except Exception as e:
            return MikroTikResult(False, f'خطأ في جلب البروفايلات: {str(e)}')

    # ------------------------------------------
    # جلب الاشتراكات (/ppp/secret)
    # ------------------------------------------
    def get_secrets(self, limit=2000) -> MikroTikResult:
        props = ['.id', 'name', 'password', 'profile', 'service', 'caller-id',
                 'remote-address', 'disabled', 'comment', 'last-logged-out']
        try:
            if self._use_rest:
                client = self._rest()
                data = client.get('/ppp/secret', params={'.proplist': ','.join(props)})
                if not isinstance(data, list): data = [data] if data else []
                return MikroTikResult(True, '', data[:limit])
            else:
                client = self._binary()
                res, api = client.get_resource(['/ppp/secret', 'ppp/secret'])
                data = res.call('print', {'.proplist': ','.join(props)})
                client.disconnect()
                if not isinstance(data, list):
                    data = [data] if isinstance(data, dict) else []
                return MikroTikResult(True, '', data[:limit])
        except Exception as e:
            return MikroTikResult(False, f'خطأ في جلب الاشتراكات: {str(e)}')

    # ------------------------------------------
    # جلب الجلسات النشطة (/ppp/active)
    # ------------------------------------------
    def get_active_sessions(self) -> MikroTikResult:
        props = ['.id', 'name', 'service', 'caller-id', 'address', 'uptime',
                 'bytes-in', 'bytes-out', 'encoding']
        try:
            if self._use_rest:
                client = self._rest()
                data = client.get('/ppp/active', params={'.proplist': ','.join(props)})
                if not isinstance(data, list): data = [data] if data else []
                return MikroTikResult(True, '', data)
            else:
                client = self._binary()
                res, api = client.get_resource(['/ppp/active', 'ppp/active'])
                data = res.call('print', {'.proplist': ','.join(props)})
                client.disconnect()
                if not isinstance(data, list):
                    data = [data] if isinstance(data, dict) else []
                return MikroTikResult(True, '', data)
        except Exception as e:
            return MikroTikResult(False, f'خطأ في جلب الجلسات النشطة: {str(e)}')

    # ------------------------------------------
    # إضافة اشتراك جديد
    # ------------------------------------------
    def add_secret(self, username, password, profile, service='pppoe',
                   comment='', static_ip='', caller_id='') -> MikroTikResult:
        payload = {'name': username, 'password': password, 'profile': profile, 'service': service}
        if comment: payload['comment'] = comment
        if static_ip: payload['remote-address'] = static_ip
        if caller_id: payload['caller-id'] = caller_id
        try:
            if self._use_rest:
                client = self._rest()
                result = client.post('/ppp/secret', payload)
                rid = result.get('ret', '') if isinstance(result, dict) else ''
                return MikroTikResult(True, f'تم إنشاء الحساب بنجاح', {'router_id': rid})
            else:
                client = self._binary()
                res, api = client.get_resource(['/ppp/secret', 'ppp/secret'])
                result = res.call('add', payload)
                client.disconnect()
                rid = ''
                if isinstance(result, dict):
                    rid = result.get('ret', '')
                elif hasattr(result, 'done_message'):
                    rid = result.done_message.get('ret', '') if isinstance(result.done_message, dict) else ''
                return MikroTikResult(True, 'تم إنشاء الحساب بنجاح', {'router_id': str(rid)})
        except Exception as e:
            return MikroTikResult(False, f'فشل إنشاء الحساب: {str(e)}')

    # ------------------------------------------
    # البحث عن معرف الحساب بالاسم
    # ------------------------------------------
    def find_secret_id_by_name(self, username: str) -> str:
        try:
            if self._use_rest:
                client = self._rest()
                data = client.get('/ppp/secret', params={'name': username})
                if isinstance(data, list) and data:
                    return str(data[0].get('id') or data[0].get('.id') or '')
                return ''
            else:
                client = self._binary()
                res, api = client.get_resource(['/ppp/secret', 'ppp/secret'])
                items = list(res.get(name=username))
                client.disconnect()
                if items:
                    return str(items[0].get('id') or items[0].get('.id') or '')
                return ''
        except Exception:
            return ''

    # ------------------------------------------
    # تعديل اشتراك
    # ------------------------------------------
    def update_secret(self, router_id: str, fields: dict, username: str = '') -> MikroTikResult:
        try:
            if not router_id and username:
                router_id = self.find_secret_id_by_name(username)
            if not router_id:
                return MikroTikResult(False, 'لم يتم العثور على معرف الحساب في الراوتر')

            if self._use_rest:
                client = self._rest()
                client.patch(f'/ppp/secret/{router_id}', fields)
                if username and 'profile' in fields:
                    self._kick_user_rest(client, username)
                return MikroTikResult(True, 'تم تعديل الحساب بنجاح', {'router_id': router_id})
            else:
                client = self._binary()
                res, api = client.get_resource(['/ppp/secret', 'ppp/secret'])
                call_fields = dict(fields)
                call_fields['numbers'] = router_id
                res.call('set', call_fields)
                if username and 'profile' in fields:
                    self._kick_user_binary(api, username)
                client.disconnect()
                return MikroTikResult(True, 'تم تعديل الحساب بنجاح', {'router_id': router_id})
        except Exception as e:
            if username and router_id:
                try:
                    new_id = self.find_secret_id_by_name(username)
                    if new_id and new_id != router_id:
                        return self.update_secret(new_id, fields, username='')
                except Exception:
                    pass
            return MikroTikResult(False, f'فشل تعديل الحساب: {str(e)}')

    # ------------------------------------------
    # حذف اشتراك
    # ------------------------------------------
    def delete_secret(self, router_id: str, username: str = '') -> MikroTikResult:
        try:
            if not router_id and username:
                router_id = self.find_secret_id_by_name(username)
            if not router_id:
                return MikroTikResult(False, 'لم يتم العثور على معرف الحساب في الراوتر')
            if self._use_rest:
                client = self._rest()
                client.delete(f'/ppp/secret/{router_id}')
                if username:
                    self._kick_user_rest(client, username)
                return MikroTikResult(True, 'تم حذف الحساب بنجاح')
            else:
                client = self._binary()
                res, api = client.get_resource(['/ppp/secret', 'ppp/secret'])
                res.call('remove', {'numbers': router_id})
                if username:
                    self._kick_user_binary(api, username)
                client.disconnect()
                return MikroTikResult(True, 'تم حذف الحساب بنجاح')
        except Exception as e:
            return MikroTikResult(False, f'فشل حذف الحساب: {str(e)}')

    # ------------------------------------------
    # تعطيل/تفعيل اشتراك
    # ------------------------------------------
    def set_disabled(self, router_id: str, disabled: bool, username: str = '') -> MikroTikResult:
        val = 'true' if disabled else 'false'
        try:
            if not router_id and username:
                router_id = self.find_secret_id_by_name(username)
            if not router_id:
                return MikroTikResult(False, 'لم يتم العثور على معرف الحساب في الراوتر')
            if self._use_rest:
                client = self._rest()
                client.patch(f'/ppp/secret/{router_id}', {'disabled': val})
                if disabled and username:
                    self._kick_user_rest(client, username)
            else:
                client = self._binary()
                res, api = client.get_resource(['/ppp/secret', 'ppp/secret'])
                res.call('set', {'numbers': router_id, 'disabled': val})
                if disabled and username:
                    self._kick_user_binary(api, username)
                client.disconnect()
            action = 'تعطيل' if disabled else 'تفعيل'
            return MikroTikResult(True, f'تم {action} الحساب بنجاح')
        except Exception as e:
            return MikroTikResult(False, f'فشل تغيير حالة الحساب: {str(e)}')

    # ------------------------------------------
    # قطع الجلسة النشطة
    # ------------------------------------------
    def disconnect_session(self, session_id: str) -> MikroTikResult:
        try:
            if self._use_rest:
                client = self._rest()
                client.delete(f'/ppp/active/{session_id}')
            else:
                client = self._binary()
                res, api = client.get_resource(['/ppp/active', 'ppp/active'])
                res.call('remove', {'numbers': session_id})
                client.disconnect()
            return MikroTikResult(True, 'تم قطع الجلسة بنجاح')
        except Exception as e:
            return MikroTikResult(False, f'فشل قطع الجلسة: {str(e)}')

    # ------------------------------------------
    # قطع جلسة مستخدم بالاسم (بحث ثم حذف)
    # ------------------------------------------
    def disconnect_by_username(self, username: str) -> MikroTikResult:
        try:
            if self._use_rest:
                client = self._rest()
                sessions = client.get('/ppp/active', params={'name': username})
                if not isinstance(sessions, list): sessions = [sessions] if sessions else []
                count = 0
                for s in sessions:
                    sid = s.get('.id', '')
                    if sid:
                        client.delete(f'/ppp/active/{sid}')
                        count += 1
                return MikroTikResult(True, f'تم قطع {count} جلسة للمستخدم {username}')
            else:
                client = self._binary()
                res, api = client.get_resource(['/ppp/active', 'ppp/active'])
                count = self._kick_user_binary(api, username)
                client.disconnect()
                return MikroTikResult(True, f'تم قطع {count} جلسة للمستخدم {username}')
        except Exception as e:
            return MikroTikResult(False, f'فشل قطع الجلسة: {str(e)}')

    def _kick_user_binary(self, api, username: str) -> int:
        try:
            res = api.get_resource('/ppp/active')
            sessions = res.get(name=username)
            count = 0
            for s in (sessions if isinstance(sessions, list) else []):
                sid = s.get('.id', '')
                if sid:
                    res.call('remove', {'numbers': sid})
                    count += 1
            return count
        except Exception:
            return 0

    def _kick_user_rest(self, client, username: str) -> int:
        try:
            sessions = client.get('/ppp/active', params={'name': username})
            if not isinstance(sessions, list): sessions = [sessions] if sessions else []
            count = 0
            for s in sessions:
                sid = s.get('.id', '')
                if sid:
                    client.delete(f'/ppp/active/{sid}')
                    count += 1
            return count
        except Exception:
            return 0

    # ------------------------------------------
    # جلب معلومات النظام
    # ------------------------------------------
    def get_system_info(self) -> MikroTikResult:
        try:
            if self._use_rest:
                client = self._rest()
                data = client.get('/system/resource')
                if isinstance(data, list): data = data[0] if data else {}
                return MikroTikResult(True, '', data)
            else:
                client = self._binary()
                data = client.get_system_resource()
                return MikroTikResult(True, '', data)
        except Exception as e:
            return MikroTikResult(False, f'خطأ في جلب معلومات النظام: {str(e)}')
