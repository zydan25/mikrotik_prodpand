// static/js/app.js - المنطق التفاعلي للتطبيق
'use strict';

// ========================
// Toast Notifications
// ========================
const Toast = {
  container: null,
  init() {
    if (!this.container) {
      this.container = document.getElementById('toast-container');
      if (!this.container) {
        this.container = document.createElement('div');
        this.container.id = 'toast-container';
        document.body.appendChild(this.container);
      }
    }
  },
  show(message, type = 'success', duration = 4000) {
    this.init();
    const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.innerHTML = `
      <span class="toast-icon">${icons[type] || icons.info}</span>
      <span>${message}</span>
    `;
    this.container.appendChild(el);
    setTimeout(() => {
      el.style.animation = 'fadeOut 0.3s ease forwards';
      setTimeout(() => el.remove(), 300);
    }, duration);
  },
  success(msg) { this.show(msg, 'success'); },
  error(msg) { this.show(msg, 'error', 6000); },
  warning(msg) { this.show(msg, 'warning'); },
  info(msg) { this.show(msg, 'info'); }
};

// ========================
// Button Loading State
// ========================
function setLoading(btn, loading) {
  if (!btn) return;
  if (loading) {
    btn.classList.add('loading');
    btn.disabled = true;
  } else {
    btn.classList.remove('loading');
    btn.disabled = false;
  }
}

