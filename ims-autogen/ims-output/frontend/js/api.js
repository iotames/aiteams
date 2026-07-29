/* API 客户端 - 封装所有后端接口调用 */

(function() {
    'use strict';

    window.ApiClient = {
        async _req(method, path, data) {
            const url = '/api/v1' + path;
            const opts = { method, headers: { 'Content-Type': 'application/json' } };
            if (data && method !== 'GET') opts.body = JSON.stringify(data);
            const res = await fetch(url, opts);
            const json = await res.json();
            if (!json.success) throw new Error(json.message || '请求失败');
            return json;
        },

        _get(path, p) { const qs = p ? '?' + new URLSearchParams(p).toString() : ''; return this._req('GET', path + qs); },
        _post(path, d) { return this._req('POST', path, d); },
        _put(path, d) { return this._req('PUT', path, d); },
        _del(path) { return this._req('DELETE', path); },

        getProducts(p) { return this._get('/products', p); },
        getProduct(id) { return this._get('/products/' + id); },
        createProduct(d) { return this._post('/products', d); },
        updateProduct(id, d) { return this._put('/products/' + id, d); },
        deleteProduct(id) { return this._del('/products/' + id); },

        getCategories() { return this._get('/categories'); },
        createCategory(d) { return this._post('/categories', d); },
        updateCategory(id, d) { return this._put('/categories/' + id, d); },
        deleteCategory(id) { return this._del('/categories/' + id); },

        getUnits() { return this._get('/units'); },
        createUnit(d) { return this._post('/units', d); },
        updateUnit(id, d) { return this._put('/units/' + id, d); },
        deleteUnit(id) { return this._del('/units/' + id); },

        getSuppliers(p) { return this._get('/suppliers', p); },
        createSupplier(d) { return this._post('/suppliers', d); },
        updateSupplier(id, d) { return this._put('/suppliers/' + id, d); },
        deleteSupplier(id) { return this._del('/suppliers/' + id); },

        getCustomers(p) { return this._get('/customers', p); },
        createCustomer(d) { return this._post('/customers', d); },
        updateCustomer(id, d) { return this._put('/customers/' + id, d); },
        deleteCustomer(id) { return this._del('/customers/' + id); },

        getPurchaseOrders(p) { return this._get('/purchase-orders', p); },
        getPurchaseOrder(id) { return this._get('/purchase-orders/' + id); },
        createPurchaseOrder(d) { return this._post('/purchase-orders', d); },
        updatePurchaseOrder(id, d) { return this._put('/purchase-orders/' + id, d); },
        deletePurchaseOrder(id) { return this._del('/purchase-orders/' + id); },
        receivePurchaseOrder(id) { return this._post('/purchase-orders/' + id + '/receive', {}); },
        cancelPurchaseOrder(id) { return this._post('/purchase-orders/' + id + '/cancel', {}); },

        getSaleOrders(p) { return this._get('/sale-orders', p); },
        getSaleOrder(id) { return this._get('/sale-orders/' + id); },
        createSaleOrder(d) { return this._post('/sale-orders', d); },
        updateSaleOrder(id, d) { return this._put('/sale-orders/' + id, d); },
        deleteSaleOrder(id) { return this._del('/sale-orders/' + id); },
        shipSaleOrder(id) { return this._post('/sale-orders/' + id + '/ship', {}); },
        cancelSaleOrder(id) { return this._post('/sale-orders/' + id + '/cancel', {}); },

        getStock(p) { return this._get('/stock', p); },
        getStockTransactions(p) { return this._get('/stock/transactions', p); },
        getLowStock() { return this._get('/stock/low-stock'); },

        getReportSummary(p) { return this._get('/reports/summary', p); },
        getReportSalesDetail(p) { return this._get('/reports/sales-detail', p); }
    };

    console.log('API客户端已加载');
})();
