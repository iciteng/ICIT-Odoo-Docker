/**
 * ICIT SaaS Admin Dashboard
 * Handles tenant management UI: listing, filtering, CRUD, and detail views.
 */
(function () {
    'use strict';

    /* =============================================
       State
       ============================================= */
    var state = {
        tenants: [],
        filteredTenants: [],
        currentFilter: 'all',
        searchQuery: '',
        selectedTenantId: null,
        csrfToken: ''
    };

    /* =============================================
       DOM References
       ============================================= */
    var dom = {};

    function cacheDom() {
        dom.statsGrid = document.getElementById('statsGrid');
        dom.statTenants = document.getElementById('statTenants');
        dom.statActive = document.getElementById('statActive');
        dom.statUsers = document.getElementById('statUsers');
        dom.statStorage = document.getElementById('statStorage');
        dom.tenantsGrid = document.getElementById('tenantsGrid');
        dom.tenantsLoading = document.getElementById('tenantsLoading');
        dom.tenantsEmpty = document.getElementById('tenantsEmpty');
        dom.searchInput = document.getElementById('searchInput');
        dom.filterPills = document.querySelectorAll('.pill[data-filter]');
        dom.btnAddTenant = document.getElementById('btnAddTenant');
        dom.slideoutOverlay = document.getElementById('slideoutOverlay');
        dom.tenantSlideout = document.getElementById('tenantSlideout');
        dom.slideoutTitle = document.getElementById('slideoutTitle');
        dom.slideoutBody = document.getElementById('slideoutBody');
        dom.btnCloseSlideout = document.getElementById('btnCloseSlideout');
        dom.detailCompany = document.getElementById('detailCompany');
        dom.detailAdmin = document.getElementById('detailAdmin');
        dom.detailPlan = document.getElementById('detailPlan');
        dom.detailStatus = document.getElementById('detailStatus');
        dom.detailUsers = document.getElementById('detailUsers');
        dom.detailCreated = document.getElementById('detailCreated');
        dom.btnEditTenant = document.getElementById('btnEditTenant');
        dom.btnToggleStatus = document.getElementById('btnToggleStatus');
        dom.btnDeleteTenant = document.getElementById('btnDeleteTenant');
        dom.appList = document.getElementById('appList');
        dom.userList = document.getElementById('userList');
        dom.usageChart = document.getElementById('usageChart');
        dom.modalOverlay = document.getElementById('modalOverlay');
        dom.modalTitle = document.getElementById('modalTitle');
        dom.btnCloseModal = document.getElementById('btnCloseModal');
        dom.btnCancelModal = document.getElementById('btnCancelModal');
        dom.btnSubmitModal = document.getElementById('btnSubmitModal');
        dom.tenantForm = document.getElementById('tenantForm');
        dom.tenantId = document.getElementById('tenantId');
        dom.companyName = document.getElementById('companyName');
        dom.adminEmail = document.getElementById('adminEmail');
        dom.adminName = document.getElementById('adminName');
        dom.tenantPlan = document.getElementById('tenantPlan');
        dom.maxUsers = document.getElementById('maxUsers');
        dom.adminPassword = document.getElementById('adminPassword');
        dom.passwordGroup = document.getElementById('passwordGroup');
        dom.toastContainer = document.getElementById('toastContainer');
        dom.adminModalOverlay = document.getElementById('adminModalOverlay');
        dom.btnManageAdmins = document.getElementById('btnManageAdmins');
        dom.btnCloseAdminModal = document.getElementById('btnCloseAdminModal');
        dom.btnAddAdmin = document.getElementById('btnAddAdmin');
        dom.newAdminEmail = document.getElementById('newAdminEmail');
        dom.newAdminName = document.getElementById('newAdminName');
        dom.newAdminPassword = document.getElementById('newAdminPassword');
        dom.adminList = document.getElementById('adminList');
    }

    /* =============================================
       API Helpers
       ============================================= */
    var VALID_STATUSES = { active: true, trial: true, suspended: true };

    function getHeaders() {
        var headers = {
            'Content-Type': 'application/json'
        };
        if (state.csrfToken) {
            headers['X-CSRF-Token'] = state.csrfToken;
        }
        return headers;
    }

    function apiCall(url, data) {
        return fetch(url, {
            method: 'POST',
            headers: getHeaders(),
            credentials: 'same-origin',
            body: JSON.stringify({
                jsonrpc: '2.0',
                params: data || {}
            })
        }).then(handleResponse);
    }

    function handleResponse(resp) {
        if (!resp.ok) {
            return resp.json().catch(function () {
                throw new Error('Request failed: ' + resp.status);
            }).then(function (data) {
                var msg = (data.error && data.error.data && data.error.data.message) || data.error || ('Request failed: ' + resp.status);
                throw new Error(msg);
            });
        }
        return resp.json().then(function (data) {
            if (data.error) {
                var msg = (data.error.data && data.error.data.message) || data.error.message || data.error;
                throw new Error(msg);
            }
            if (data.result) {
                if (data.result.error) {
                    throw new Error(data.result.error);
                }
                return data.result;
            }
            return data;
        }).catch(function (err) {
            if (err instanceof Error) { throw err; }
            throw new Error('Invalid response from server');
        });
    }

    /* =============================================
       Stats
       ============================================= */
    function loadStats() {
        apiCall('/admin/api/stats')
            .then(function (data) {
                dom.statTenants.textContent = data.total_tenants || 0;
                dom.statActive.textContent = data.active_today || 0;
                dom.statUsers.textContent = data.total_users || 0;
                dom.statStorage.textContent = formatStorage(data.storage_mb || 0);
            })
            .catch(function () {
                dom.statTenants.textContent = '0';
                dom.statActive.textContent = '0';
                dom.statUsers.textContent = '0';
                dom.statStorage.textContent = '0 MB';
            });
    }

    function formatStorage(mb) {
        if (mb >= 1024) {
            return (mb / 1024).toFixed(1) + ' GB';
        }
        return Math.round(mb) + ' MB';
    }

    /* =============================================
       Tenants List
       ============================================= */
    function loadTenants() {
        showLoading();
        apiCall('/admin/api/tenants/list')
            .then(function (data) {
                state.tenants = data.tenants || data || [];
                applyFilters();
            })
            .catch(function (err) {
                showToast('Failed to load companies: ' + err.message, 'error');
                state.tenants = [];
                applyFilters();
            });
    }

    function applyFilters() {
        var filtered = state.tenants;

        if (state.currentFilter !== 'all') {
            filtered = filtered.filter(function (t) {
                return t.status === state.currentFilter;
            });
        }

        if (state.searchQuery) {
            var q = state.searchQuery.toLowerCase();
            filtered = filtered.filter(function (t) {
                var name = (t.company_name || '').toLowerCase();
                var admin = (t.admin_email || '').toLowerCase();
                return name.indexOf(q) !== -1 || admin.indexOf(q) !== -1;
            });
        }

        state.filteredTenants = filtered;
        renderTenants();
    }

    function renderTenants() {
        var grid = dom.tenantsGrid;
        grid.innerHTML = '';

        if (state.filteredTenants.length === 0) {
            dom.tenantsEmpty.style.display = 'flex';
            return;
        }

        dom.tenantsEmpty.style.display = 'none';

        state.filteredTenants.forEach(function (tenant) {
            grid.appendChild(createTenantCard(tenant));
        });
    }

    function createTenantCard(tenant) {
        var card = document.createElement('div');
        card.className = 'tenant-card';
        card.setAttribute('data-id', tenant.id);

        var safeStatus = VALID_STATUSES[tenant.status] ? tenant.status : 'active';
        var statusClass = 'badge--' + safeStatus;
        var planLabel = escapeHtml(capitalize(tenant.plan || 'free'));
        var statusLabel = escapeHtml(capitalize(safeStatus));
        var userCount = tenant.user_count || tenant.active_users || 0;
        var maxUsers = tenant.max_users || '-';
        var adminEmail = tenant.admin_email || '-';
        var createdDate = tenant.created_date ? formatDate(tenant.created_date) : '-';

        card.innerHTML =
            '<div class="tenant-card-header">' +
                '<span class="tenant-name">' + escapeHtml(tenant.company_name || 'Unnamed') + '</span>' +
                '<span class="badge ' + statusClass + '">' + statusLabel + '</span>' +
            '</div>' +
            '<div class="tenant-card-meta">' +
                '<span class="badge badge--plan">' + planLabel + '</span>' +
                '<div class="tenant-card-stats">' +
                    '<span class="tenant-stat">' +
                        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>' +
                        '<strong>' + userCount + '</strong> / ' + maxUsers + ' users' +
                    '</span>' +
                '</div>' +
            '</div>' +
            '<div class="tenant-card-footer">' +
                '<span class="tenant-admin">Admin: <strong>' + escapeHtml(adminEmail) + '</strong></span>' +
                '<span class="tenant-date">' + createdDate + '</span>' +
            '</div>';

        card.addEventListener('click', function () {
            openTenantDetail(tenant.id);
        });

        return card;
    }

    function showLoading() {
        dom.tenantsGrid.innerHTML =
            '<div class="loading-state">' +
                '<div class="spinner"></div>' +
                '<span>Loading companies...</span>' +
            '</div>';
        dom.tenantsEmpty.style.display = 'none';
    }

    /* =============================================
       Tenant Detail (Slideout)
       ============================================= */
    function openTenantDetail(tenantId) {
        state.selectedTenantId = tenantId;
        var tenant = state.tenants.find(function (t) { return t.id === tenantId; });
        if (!tenant) return;

        dom.slideoutTitle.textContent = tenant.company_name || 'Company Details';
        dom.detailCompany.textContent = tenant.company_name || '-';
        dom.detailAdmin.textContent = tenant.admin_email || '-';
        dom.detailPlan.textContent = capitalize(tenant.plan || 'free');
        dom.detailStatus.textContent = capitalize(tenant.status || 'active');
        dom.detailUsers.textContent = (tenant.user_count || 0) + ' / ' + (tenant.max_users || '-');
        dom.detailCreated.textContent = tenant.created_date ? formatDate(tenant.created_date) : '-';

        updateToggleStatusButton(tenant.status);

        dom.slideoutOverlay.classList.add('is-visible');
        dom.tenantSlideout.classList.add('is-open');
        dom.tenantSlideout.setAttribute('aria-hidden', 'false');

        loadTenantUsers(tenantId);
        loadTenantApps(tenantId);
        loadTenantUsage(tenantId);
    }

    function closeTenantDetail() {
        state.selectedTenantId = null;
        dom.slideoutOverlay.classList.remove('is-visible');
        dom.tenantSlideout.classList.remove('is-open');
        dom.tenantSlideout.setAttribute('aria-hidden', 'true');
    }

    function updateToggleStatusButton(status) {
        var btn = dom.btnToggleStatus;
        var span = btn.querySelector('span');
        if (status === 'suspended') {
            span.textContent = 'Activate';
            btn.classList.remove('btn-outline--danger');
        } else {
            span.textContent = 'Suspend';
            btn.classList.add('btn-outline--danger');
        }
    }

    function loadTenantUsers(tenantId) {
        dom.userList.innerHTML =
            '<div class="loading-state loading-state--sm">' +
                '<div class="spinner spinner--sm"></div>' +
            '</div>';

        apiCall('/admin/api/tenants/' + tenantId + '/users')
            .then(function (data) {
                var users = data.users || data || [];
                renderUserList(users);
            })
            .catch(function () {
                dom.userList.innerHTML = '<div class="empty-state" style="padding:16px"><p>Could not load users</p></div>';
            });
    }

    function renderUserList(users) {
        if (users.length === 0) {
            dom.userList.innerHTML = '<div class="empty-state" style="padding:16px"><p>No users</p></div>';
            return;
        }

        dom.userList.innerHTML = '';
        users.forEach(function (user) {
            var initials = getInitials(user.name || user.login || '?');
            var item = document.createElement('div');
            item.className = 'user-item';
            item.innerHTML =
                '<div class="user-avatar">' + initials + '</div>' +
                '<div class="user-info">' +
                    '<div class="user-name">' + escapeHtml(user.name || user.login) + '</div>' +
                    '<div class="user-email">' + escapeHtml(user.login || user.email || '') + '</div>' +
                '</div>';
            dom.userList.appendChild(item);
        });
    }

    function loadTenantApps(tenantId) {
        dom.appList.innerHTML =
            '<div class="loading-state loading-state--sm">' +
                '<div class="spinner spinner--sm"></div>' +
            '</div>';

        apiCall('/admin/api/tenants/' + tenantId + '/apps')
            .then(function (data) {
                var apps = data.apps || data || [];
                renderAppList(apps, tenantId);
            })
            .catch(function () {
                dom.appList.innerHTML = '<div class="empty-state" style="padding:16px"><p>Could not load apps</p></div>';
            });
    }

    function renderAppList(apps, tenantId) {
        if (apps.length === 0) {
            dom.appList.innerHTML = '<div class="empty-state" style="padding:16px"><p>No apps configured</p></div>';
            return;
        }

        dom.appList.innerHTML = '';
        apps.forEach(function (app) {
            var item = document.createElement('div');
            item.className = 'app-item';
            item.setAttribute('data-app-id', app.id);

            var installedBadge = app.installed
                ? ''
                : '<span class="badge badge--not-installed">Not available</span>';
            var dependencyBadge = '';
            if (app.locked) {
                var requiredBy = Array.isArray(app.required_by) ? app.required_by.join(', ') : '';
                var title = requiredBy
                    ? ('Required by: ' + requiredBy)
                    : 'Required dependency';
                dependencyBadge = '<span class="badge badge--plan" title="' + escapeHtml(title) + '">Required</span>';
            }
            var isToggleDisabled = !app.installed || app.locked;

            item.innerHTML =
                '<div class="app-item-info">' +
                    '<span class="app-name">' + escapeHtml(app.name || app.module_name) + '</span>' +
                    dependencyBadge +
                    installedBadge +
                '</div>' +
                '<label class="toggle">' +
                    '<input type="checkbox" ' + (app.enabled ? 'checked' : '') + (isToggleDisabled ? ' disabled' : '') + ' data-app-id="' + app.id + '"/>' +
                    '<span class="toggle-track"></span>' +
                    '<span class="toggle-thumb"></span>' +
                '</label>';

            var checkbox = item.querySelector('input');
            checkbox.addEventListener('change', function () {
                toggleApp(tenantId, app.id, this.checked, item);
            });

            dom.appList.appendChild(item);
        });
    }

    function toggleApp(tenantId, appId, enabled, itemEl) {
        var checkbox = itemEl.querySelector('input[type="checkbox"]');
        var nameEl = itemEl.querySelector('.app-name');
        var appName = nameEl ? nameEl.textContent : 'App';

        checkbox.disabled = true;

        showToast((enabled ? 'Enabling' : 'Disabling') + ' ' + appName + '...', 'success');

        apiCall('/admin/api/tenants/' + tenantId + '/apps/' + appId, { enabled: enabled })
            .then(function (result) {
                var msg = enabled ? 'App enabled' : 'App disabled';
                showToast(msg, 'success');
                loadTenantApps(tenantId);
            })
            .catch(function (err) {
                showToast('Failed to update app: ' + err.message, 'error');
                loadTenantApps(tenantId);
            });
    }

    function loadTenantUsage(tenantId) {
        dom.usageChart.innerHTML =
            '<div class="loading-state loading-state--sm">' +
                '<div class="spinner spinner--sm"></div>' +
            '</div>';

        apiCall('/admin/api/tenants/' + tenantId + '/usage')
            .then(function (data) {
                var usage = data.usage || data || [];
                renderUsageChart(usage);
            })
            .catch(function () {
                dom.usageChart.innerHTML = '<div class="empty-state" style="padding:16px"><p>No usage data</p></div>';
            });
    }

    function renderUsageChart(usage) {
        if (usage.length === 0) {
            dom.usageChart.innerHTML = '<div class="empty-state" style="padding:16px"><p>No usage data yet</p></div>';
            return;
        }

        var maxLogins = Math.max.apply(null, usage.map(function (u) { return u.login_count || 0; }));
        if (maxLogins === 0) maxLogins = 1;

        var barsHtml = usage.map(function (u) {
            var height = Math.max(4, ((u.login_count || 0) / maxLogins) * 100);
            return '<div class="chart-bar" style="height:' + height + '%" data-value="' + (u.login_count || 0) + ' logins"></div>';
        }).join('');

        var first = usage[0].date || '';
        var last = usage[usage.length - 1].date || '';

        dom.usageChart.innerHTML =
            '<div class="chart-bars">' + barsHtml + '</div>' +
            '<div class="chart-legend">' +
                '<span>' + formatDate(first) + '</span>' +
                '<span>' + formatDate(last) + '</span>' +
            '</div>';
    }

    /* =============================================
       Tenant CRUD
       ============================================= */
    function openAddModal() {
        dom.modalTitle.textContent = 'Add Company';
        dom.btnSubmitModal.textContent = 'Create Company';
        dom.tenantId.value = '';
        dom.tenantForm.reset();
        dom.maxUsers.value = '5';
        dom.passwordGroup.style.display = '';
        dom.adminPassword.required = true;
        dom.modalOverlay.classList.add('is-visible');
        dom.modalOverlay.setAttribute('aria-hidden', 'false');
    }

    function openEditModal(tenant) {
        dom.modalTitle.textContent = 'Edit Company';
        dom.btnSubmitModal.textContent = 'Save Changes';
        dom.tenantId.value = tenant.id;
        dom.companyName.value = tenant.company_name || '';
        dom.adminEmail.value = tenant.admin_email || '';
        dom.adminName.value = tenant.admin_name || '';
        dom.tenantPlan.value = tenant.plan || 'trial';
        dom.maxUsers.value = tenant.max_users || 5;
        dom.passwordGroup.style.display = 'none';
        dom.adminPassword.required = false;
        dom.modalOverlay.classList.add('is-visible');
        dom.modalOverlay.setAttribute('aria-hidden', 'false');
    }

    function editCurrentTenant() {
        var tenantId = state.selectedTenantId;
        if (!tenantId) return;
        var tenant = state.tenants.find(function (t) { return t.id === tenantId; });
        if (!tenant) return;
        closeTenantDetail();
        openEditModal(tenant);
    }

    function closeModal() {
        dom.modalOverlay.classList.remove('is-visible');
        dom.modalOverlay.setAttribute('aria-hidden', 'true');
    }

    function handleFormSubmit(e) {
        e.preventDefault();

        var id = dom.tenantId.value;
        var payload = {
            company_name: dom.companyName.value.trim(),
            admin_email: dom.adminEmail.value.trim(),
            admin_name: dom.adminName.value.trim(),
            plan: dom.tenantPlan.value,
            max_users: parseInt(dom.maxUsers.value, 10) || 5
        };

        if (!id) {
            payload.admin_password = dom.adminPassword.value.trim();
        }

        if (!payload.company_name || !payload.admin_email || !payload.admin_name) {
            showToast('Please fill in all required fields', 'error');
            return;
        }
        if (!id && !payload.admin_password) {
            showToast('Password is required for new companies', 'error');
            return;
        }

        var promise;

        if (id) {
            promise = apiCall('/admin/api/tenants/' + id + '/update', payload);
        } else {
            promise = apiCall('/admin/api/tenants', payload);
        }

        dom.btnSubmitModal.disabled = true;
        dom.btnSubmitModal.textContent = id ? 'Saving...' : 'Creating...';

        promise
            .then(function () {
                showToast(id ? 'Company updated' : 'Company created', 'success');
                closeModal();
                loadTenants();
                loadStats();
            })
            .catch(function (err) {
                showToast('Error: ' + err.message, 'error');
            })
            .finally(function () {
                dom.btnSubmitModal.disabled = false;
                dom.btnSubmitModal.textContent = id ? 'Save Changes' : 'Create Company';
            });
    }

    function toggleTenantStatus() {
        var tenantId = state.selectedTenantId;
        if (!tenantId) return;

        var tenant = state.tenants.find(function (t) { return t.id === tenantId; });
        if (!tenant) return;

        var newStatus = tenant.status === 'suspended' ? 'active' : 'suspended';
        var action = newStatus === 'suspended' ? 'suspend' : 'activate';

        if (!confirm('Are you sure you want to ' + action + ' ' + (tenant.company_name || 'this company') + '?')) {
            return;
        }

        apiCall('/admin/api/tenants/' + tenantId + '/update', { status: newStatus })
            .then(function () {
                showToast('Company ' + action + 'd', 'success');
                loadTenants();
                loadStats();
                closeTenantDetail();
            })
            .catch(function (err) {
                showToast('Error: ' + err.message, 'error');
            });
    }

    function deleteTenant() {
        var tenantId = state.selectedTenantId;
        if (!tenantId) return;

        var tenant = state.tenants.find(function (t) { return t.id === tenantId; });
        var name = tenant ? tenant.company_name : 'this company';

        if (!confirm('Are you sure you want to delete ' + name + '? This action cannot be undone.')) {
            return;
        }

        apiCall('/admin/api/tenants/' + tenantId + '/delete')
            .then(function () {
                showToast('Company deleted', 'success');
                closeTenantDetail();
                loadTenants();
                loadStats();
            })
            .catch(function (err) {
                showToast('Error: ' + err.message, 'error');
            });
    }

    /* =============================================
       Filter & Search
       ============================================= */
    function setFilter(filter) {
        state.currentFilter = filter;
        dom.filterPills.forEach(function (pill) {
            pill.classList.toggle('pill--active', pill.getAttribute('data-filter') === filter);
        });
        applyFilters();
    }

    function handleSearch(e) {
        state.searchQuery = e.target.value;
        applyFilters();
    }

    /* =============================================
       Toast Notifications
       ============================================= */
    function showToast(message, type) {
        type = type || 'success';
        var iconSvg = type === 'success'
            ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>'
            : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';

        var toast = document.createElement('div');
        toast.className = 'toast toast--' + type;
        toast.innerHTML = '<span class="toast-icon">' + iconSvg + '</span><span>' + escapeHtml(message) + '</span>';

        dom.toastContainer.appendChild(toast);

        setTimeout(function () {
            toast.style.animation = 'toast-out 0.3s ease forwards';
            setTimeout(function () {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, 4000);
    }

    /* =============================================
       Utility Functions
       ============================================= */
    function escapeHtml(str) {
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    function capitalize(str) {
        if (!str) return '';
        return str.charAt(0).toUpperCase() + str.slice(1);
    }

    function formatDate(dateStr) {
        if (!dateStr) return '-';
        try {
            var d = new Date(dateStr);
            if (isNaN(d.getTime())) return escapeHtml(String(dateStr));
            return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        } catch (e) {
            return escapeHtml(String(dateStr));
        }
    }

    function getInitials(name) {
        return name
            .split(/\s+/)
            .slice(0, 2)
            .map(function (w) { return w.charAt(0).toUpperCase(); })
            .join('');
    }

    /* =============================================
       Admin Users Management
       ============================================= */
    function openAdminModal() {
        dom.adminModalOverlay.classList.add('is-visible');
        dom.adminModalOverlay.setAttribute('aria-hidden', 'false');
        loadAdmins();
    }

    function closeAdminModal() {
        dom.adminModalOverlay.classList.remove('is-visible');
        dom.adminModalOverlay.setAttribute('aria-hidden', 'true');
    }

    function loadAdmins() {
        var listEl = dom.adminList;
        listEl.innerHTML = '<div class="loading-state loading-state--sm"><div class="spinner spinner--sm"></div></div>';
        apiCall('/admin/api/admins')
            .then(function (data) {
                var admins = data.admins || [];
                if (admins.length === 0) {
                    listEl.innerHTML = '<p style="color:rgba(255,255,255,0.5);text-align:center;padding:16px;">No admin users found.</p>';
                    return;
                }
                var html = '';
                admins.forEach(function (admin) {
                    html += '<div class="admin-item" data-admin-id="' + admin.id + '">';
                    html += '<div class="admin-item-info">';
                    html += '<span class="admin-item-name">' + escapeHtml(admin.name) + '</span>';
                    html += '<span class="admin-item-email">' + escapeHtml(admin.login) + '</span>';
                    html += '</div>';
                    html += '<button class="btn-icon btn-remove-admin" data-user-id="' + admin.id + '" title="Remove admin access">';
                    html += '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>';
                    html += '</button>';
                    html += '</div>';
                });
                listEl.innerHTML = html;

                listEl.querySelectorAll('.btn-remove-admin').forEach(function (btn) {
                    btn.addEventListener('click', function () {
                        var userId = parseInt(this.getAttribute('data-user-id'), 10);
                        if (confirm('Remove admin access for this user?')) {
                            removeAdmin(userId);
                        }
                    });
                });
            })
            .catch(function (err) {
                listEl.innerHTML = '<p style="color:#ef4444;text-align:center;padding:16px;">' + escapeHtml(err.message) + '</p>';
            });
    }

    function addAdmin() {
        var email = dom.newAdminEmail.value.trim().toLowerCase();
        var name = dom.newAdminName.value.trim();
        var password = dom.newAdminPassword.value.trim();

        if (!email || !name || !password) {
            showToast('Email, name, and password are required.', 'error');
            return;
        }
        if (!email.endsWith('@icitsolutions.com')) {
            showToast('Only @icitsolutions.com emails allowed.', 'error');
            return;
        }

        dom.btnAddAdmin.disabled = true;
        dom.btnAddAdmin.textContent = 'Adding...';

        apiCall('/admin/api/admins/add', { email: email, name: name, password: password })
            .then(function (data) {
                showToast(data.message || 'Admin user added', 'success');
                dom.newAdminEmail.value = '';
                dom.newAdminName.value = '';
                dom.newAdminPassword.value = '';
                loadAdmins();
            })
            .catch(function (err) {
                showToast('Error: ' + err.message, 'error');
            })
            .finally(function () {
                dom.btnAddAdmin.disabled = false;
                dom.btnAddAdmin.textContent = 'Add';
            });
    }

    function removeAdmin(userId) {
        apiCall('/admin/api/admins/remove', { user_id: userId })
            .then(function () {
                showToast('Admin access removed', 'success');
                loadAdmins();
            })
            .catch(function (err) {
                showToast('Error: ' + err.message, 'error');
            });
    }

    /* =============================================
       Event Binding
       ============================================= */
    function bindEvents() {
        dom.btnAddTenant.addEventListener('click', openAddModal);
        dom.btnCloseModal.addEventListener('click', closeModal);
        dom.btnCancelModal.addEventListener('click', closeModal);
        dom.tenantForm.addEventListener('submit', handleFormSubmit);

        dom.modalOverlay.addEventListener('click', function (e) {
            if (e.target === dom.modalOverlay) closeModal();
        });

        dom.slideoutOverlay.addEventListener('click', closeTenantDetail);
        dom.btnCloseSlideout.addEventListener('click', closeTenantDetail);

        dom.btnEditTenant.addEventListener('click', editCurrentTenant);
        dom.btnToggleStatus.addEventListener('click', toggleTenantStatus);
        dom.btnDeleteTenant.addEventListener('click', deleteTenant);

        /* Admin users modal */
        dom.btnManageAdmins.addEventListener('click', openAdminModal);
        dom.btnCloseAdminModal.addEventListener('click', closeAdminModal);
        dom.btnAddAdmin.addEventListener('click', addAdmin);
        dom.adminModalOverlay.addEventListener('click', function (e) {
            if (e.target === dom.adminModalOverlay) closeAdminModal();
        });

        var searchTimeout;
        dom.searchInput.addEventListener('input', function (e) {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(function () {
                handleSearch(e);
            }, 250);
        });

        dom.filterPills.forEach(function (pill) {
            pill.addEventListener('click', function () {
                setFilter(this.getAttribute('data-filter'));
            });
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                if (dom.adminModalOverlay.classList.contains('is-visible')) {
                    closeAdminModal();
                } else if (dom.modalOverlay.classList.contains('is-visible')) {
                    closeModal();
                } else if (dom.tenantSlideout.classList.contains('is-open')) {
                    closeTenantDetail();
                }
            }
        });
    }

    /* =============================================
       Init
       ============================================= */
    function init() {
        cacheDom();

        var tokenEl = document.getElementById('csrf_token');
        if (tokenEl) {
            state.csrfToken = tokenEl.value;
        }

        bindEvents();
        loadStats();
        loadTenants();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