function btnLoading(btn) {
  const text = btn.innerHTML;
  btn.disabled = true;
  btn.dataset.originalHtml = text;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> جاري...`;
  return () => {
    btn.disabled = false;
    btn.innerHTML = text;
  };
}

// ========================
// AJAX fetch helper
// ========================
async function apiPost(url, data = {}) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrfToken()
    },
    body: JSON.stringify(data)
  });
  return resp.json();
}

function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.content : '';
}

// ========================
// Modal System
// ========================
const Modal = {
  open(id) {
    const overlay = document.getElementById(id);
    if (overlay) { overlay.classList.add('active'); document.body.style.overflow = 'hidden'; }
  },
  close(id) {
    const overlay = document.getElementById(id);
    if (overlay) { overlay.classList.remove('active'); document.body.style.overflow = ''; }
  },
  closeAll() {
    document.querySelectorAll('.modal-overlay.active').forEach(m => {
      m.classList.remove('active');
    });
    document.body.style.overflow = '';
  }
};

// Close modal on overlay click
document.addEventListener('click', e => {
  if (e.target.classList.contains('modal-overlay')) Modal.closeAll();
  if (e.target.dataset.closeModal) Modal.close(e.target.closest('.modal-overlay').id);
});

// Close on ESC
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') Modal.closeAll();
});

// ========================
// Confirm Dialog
// ========================
function showConfirm(options) {
  const { title, message, confirmText = 'تأكيد', confirmClass = 'btn-danger', onConfirm } = options;
  
  let modal = document.getElementById('confirm-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'confirm-modal';
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal-box modal-sm">
        <div class="modal-header">
          <h3 class="modal-title" id="confirm-title"></h3>
          <button class="modal-close" data-close-modal>✕</button>
        </div>
        <div class="modal-body">
          <p id="confirm-message" style="color:var(--text-secondary);line-height:1.7;font-size:0.9rem;"></p>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" data-close-modal>إلغاء</button>
          <button class="btn" id="confirm-ok-btn"></button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  }
  
  document.getElementById('confirm-title').textContent = title || 'تأكيد';
  document.getElementById('confirm-message').textContent = message || '';
  const okBtn = document.getElementById('confirm-ok-btn');
  okBtn.textContent = confirmText;
  okBtn.className = `btn ${confirmClass}`;
  okBtn.onclick = () => { Modal.close('confirm-modal'); onConfirm && onConfirm(); };
  
  // Close button
  modal.querySelectorAll('[data-close-modal]').forEach(btn => {
    btn.onclick = () => Modal.close('confirm-modal');
  });
  
  Modal.open('confirm-modal');
}

// ========================
// Sidebar Toggle (Mobile)
// ========================
document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.getElementById('sidebar-toggle');
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  const closeBtn = document.getElementById('sidebar-close-btn');

  function openSidebar() {
    if (sidebar) sidebar.classList.add('open');
    if (overlay) overlay.classList.add('active');
    document.body.style.overflow = 'hidden';
  }

  function closeSidebar() {
    if (sidebar) sidebar.classList.remove('open');
    if (overlay) overlay.classList.remove('active');
    document.body.style.overflow = '';
  }

  if (toggle) {
    toggle.addEventListener('click', (e) => {
      e.stopPropagation();
      if (sidebar && sidebar.classList.contains('open')) {
        closeSidebar();
      } else {
        openSidebar();
      }
    });
  }

  if (closeBtn) {
    closeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      closeSidebar();
    });
  }

  if (overlay) {
    overlay.addEventListener('click', closeSidebar);
  }

  // Close sidebar on link click on small screens
  document.querySelectorAll('.sidebar-nav .nav-link').forEach(link => {
    link.addEventListener('click', () => {
      if (window.innerWidth <= 900) {
        closeSidebar();
      }
    });
  });

  // Auto-dismiss flash messages
  document.querySelectorAll('.flash-msg').forEach(el => {
    setTimeout(() => el.style.display = 'none', 5000);
  });
});

// ========================
// Delete Subscription
// ========================
function deleteSubscription(subId, username) {
  showConfirm({
    title: 'حذف الاشتراك',
    message: `هل أنت متأكد من حذف اشتراك "${username}" نهائياً؟ سيتم حذفه من الراوتر وقاعدة البيانات.`,
    confirmText: 'حذف نهائياً',
    confirmClass: 'btn-danger',
    onConfirm: async () => {
      const btn = document.querySelector(`[data-delete="${subId}"]`);
      const restore = btn ? btnLoading(btn) : null;
      try {
        const res = await apiPost(`/subscriptions/${subId}/delete`);
        if (res.ok) {
          Toast.success(res.message);
          document.getElementById(`sub-row-${subId}`)?.remove();
          // تحديث العدادات
          updateCounters();
        } else {
          Toast.error(res.message || 'فشل الحذف');
        }
      } catch(e) {
        Toast.error('حدث خطأ في الاتصال');
      } finally {
        restore && restore();
      }
    }
  });
}

// ========================
// Toggle Disable
// ========================
async function toggleDisable(subId, username, currentDisabled) {
  const action = currentDisabled ? 'تفعيل' : 'تعطيل';
  showConfirm({
    title: `${action} الاشتراك`,
    message: `هل تريد ${action} اشتراك "${username}"؟`,
    confirmText: action,
    confirmClass: currentDisabled ? 'btn-success' : 'btn-warning',
    onConfirm: async () => {
      try {
        const res = await apiPost(`/subscriptions/${subId}/toggle-disable`);
        if (res.ok) {
          Toast.success(res.message);
          // تحديث الزر والشارة في الجدول
          const row = document.getElementById(`sub-row-${subId}`);
          if (row) {
            const badge = row.querySelector('.sub-status-badge');
            const toggleBtn = row.querySelector('.toggle-btn');
            if (res.disabled) {
              badge && (badge.className = 'badge badge-disabled', badge.textContent = 'موقوف');
              toggleBtn && (toggleBtn.title = 'تفعيل', toggleBtn.dataset.disabled = 'true');
            } else {
              badge && (badge.className = 'badge badge-active', badge.textContent = 'نشط');
              toggleBtn && (toggleBtn.title = 'تعطيل', toggleBtn.dataset.disabled = 'false');
            }
          }
        } else {
          Toast.error(res.message);
        }
      } catch(e) {
        Toast.error('حدث خطأ في الاتصال');
      }
    }
  });
}

// ========================
// Active Sessions Loader
// ========================
let sessionsInterval = null;

function loadActiveSessions(deviceId) {
  if (!deviceId) return;
  const container = document.getElementById('active-sessions-container');
  const refreshBtn = document.getElementById('refresh-sessions-btn');
  if (!container) return;
  
  if (refreshBtn) {
    const restore = btnLoading(refreshBtn);
    _fetchSessions(deviceId, container).finally(restore);
  } else {
    _fetchSessions(deviceId, container);
  }
}

async function _fetchSessions(deviceId, container) {
  try {
    const res = await fetch(`/api/active-sessions/${deviceId}`);
    const data = await res.json();
    if (!data.ok) {
      container.innerHTML = `<div class="empty-state"><span class="empty-icon">⚠️</span><h3>${data.message}</h3></div>`;
      return;
    }
    const sessions = data.data || [];
    document.getElementById('sessions-count')?.textContent && (document.getElementById('sessions-count').textContent = sessions.length);
    
    if (sessions.length === 0) {
      container.innerHTML = `<div class="empty-state"><span class="empty-icon">🔌</span><h3>لا توجد جلسات متصلة حالياً</h3></div>`;
      return;
    }
    
    container.innerHTML = `
      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>المستخدم</th><th>عنوان IP</th><th>MAC / Caller-ID</th>
              <th>مدة الاتصال</th><th>تنزيل</th><th>رفع</th><th>إجراء</th>
            </tr>
          </thead>
          <tbody>
            ${sessions.map(s => `
              <tr class="session-row">
                <td><span class="session-username">${s.name || '-'}</span></td>
                <td><span class="session-ip">${s.address || '-'}</span></td>
                <td><span class="mono fs-sm">${s['caller-id'] || '-'}</span></td>
                <td><span class="session-uptime">${s.uptime || '-'}</span></td>
                <td><span class="bytes-display">${formatBytes(parseInt(s['bytes-in']||0))}</span></td>
                <td><span class="bytes-display">${formatBytes(parseInt(s['bytes-out']||0))}</span></td>
                <td>
                  <button class="btn btn-danger btn-xs" onclick="disconnectSession('${deviceId}','${s['.id']}','${s.name||''}')">
                    قطع
                  </button>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>`;
  } catch(e) {
    container.innerHTML = `<div class="empty-state"><span class="empty-icon">❌</span><h3>خطأ في الاتصال بالخادم</h3></div>`;
  }
}

async function disconnectSession(deviceId, sessionId, username) {
  showConfirm({
    title: 'قطع الجلسة',
    message: `هل تريد قطع اتصال "${username}" فوراً؟`,
    confirmText: 'قطع الاتصال',
    confirmClass: 'btn-danger',
    onConfirm: async () => {
      try {
        const res = await apiPost('/api/disconnect-session', { device_id: parseInt(deviceId), session_id: sessionId });
        if (res.ok) {
          Toast.success(res.message);
          loadActiveSessions(deviceId);
        } else {
          Toast.error(res.message);
        }
      } catch(e) {
        Toast.error('حدث خطأ في الاتصال');
      }
    }
  });
}

// ========================
// Sync Functions
// ========================
async function syncProfiles(deviceId) {
  const btn = document.getElementById('sync-profiles-btn');
  const restore = btn ? btnLoading(btn) : null;
  try {
    const res = await apiPost(`/api/sync-profiles/${deviceId}`);
    if (res.ok) Toast.success(res.message);
    else Toast.error(res.message);
  } catch(e) {
    Toast.error('خطأ في المزامنة');
  } finally {
    restore && restore();
  }
}

async function syncSecrets(deviceId) {
  const btn = document.getElementById('sync-secrets-btn');
  const restore = btn ? btnLoading(btn) : null;
  Toast.info('جاري مزامنة الاشتراكات من الراوتر...');
  try {
    const res = await apiPost(`/api/sync-secrets/${deviceId}`);
    if (res.ok) { Toast.success(res.message); setTimeout(() => location.reload(), 1500); }
    else Toast.error(res.message);
  } catch(e) {
    Toast.error('خطأ في المزامنة');
  } finally {
    restore && restore();
  }
}

async function testDevice(deviceId) {
  const btn = document.getElementById(`test-btn-${deviceId}`);
  const restore = btn ? btnLoading(btn) : null;
  const statusEl = document.getElementById(`device-status-${deviceId}`);
  try {
    const res = await apiPost(`/admin/devices/${deviceId}/test`);
    if (res.ok) {
      Toast.success(res.message);
      if (statusEl) { statusEl.className = 'status-dot online'; statusEl.title = 'متصل'; }
    } else {
      Toast.error(res.message);
      if (statusEl) { statusEl.className = 'status-dot offline'; statusEl.title = 'غير متصل'; }
    }
  } catch(e) {
    Toast.error('خطأ في فحص الاتصال');
  } finally {
    restore && restore();
  }
}

// ========================
// Utility
// ========================
function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024, sizes = ['B','KB','MB','GB','TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return (bytes / Math.pow(k, i)).toFixed(1) + ' ' + sizes[i];
}

function updateCounters() {
  // يتم تنفيذه بعد حذف/تعطيل لتحديث الأرقام في الصفحة
}

// ========================
// Form Submission via AJAX
// ========================
function submitFormAjax(formId, successCallback) {
  const form = document.getElementById(formId);
  if (!form) return;
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const btn = form.querySelector('[type="submit"]');
    const restore = btn ? btnLoading(btn) : null;
    
    const data = {};
    new FormData(form).forEach((v, k) => { data[k] = v; });
    
    try {
      const res = await apiPost(form.action, data);
      if (res.ok) {
        Toast.success(res.message);
        successCallback && successCallback(res);
      } else {
        Toast.error(res.message || 'حدث خطأ');
      }
    } catch(e) {
      Toast.error('خطأ في الاتصال بالخادم');
    } finally {
      restore && restore();
    }
  });
}

