/* 
  High-Fidelity Dashboard Logic
  Optimized for 4K and PC screens
  Warehouse Filtering & Real-time Search
*/

window.addEventListener('DOMContentLoaded', () => {
    initDashboard();
});

const REFRESH_INTERVAL_MS = 10000; // 10 seconds for near real-time updates
let refreshTimer = null;

const initDashboard = () => {
    fetchDashboardData();
    startAutoRefresh();
    registerVisibilityRefresh();

    // Set Global Date
    const globalDateEl = document.getElementById('current-date-display');
    if (globalDateEl) {
        const now = new Date();
        globalDateEl.innerText = now.toLocaleString('en-US', { month: 'long', day: 'numeric', year: 'numeric' }).toUpperCase();
    }

    // Tab buttons logic (Warehouse Filter for Active Quotation) with Multi-Select
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const parentPanel = btn.closest('.panel');

            // Toggle current
            btn.classList.toggle('active');

            const listId = parentPanel.querySelector('.panel-content').id;
            filterList(listId);
        });
    });

    // Expand logic
    document.querySelectorAll('.expand-trigger').forEach(trigger => {
        trigger.addEventListener('click', () => {
            const targetId = trigger.getAttribute('data-target');
            toggleExpand(targetId, true);
        });
    });

    // Close Expand logic
    document.querySelectorAll('.close-trigger').forEach(trigger => {
        trigger.addEventListener('click', () => {
            const targetId = trigger.getAttribute('data-target');
            toggleExpand(targetId, false);
        });
    });

    // Generic Filter Toggle Logic for all panels
    document.querySelectorAll('.filter-box').forEach(box => {
        box.addEventListener('click', (e) => {
            e.stopPropagation();
            const panel = box.closest('.panel');
            const tabs = panel.querySelector('.panel-tabs');
            if (tabs) {
                const isHidden = window.getComputedStyle(tabs).display === 'none';
                // Close others if needed, or just toggle this one
                document.querySelectorAll('.panel-tabs').forEach(t => t.style.display = 'none');
                tabs.style.display = isHidden ? 'flex' : 'none';
            }
        });
    });

    // Close tabs when clicking outside
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.filter-box') && !e.target.closest('.panel-tabs')) {
            document.querySelectorAll('.panel-tabs').forEach(t => t.style.display = 'none');
        }
    });
};

const toggleExpand = (panelId, isExpand) => {
    const panel = document.getElementById(panelId);
    if (!panel) return;

    if (isExpand) {
        panel.classList.add('expanded');
    } else {
        panel.classList.remove('expanded');
    }
};

const fetchDashboardData = () => {
    fetchSection("/api/invoices", 'list-incomplete-invoice', renderInvoiceCard, 'count-invoice');
    fetchSection("/api/journals", 'list-unposted-journal', renderJournalCard, 'count-journal');
    fetchSection("/api/quotations/pending", 'list-active-quotation', renderQuotationCard, 'count-quotation', 'data');
    fetchSection("/api/customers", 'list-new-customers', renderCustomerCard, 'count-new-customers');
    fetchSection("/api/overshoot", 'list-balance-overshoot', renderOvershootCard, 'count-overshoot');
    fetchSection("/api/reconciliation", 'list-reconciliation', renderReconciliationCard, 'count-reconciliation');
};

const fetchSection = (url, containerId, renderFunc, countId, dataKey = null) => {
    const requestUrl = appendCacheBuster(url);
    fetch(requestUrl, { cache: 'no-store', headers: { 'Cache-Control': 'no-cache' } })
        .then(r => r.json())
        .then(data => {
            const items = dataKey ? data[dataKey] : data;
            const container = document.getElementById(containerId);
            if (!container) return;

            container.dataItems = items;
            // Update the total count initially
            const countEl = document.getElementById(countId);
            if (countEl) countEl.innerHTML = `${items.length} <span style="font-size: 10px;">items</span>`; // Just total initially

            filterList(containerId);
        })
        .catch(err => console.error(`Error fetching ${url}:`, err));
};

const startAutoRefresh = () => {
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(() => {
        if (!document.hidden) {
            fetchDashboardData();
        }
    }, REFRESH_INTERVAL_MS);
};

const registerVisibilityRefresh = () => {
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
            fetchDashboardData();
        }
    });
};

const appendCacheBuster = (url) => {
    const suffix = `_=${Date.now()}`;
    return url.includes('?') ? `${url}&${suffix}` : `${url}?${suffix}`;
};

