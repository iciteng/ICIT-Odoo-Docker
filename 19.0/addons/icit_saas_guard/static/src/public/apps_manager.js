/**
 * ICIT SaaS Guard — App Manager
 * Tab switching, module listing, search/filter, auth, actions, polling, toasts.
 */
(function () {
    'use strict';

    // ── State ────────────────────────────────────────────────────────────
    var _authToken = null;
    var _modules = [];
    var _categories = {};
    var _currentDb = '';
    var _currentFilter = 'all';
    var _appsOnly = false;
    var _searchQuery = '';
    var _collapsedCats = {};
    var _selectedModules = new Set();
    var _pollingTimer = null;

    // ── Helpers ──────────────────────────────────────────────────────────

    function $(sel, ctx) { return (ctx || document).querySelector(sel); }
    function $$(sel, ctx) { return Array.from((ctx || document).querySelectorAll(sel)); }

    function jsonFetch(url, opts) {
        opts = opts || {};
        var headers = opts.headers || {};
        headers['Accept'] = 'application/json';
        if (_authToken) {
            headers['X-Apps-Token'] = _authToken;
        }
        if (opts.body && typeof opts.body === 'object') {
            headers['Content-Type'] = 'application/json';
            opts.body = JSON.stringify(opts.body);
        }
        opts.headers = headers;
        return fetch(url, opts).then(function (r) { return r.json(); });
    }

    // ── Toast Notifications ──────────────────────────────────────────────

    function toast(type, message) {
        var container = $('#icit-toast-container');
        if (!container) return;
        var icons = { success: 'fa-check-circle', error: 'fa-times-circle', info: 'fa-info-circle' };
        var el = document.createElement('div');
        el.className = 'icit-toast icit-toast-' + type;
        el.innerHTML =
            '<i class="fa ' + (icons[type] || icons.info) + '"></i>' +
            '<span class="icit-toast-msg">' + _escHtml(message) + '</span>' +
            '<button class="icit-toast-close" type="button"><i class="fa fa-times"></i></button>';
        el.querySelector('.icit-toast-close').addEventListener('click', function () {
            _dismissToast(el);
        });
        container.appendChild(el);
        setTimeout(function () { _dismissToast(el); }, 5000);
    }

    function _dismissToast(el) {
        if (el.classList.contains('icit-toast-out')) return;
        el.classList.add('icit-toast-out');
        setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 250);
    }

    function _escHtml(s) {
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    // ── Tab Switching ────────────────────────────────────────────────────

    function initTabs() {
        var tabs = $$('.icit-tab');
        tabs.forEach(function (tab) {
            tab.addEventListener('click', function () {
                var target = tab.getAttribute('data-tab');
                tabs.forEach(function (t) { t.classList.remove('active'); });
                tab.classList.add('active');
                $$('.icit-tab-pane').forEach(function (p) { p.classList.remove('active'); });
                var pane = $('[data-tab-pane="' + target + '"]');
                if (pane) pane.classList.add('active');

                // Widen container for apps tab
                var container = $('#icit-dashboard-container');
                if (container) {
                    if (target === 'apps') {
                        container.classList.add('icit-wide');
                    } else {
                        container.classList.remove('icit-wide');
                    }
                }
            });
        });
    }

    // ── Auth ─────────────────────────────────────────────────────────────

    function initAuth() {
        var btn = $('#icit-apps-auth-btn');
        var input = $('#icit-apps-master-pwd');
        if (!btn || !input) return;

        btn.addEventListener('click', function () { doAuth(); });
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') { e.preventDefault(); doAuth(); }
        });
    }

    function doAuth() {
        var input = $('#icit-apps-master-pwd');
        var pwd = input ? input.value.trim() : '';
        if (!pwd) { toast('error', 'Please enter the master password'); return; }

        var btn = $('#icit-apps-auth-btn');
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fa fa-spinner fa-spin me-1"></i> Authenticating...'; }

        jsonFetch('/web/database/apps/auth', {
            method: 'POST',
            body: { master_pwd: pwd }
        }).then(function (data) {
            if (data.success && data.data && data.data.token) {
                _authToken = data.data.token;
                $('#icit-apps-auth').style.display = 'none';
                $('#icit-apps-content').style.display = 'block';
                showAllowlistButton();
                toast('success', 'Authenticated successfully');
                // Re-render if modules are loaded to show action buttons
                if (_modules.length) renderModules();
            } else {
                toast('error', data.error || 'Authentication failed');
                if (input) { input.value = ''; input.focus(); }
            }
        }).catch(function () {
            toast('error', 'Authentication request failed');
        }).finally(function () {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fa fa-unlock-alt me-1"></i> Authenticate'; }
        });
    }

    function requireAuth() {
        if (_authToken) return true;
        toast('info', 'Please authenticate first');
        return false;
    }

    // ── Database Selector ────────────────────────────────────────────────

    function initDbSelector() {
        var sel = $('#icit-apps-db-select');
        if (!sel) return;
        sel.addEventListener('change', function () {
            _currentDb = sel.value;
            _selectedModules.clear();
            updateBulkBar();
            if (_currentDb) {
                loadModules(_currentDb);
            } else {
                renderEmpty('Select a database to view modules');
            }
        });
    }

    // ── Load Modules ─────────────────────────────────────────────────────

    function loadModules(dbname) {
        var container = $('#icit-apps-modules');
        if (!container) return;
        container.innerHTML =
            '<div class="icit-apps-loading">' +
            '<div class="icit-spinner"></div>' +
            '<p>Loading modules...</p>' +
            '</div>';

        jsonFetch('/web/database/apps/list/' + encodeURIComponent(dbname))
            .then(function (data) {
                if (data.success && data.data) {
                    _modules = data.data.modules || [];
                    _categories = {};
                    (data.data.categories || []).forEach(function (c) {
                        _categories[c.id] = c;
                    });
                    // Store allowlist config if present
                    if (data.data.allowlist) {
                        _allowlistConfig = data.data.allowlist;
                    }
                    // Show allowlist button when authenticated
                    showAllowlistButton();
                    updateCounts();
                    renderModules();
                } else {
                    renderEmpty(data.error || 'Failed to load modules');
                }
            })
            .catch(function (err) {
                renderEmpty('Error loading modules: ' + err.message);
            });
    }

    // ── Search & Filter ──────────────────────────────────────────────────

    function initSearchFilter() {
        var search = $('#icit-apps-search');
        if (search) {
            search.addEventListener('input', function () {
                _searchQuery = search.value.trim().toLowerCase();
                renderModules();
            });
            // Keyboard shortcut: / to focus search
            document.addEventListener('keydown', function (e) {
                if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
                    var appsPane = $('[data-tab-pane="apps"]');
                    if (appsPane && appsPane.classList.contains('active')) {
                        e.preventDefault();
                        search.focus();
                    }
                }
                if (e.key === 'Escape' && search === document.activeElement) {
                    search.value = '';
                    _searchQuery = '';
                    renderModules();
                    search.blur();
                }
            });
        }

        // Filter buttons
        $$('.icit-apps-filters .btn[data-filter]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                $$('.icit-apps-filters .btn[data-filter]').forEach(function (b) { b.classList.remove('active'); });
                btn.classList.add('active');
                _currentFilter = btn.getAttribute('data-filter');
                renderModules();
            });
        });

        // Apps only toggle
        var toggle = $('#icit-apps-only');
        if (toggle) {
            toggle.addEventListener('change', function () {
                _appsOnly = toggle.checked;
                renderModules();
            });
        }
    }

    // ── Filtering Logic ──────────────────────────────────────────────────

    function getFilteredModules() {
        return _modules.filter(function (m) {
            // Filter by state
            if (_currentFilter === 'installed' && m.state !== 'installed') return false;
            if (_currentFilter === 'available' && m.state !== 'uninstalled') return false;

            // Apps only
            if (_appsOnly && !m.application) return false;

            // Search
            if (_searchQuery) {
                var hay = (
                    (m.shortdesc || '') + ' ' +
                    (m.name || '') + ' ' +
                    (m.summary || '') + ' ' +
                    (m.author || '')
                ).toLowerCase();
                if (hay.indexOf(_searchQuery) === -1) return false;
            }

            return true;
        });
    }

    function updateCounts() {
        var installed = 0;
        var available = 0;
        _modules.forEach(function (m) {
            if (m.state === 'installed') installed++;
            else if (m.state === 'uninstalled') available++;
        });
        var el;
        el = $('#icit-count-all');
        if (el) el.textContent = _modules.length;
        el = $('#icit-count-installed');
        if (el) el.textContent = installed;
        el = $('#icit-count-available');
        if (el) el.textContent = available;
    }

    // ── Render Modules ───────────────────────────────────────────────────

    function renderModules() {
        var container = $('#icit-apps-modules');
        if (!container) return;

        var filtered = getFilteredModules();
        if (filtered.length === 0) {
            renderEmpty(_searchQuery ? 'No modules match your search' : 'No modules found');
            return;
        }

        // Group by category
        var groups = {};
        var uncategorized = [];
        filtered.forEach(function (m) {
            var catId = m.category_id ? m.category_id[0] : null;
            if (catId && _categories[catId]) {
                if (!groups[catId]) groups[catId] = { name: _categories[catId].name, modules: [] };
                groups[catId].modules.push(m);
            } else {
                uncategorized.push(m);
            }
        });

        // Sort groups by name
        var sortedKeys = Object.keys(groups).sort(function (a, b) {
            return groups[a].name.localeCompare(groups[b].name);
        });

        var html = '';
        sortedKeys.forEach(function (catId) {
            html += renderCategoryGroup(catId, groups[catId].name, groups[catId].modules);
        });
        if (uncategorized.length) {
            html += renderCategoryGroup('uncategorized', 'Uncategorized', uncategorized);
        }

        container.innerHTML = html;
        attachModuleEvents(container);
    }

    function renderCategoryGroup(catId, catName, modules) {
        var collapsed = _collapsedCats[catId] || false;
        var chevron = collapsed ? 'fa-chevron-right' : 'fa-chevron-down';
        var html = '<div class="icit-cat-group" data-cat="' + catId + '">';
        html += '<div class="icit-cat-header" data-cat-toggle="' + catId + '">';
        html += '<i class="fa ' + chevron + '"></i>';
        html += '<span>' + _escHtml(catName) + '</span>';
        html += '<span class="icit-cat-count">(' + modules.length + ')</span>';
        html += '</div>';
        html += '<div class="icit-cat-body"' + (collapsed ? ' style="display:none"' : '') + '>';
        modules.forEach(function (m) {
            html += renderModuleRow(m);
        });
        html += '</div></div>';
        return html;
    }

    function renderModuleRow(m) {
        var stateClass = 'icit-state-' + (m.state || 'uninstalled').replace(/\s+/g, '-');
        var stateLabel = _stateLabel(m.state);
        var icon = m.application ? 'fa-th-large' : 'fa-puzzle-piece';
        var blocked = m._blocked || false;

        var html = '<div class="icit-mod-row' + (blocked ? ' icit-blocked' : '') + '" data-module="' + _escHtml(m.name) + '">';

        // Checkbox (Phase 4 — hidden by default, shown via CSS when bulk mode active)
        html += '<input type="checkbox" class="icit-mod-check form-check-input" value="' + _escHtml(m.name) + '" />';

        // Icon
        html += '<div class="icit-mod-icon"><i class="fa ' + icon + '"></i></div>';

        // Info
        html += '<div class="icit-mod-info">';
        html += '<div class="icit-mod-name">';
        if (blocked) html += '<i class="fa fa-lock icit-lock-icon" title="Blocked by allowlist"></i>';
        html += _escHtml(m.shortdesc || m.name);
        html += '</div>';
        html += '<div class="icit-mod-technical">' + _escHtml(m.name);
        if (m.installed_version) html += ' v' + _escHtml(m.installed_version);
        html += '</div>';
        if (m.summary) {
            html += '<div class="icit-mod-summary">' + _escHtml(m.summary) + '</div>';
        }
        html += '</div>';

        // State badge
        html += '<span class="icit-state ' + stateClass + '">' + stateLabel + '</span>';

        // Action buttons (only if authenticated)
        if (_authToken) {
            html += '<div class="icit-mod-actions">';
            if (m.state === 'uninstalled' && !blocked) {
                html += '<button class="btn btn-primary btn-sm icit-action" data-action="install" data-module="' + _escHtml(m.name) + '"><i class="fa fa-download"></i></button>';
            } else if (m.state === 'installed') {
                html += '<button class="btn btn-secondary btn-sm icit-action" data-action="upgrade" data-module="' + _escHtml(m.name) + '" title="Upgrade"><i class="fa fa-refresh"></i></button>';
                html += '<button class="btn btn-danger btn-sm icit-action" data-action="uninstall" data-module="' + _escHtml(m.name) + '" title="Uninstall"><i class="fa fa-trash-o"></i></button>';
            }
            html += '</div>';
        }

        html += '</div>';
        return html;
    }

    function renderEmpty(msg) {
        var container = $('#icit-apps-modules');
        if (!container) return;
        container.innerHTML =
            '<div class="icit-apps-empty">' +
            '<i class="fa fa-cubes"></i>' +
            '<p>' + _escHtml(msg) + '</p>' +
            '</div>';
    }

    function _stateLabel(state) {
        var labels = {
            'installed': 'Installed',
            'uninstalled': 'Available',
            'to install': 'Pending Install',
            'to upgrade': 'Pending Upgrade',
            'to remove': 'Pending Remove',
            'uninstallable': 'N/A'
        };
        return labels[state] || state || 'Unknown';
    }

    // ── Module Events ────────────────────────────────────────────────────

    function attachModuleEvents(container) {
        // Category collapse/expand
        $$('.icit-cat-header', container).forEach(function (header) {
            header.addEventListener('click', function () {
                var catId = header.getAttribute('data-cat-toggle');
                var body = header.nextElementSibling;
                var icon = header.querySelector('i');
                if (body.style.display === 'none') {
                    body.style.display = '';
                    icon.className = 'fa fa-chevron-down';
                    delete _collapsedCats[catId];
                } else {
                    body.style.display = 'none';
                    icon.className = 'fa fa-chevron-right';
                    _collapsedCats[catId] = true;
                }
            });
        });

        // Action buttons
        $$('.icit-action', container).forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.stopPropagation();
                if (!requireAuth()) return;
                var action = btn.getAttribute('data-action');
                var modName = btn.getAttribute('data-module');
                doModuleAction(action, modName);
            });
        });

        // Checkboxes for bulk select
        $$('.icit-mod-check', container).forEach(function (cb) {
            cb.addEventListener('change', function () {
                if (cb.checked) {
                    _selectedModules.add(cb.value);
                } else {
                    _selectedModules.delete(cb.value);
                }
                updateBulkBar();
            });
        });
    }

    // ── Module Actions (Install / Uninstall / Upgrade) ───────────────────

    function doModuleAction(action, moduleName) {
        var row = $('[data-module="' + moduleName + '"].icit-mod-row');
        if (!row) return;

        // Add loading overlay
        var overlay = document.createElement('div');
        overlay.className = 'icit-mod-loading';
        overlay.innerHTML = '<div class="icit-spinner"></div>';
        row.appendChild(overlay);

        jsonFetch('/web/database/apps/' + action, {
            method: 'POST',
            body: { dbname: _currentDb, module_name: moduleName }
        }).then(function (data) {
            if (data.success) {
                toast('success', _capitalize(action) + ' started for ' + moduleName);
                startPolling(moduleName);
            } else {
                if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
                if (data.error && data.error.indexOf('token') !== -1) {
                    _authToken = null;
                    $('#icit-apps-auth').style.display = '';
                    $('#icit-apps-content').style.display = 'none';
                    toast('error', 'Session expired — please re-authenticate');
                } else {
                    toast('error', data.error || action + ' failed');
                }
            }
        }).catch(function () {
            if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
            toast('error', 'Request failed for ' + action);
        });
    }

    function _capitalize(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

    // ── Polling ──────────────────────────────────────────────────────────

    function startPolling(moduleName) {
        if (_pollingTimer) clearInterval(_pollingTimer);
        var attempts = 0;
        _pollingTimer = setInterval(function () {
            attempts++;
            if (attempts > 60) { // ~3 min max
                clearInterval(_pollingTimer);
                _pollingTimer = null;
                toast('info', 'Operation taking longer than expected. Refresh to check status.');
                return;
            }
            jsonFetch('/web/database/apps/status/' + encodeURIComponent(_currentDb) + '?module=' + encodeURIComponent(moduleName))
                .then(function (data) {
                    if (data.success && data.data) {
                        var state = data.data.state;
                        if (state === 'installed' || state === 'uninstalled') {
                            clearInterval(_pollingTimer);
                            _pollingTimer = null;
                            loadModules(_currentDb);
                            toast('success', moduleName + ' is now ' + state);
                        }
                    }
                })
                .catch(function () {
                    // Silent retry
                });
        }, 3000);
    }

    // ── Bulk Operations ──────────────────────────────────────────────────

    var _bulkMode = false;

    function toggleBulkMode() {
        _bulkMode = !_bulkMode;
        var container = $('#icit-apps-modules');
        if (container) {
            if (_bulkMode) {
                container.classList.add('icit-bulk-mode');
            } else {
                container.classList.remove('icit-bulk-mode');
                _selectedModules.clear();
            }
        }
        updateBulkBar();
    }

    function updateBulkBar() {
        var bar = $('#icit-apps-bulk-bar');
        if (!bar) return;
        var count = _selectedModules.size;
        if (_bulkMode && count > 0) {
            bar.style.display = '';
            $('#icit-bulk-count').textContent = count + ' selected';
        } else {
            bar.style.display = 'none';
        }
    }

    function initBulkActions() {
        var selectBtn = $('#icit-apps-select-btn');
        if (selectBtn) {
            selectBtn.addEventListener('click', function () {
                toggleBulkMode();
                selectBtn.classList.toggle('active', _bulkMode);
            });
        }

        var installBtn = $('#icit-bulk-install');
        var uninstallBtn = $('#icit-bulk-uninstall');

        if (installBtn) {
            installBtn.addEventListener('click', function () {
                if (!requireAuth()) return;
                if (_selectedModules.size === 0) return;
                var names = Array.from(_selectedModules);
                jsonFetch('/web/database/apps/install', {
                    method: 'POST',
                    body: { dbname: _currentDb, module_names: names }
                }).then(function (data) {
                    if (data.success) {
                        toast('success', 'Bulk install started for ' + names.length + ' modules');
                        _selectedModules.clear();
                        updateBulkBar();
                        // Poll on first module
                        startPolling(names[0]);
                    } else {
                        toast('error', data.error || 'Bulk install failed');
                    }
                }).catch(function () { toast('error', 'Bulk install request failed'); });
            });
        }

        if (uninstallBtn) {
            uninstallBtn.addEventListener('click', function () {
                if (!requireAuth()) return;
                if (_selectedModules.size === 0) return;
                var names = Array.from(_selectedModules);
                jsonFetch('/web/database/apps/uninstall', {
                    method: 'POST',
                    body: { dbname: _currentDb, module_names: names }
                }).then(function (data) {
                    if (data.success) {
                        toast('success', 'Bulk uninstall started for ' + names.length + ' modules');
                        _selectedModules.clear();
                        updateBulkBar();
                        startPolling(names[0]);
                    } else {
                        toast('error', data.error || 'Bulk uninstall failed');
                    }
                }).catch(function () { toast('error', 'Bulk uninstall request failed'); });
            });
        }
    }

    // ── Allowlist ────────────────────────────────────────────────────────

    var _allowlistConfig = null;

    function initAllowlist() {
        var btn = $('#icit-apps-allowlist-btn');
        if (!btn) return;
        btn.addEventListener('click', function () {
            if (!requireAuth()) return;
            if (!_currentDb) { toast('info', 'Select a database first'); return; }
            openAllowlistModal();
        });

        // Mode radio buttons — show/hide module section
        $$('input[name="icit-al-mode"]').forEach(function (radio) {
            radio.addEventListener('change', function () {
                var section = $('#icit-al-modules-section');
                if (section) {
                    section.style.display = radio.value === 'disabled' ? 'none' : '';
                }
                updateModeHelp(radio.value);
            });
        });

        // Save button
        var saveBtn = $('#icit-al-save');
        if (saveBtn) {
            saveBtn.addEventListener('click', function () { saveAllowlist(); });
        }

        // Select All / None / Apps Only
        var selAll = $('#icit-al-select-all');
        var selNone = $('#icit-al-select-none');
        var selApps = $('#icit-al-select-apps');

        if (selAll) selAll.addEventListener('click', function () {
            $$('#icit-al-module-list .icit-al-check').forEach(function (cb) { cb.checked = true; });
            updateAlSelectedCount();
        });
        if (selNone) selNone.addEventListener('click', function () {
            $$('#icit-al-module-list .icit-al-check').forEach(function (cb) { cb.checked = false; });
            updateAlSelectedCount();
        });
        if (selApps) selApps.addEventListener('click', function () {
            $$('#icit-al-module-list .icit-al-check').forEach(function (cb) {
                cb.checked = cb.getAttribute('data-app') === 'true';
            });
            updateAlSelectedCount();
        });

        // Search inside modal
        var alSearch = $('#icit-al-search');
        if (alSearch) {
            alSearch.addEventListener('input', function () {
                var q = alSearch.value.trim().toLowerCase();
                $$('#icit-al-module-list .icit-al-item').forEach(function (item) {
                    var text = item.textContent.toLowerCase();
                    item.style.display = (!q || text.indexOf(q) !== -1) ? '' : 'none';
                });
            });
        }
    }

    function openAllowlistModal() {
        // Show the allowlist button after auth
        var alBtn = $('#icit-apps-allowlist-btn');
        if (alBtn) alBtn.style.display = '';

        // Fetch current config
        jsonFetch('/web/database/apps/allowlist/' + encodeURIComponent(_currentDb))
            .then(function (data) {
                if (data.success && data.data) {
                    _allowlistConfig = data.data;
                } else {
                    _allowlistConfig = { mode: 'disabled' };
                }
                populateAllowlistModal();
                var modalEl = document.getElementById('icit-allowlist-modal');
                if (modalEl && typeof Modal !== 'undefined') {
                    Modal.getOrCreateInstance(modalEl).show();
                }
            })
            .catch(function () {
                toast('error', 'Failed to load allowlist config');
            });
    }

    function populateAllowlistModal() {
        // Set DB name
        var dbSpan = $('#icit-allowlist-dbname');
        if (dbSpan) dbSpan.textContent = _currentDb;

        // Set mode
        var mode = (_allowlistConfig && _allowlistConfig.mode) || 'disabled';
        var radio = document.getElementById('icit-al-' + mode);
        if (radio) radio.checked = true;
        updateModeHelp(mode);

        // Show/hide module section
        var section = $('#icit-al-modules-section');
        if (section) section.style.display = mode === 'disabled' ? 'none' : '';

        // Build module checklist
        var list = $('#icit-al-module-list');
        if (!list) return;

        var allowedSet = new Set(_allowlistConfig.allowed_modules || []);
        var deniedSet = new Set(_allowlistConfig.denied_modules || []);

        var html = '';
        // Sort modules by display name
        var sorted = _modules.slice().sort(function (a, b) {
            return (a.shortdesc || a.name).localeCompare(b.shortdesc || b.name);
        });

        sorted.forEach(function (m) {
            var checked = false;
            if (mode === 'allowlist') {
                checked = allowedSet.has(m.name);
            } else if (mode === 'denylist') {
                checked = deniedSet.has(m.name);
            }
            var id = 'icit-al-mod-' + m.name;
            html += '<div class="icit-al-item">';
            html += '<input type="checkbox" class="form-check-input icit-al-check" id="' + id + '" value="' + _escHtml(m.name) + '" data-app="' + (m.application ? 'true' : 'false') + '"' + (checked ? ' checked' : '') + ' />';
            html += '<label for="' + id + '">' + _escHtml(m.shortdesc || m.name) + ' <span class="icit-al-tech">' + _escHtml(m.name) + '</span></label>';
            html += '</div>';
        });

        list.innerHTML = html;

        // Attach change events for count
        $$('.icit-al-check', list).forEach(function (cb) {
            cb.addEventListener('change', function () { updateAlSelectedCount(); });
        });
        updateAlSelectedCount();
    }

    function updateModeHelp(mode) {
        var help = $('#icit-al-mode-help');
        if (!help) return;
        var texts = {
            disabled: 'No restrictions — tenant can install any module.',
            allowlist: 'Only checked modules can be installed by this tenant.',
            denylist: 'Checked modules are blocked — all others are allowed.'
        };
        help.textContent = texts[mode] || '';
    }

    function updateAlSelectedCount() {
        var el = $('#icit-al-selected-count');
        if (!el) return;
        var checked = $$('#icit-al-module-list .icit-al-check:checked').length;
        var total = $$('#icit-al-module-list .icit-al-check').length;
        el.textContent = checked + ' / ' + total + ' selected';
    }

    function saveAllowlist() {
        if (!requireAuth()) return;

        var mode = 'disabled';
        $$('input[name="icit-al-mode"]').forEach(function (r) {
            if (r.checked) mode = r.value;
        });

        var config = { mode: mode };
        if (mode === 'allowlist') {
            config.allowed_modules = [];
            $$('#icit-al-module-list .icit-al-check:checked').forEach(function (cb) {
                config.allowed_modules.push(cb.value);
            });
        } else if (mode === 'denylist') {
            config.denied_modules = [];
            $$('#icit-al-module-list .icit-al-check:checked').forEach(function (cb) {
                config.denied_modules.push(cb.value);
            });
        }

        var saveBtn = $('#icit-al-save');
        if (saveBtn) { saveBtn.disabled = true; saveBtn.innerHTML = '<i class="fa fa-spinner fa-spin me-1"></i> Saving...'; }

        jsonFetch('/web/database/apps/allowlist/' + encodeURIComponent(_currentDb), {
            method: 'POST',
            body: config
        }).then(function (data) {
            if (data.success) {
                toast('success', 'Allowlist saved for ' + _currentDb);
                var modalEl = document.getElementById('icit-allowlist-modal');
                if (modalEl && typeof Modal !== 'undefined') {
                    Modal.getOrCreateInstance(modalEl).hide();
                }
                // Refresh modules to show blocked state
                loadModules(_currentDb);
            } else {
                toast('error', data.error || 'Failed to save allowlist');
            }
        }).catch(function () {
            toast('error', 'Request failed');
        }).finally(function () {
            if (saveBtn) { saveBtn.disabled = false; saveBtn.innerHTML = '<i class="fa fa-save me-1"></i> Save Allowlist'; }
        });
    }

    // ── Show Allowlist Button After Auth ──────────────────────────────────

    function showAllowlistButton() {
        var btn = $('#icit-apps-allowlist-btn');
        if (btn && _authToken) btn.style.display = '';
    }

    // ── Init ─────────────────────────────────────────────────────────────

    document.addEventListener('DOMContentLoaded', function () {
        initTabs();
        initAuth();
        initDbSelector();
        initSearchFilter();
        initBulkActions();
        initAllowlist();
    });
})();