// Profile price quick-edit
async function setProfilePrice(profId) {
  const priceInput = document.getElementById(`price-${profId}`);
  if (!priceInput) return;
  const price = parseFloat(priceInput.value || 0);
  try {
    const res = await apiPost(`/profiles/${profId}/set-price`, { price, currency: 'IQD' });
    if (res.ok) Toast.success('تم تحديث السعر');
    else Toast.error(res.message);
  } catch(e) {
    Toast.error('خطأ في الاتصال');
  }
}

// Device selector - redirect on change
document.querySelectorAll('.device-select').forEach(sel => {
  sel.addEventListener('change', () => {
    const url = new URL(window.location);
    url.searchParams.set('device_id', sel.value);
    url.searchParams.delete('page');
    window.location = url.toString();
  });
});


// ========================================================
// CUSTOM SEARCHABLE DROPDOWN (قوائم الاختيار التفاعلية الموحدة)
// ========================================================
function initSearchableSelects(container = document) {
  const selects = container.querySelectorAll('select.searchable-select, select[data-searchable="true"]');
  selects.forEach(selectEl => makeSearchableSelect(selectEl));
}

function makeSearchableSelect(selectEl) {
  if (!selectEl || selectEl.dataset.customized === 'true') return;
  selectEl.dataset.customized = 'true';
  selectEl.style.display = 'none';

  const wrapper = document.createElement('div');
  wrapper.className = 'custom-select-wrapper';

  const selectedOpt = selectEl.options[selectEl.selectedIndex] || selectEl.options[0];
  const placeholder = selectEl.dataset.placeholder || (selectedOpt ? selectedOpt.text : 'اختر من القائمة...');

  const trigger = document.createElement('div');
  trigger.className = 'custom-select-trigger';
  trigger.innerHTML = `
    <span class="custom-select-text">${selectedOpt ? selectedOpt.text : placeholder}</span>
    <span class="custom-select-arrow">▼</span>
  `;

  const dropdown = document.createElement('div');
  dropdown.className = 'custom-select-dropdown';

  const searchBox = document.createElement('div');
  searchBox.className = 'custom-select-search-box';
  const searchInput = document.createElement('input');
  searchInput.type = 'text';
  searchInput.className = 'custom-select-search-input';
  searchInput.placeholder = '🔍 اكتب للبحث السريع...';
  searchBox.appendChild(searchInput);
  dropdown.appendChild(searchBox);

  const list = document.createElement('ul');
  list.className = 'custom-select-options-list';
  dropdown.appendChild(list);

  function populateOptions(filterText = '') {
    list.innerHTML = '';
    let matchCount = 0;
    const query = filterText.trim().toLowerCase();

    Array.from(selectEl.options).forEach((opt) => {
      const text = opt.text;
      const val = opt.value;
      if (!val && !text && opt.index !== 0) return;

      if (!query || text.toLowerCase().includes(query) || (opt.dataset.keywords && opt.dataset.keywords.toLowerCase().includes(query))) {
        matchCount++;
        const li = document.createElement('li');
        li.className = 'custom-select-option' + (opt.selected ? ' selected' : '');
        
        let badgeHtml = '';
        if (opt.dataset.badge) {
          badgeHtml = `<span class="custom-select-option-badge">${opt.dataset.badge}</span>`;
        }
        li.innerHTML = `<span>${text}</span>${badgeHtml}`;
        
        li.addEventListener('click', (e) => {
          e.stopPropagation();
          selectEl.value = val;
          trigger.querySelector('.custom-select-text').textContent = text;
          wrapper.classList.remove('open');
          searchInput.value = '';
          selectEl.dispatchEvent(new Event('change', { bubbles: true }));
          populateOptions();
        });
        list.appendChild(li);
      }
    });

    if (matchCount === 0) {
      const empty = document.createElement('li');
      empty.className = 'custom-select-empty';
      empty.textContent = 'لا توجد نتائج مطابقة';
      list.appendChild(empty);
    }
  }

  populateOptions();

  searchInput.addEventListener('input', (e) => {
    populateOptions(e.target.value);
  });

  searchInput.addEventListener('click', (e) => e.stopPropagation());

  trigger.addEventListener('click', (e) => {
    e.stopPropagation();
    const isOpen = wrapper.classList.contains('open');
    document.querySelectorAll('.custom-select-wrapper.open').forEach(w => w.classList.remove('open'));
    if (!isOpen) {
      wrapper.classList.add('open');
      populateOptions();
      setTimeout(() => searchInput.focus(), 60);
    }
  });

  selectEl.parentNode.insertBefore(wrapper, selectEl);
  wrapper.appendChild(selectEl);
  wrapper.appendChild(trigger);
  wrapper.appendChild(dropdown);

  // تحديث العنصر برمجياً عند تغيير الـ select من جافاسكريبت
  selectEl.addEventListener('refreshCustomSelect', () => {
    const curr = selectEl.options[selectEl.selectedIndex];
    trigger.querySelector('.custom-select-text').textContent = curr ? curr.text : placeholder;
    populateOptions();
  });
}