const filterList = (containerId, text = null) => {
    const container = document.getElementById(containerId);
    if (!container || !container.dataItems) return;

    // Get current search text
    if (text === null) {
        const searchInput = document.querySelector(`.search-input[onkeyup*="${containerId}"]`);
        text = searchInput ? searchInput.value : "";
    }
    const searchText = text.toLowerCase();

    // Get Warehouse Filter for Active Quotation (Multi-Select)
    let activeWarehouses = [];
    // Get Source Filter for Unposted Journal (Deposit/Journal)
    let activeSources = [];
    const panel = container.closest('.panel');
    if (containerId === 'list-active-quotation') {
        const activeTabs = panel.querySelectorAll('.tab-btn.active');
        activeTabs.forEach(tab => {
            const val = tab.getAttribute('data-warehouse');
            if (val && val !== 'all') {
                activeWarehouses.push(val.toLowerCase());
            }
        });
    }
    if (containerId === 'list-unposted-journal') {
        const activeTabs = panel.querySelectorAll('.tab-btn.active');
        activeTabs.forEach(tab => {
            const val = tab.getAttribute('data-source');
            if (val) {
                activeSources.push(val.toLowerCase());
            }
        });
    }

    // Determine render function
    const map = {
        'list-incomplete-invoice': renderInvoiceCard,
        'list-unposted-journal': renderJournalCard,
        'list-active-quotation': renderQuotationCard,
        'list-new-customers': renderCustomerCard,
        'list-balance-overshoot': renderOvershootCard,
        'list-reconciliation': renderReconciliationCard
    };
    const renderFunc = map[containerId];

    // Filter Logic
    const filteredItems = container.dataItems.filter(item => {
        const nameMatch = (item.name || item.partner_name || formatM2O(item.partner_id) || formatM2O(item.partner) || "").toLowerCase().includes(searchText);

        // Specific logic for warehouse tabs
        let warehouseMatch = true;
        if (activeWarehouses.length > 0) {
            const itemWh = (item.warehouse_id ? item.warehouse_id[1] : "").toLowerCase();
            // Match if item's warehouse includes ANY of the selected filter texts
            warehouseMatch = activeWarehouses.some(filter => itemWh.includes(filter));
        }

        // Source filter for Unposted Journal
        let sourceMatch = true;
        if (containerId === 'list-unposted-journal' && activeSources.length > 0) {
            const itemSource = (item.source || '').toLowerCase();
            sourceMatch = activeSources.includes(itemSource);
        }

        return nameMatch && warehouseMatch && sourceMatch;
    });

    renderWithGrouping(container, filteredItems, renderFunc);

    // Update visible count with format (Total/Filtered) only if filtered
    const panelRef = container.closest('.panel');
    const countSpan = panelRef.querySelector('.panel-title span[id^="count-"]');
    if (countSpan) {
        const total = container.dataItems.length;
        const visible = filteredItems.length;
        if (total === visible) {
            countSpan.innerHTML = `${total} <span style="font-size: 10px;">items</span>`;
        } else {
            countSpan.innerHTML = `${total} <span style="font-size: 10px;">of</span> ${visible} <span style="font-size: 10px;">items</span>`;
        }
    }
};

const renderWithGrouping = (container, items, renderFunc) => {
    // Group items by date first
    // Re-approach: Iterate items and open/close divs
    let currentGroupRaw = [];
    let currentDateKey = null;
    let html = '';

    items.forEach((item, index) => {
        const dateStr = item.date_invoice || item.invoice_date || item.date || item.date_order || item.create_date || "";
        let dateKey = dateStr ? dateStr.split(' ')[0] : "Other";
        
        // Custom grouping for Incomplete Orders and Unposted Journals: Month and Year only
        if (container.id === 'list-incomplete-invoice' && dateStr) {
            dateKey = dateStr.substring(0, 7); // YYYY-MM
        }
        if (container.id === 'list-unposted-journal') {
            if (!dateStr) {
                dateKey = "UNKNOWN";
            } else {
                const d = new Date(dateStr);
                if (!Number.isNaN(d.getTime())) {
                    const y = d.getFullYear();
                    const m = String(d.getMonth() + 1).padStart(2, '0');
                    dateKey = `${y}-${m}`;
                }
            }
        }

        if (dateKey !== currentDateKey) {
            // Close previous group if exists
            if (currentDateKey !== null) {
                html += renderGroupHtml(currentDateKey, currentGroupRaw, renderFunc);
            }
            // Start new group
            currentDateKey = dateKey;
            currentGroupRaw = [item];
        } else {
            currentGroupRaw.push(item);
        }

        // Clean up last group
        if (index === items.length - 1) {
            html += renderGroupHtml(currentDateKey, currentGroupRaw, renderFunc);
        }
    });


    if (items.length === 0) {
        container.innerHTML = `<div style="padding: 20px; color: var(--text-secondary); text-align: center; font-size: 11px;">No records found</div>`;
        return;
    }

    container.innerHTML = html;
};

