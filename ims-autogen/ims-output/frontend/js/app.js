/* 应用初始化 - 注册路由 */

(function() {
    'use strict';

    // ===== 工具函数 =====
    const Utils = {
        // 显示 Toast 通知
        toast(message, type = 'success') {
            const container = document.getElementById('toastContainer');
            if (!container) return;

            const bgColor = {
                success: '#10b981',
                error: '#ef4444',
                warning: '#f59e0b',
                info: '#3b82f6'
            };

            const toast = document.createElement('div');
            toast.className = 'toast show';
            toast.style.cssText = `
                background: ${bgColor[type] || bgColor.info};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 20px;
                margin-bottom: 8px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                animation: slideIn 0.3s ease;
                min-width: 280px;
            `;
            toast.innerHTML = `<div class="d-flex align-items-center gap-2"><i class="bi bi-${type === 'success' ? 'check-circle' : type === 'error' ? 'x-circle' : type === 'warning' ? 'exclamation-triangle' : 'info-circle'}"></i> ${message}</div>`;
            container.appendChild(toast);

            setTimeout(() => {
                toast.style.opacity = '0';
                toast.style.transition = 'opacity 0.3s';
                setTimeout(() => toast.remove(), 300);
            }, 3000);
        },

        // 确认对话框
        async confirm(message) {
            return new Promise((resolve) => {
                const modal = document.createElement('div');
                modal.style.cssText = `
                    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
                    background: rgba(0,0,0,0.5); z-index: 9999;
                    display: flex; align-items: center; justify-content: center;
                `;
                modal.innerHTML = `
                    <div style="background: #fff; border-radius: 12px; padding: 24px; max-width: 400px; width: 90%; box-shadow: 0 20px 60px rgba(0,0,0,0.3);">
                        <div class="text-center mb-3">
                            <i class="bi bi-exclamation-triangle" style="font-size: 48px; color: #f59e0b;"></i>
                        </div>
                        <p style="text-align: center; font-size: 16px; margin-bottom: 24px;">${message}</p>
                        <div style="display: flex; gap: 12px; justify-content: center;">
                            <button class="btn btn-secondary" id="confirmNo">取消</button>
                            <button class="btn btn-danger" id="confirmYes">确认</button>
                        </div>
                    </div>
                `;
                document.body.appendChild(modal);
                modal.querySelector('#confirmYes').onclick = () => { modal.remove(); resolve(true); };
                modal.querySelector('#confirmNo').onclick = () => { modal.remove(); resolve(false); };
                modal.onclick = (e) => { if (e.target === modal) { modal.remove(); resolve(false); } };
            });
        },

        // 渲染分页
        renderPagination(container, { page, pages, total, per_page }, callback) {
            if (pages <= 1) { container.innerHTML = ''; return; }
            let html = `<nav><ul class="pagination pagination-sm justify-content-center mb-0">`;
            html += `<li class="page-item ${page <= 1 ? 'disabled' : ''}">
                <a class="page-link" href="#" data-page="${page - 1}">上一页</a></li>`;

            for (let i = Math.max(1, page - 2); i <= Math.min(pages, page + 2); i++) {
                html += `<li class="page-item ${i === page ? 'active' : ''}">
                    <a class="page-link" href="#" data-page="${i}">${i}</a></li>`;
            }

            html += `<li class="page-item ${page >= pages ? 'disabled' : ''}">
                <a class="page-link" href="#" data-page="${page + 1}">下一页</a></li>`;
            html += '</ul></nav>';
            container.innerHTML = html;

            container.querySelectorAll('[data-page]').forEach(a => {
                a.addEventListener('click', (e) => {
                    e.preventDefault();
                    const p = parseInt(e.target.dataset.page);
                    if (p && p !== page) callback(p);
                });
            });
        },

        // 获取状态标签的 CSS 类
        statusBadge(status) {
            const map = {
                '待入库': 'bg-warning text-dark',
                '部分入库': 'bg-info text-white',
                '已完成': 'bg-success text-white',
                '已取消': 'bg-danger text-white',
                '草稿': 'bg-secondary text-white',
                '待出库': 'bg-warning text-dark',
                '部分出库': 'bg-info text-white'
            };
            return map[status] || 'bg-secondary text-white';
        },

        // 格式化金额
        formatMoney(val) {
            return parseFloat(val || 0).toFixed(2);
        },

        // 格式化数量
        formatQty(val) {
            const v = parseFloat(val || 0);
            return Number.isInteger(v) ? v.toString() : v.toFixed(2);
        },

        // 获取当前日期字符串
        today() {
            return new Date().toISOString().slice(0, 10);
        },

        // 获取30天前日期
        monthAgo() {
            const d = new Date();
            d.setDate(d.getDate() - 30);
            return d.toISOString().slice(0, 10);
        },

        // 转义 HTML
        esc(str) {
            const div = document.createElement('div');
            div.textContent = str || '';
            return div.innerHTML;
        }
    };

    // 暴露到全局
    window.Utils = Utils;

    // ===== 渲染函数 =====

    // 仪表盘
    function renderDashboard(container) {
        container.innerHTML = `
            <div class="row g-3 mb-4">
                <div class="col-md-3">
                    <div class="card p-3 text-center">
                        <div class="fs-2 text-primary"><i class="bi bi-box"></i></div>
                        <div class="fs-3 fw-bold" id="statProducts">-</div>
                        <div class="text-muted small">商品总数</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card p-3 text-center">
                        <div class="fs-2 text-success"><i class="bi bi-boxes"></i></div>
                        <div class="fs-3 fw-bold" id="statLowStock">-</div>
                        <div class="text-muted small">低库存预警</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card p-3 text-center">
                        <div class="fs-2 text-warning"><i class="bi bi-cart-plus"></i></div>
                        <div class="fs-3 fw-bold" id="statPendingPurchase">-</div>
                        <div class="text-muted small">待入库订单</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card p-3 text-center">
                        <div class="fs-2 text-info"><i class="bi bi-cart"></i></div>
                        <div class="fs-3 fw-bold" id="statPendingSale">-</div>
                        <div class="text-muted small">待出库订单</div>
                    </div>
                </div>
            </div>
            <div class="card">
                <div class="card-header">快速入口</div>
                <div class="card-body">
                    <div class="row g-2">
                        <div class="col-6 col-md-3">
                            <a href="#/products" class="btn btn-outline-primary w-100 py-3">
                                <i class="bi bi-box d-block fs-4 mb-1"></i>商品管理
                            </a>
                        </div>
                        <div class="col-6 col-md-3">
                            <a href="#/purchase-orders" class="btn btn-outline-success w-100 py-3">
                                <i class="bi bi-cart-plus d-block fs-4 mb-1"></i>采购管理
                            </a>
                        </div>
                        <div class="col-6 col-md-3">
                            <a href="#/sale-orders" class="btn btn-outline-info w-100 py-3">
                                <i class="bi bi-cart d-block fs-4 mb-1"></i>销售管理
                            </a>
                        </div>
                        <div class="col-6 col-md-3">
                            <a href="#/stock" class="btn btn-outline-warning w-100 py-3">
                                <i class="bi bi-boxes d-block fs-4 mb-1"></i>库存查询
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // 加载统计数据
        Promise.all([
            ApiClient.getProducts({ per_page: 1 }),
            ApiClient.getLowStock(),
            ApiClient.getPurchaseOrders({ status: '待入库', per_page: 1 }),
            ApiClient.getSaleOrders({ status: '待出库', per_page: 1 })
        ]).then(([products, lowStock, purchases, sales]) => {
            const pData = products.data || {};
            document.getElementById('statProducts').textContent = pData.total || 0;
            document.getElementById('statLowStock').textContent = (lowStock.data || []).length;
            const purData = purchases.data || {};
            document.getElementById('statPendingPurchase').textContent = purData.total || 0;
            const saleData = sales.data || {};
            document.getElementById('statPendingSale').textContent = saleData.total || 0;
        }).catch(err => {
            Utils.toast('加载统计数据失败: ' + err.message, 'error');
        });
    }

    // 通用列表页渲染函数
    function renderListPage(container, options) {
        const { title, columns, fetchFn, renderRow, formatters, searchPlaceholder } = options;
        let html = `
            <div class="card">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <span>${title}</span>
                    <div class="d-flex gap-2 align-items-center">
                        <div class="input-group input-group-sm" style="max-width: 250px;">
                            <input type="text" class="form-control" placeholder="${searchPlaceholder || '搜索...'}" id="searchInput">
                            <button class="btn btn-outline-secondary" type="button" id="searchBtn"><i class="bi bi-search"></i></button>
                        </div>
                        <button class="btn btn-primary btn-sm" id="addBtn"><i class="bi bi-plus"></i> 新增</button>
                    </div>
                </div>
                <div class="table-responsive">
                    <table class="table table-hover mb-0">
                        <thead><tr>${columns.map(c => `<th>${c}</th>`).join('')}<th style="width: 120px;">操作</th></tr></thead>
                        <tbody id="dataBody">
                            <tr><td colspan="${columns.length + 1}" class="text-center text-muted py-4">加载中...</td></tr>
                        </tbody>
                    </table>
                </div>
                <div class="card-footer d-flex justify-content-between align-items-center">
                    <small class="text-muted" id="totalInfo">共 0 条</small>
                    <div id="pagination"></div>
                </div>
            </div>
        `;
        container.innerHTML = html;

        let currentPage = 1;
        let currentKeyword = '';

        function loadData() {
            const tbody = document.getElementById('dataBody');
            if (!tbody) return;
            tbody.innerHTML = '<tr><td colspan="999" class="text-center py-4"><div class="loading"></div></td></tr>';

            fetchFn({ page: currentPage, per_page: 20, keyword: currentKeyword || undefined })
                .then(result => {
                    const data = result.data || {};
                    const items = data.items || [];
                    const total = data.total || 0;

                    document.getElementById('totalInfo').textContent = `共 ${total} 条`;

                    if (items.length === 0) {
                        tbody.innerHTML = `<tr><td colspan="999" class="text-center text-muted py-4">
                            <i class="bi bi-inbox fs-2 d-block mb-2"></i>暂无数据</td></tr>`;
                        return;
                    }

                    tbody.innerHTML = items.map(item => {
                        const row = renderRow(item);
                        const rowClass = item.is_low_stock ? ' class="low-stock"' : '';
                        return `<tr${rowClass}>${row.map(cell => `<td>${cell}</td>`).join('')}</tr>`;
                    }).join('');

                    const pagination = document.getElementById('pagination');
                    if (pagination) {
                        Utils.renderPagination(pagination, data, page => {
                            currentPage = page;
                            loadData();
                        });
                    }
                })
                .catch(err => {
                    tbody.innerHTML = `<tr><td colspan="999" class="text-center text-danger py-4">
                        <i class="bi bi-exclamation-triangle"></i> ${err.message}</td></tr>`;
                });
        }

        // 事件绑定 (延迟确保元素存在)
        setTimeout(() => {
            const searchInput = document.getElementById('searchInput');
            const searchBtn = document.getElementById('searchBtn');
            const addBtn = document.getElementById('addBtn');

            if (searchBtn && searchInput) {
                const doSearch = () => {
                    currentKeyword = searchInput.value.trim();
                    currentPage = 1;
                    loadData();
                };
                searchBtn.onclick = doSearch;
                searchInput.onkeydown = (e) => { if (e.key === 'Enter') doSearch(); };
            }

            if (addBtn && options.onAdd) {
                addBtn.onclick = options.onAdd;
            }
        }, 50);

        loadData();
    }

    // ===== 注册路由 =====

    // 仪表盘
    router.addRoute('/dashboard', renderDashboard);

    // 商品列表 (使用通用列表)
    router.addRoute('/products', (container) => {
        renderListPage(container, {
            title: '商品列表',
            columns: ['编码', '商品名称', '分类', '单位', '采购价', '销售价', '当前库存', '库存下限'],
            searchPlaceholder: '搜索商品名称/编码...',
            fetchFn: (params) => ApiClient.getProducts(params),
            renderRow: (item) => [
                Utils.esc(item.code),
                Utils.esc(item.name),
                Utils.esc(item.category_name || '-'),
                Utils.esc(item.unit_name || '-'),
                `¥${Utils.formatMoney(item.purchase_price)}`,
                `¥${Utils.formatMoney(item.sale_price)}`,
                `<span class="fw-bold ${item.is_low_stock ? 'text-danger' : ''}">${Utils.formatQty(item.current_stock)}</span>`,
                Utils.formatQty(item.min_stock)
            ],
            onAdd: () => window.location.hash = '#/products/new'
        });
    });

    // 商品表单（新增/编辑）
    router.addRoute('/products/new', (container) => {
        renderProductForm(container, null);
    });
    router.addRoute('/products/:id/edit', (container, params) => {
        renderProductForm(container, parseInt(params.id));
    });

    async function renderProductForm(container, id) {
        const isEdit = id !== null;
        let product = null;
        let categories = [];
        let units = [];

        try {
            [categories, units] = await Promise.all([
                ApiClient.getCategories(),
                ApiClient.getUnits()
            ]);
            if (isEdit) {
                const resp = await ApiClient.getProduct(id);
                product = resp.data;
            }
        } catch (err) {
            Utils.toast('加载数据失败: ' + err.message, 'error');
        }

        const catOptions = (categories.data || []).map(c =>
            `<option value="${c.id}" ${product && product.category_id === c.id ? 'selected' : ''}>${Utils.esc(c.name)}</option>`
        ).join('');
        const unitOptions = (units.data || []).map(u =>
            `<option value="${u.id}" ${product && product.unit_id === u.id ? 'selected' : ''}>${Utils.esc(u.name)}</option>`
        ).join('');

        container.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <a href="#/products" class="btn btn-sm btn-outline-secondary me-2">&larr; 返回</a>
                    ${isEdit ? '编辑商品' : '新增商品'}
                </div>
                <div class="card-body">
                    <form id="productForm" class="row g-3">
                        <div class="col-md-4">
                            <label class="form-label">商品编码 <span class="text-danger">*</span></label>
                            <input type="text" class="form-control" name="code" value="${product ? Utils.esc(product.code) : ''}" required>
                        </div>
                        <div class="col-md-4">
                            <label class="form-label">商品名称 <span class="text-danger">*</span></label>
                            <input type="text" class="form-control" name="name" value="${product ? Utils.esc(product.name) : ''}" required>
                        </div>
                        <div class="col-md-2">
                            <label class="form-label">分类</label>
                            <select class="form-select" name="category_id">
                                <option value="">无分类</option>
                                ${catOptions}
                            </select>
                        </div>
                        <div class="col-md-2">
                            <label class="form-label">单位</label>
                            <select class="form-select" name="unit_id">
                                <option value="">无单位</option>
                                ${unitOptions}
                            </select>
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">采购价</label>
                            <input type="number" class="form-control" name="purchase_price" step="0.01" min="0"
                                value="${product ? product.purchase_price : '0'}">
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">销售价</label>
                            <input type="number" class="form-control" name="sale_price" step="0.01" min="0"
                                value="${product ? product.sale_price : '0'}">
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">库存下限</label>
                            <input type="number" class="form-control" name="min_stock" step="0.01" min="0"
                                value="${product ? product.min_stock : '0'}">
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">库存上限</label>
                            <input type="number" class="form-control" name="max_stock" step="0.01" min="0"
                                value="${product ? product.max_stock : '0'}">
                        </div>
                        <div class="col-12">
                            <label class="form-label">备注</label>
                            <textarea class="form-control" name="remark" rows="2">${product ? Utils.esc(product.remark) : ''}</textarea>
                        </div>
                        <div class="col-12">
                            <button type="submit" class="btn btn-primary">
                                <i class="bi bi-check"></i> ${isEdit ? '保存修改' : '创建商品'}
                            </button>
                            <a href="#/products" class="btn btn-outline-secondary ms-2">取消</a>
                        </div>
                    </form>
                </div>
            </div>
        `;

        document.getElementById('productForm').onsubmit = async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData.entries());
            // 数字字段处理
            data.purchase_price = parseFloat(data.purchase_price) || 0;
            data.sale_price = parseFloat(data.sale_price) || 0;
            data.min_stock = parseFloat(data.min_stock) || 0;
            data.max_stock = parseFloat(data.max_stock) || 0;
            data.category_id = data.category_id ? parseInt(data.category_id) : null;
            data.unit_id = data.unit_id ? parseInt(data.unit_id) : null;

            try {
                if (isEdit) {
                    await ApiClient.updateProduct(id, data);
                    Utils.toast('商品更新成功');
                } else {
                    await ApiClient.createProduct(data);
                    Utils.toast('商品创建成功');
                }
                window.location.hash = '#/products';
            } catch (err) {
                Utils.toast(err.message, 'error');
            }
        };
    }

    // 分类管理
    router.addRoute('/categories', async (container) => {
        container.innerHTML = `<div class="card">
            <div class="card-header d-flex justify-content-between align-items-center">
                <span>分类管理</span>
                <button class="btn btn-primary btn-sm" id="addCategoryBtn"><i class="bi bi-plus"></i> 新增分类</button>
            </div>
            <div class="table-responsive">
                <table class="table table-hover mb-0">
                    <thead><tr><th>ID</th><th>分类名称</th><th>备注</th><th>创建时间</th><th style="width:120px">操作</th></tr></thead>
                    <tbody id="categoryBody"></tbody>
                </table>
            </div>
        </div>`;

        function loadCategories() {
            const tbody = document.getElementById('categoryBody');
            tbody.innerHTML = '<tr><td colspan="5" class="text-center py-3"><div class="loading"></div></td></tr>';
            ApiClient.getCategories().then(resp => {
                const items = resp.data || [];
                if (items.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-4">暂无分类</td></tr>';
                    return;
                }
                tbody.innerHTML = items.map(c => `<tr>
                    <td>${c.id}</td>
                    <td>${Utils.esc(c.name)}</td>
                    <td>${Utils.esc(c.remark || '-')}</td>
                    <td>${c.created_at || '-'}</td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary edit-cat" data-id="${c.id}" data-name="${Utils.esc(c.name)}" data-remark="${Utils.esc(c.remark || '')}">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger del-cat" data-id="${c.id}">
                            <i class="bi bi-trash"></i>
                        </button>
                    </td>
                </tr>`).join('');

                tbody.querySelectorAll('.edit-cat').forEach(btn => {
                    btn.onclick = () => showCategoryModal(parseInt(btn.dataset.id), btn.dataset.name, btn.dataset.remark);
                });
                tbody.querySelectorAll('.del-cat').forEach(btn => {
                    btn.onclick = async () => {
                        if (await Utils.confirm('确认删除此分类？')) {
                            try {
                                await ApiClient.deleteCategory(parseInt(btn.dataset.id));
                                Utils.toast('分类已删除');
                                loadCategories();
                            } catch (err) { Utils.toast(err.message, 'error'); }
                        }
                    };
                });
            }).catch(err => Utils.toast(err.message, 'error'));
        }

        function showCategoryModal(id = null, name = '', remark = '') {
            const isEdit = id !== null;
            const modal = document.createElement('div');
            modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;';
            modal.innerHTML = `<div style="background:#fff;border-radius:12px;padding:24px;max-width:400px;width:90%">
                <h5 class="mb-3">${isEdit ? '编辑分类' : '新增分类'}</h5>
                <form id="catForm">
                    <div class="mb-3">
                        <label class="form-label">分类名称 <span class="text-danger">*</span></label>
                        <input type="text" class="form-control" name="name" value="${Utils.esc(name)}" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">备注</label>
                        <textarea class="form-control" name="remark" rows="2">${Utils.esc(remark)}</textarea>
                    </div>
                    <div class="d-flex gap-2 justify-content-end">
                        <button type="button" class="btn btn-secondary" id="catCancel">取消</button>
                        <button type="submit" class="btn btn-primary">${isEdit ? '保存' : '创建'}</button>
                    </div>
                </form>
            </div>`;
            document.body.appendChild(modal);

            modal.querySelector('#catCancel').onclick = () => modal.remove();
            modal.onclick = (e) => { if (e.target === modal) modal.remove(); };

            modal.querySelector('#catForm').onsubmit = async (e) => {
                e.preventDefault();
                const data = Object.fromEntries(new FormData(e.target));
                try {
                    if (isEdit) {
                        await ApiClient.updateCategory(id, data);
                        Utils.toast('分类更新成功');
                    } else {
                        await ApiClient.createCategory(data);
                        Utils.toast('分类创建成功');
                    }
                    modal.remove();
                    loadCategories();
                } catch (err) { Utils.toast(err.message, 'error'); }
            };
        }

        setTimeout(() => {
            document.getElementById('addCategoryBtn').onclick = () => showCategoryModal();
        }, 50);

        loadCategories();
    });

    // 单位管理
    router.addRoute('/units', async (container) => {
        container.innerHTML = `<div class="card">
            <div class="card-header d-flex justify-content-between align-items-center">
                <span>单位管理</span>
                <button class="btn btn-primary btn-sm" id="addUnitBtn"><i class="bi bi-plus"></i> 新增单位</button>
            </div>
            <div class="table-responsive">
                <table class="table table-hover mb-0">
                    <thead><tr><th>ID</th><th>单位名称</th><th>创建时间</th><th style="width:120px">操作</th></tr></thead>
                    <tbody id="unitBody"></tbody>
                </table>
            </div>
        </div>`;

        function loadUnits() {
            const tbody = document.getElementById('unitBody');
            tbody.innerHTML = '<tr><td colspan="4" class="text-center py-3"><div class="loading"></div></td></tr>';
            ApiClient.getUnits().then(resp => {
                const items = resp.data || [];
                if (items.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted py-4">暂无单位</td></tr>';
                    return;
                }
                tbody.innerHTML = items.map(u => `<tr>
                    <td>${u.id}</td>
                    <td>${Utils.esc(u.name)}</td>
                    <td>${u.created_at || '-'}</td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary edit-unit" data-id="${u.id}" data-name="${Utils.esc(u.name)}"><i class="bi bi-pencil"></i></button>
                        <button class="btn btn-sm btn-outline-danger del-unit" data-id="${u.id}"><i class="bi bi-trash"></i></button>
                    </td>
                </tr>`).join('');

                tbody.querySelectorAll('.edit-unit').forEach(btn => {
                    btn.onclick = () => showUnitModal(parseInt(btn.dataset.id), btn.dataset.name);
                });
                tbody.querySelectorAll('.del-unit').forEach(btn => {
                    btn.onclick = async () => {
                        if (await Utils.confirm('确认删除此单位？')) {
                            try {
                                await ApiClient.deleteUnit(parseInt(btn.dataset.id));
                                Utils.toast('单位已删除');
                                loadUnits();
                            } catch (err) { Utils.toast(err.message, 'error'); }
                        }
                    };
                });
            }).catch(err => Utils.toast(err.message, 'error'));
        }

        function showUnitModal(id = null, name = '') {
            const isEdit = id !== null;
            const modal = document.createElement('div');
            modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;';
            modal.innerHTML = `<div style="background:#fff;border-radius:12px;padding:24px;max-width:400px;width:90%">
                <h5 class="mb-3">${isEdit ? '编辑单位' : '新增单位'}</h5>
                <form id="unitForm">
                    <div class="mb-3">
                        <label class="form-label">单位名称 <span class="text-danger">*</span></label>
                        <input type="text" class="form-control" name="name" value="${Utils.esc(name)}" required>
                    </div>
                    <div class="d-flex gap-2 justify-content-end">
                        <button type="button" class="btn btn-secondary" id="unitCancel">取消</button>
                        <button type="submit" class="btn btn-primary">${isEdit ? '保存' : '创建'}</button>
                    </div>
                </form>
            </div>`;
            document.body.appendChild(modal);
            modal.querySelector('#unitCancel').onclick = () => modal.remove();
            modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
            modal.querySelector('#unitForm').onsubmit = async (e) => {
                e.preventDefault();
                const data = Object.fromEntries(new FormData(e.target));
                try {
                    if (isEdit) { await ApiClient.updateUnit(id, data); Utils.toast('单位更新成功'); }
                    else { await ApiClient.createUnit(data); Utils.toast('单位创建成功'); }
                    modal.remove();
                    loadUnits();
                } catch (err) { Utils.toast(err.message, 'error'); }
            };
        }

        setTimeout(() => {
            document.getElementById('addUnitBtn').onclick = () => showUnitModal();
        }, 50);

        loadUnits();
    });

    // 供应商列表
    router.addRoute('/suppliers', (container) => {
        renderListPage(container, {
            title: '供应商管理',
            columns: ['供应商名称', '联系人', '联系电话', '地址', '备注'],
            searchPlaceholder: '搜索供应商名称...',
            fetchFn: (params) => ApiClient.getSuppliers(params),
            renderRow: (item) => [
                Utils.esc(item.name),
                Utils.esc(item.contact || '-'),
                Utils.esc(item.phone || '-'),
                Utils.esc(item.address || '-'),
                Utils.esc(item.remark || '-')
            ],
            onAdd: () => window.location.hash = '#/suppliers/new'
        });
    });

    // 供应商表单
    router.addRoute('/suppliers/new', (container) => renderSupplierForm(container, null));
    router.addRoute('/suppliers/:id/edit', (container, params) => renderSupplierForm(container, parseInt(params.id)));

    async function renderSupplierForm(container, id) {
        const isEdit = id !== null;
        let supplier = null;
        if (isEdit) {
            try {
                const resp = await ApiClient.getSuppliers({ per_page: 100 });
                const items = resp.data?.items || [];
                supplier = items.find(s => s.id === id);
            } catch (err) { Utils.toast(err.message, 'error'); }
        }

        container.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <a href="#/suppliers" class="btn btn-sm btn-outline-secondary me-2">&larr; 返回</a>
                    ${isEdit ? '编辑供应商' : '新增供应商'}
                </div>
                <div class="card-body">
                    <form id="supplierForm" class="row g-3">
                        <div class="col-md-6">
                            <label class="form-label">供应商名称 <span class="text-danger">*</span></label>
                            <input type="text" class="form-control" name="name" value="${supplier ? Utils.esc(supplier.name) : ''}" required>
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">联系人</label>
                            <input type="text" class="form-control" name="contact" value="${supplier ? Utils.esc(supplier.contact || '') : ''}">
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">联系电话</label>
                            <input type="text" class="form-control" name="phone" value="${supplier ? Utils.esc(supplier.phone || '') : ''}">
                        </div>
                        <div class="col-md-8">
                            <label class="form-label">地址</label>
                            <input type="text" class="form-control" name="address" value="${supplier ? Utils.esc(supplier.address || '') : ''}">
                        </div>
                        <div class="col-12">
                            <label class="form-label">备注</label>
                            <textarea class="form-control" name="remark" rows="2">${supplier ? Utils.esc(supplier.remark || '') : ''}</textarea>
                        </div>
                        <div class="col-12">
                            <button type="submit" class="btn btn-primary"><i class="bi bi-check"></i> ${isEdit ? '保存修改' : '创建供应商'}</button>
                            <a href="#/suppliers" class="btn btn-outline-secondary ms-2">取消</a>
                        </div>
                    </form>
                </div>
            </div>
        `;

        document.getElementById('supplierForm').onsubmit = async (e) => {
            e.preventDefault();
            const data = Object.fromEntries(new FormData(e.target));
            try {
                if (isEdit) { await ApiClient.updateSupplier(id, data); Utils.toast('供应商更新成功'); }
                else { await ApiClient.createSupplier(data); Utils.toast('供应商创建成功'); }
                window.location.hash = '#/suppliers';
            } catch (err) { Utils.toast(err.message, 'error'); }
        };
    }

    // 客户列表
    router.addRoute('/customers', (container) => {
        renderListPage(container, {
            title: '客户管理',
            columns: ['客户名称', '联系人', '联系电话', '地址', '备注'],
            searchPlaceholder: '搜索客户名称...',
            fetchFn: (params) => ApiClient.getCustomers(params),
            renderRow: (item) => [
                Utils.esc(item.name),
                Utils.esc(item.contact || '-'),
                Utils.esc(item.phone || '-'),
                Utils.esc(item.address || '-'),
                Utils.esc(item.remark || '-')
            ],
            onAdd: () => window.location.hash = '#/customers/new'
        });
    });

    // 客户表单
    router.addRoute('/customers/new', (container) => renderCustomerForm(container, null));
    router.addRoute('/customers/:id/edit', (container, params) => renderCustomerForm(container, parseInt(params.id)));

    async function renderCustomerForm(container, id) {
        const isEdit = id !== null;
        let customer = null;
        if (isEdit) {
            try {
                const resp = await ApiClient.getCustomers({ per_page: 100 });
                const items = resp.data?.items || [];
                customer = items.find(c => c.id === id);
            } catch (err) { Utils.toast(err.message, 'error'); }
        }

        container.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <a href="#/customers" class="btn btn-sm btn-outline-secondary me-2">&larr; 返回</a>
                    ${isEdit ? '编辑客户' : '新增客户'}
                </div>
                <div class="card-body">
                    <form id="customerForm" class="row g-3">
                        <div class="col-md-6">
                            <label class="form-label">客户名称 <span class="text-danger">*</span></label>
                            <input type="text" class="form-control" name="name" value="${customer ? Utils.esc(customer.name) : ''}" required>
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">联系人</label>
                            <input type="text" class="form-control" name="contact" value="${customer ? Utils.esc(customer.contact || '') : ''}">
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">联系电话</label>
                            <input type="text" class="form-control" name="phone" value="${customer ? Utils.esc(customer.phone || '') : ''}">
                        </div>
                        <div class="col-md-8">
                            <label class="form-label">地址</label>
                            <input type="text" class="form-control" name="address" value="${customer ? Utils.esc(customer.address || '') : ''}">
                        </div>
                        <div class="col-12">
                            <label class="form-label">备注</label>
                            <textarea class="form-control" name="remark" rows="2">${customer ? Utils.esc(customer.remark || '') : ''}</textarea>
                        </div>
                        <div class="col-12">
                            <button type="submit" class="btn btn-primary"><i class="bi bi-check"></i> ${isEdit ? '保存修改' : '创建客户'}</button>
                            <a href="#/customers" class="btn btn-outline-secondary ms-2">取消</a>
                        </div>
                    </form>
                </div>
            </div>
        `;

        document.getElementById('customerForm').onsubmit = async (e) => {
            e.preventDefault();
            const data = Object.fromEntries(new FormData(e.target));
            try {
                if (isEdit) { await ApiClient.updateCustomer(id, data); Utils.toast('客户更新成功'); }
                else { await ApiClient.createCustomer(data); Utils.toast('客户创建成功'); }
                window.location.hash = '#/customers';
            } catch (err) { Utils.toast(err.message, 'error'); }
        };
    }

    // 采购订单列表
    router.addRoute('/purchase-orders', (container) => {
        renderOrderList(container, 'purchase');
    });

    // 采购订单新增
    router.addRoute('/purchase-orders/new', (container) => renderOrderForm(container, 'purchase', null));
    router.addRoute('/purchase-orders/:id/edit', (container, params) => renderOrderForm(container, 'purchase', parseInt(params.id)));

    // 销售订单列表
    router.addRoute('/sale-orders', (container) => {
        renderOrderList(container, 'sale');
    });

    // 销售订单新增
    router.addRoute('/sale-orders/new', (container) => renderOrderForm(container, 'sale', null));
    router.addRoute('/sale-orders/:id/edit', (container, params) => renderOrderForm(container, 'sale', parseInt(params.id)));

    // 通用订单列表
    function renderOrderList(container, type) {
        const isPurchase = type === 'purchase';
        const title = isPurchase ? '采购订单' : '销售订单';
        const partnerName = isPurchase ? '供应商' : '客户';
        const statusFilter = isPurchase ? '待入库' : '待出库';
        const apiFn = isPurchase
            ? (p) => ApiClient.getPurchaseOrders(p)
            : (p) => ApiClient.getSaleOrders(p);

        container.innerHTML = `
            <div class="card">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <span>${title}</span>
                    <div class="d-flex gap-2 align-items-center">
                        <select class="form-select form-select-sm" id="statusFilter" style="width:140px">
                            <option value="">全部状态</option>
                            <option value="待入库">待入库</option>
                            <option value="部分入库">部分入库</option>
                            <option value="已完成">已完成</option>
                            <option value="待出库">待出库</option>
                            <option value="部分出库">部分出库</option>
                            <option value="已取消">已取消</option>
                        </select>
                        <div class="input-group input-group-sm" style="max-width:250px">
                            <input type="text" class="form-control" placeholder="搜索订单号/${partnerName}..." id="searchInput">
                            <button class="btn btn-outline-secondary" id="searchBtn"><i class="bi bi-search"></i></button>
                        </div>
                        <a href="#/${isPurchase ? 'purchase-orders' : 'sale-orders'}/new" class="btn btn-primary btn-sm">
                            <i class="bi bi-plus"></i> 新增
                        </a>
                    </div>
                </div>
                <div class="table-responsive">
                    <table class="table table-hover mb-0">
                        <thead><tr>
                            <th>订单号</th>
                            <th>${partnerName}</th>
                            <th>金额</th>
                            <th>状态</th>
                            <th>创建时间</th>
                            <th style="width:150px">操作</th>
                        </tr></thead>
                        <tbody id="orderBody"></tbody>
                    </table>
                </div>
                <div class="card-footer d-flex justify-content-between align-items-center">
                    <small class="text-muted" id="totalInfo">共 0 条</small>
                    <div id="pagination"></div>
                </div>
            </div>
        `;

        let currentPage = 1;
        let currentKeyword = '';
        let currentStatus = '';

        function loadOrders() {
            const tbody = document.getElementById('orderBody');
            tbody.innerHTML = '<tr><td colspan="6" class="text-center py-3"><div class="loading"></div></td></tr>';

            const params = { page: currentPage, per_page: 20 };
            if (currentKeyword) params.keyword = currentKeyword;
            if (currentStatus) params.status = currentStatus;

            apiFn(params).then(result => {
                const data = result.data || {};
                const items = data.items || [];
                document.getElementById('totalInfo').textContent = `共 ${data.total || 0} 条`;

                if (items.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-4">暂无订单</td></tr>';
                    return;
                }

                tbody.innerHTML = items.map(o => {
                    const partner = isPurchase ? (o.supplier_name || '-') : (o.customer_name || '-');
                    const detailHash = `#/${isPurchase ? 'purchase-orders' : 'sale-orders'}/${o.id}/edit`;

                    let actions = '';
                    const status = o.status || '';
                    if (status === '待入库' || status === '待出库') {
                        actions += `<a href="${detailHash}" class="btn btn-sm btn-outline-primary" title="编辑"><i class="bi bi-pencil"></i></a>`;
                        if (isPurchase) {
                            actions += `<button class="btn btn-sm btn-success ms-1 receive-btn" data-id="${o.id}" title="入库确认"><i class="bi bi-check-lg"></i></button>`;
                        } else {
                            actions += `<button class="btn btn-sm btn-success ms-1 ship-btn" data-id="${o.id}" title="出库确认"><i class="bi bi-check-lg"></i></button>`;
                        }
                    } else {
                        actions += `<a href="${detailHash}" class="btn btn-sm btn-outline-secondary" title="查看"><i class="bi bi-eye"></i></a>`;
                    }

                    return `<tr>
                        <td><a href="${detailHash}" class="text-decoration-none fw-bold">${Utils.esc(o.order_no)}</a></td>
                        <td>${Utils.esc(partner)}</td>
                        <td>¥${Utils.formatMoney(o.total_amount)}</td>
                        <td><span class="badge ${Utils.statusBadge(status)}">${status}</span></td>
                        <td>${o.created_at || '-'}</td>
                        <td>${actions}</td>
                    </tr>`;
                }).join('');

                // 事件绑定
                tbody.querySelectorAll('.receive-btn').forEach(btn => {
                    btn.onclick = async () => {
                        if (await Utils.confirm('确认入库？')) {
                            try {
                                await ApiClient.receivePurchaseOrder(parseInt(btn.dataset.id), {});
                                Utils.toast('入库确认成功');
                                loadOrders();
                            } catch (err) { Utils.toast(err.message, 'error'); }
                        }
                    };
                });
                tbody.querySelectorAll('.ship-btn').forEach(btn => {
                    btn.onclick = async () => {
                        if (await Utils.confirm('确认出库？')) {
                            try {
                                await ApiClient.shipSaleOrder(parseInt(btn.dataset.id), {});
                                Utils.toast('出库确认成功');
                                loadOrders();
                            } catch (err) { Utils.toast(err.message, 'error'); }
                        }
                    };
                });

                const pagination = document.getElementById('pagination');
                if (pagination) {
                    Utils.renderPagination(pagination, data, p => { currentPage = p; loadOrders(); });
                }
            }).catch(err => {
                tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger py-3">${err.message}</td></tr>`;
            });
        }

        setTimeout(() => {
            const searchInput = document.getElementById('searchInput');
            const searchBtn = document.getElementById('searchBtn');
            const statusFilter = document.getElementById('statusFilter');

            if (searchInput && searchBtn) {
                const doSearch = () => {
                    currentKeyword = searchInput.value.trim();
                    currentPage = 1;
                    loadOrders();
                };
                searchBtn.onclick = doSearch;
                searchInput.onkeydown = (e) => { if (e.key === 'Enter') doSearch(); };
            }
            if (statusFilter) {
                statusFilter.onchange = () => {
                    currentStatus = statusFilter.value;
                    currentPage = 1;
                    loadOrders();
                };
            }
        }, 50);

        loadOrders();
    }

    // 通用订单表单（新增/编辑）
    async function renderOrderForm(container, type, id) {
        const isPurchase = type === 'purchase';
        const isEdit = id !== null;
        const orderType = isPurchase ? '采购' : '销售';
        const partnerType = isPurchase ? '供应商' : '客户';
        const apiGetPartners = isPurchase
            ? () => ApiClient.getSuppliers({ per_page: 200 })
            : () => ApiClient.getCustomers({ per_page: 200 });

        let order = null;
        let partners = [];
        let products = [];

        try {
            [partners, products] = await Promise.all([
                apiGetPartners(),
                ApiClient.getProducts({ per_page: 500 })
            ]);

            if (isEdit) {
                const resp = isPurchase
                    ? await ApiClient.getPurchaseOrder(id)
                    : await ApiClient.getSaleOrder(id);
                order = resp.data;
            }
        } catch (err) {
            Utils.toast('加载数据失败: ' + err.message, 'error');
        }

        const partnersData = partners.data?.items || partners.data || [];
        const productsData = products.data?.items || [];

        const partnerOptions = partnersData.map(p =>
            `<option value="${p.id}" ${order && (order.supplier_id === p.id || order.customer_id === p.id) ? 'selected' : ''}>
                ${Utils.esc(p.name)}
            </option>`
        ).join('');

        const productOptions = productsData.map(p =>
            `<option value="${p.id}" data-price="${p.purchase_price || p.sale_price || 0}">
                [${Utils.esc(p.code || '')}] ${Utils.esc(p.name)} (¥${Utils.formatMoney(p.purchase_price || p.sale_price || 0)}/${Utils.esc(p.unit_name || '')})
            </option>`
        ).join('');

        // 现有明细
        let existingItems = [];
        if (order && order.items) {
            existingItems = order.items;
        }

        container.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <a href="#/${isPurchase ? 'purchase-orders' : 'sale-orders'}" class="btn btn-sm btn-outline-secondary me-2">&larr; 返回</a>
                    ${isEdit ? `编辑${orderType}订单 #${order ? order.order_no : ''}` : `新增${orderType}订单`}
                </div>
                <div class="card-body">
                    <form id="orderForm">
                        <div class="row g-3 mb-3">
                            <div class="col-md-6">
                                <label class="form-label">${partnerType} <span class="text-danger">*</span></label>
                                <select class="form-select" name="partner_id" required>
                                    <option value="">请选择${partnerType}</option>
                                    ${partnerOptions}
                                </select>
                            </div>
                            <div class="col-md-6">
                                <label class="form-label">备注</label>
                                <input type="text" class="form-control" name="remark" value="${order ? Utils.esc(order.remark || '') : ''}">
                            </div>
                        </div>
                    </form>

                    <h6 class="mt-3 mb-2">订单明细</h6>
                    <div class="table-responsive">
                        <table class="table table-bordered table-sm" id="itemsTable">
                            <thead>
                                <tr>
                                    <th style="width:40%">商品</th>
                                    <th style="width:15%">数量</th>
                                    <th style="width:15%">单价</th>
                                    <th style="width:15%">金额</th>
                                    <th style="width:60px">操作</th>
                                </tr>
                            </thead>
                            <tbody id="itemsBody">
                            </tbody>
                            <tfoot>
                                <tr class="total-row">
                                    <td colspan="3" class="text-end fw-bold">合计：</td>
                                    <td class="fw-bold" id="totalAmount">¥0.00</td>
                                    <td></td>
                                </tr>
                            </tfoot>
                        </table>
                    </div>

                    <div class="row g-2 mb-3">
                        <div class="col-md-5">
                            <select class="form-select form-select-sm" id="addProductSelect">
                                <option value="">选择商品添加</option>
                                ${productOptions}
                            </select>
                        </div>
                        <div class="col-md-2">
                            <input type="number" class="form-control form-control-sm" id="addQty" value="1" min="0.01" step="1" placeholder="数量">
                        </div>
                        <div class="col-md-2">
                            <input type="number" class="form-control form-control-sm" id="addPrice" value="0" min="0" step="0.01" placeholder="单价">
                        </div>
                        <div class="col-md-3">
                            <button type="button" class="btn btn-success btn-sm w-100" id="addItemBtn">
                                <i class="bi bi-plus"></i> 添加
                            </button>
                        </div>
                    </div>

                    <div class="mt-3">
                        <button type="button" class="btn btn-primary" id="submitOrderBtn">
                            <i class="bi bi-check"></i> ${isEdit ? '保存修改' : `创建${orderType}订单`}
                        </button>
                        <a href="#/${isPurchase ? 'purchase-orders' : 'sale-orders'}" class="btn btn-outline-secondary ms-2">取消</a>
                    </div>
                </div>
            </div>
        `;

        // 明细数据
        let items = [];
        if (existingItems.length > 0) {
            existingItems.forEach(item => {
                items.push({
                    product_id: item.product_id,
                    product_name: item.product_name || '',
                    quantity: item.quantity,
                    unit_price: item.unit_price || item.price || 0,
                    subtotal: item.subtotal || item.amount || 0
                });
            });
        }

        function renderItems() {
            const tbody = document.getElementById('itemsBody');
            if (!tbody) return;

            if (items.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-3">暂无明细，请添加商品</td></tr>';
                document.getElementById('totalAmount').textContent = '¥0.00';
                return;
            }

            let total = 0;
            tbody.innerHTML = items.map((item, idx) => {
                const subtotal = item.quantity * item.unit_price;
                item.subtotal = subtotal;
                total += subtotal;
                return `<tr>
                    <td>${Utils.esc(item.product_name)}</td>
                    <td><input type="number" class="form-control form-control-sm item-qty" data-idx="${idx}" value="${item.quantity}" min="0" step="0.01"></td>
                    <td><input type="number" class="form-control form-control-sm item-price" data-idx="${idx}" value="${item.unit_price}" min="0" step="0.01"></td>
                    <td class="text-end fw-bold">¥${Utils.formatMoney(subtotal)}</td>
                    <td><button class="btn btn-sm btn-outline-danger remove-item" data-idx="${idx}"><i class="bi bi-trash"></i></button></td>
                </tr>`;
            }).join('');

            document.getElementById('totalAmount').textContent = `¥${Utils.formatMoney(total)}`;

            // 数量/单价变更
            tbody.querySelectorAll('.item-qty').forEach(inp => {
                inp.onchange = () => {
                    items[parseInt(inp.dataset.idx)].quantity = parseFloat(inp.value) || 0;
                    renderItems();
                };
            });
            tbody.querySelectorAll('.item-price').forEach(inp => {
                inp.onchange = () => {
                    items[parseInt(inp.dataset.idx)].unit_price = parseFloat(inp.value) || 0;
                    renderItems();
                };
            });
            tbody.querySelectorAll('.remove-item').forEach(btn => {
                btn.onclick = () => {
                    items.splice(parseInt(btn.dataset.idx), 1);
                    renderItems();
                };
            });
        }

        renderItems();

        // 添加商品
        setTimeout(() => {
            const addSelect = document.getElementById('addProductSelect');
            const addQty = document.getElementById('addQty');
            const addPrice = document.getElementById('addPrice');
            const addBtn = document.getElementById('addItemBtn');

            if (addSelect && addBtn) {
                addSelect.onchange = () => {
                    const opt = addSelect.selectedOptions[0];
                    if (opt && opt.value) {
                        const price = parseFloat(opt.dataset.price) || 0;
                        addPrice.value = price;
                    }
                };

                addBtn.onclick = () => {
                    const opt = addSelect.selectedOptions[0];
                    if (!opt || !opt.value) {
                        Utils.toast('请选择商品', 'warning');
                        return;
                    }
                    const qty = parseFloat(addQty.value) || 1;
                    const price = parseFloat(addPrice.value) || 0;

                    const productId = parseInt(opt.value);
                    const productName = opt.text.split(']')[1]?.trim() || opt.text;

                    // 检查是否已添加
                    const exists = items.find(item => item.product_id === productId);
                    if (exists) {
                        exists.quantity += qty;
                    } else {
                        items.push({
                            product_id: productId,
                            product_name: productName,
                            quantity: qty,
                            unit_price: price,
                            subtotal: qty * price
                        });
                    }
                    renderItems();
                    addSelect.value = '';
                };
            }

            // 提交订单
            const submitBtn = document.getElementById('submitOrderBtn');
            if (submitBtn) {
                submitBtn.onclick = async () => {
                    const form = document.getElementById('orderForm');
                    const formData = new FormData(form);
                    const partnerId = parseInt(formData.get('partner_id'));
                    const remark = formData.get('remark') || '';

                    if (!partnerId) {
                        Utils.toast(`请选择${partnerType}`, 'warning');
                        return;
                    }
                    if (items.length === 0) {
                        Utils.toast('请至少添加一个商品', 'warning');
                        return;
                    }

                    const data = {
                        [isPurchase ? 'supplier_id' : 'customer_id']: partnerId,
                        remark,
                        items: items.map(item => ({
                            product_id: item.product_id,
                            quantity: item.quantity,
                            unit_price: item.unit_price
                        }))
                    };

                    try {
                        if (isEdit) {
                            if (isPurchase) {
                                await ApiClient.updatePurchaseOrder(id, data);
                            } else {
                                await ApiClient.updateSaleOrder(id, data);
                            }
                            Utils.toast('订单更新成功');
                        } else {
                            if (isPurchase) {
                                await ApiClient.createPurchaseOrder(data);
                            } else {
                                await ApiClient.createSaleOrder(data);
                            }
                            Utils.toast(`${orderType}订单创建成功`);
                        }
                        window.location.hash = `#/${isPurchase ? 'purchase-orders' : 'sale-orders'}`;
                    } catch (err) {
                        Utils.toast(err.message, 'error');
                    }
                };
            }
        }, 50);
    }

    // 库存查询
    router.addRoute('/stock', (container) => {
        renderListPage(container, {
            title: '库存查询',
            columns: ['编码', '商品名称', '分类', '单位', '当前库存', '销售价', '库存下限', '库存上限'],
            searchPlaceholder: '搜索商品名称/编码...',
            fetchFn: (params) => ApiClient.getStock(params),
            renderRow: (item) => [
                Utils.esc(item.code),
                Utils.esc(item.name),
                Utils.esc(item.category_name || '-'),
                Utils.esc(item.unit_name || '-'),
                `<span class="fw-bold ${item.is_low_stock ? 'text-danger' : ''}">${Utils.formatQty(item.current_stock)}</span>`,
                `¥${Utils.formatMoney(item.sale_price)}`,
                Utils.formatQty(item.min_stock),
                Utils.formatQty(item.max_stock)
            ]
        });
    });

    // 库存流水
    router.addRoute('/stock/transactions', (container) => {
        container.innerHTML = `
            <div class="card">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <span>库存流水</span>
                    <div class="d-flex gap-2">
                        <input type="date" class="form-control form-control-sm" id="startDate" style="width:160px">
                        <input type="date" class="form-control form-control-sm" id="endDate" style="width:160px">
                        <button class="btn btn-sm btn-outline-primary" id="filterBtn"><i class="bi bi-funnel"></i> 筛选</button>
                    </div>
                </div>
                <div class="table-responsive">
                    <table class="table table-hover mb-0">
                        <thead><tr>
                            <th>时间</th>
                            <th>商品</th>
                            <th>类型</th>
                            <th>数量变化</th>
                            <th>变更前</th>
                            <th>变更后</th>
                            <th>备注</th>
                        </tr></thead>
                        <tbody id="txnBody"></tbody>
                    </table>
                </div>
                <div class="card-footer d-flex justify-content-between align-items-center">
                    <small class="text-muted" id="totalInfo">共 0 条</small>
                    <div id="pagination"></div>
                </div>
            </div>
        `;

        let currentPage = 1;

        function loadTxns() {
            const tbody = document.getElementById('txnBody');
            tbody.innerHTML = '<tr><td colspan="7" class="text-center py-3"><div class="loading"></div></td></tr>';

            const params = { page: currentPage, per_page: 20 };
            const sd = document.getElementById('startDate')?.value;
            const ed = document.getElementById('endDate')?.value;
            if (sd) params.start_date = sd;
            if (ed) params.end_date = ed;

            ApiClient.getStockTransactions(params).then(result => {
                const data = result.data || {};
                const items = data.items || [];
                document.getElementById('totalInfo').textContent = `共 ${data.total || 0} 条`;

                if (items.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-4">暂无流水记录</td></tr>';
                    return;
                }

                tbody.innerHTML = items.map(t => {
                    const qtyChange = t.quantity_change;
                    const changeClass = qtyChange > 0 ? 'text-success' : qtyChange < 0 ? 'text-danger' : '';
                    const changeIcon = qtyChange > 0 ? 'bi bi-arrow-up-circle' : qtyChange < 0 ? 'bi bi-arrow-down-circle' : '';
                    return `<tr>
                        <td class="text-nowrap">${t.created_at || '-'}</td>
                        <td>${Utils.esc(t.product_name || '')}</td>
                        <td><span class="badge bg-secondary">${Utils.esc(t.type || '-')}</span></td>
                        <td class="fw-bold ${changeClass}">
                            ${changeIcon ? `<i class="${changeIcon} me-1"></i>` : ''}
                            ${qtyChange > 0 ? '+' : ''}${Utils.formatQty(qtyChange)}
                        </td>
                        <td>${Utils.formatQty(t.stock_before)}</td>
                        <td>${Utils.formatQty(t.stock_after)}</td>
                        <td class="text-muted small">${Utils.esc(t.remark || '')}</td>
                    </tr>`;
                }).join('');

                const pagination = document.getElementById('pagination');
                if (pagination) {
                    Utils.renderPagination(pagination, data, p => { currentPage = p; loadTxns(); });
                }
            }).catch(err => {
                tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger py-3">${err.message}</td></tr>`;
            });
        }

        setTimeout(() => {
            const sd = document.getElementById('startDate');
            const ed = document.getElementById('endDate');
            if (sd) sd.value = Utils.monthAgo();
            if (ed) ed.value = Utils.today();
            document.getElementById('filterBtn').onclick = () => { currentPage = 1; loadTxns(); };
        }, 50);

        loadTxns();
    });

    // 报表：进销存汇总
    router.addRoute('/reports/summary', (container) => {
        container.innerHTML = `
            <div class="card">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <span>进销存汇总报表</span>
                    <div class="d-flex gap-2">
                        <input type="date" class="form-control form-control-sm" id="startDate" style="width:160px">
                        <input type="date" class="form-control form-control-sm" id="endDate" style="width:160px">
                        <button class="btn btn-sm btn-primary" id="generateBtn"><i class="bi bi-file-earmark-bar-graph"></i> 生成报表</button>
                    </div>
                </div>
                <div class="card-body" id="reportBody">
                    <p class="text-muted text-center py-4">请选择日期范围，点击"生成报表"</p>
                </div>
            </div>
        `;

        setTimeout(() => {
            document.getElementById('startDate').value = Utils.monthAgo();
            document.getElementById('endDate').value = Utils.today();

            document.getElementById('generateBtn').onclick = async () => {
                const sd = document.getElementById('startDate').value;
                const ed = document.getElementById('endDate').value;
                const body = document.getElementById('reportBody');
                body.innerHTML = '<div class="text-center py-4"><div class="loading"></div></div>';

                try {
                    const resp = await ApiClient.getReportSummary({ start_date: sd, end_date: ed });
                    const report = resp.data || {};
                    const items = report.items || [];
                    const summary = report.summary || {};

                    if (items.length === 0) {
                        body.innerHTML = '<p class="text-muted text-center py-4">所选日期范围内无数据</p>';
                        return;
                    }

                    let html = `
                        <div class="row g-3 mb-4">
                            <div class="col-md-3"><div class="border rounded p-3 text-center bg-light">
                                <div class="text-muted small">期初库存</div>
                                <div class="fs-5 fw-bold">${Utils.formatQty(summary.total_begin)}</div>
                            </div></div>
                            <div class="col-md-3"><div class="border rounded p-3 text-center bg-light">
                                <div class="text-muted small">采购入库</div>
                                <div class="fs-5 fw-bold text-success">+${Utils.formatQty(summary.total_purchase)}</div>
                            </div></div>
                            <div class="col-md-3"><div class="border rounded p-3 text-center bg-light">
                                <div class="text-muted small">销售出库</div>
                                <div class="fs-5 fw-bold text-danger">-${Utils.formatQty(summary.total_sale)}</div>
                            </div></div>
                            <div class="col-md-3"><div class="border rounded p-3 text-center bg-light">
                                <div class="text-muted small">期末库存</div>
                                <div class="fs-5 fw-bold">${Utils.formatQty(summary.total_end)}</div>
                            </div></div>
                        </div>
                        <div class="table-responsive">
                            <table class="table table-sm table-bordered">
                                <thead><tr>
                                    <th>商品</th><th>分类</th><th>单位</th><th>期初</th><th>采购</th><th>销售</th><th>期末</th>
                                </tr></thead>
                                <tbody>
                    `;
                    items.forEach(item => {
                        html += `<tr>
                            <td>${Utils.esc(item.product_name)} [${Utils.esc(item.product_code)}]</td>
                            <td>${Utils.esc(item.category_name || '-')}</td>
                            <td>${Utils.esc(item.unit_name || '-')}</td>
                            <td>${Utils.formatQty(item.begin_stock)}</td>
                            <td class="text-success">+${Utils.formatQty(item.purchase_qty)}</td>
                            <td class="text-danger">-${Utils.formatQty(item.sale_qty)}</td>
                            <td class="fw-bold">${Utils.formatQty(item.end_stock)}</td>
                        </tr>`;
                    });
                    html += '</tbody></table></div>';
                    body.innerHTML = html;
                } catch (err) {
                    body.innerHTML = `<p class="text-danger text-center py-4">${err.message}</p>`;
                }
            };
        }, 50);
    });

    // 报表：销售明细
    router.addRoute('/reports/sales', (container) => {
        container.innerHTML = `
            <div class="card">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <span>销售明细报表</span>
                    <div class="d-flex gap-2">
                        <input type="date" class="form-control form-control-sm" id="startDate" style="width:160px">
                        <input type="date" class="form-control form-control-sm" id="endDate" style="width:160px">
                        <button class="btn btn-sm btn-primary" id="filterBtn"><i class="bi bi-funnel"></i> 筛选</button>
                    </div>
                </div>
                <div class="table-responsive">
                    <table class="table table-hover mb-0">
                        <thead><tr>
                            <th>订单号</th><th>日期</th><th>客户</th><th>商品</th><th>数量</th><th>单价</th><th>金额</th><th>状态</th>
                        </tr></thead>
                        <tbody id="detailBody">
                            <tr><td colspan="8" class="text-center text-muted py-4">加载中...</td></tr>
                        </tbody>
                    </table>
                </div>
                <div class="card-footer d-flex justify-content-between align-items-center">
                    <small class="text-muted" id="totalInfo">共 0 条</small>
                    <div id="pagination"></div>
                </div>
            </div>
        `;

        let currentPage = 1;

        function loadData() {
            const body = document.getElementById('detailBody');
            body.innerHTML = '<tr><td colspan="8" class="text-center py-3"><div class="loading"></div></td></tr>';

            const params = { page: currentPage, per_page: 20 };
            const sd = document.getElementById('startDate')?.value;
            const ed = document.getElementById('endDate')?.value;
            if (sd) params.start_date = sd;
            if (ed) params.end_date = ed;

            ApiClient.getReportSalesDetail(params).then(resp => {
                const data = resp.data || {};
                const items = data.items || [];
                document.getElementById('totalInfo').textContent = `共 ${data.total || 0} 条`;

                if (items.length === 0) {
                    body.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-4">暂无数据</td></tr>';
                    return;
                }

                body.innerHTML = items.map(item => {
                    const status = item.status || '';
                    return `<tr>
                        <td>${Utils.esc(item.order_no)}</td>
                        <td class="text-nowrap">${item.order_date || '-'}</td>
                        <td>${Utils.esc(item.customer_name || '-')}</td>
                        <td>${Utils.esc(item.product_name)} [${Utils.esc(item.product_code || '')}]</td>
                        <td>${Utils.formatQty(item.quantity)} ${Utils.esc(item.unit_name || '')}</td>
                        <td>¥${Utils.formatMoney(item.unit_price)}</td>
                        <td class="fw-bold">¥${Utils.formatMoney(item.subtotal)}</td>
                        <td><span class="badge ${Utils.statusBadge(status)}">${status}</span></td>
                    </tr>`;
                }).join('');

                const pagination = document.getElementById('pagination');
                if (pagination) {
                    Utils.renderPagination(pagination, data, p => { currentPage = p; loadData(); });
                }
            }).catch(err => {
                body.innerHTML = `<tr><td colspan="8" class="text-center text-danger py-3">${err.message}</td></tr>`;
            });
        }

        setTimeout(() => {
            document.getElementById('startDate').value = Utils.monthAgo();
            document.getElementById('endDate').value = Utils.today();
            document.getElementById('filterBtn').onclick = () => { currentPage = 1; loadData(); };
        }, 50);

        loadData();
    });

    // 初始化路由
    router.init('appContent');
    console.log('✅ 进销存管理系统 (IMS) 已加载');
})();