// إغلاق أي قائمة منسدلة مفتوحة عند النقر خارجها
document.addEventListener('click', (e) => {
  if (!e.target.closest('.custom-select-wrapper')) {
    document.querySelectorAll('.custom-select-wrapper.open').forEach(w => w.classList.remove('open'));
  }
});

// ========================================================
// QUICK RENEWAL MODAL (نافذة التجديد والاشتراك السريع)
// ========================================================
let allSubscribersCache = [];

async function openQuickRenewModal(subId = null, prefillUsername = null) {
  const modal = document.getElementById('quick-renew-modal');
  if (!modal) return;

  const deviceSelect = document.getElementById('qr-device-id');
  const deviceId = deviceSelect ? deviceSelect.value : null;

  // جلب قائمة المشتركين للتعبئة التلقائية
  const userSelect = document.getElementById('qr-existing-user-select');
  if (userSelect && (allSubscribersCache.length === 0 || subId)) {
    try {
      const res = await fetch(`/api/sub-lookup?device_id=${deviceId || ''}`);
      const data = await res.json();
      if (data.ok) {
        allSubscribersCache = data.subs;
        userSelect.innerHTML = '<option value="">-- ابحث أو اختر اسم المستخدم السابق --</option>';
        data.subs.forEach(s => {
          const opt = document.createElement('option');
          opt.value = s.id;
          opt.text = `${s.username} ${s.customer_name ? '(' + s.customer_name + ')' : ''}`;
          opt.dataset.keywords = `${s.username} ${s.customer_name} ${s.customer_phone}`;
          opt.dataset.badge = s.profile_name || 'عام';
          userSelect.appendChild(opt);
        });
        userSelect.dispatchEvent(new Event('refreshCustomSelect'));
      }
    } catch(err) {
      console.error('Error fetching subscribers:', err);
    }
  }

  // إذا تم تمرير مشترك محدد للتجديد
  if (subId) {
    setQuickRenewMode('existing');
    if (userSelect) {
      userSelect.value = subId;
      userSelect.dispatchEvent(new Event('change'));
      userSelect.dispatchEvent(new Event('refreshCustomSelect'));
    }
  }

  Modal.open('quick-renew-modal');
}