const renderGroupHtml = (dateKey, items, renderFunc) => {
    const headerText = dateKey === "UNKNOWN" ? "UNKNOWN DATE" : formatGroupDate(dateKey === "Other" ? "" : dateKey);
    let groupHtml = `<div class="date-group" style="position: relative;">`; // Group wrapper
    if (headerText !== "N/A") {
        groupHtml += `<div class="date-header">${headerText}</div>`;
    }
    items.forEach(item => {
        groupHtml += renderFunc(item);
    });
    groupHtml += `</div>`;
    return groupHtml;
};

/* RENDERERS */

const renderInvoiceCard = (item) => {
    // Label "Order" for reference
    const refLabel = "Order";
    const refValue = (item.ref) ? item.ref : item.name;
    const issueLabel = item.issue || "Action Required";
    
    // Use standardized date format
    const dateStr = item.date_invoice || item.invoice_date || item.date_order;
    const timeStr = formatDateTimeStandard(dateStr);

    return `
    <div class="card journal-card incomplete-card" onclick="window.open('${window.ODOO_BASE_URL}/web#id=${item.id}&view_type=form&model=sale.order', '_blank')">
        <div class="card-title">${formatM2O(item.partner_id)}</div>
        <div class="journal-row">
            <span class="journal-label">${refLabel}:</span>
            <span class="journal-amount">${refValue}</span>
        </div>
        <div class="journal-row">
            <span class="journal-label">Status:</span>
            <span class="journal-source">${issueLabel}</span>
        </div>
        <div class="card-footer journal-footer">
            <span>${timeStr}</span>
        </div>
    </div>
`};

const renderJournalCard = (item) => {
    const sourceLabel = (item.source === 'journal') ? 'Journal' : 'Deposit';
    const bankName = item.journal_id ? item.journal_id[1] : '';
    const bankAbbrev = abbreviateBankName(bankName);
    const fromLabel = bankAbbrev ? `${bankAbbrev} ${sourceLabel}` : sourceLabel;

    // Money: Integer only (no decimals)
    const amountVal = Math.floor(item.amount || 0).toLocaleString('en-US');

    const modelName = item.model || (item.source === 'journal' ? 'account.move' : 'bank.deposit');
    const recordId = item.record_id || item.id;

    return `
    <div class="card journal-card" onclick="window.open('${window.ODOO_BASE_URL}/web#id=${recordId}&view_type=form&model=${modelName}', '_blank')">
        <div class="card-title">${formatM2O(item.partner)}</div>
        <div class="journal-row">
            <span class="journal-label">Deposit:</span>
            <span class="journal-amount">${amountVal} ETB</span>
        </div>
        <div class="journal-row">
            <span class="journal-label">From: ${bankAbbrev}</span>
            <span class="journal-source">${sourceLabel}</span>
        </div>
        <div class="card-footer journal-footer">
            <span>${formatDateTimeStandard(item.date)}</span>
        </div>
    </div>
`};

const renderQuotationCard = (item) => {
    // Format Date: "Jan 23, 11:16 AM" via utility
    const timeStr = formatDateTimeStandard(item.date_order);
    const partnerName = formatM2O(item.partner_id);
    const orderName = item.name || '';
    const warehouseName = item.warehouse_id ? formatWarehouseDisplay(item.warehouse_id[1]) : 'N/A';

    return `
    <div class="card journal-card" onclick="window.open('${window.ODOO_BASE_URL}/web#id=${item.id}&view_type=form&model=sale.order', '_blank')">
        <div class="card-title">${partnerName}</div>
        
        <div class="journal-row">
            <span class="journal-label">Order:</span>
            <span class="journal-amount">${orderName}</span>
        </div>
        
        <div class="journal-row">
            <span class="journal-label">Site:</span>
            <span class="journal-amount">${warehouseName}</span>
        </div>

        <div class="card-footer" style="justify-content: flex-end; margin-top: 8px;">
            <span style="color: var(--text-secondary); font-size: 11px;">${timeStr}</span>
        </div>
    </div>
`};