function setQuickRenewMode(mode) {
  const modeInput = document.getElementById('qr-mode');
  const tabExisting = document.getElementById('qr-tab-existing');
  const tabNew = document.getElementById('qr-tab-new');
  const existingSection = document.getElementById('qr-existing-section');
  const newSection = document.getElementById('qr-new-section');

  if (modeInput) modeInput.value = mode;

  if (mode === 'existing') {
    tabExisting && tabExisting.classList.add('active');
    tabNew && tabNew.classList.remove('active');
    existingSection && (existingSection.style.display = 'block');
    newSection && (newSection.style.display = 'none');
  } else {
    tabNew && tabNew.classList.add('active');
    tabExisting && tabExisting.classList.remove('active');
    existingSection && (existingSection.style.display = 'none');
    newSection && (newSection.style.display = 'block');
  }
}

// مستمع لاختيار مشترك سابق للتعبئة الفورية
document.addEventListener('DOMContentLoaded', () => {
  initSearchableSelects();

  const userSelect = document.getElementById('qr-existing-user-select');
  if (userSelect) {
    userSelect.addEventListener('change', () => {
      const selectedId = parseInt(userSelect.value);
      const sub = allSubscribersCache.find(s => s.id === selectedId);
      if (sub) {
        // تعبئة البيانات التلقائية
        const nameInput = document.getElementById('qr-customer-name');
        const phoneInput = document.getElementById('qr-customer-phone');
        const priceInput = document.getElementById('qr-price');
        const profileSelect = document.getElementById('qr-profile-id');
        const categorySelect = document.getElementById('qr-category-select');
        const infoBadge = document.getElementById('qr-sub-info-badge');

        if (nameInput) nameInput.value = sub.customer_name || '';
        if (phoneInput) phoneInput.value = sub.customer_phone || '';
        if (priceInput) priceInput.value = sub.price || 0;

        if (infoBadge) {
          infoBadge.style.display = 'block';
          infoBadge.innerHTML = `
            <span>📅 تاريخ الانتهاء الحالي: <strong>${sub.expires_at || 'غير محدد'}</strong></span>
            <span>(${sub.days_remaining !== null ? (sub.days_remaining > 0 ? 'متبقي ' + sub.days_remaining + ' يوم' : 'منتهي') : '—'})</span>
          `;
        }

        // تحديد فئة وباقة المشترك
        if (categorySelect && sub.category) {
          categorySelect.value = sub.category;
          categorySelect.dispatchEvent(new Event('refreshCustomSelect'));
          filterProfilesByCategory(sub.category, sub.profile_id);
        } else if (profileSelect && sub.profile_id) {
          profileSelect.value = sub.profile_id;
          profileSelect.dispatchEvent(new Event('refreshCustomSelect'));
        }
      }
    });
  }

  // فلترة الباقات عند تغيير الفئة
  const catSelect = document.getElementById('qr-category-select');
  if (catSelect) {
    catSelect.addEventListener('change', () => {
      filterProfilesByCategory(catSelect.value);
    });
  }

  // تحديث السعر عند تغيير الباقة
  const profSelect = document.getElementById('qr-profile-id');
  if (profSelect) {
    profSelect.addEventListener('change', () => {
      const opt = profSelect.options[profSelect.selectedIndex];
      if (opt && opt.dataset.price) {
        const priceInput = document.getElementById('qr-price');
        if (priceInput) priceInput.value = opt.dataset.price;
      }
    });
  }
});

function filterProfilesByCategory(category, selectProfileId = null) {
  const profSelect = document.getElementById('qr-profile-id');
  if (!profSelect) return;

  Array.from(profSelect.options).forEach(opt => {
    if (!opt.value) return; // ignore default
    if (!category || category === 'all' || opt.dataset.category === category) {
      opt.style.display = '';
    } else {
      opt.style.display = 'none';
    }
  });

  if (selectProfileId) {
    profSelect.value = selectProfileId;
  }
  profSelect.dispatchEvent(new Event('refreshCustomSelect'));
}

// تنفيذ التجديد والحفظ السريع مع التأكيد والسبينر
async function submitQuickRenew(event) {
  event.preventDefault();
  const form = document.getElementById('quick-renew-form');
  if (!form) return;

  const mode = document.getElementById('qr-mode').value;
  let confirmMsg = 'هل أنت متأكد من حفظ وتفعيل الاشتراك؟';

  if (mode === 'existing') {
    const userSel = document.getElementById('qr-existing-user-select');
    const uText = userSel && userSel.options[userSel.selectedIndex] ? userSel.options[userSel.selectedIndex].text : '';
    if (!userSel.value) {
      Toast.error('يرجى اختيار اسم المستخدم المراد تجديد اشتراكه');
      return;
    }
    confirmMsg = `تأكيد تجديد الاشتراك للمستخدم: ${uText}؟`;
  } else {
    const uname = document.getElementById('qr-new-username').value.trim();
    if (!uname) {
      Toast.error('يرجى إدخال اسم المستخدم الجديد');
      return;
    }
    confirmMsg = `تأكيد إنشاء وتفعيل اشتراك جديد للمستخدم: ${uname}؟`;
  }

  showConfirm({
    title: 'تأكيد التجديد والحفظ',
    message: confirmMsg,
    confirmText: 'تجديد وحفظ الآن',
    confirmClass: 'btn-primary',
    onConfirm: async () => {
      const submitBtn = document.getElementById('qr-submit-btn');
      const restore = submitBtn ? btnLoading(submitBtn) : null;

      const formData = new FormData(form);
      const payload = {};
      formData.forEach((val, key) => { payload[key] = val; });

      try {
        const res = await apiPost('/subscriptions/quick-renew', payload);
        if (res.ok) {
          Toast.success(res.message);
          Modal.close('quick-renew-modal');
          // تحديث الصفحة أو العنصر بعد ثانية
          setTimeout(() => window.location.reload(), 1200);
        } else {
          Toast.error(res.message || 'حدث خطأ أثناء التجديد');
        }
      } catch (err) {
        Toast.error('خطأ في الاتصال بالخادم');
      } finally {
        restore && restore();
      }
    }
  });
}