const renderOvershootCard = (item) => `
    <div class="card journal-card" onclick="window.open('${window.ODOO_BASE_URL}/web#id=${item.id}&view_type=form&model=res.partner', '_blank')">
        <div class="card-title">${formatNameDisplay(item.partner_name) || formatM2O(item.partner_id)}</div>
        <div class="journal-row">
            <span class="journal-label">Available:</span>
            <span class="journal-amount">${formatCurrency(item.customer_limit)}</span>
        </div>
        <div class="journal-row">
            <span class="journal-label">Orders(${item.order_count || 0}):</span>
            <span class="journal-amount">${formatCurrency(item.total_amount)}</span>
        </div>
        <div class="journal-row">
            <span class="journal-label">Delta:</span>
            <span class="journal-amount">${formatCurrency(item.delta, { preserveSign: true })}</span>
        </div>
        <div class="card-footer journal-footer">
            <span>${formatDateTimeStandard(item.latest_date)}</span>
        </div>
    </div>
`;

const renderCustomerCard = (item) => `
    <div class="card journal-card" onclick="window.open('${window.ODOO_BASE_URL}/web#id=${item.id}&view_type=form&model=res.partner', '_blank')">
        <div class="card-title">${formatNameDisplay(item.name)}</div>
        <div class="journal-row">
            <span class="journal-label">Orders:</span>
            <span class="journal-amount">${item.order_count || 0}</span>
        </div>
        <div class="journal-row">
            <span class="journal-label">P_CODE:</span>
            <span class="journal-source">${item.partner_code || "N/A"}</span>
        </div>
        <div class="card-footer journal-footer">
            <span>${formatDateTimeStandard(item.create_date)}</span>
        </div>
    </div>
`;

const renderReconciliationCard = (item) => `
    <div class="card">
        <div class="card-title">${formatM2O(item.partner_id)}</div>
        <div class="card-footer">
            <span class="card-amount">${formatCurrency(item.amount)}</span>
            <span style="font-size: 9px;">${formatDateTimeStandard(item.date)}</span>
        </div>
    </div>
`;

/* UTILITY FUNCTIONS */
const stripParenthetical = (val) => (val || '').replace(/\s*\(.*?\)\s*/g, ' ').replace(/\s+/g, ' ').trim();
const toTitleCase = (val) => {
    return (val || '')
        .split(/\s+/)
        .map(word => {
            const cleaned = word.trim();
            if (!cleaned) return '';
            if (/[.]/.test(cleaned)) return cleaned.toUpperCase();
            if (cleaned.length <= 3 && cleaned === cleaned.toUpperCase()) return cleaned;
            const lower = cleaned.toLowerCase();
            return lower.charAt(0).toUpperCase() + lower.slice(1);
        })
        .filter(Boolean)
        .join(' ');
};
const formatNameDisplay = (val) => toTitleCase(stripParenthetical(val || ''));
const formatWarehouseDisplay = (val) => {
    const cleaned = stripParenthetical(val || '');
    const match = cleaned.match(/\bTOP\s*\d+\b/i);
    return match ? match[0].toUpperCase() : formatNameDisplay(cleaned);
};
const abbreviateBankName = (val) => {
    const cleaned = stripParenthetical(val || '')
        .replace(/\bETB\b/ig, '')
        .replace(/\d+/g, '')
        .replace(/\s+/g, ' ')
        .trim();
    if (!cleaned) return '';
    const letters = cleaned
        .split(' ')
        .filter(Boolean)
        .map(word => word[0])
        .join('')
        .toUpperCase();
    return letters || '';
};
const formatM2O = (f) => formatNameDisplay(Array.isArray(f) ? f[1] : (f || 'Unknown'));
const formatCurrency = (val, options = {}) => {
    const num = Number(val || 0);
    const { preserveSign = false } = options;
    const formatted = formatNumber(Math.abs(num));
    if (preserveSign && num < 0) {
        return "-" + formatted + " ETB";
    }
    return formatted + " ETB";
};
const formatNumber = (num) => new Intl.NumberFormat('en-US', { minimumFractionDigits: 2 }).format(num || 0);
const formatGroupDate = (dateStr) => {
    if (!dateStr) return "N/A";
    if (dateStr.length === 7) { 
        // Likely YYYY-MM
        const [y, m] = dateStr.split('-');
        const dateObj = new Date(parseInt(y), parseInt(m)-1);
        return dateObj.toLocaleString('en-US', { month: 'long', year: 'numeric' }).toUpperCase();
    }
    const d = new Date(dateStr);
    return d.toLocaleString('en-US', { month: 'long', day: 'numeric', year: 'numeric' }).toUpperCase();
};
// Standardized Date Time Format: "Feb 4, 8:55 AM"
const formatDateTimeStandard = (dateStr) => {
    if (!dateStr) return "";
    const d = new Date(dateStr);
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true });
};
const formatTime = (dateStr) => formatDateTimeStandard(dateStr); // Reuse standard
const formatDateTimeShort = (dateStr) => formatDateTimeStandard(dateStr); // Reuse standard