// ========================================================
// EMPLOYEE SETTLEMENTS & ZEROING (سندات وتصفير الموظفين)
// ========================================================
function openSettlementModal(userId, userName, currentBalance) {
  const modal = document.getElementById('settlement-modal');
  if (!modal) return;

  document.getElementById('settlement-user-id').value = userId;
  document.getElementById('settlement-user-name').textContent = userName;
  document.getElementById('settlement-curr-balance').textContent = currentBalance + ' د.ع';
  document.getElementById('settlement-amount').value = currentBalance > 0 ? currentBalance : '';

  Modal.open('settlement-modal');
}

async function submitSettlement(event) {
  event.preventDefault();
  const form = document.getElementById('settlement-form');
  if (!form) return;

  const btn = document.getElementById('settlement-submit-btn');
  const restore = btn ? btnLoading(btn) : null;

  const formData = new FormData(form);
  const payload = {};
  formData.forEach((v, k) => { payload[k] = v; });

  try {
    const res = await apiPost('/accounting/settlements/add', payload);
    if (res.ok) {
      Toast.success(res.message);
      Modal.close('settlement-modal');
      setTimeout(() => window.location.reload(), 1000);
    } else {
      Toast.error(res.message || 'فشل تسجيل السند');
    }
  } catch (err) {
    Toast.error('خطأ في الاتصال');
  } finally {
    restore && restore();
  }
}

function confirmZeroBalance(userId, userName, balance) {
  if (balance <= 0) {
    Toast.info(`رصيد الموظف ${userName} مصفّر مسبقاً ولا توجد مبالغ في ذمته.`);
    return;
  }

  showConfirm({
    title: 'تأكيد تصفير الحساب بالكامل',
    message: `هل أنت متأكد من تصفير حساب الموظف (${userName}) واستلام كامل المبلغ المتبقي (${balance} د.ع) وإنشاء سند تسوية تصفير؟`,
    confirmText: 'تصفير الحساب الآن',
    confirmClass: 'btn-danger',
    onConfirm: async () => {
      try {
        const res = await apiPost(`/accounting/settlements/zero/${userId}`, {});
        if (res.ok) {
          Toast.success(res.message);
          setTimeout(() => window.location.reload(), 1000);
        } else {
          Toast.error(res.message || 'فشل تصفير الحساب');
        }
      } catch (err) {
        Toast.error('خطأ في الاتصال بالخادم');
      }
    }
  });
}


// Auto-inject CSRF token to all POST forms on the page
function ensureFormCsrfTokens() {
  const token = getCsrfToken();
  if (!token) return;
  document.querySelectorAll('form').forEach(form => {
    const method = (form.getAttribute('method') || '').toUpperCase();
    if (method === 'POST') {
      let csrfInput = form.querySelector('input[name="csrf_token"]');
      if (!csrfInput) {
        csrfInput = document.createElement('input');
        csrfInput.type = 'hidden';
        csrfInput.name = 'csrf_token';
        form.prepend(csrfInput);
      }
      csrfInput.value = token;
    }
  });
}

document.addEventListener('DOMContentLoaded', ensureFormCsrfTokens);


async function syncSubscriptions(deviceId, btn) {
  const restore = btnLoading(btn);
  try {
    const res = await apiPost(`/api/sync-subscriptions/${deviceId}`);
    if (res.ok) {
      Toast.success(res.message);
      setTimeout(() => location.reload(), 1200);
    } else {
      Toast.error(res.message);
    }
  } catch (e) {
    Toast.error('خطأ في استيراد المشتركين');
  } finally {
    restore();
  }
}
