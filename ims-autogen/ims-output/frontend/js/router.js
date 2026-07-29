/* Hash 路由管理器 */

(function() {
    'use strict';

    const Router = {
        routes: [],
        container: null,

        init(containerId) {
            this.container = document.getElementById(containerId) || document.getElementById('appContent');
            window.addEventListener('hashchange', () => this.resolve());
            if (!window.location.hash) {
                window.location.hash = '#/dashboard';
            } else {
                this.resolve();
            }
        },

        addRoute(pattern, handler) {
            this.routes.push({ pattern, handler });
        },

        resolve() {
            let hash = window.location.hash.replace(/^#\//, '') || 'dashboard';
            if (hash === 'purchases') hash = 'purchase-orders';
            if (hash === 'sales') hash = 'sale-orders';
            this.currentHash = hash;

            if (this.container) {
                this.container.innerHTML = '<div class="text-center py-5"><div class="spinner-border text-primary mb-2"></div><p class="text-muted">加载中...</p></div>';
            }

            for (const route of this.routes) {
                const params = this._match(route.pattern, hash);
                if (params !== null) {
                    if (this.container) route.handler(this.container, params);
                    return;
                }
            }
            if (this.container) {
                this.container.innerHTML = '<div class="text-center py-5"><i class="bi bi-emoji-frown fs-1 text-muted"></i><h4 class="mt-2 text-muted">页面未找到</h4><a href="#/dashboard" class="btn btn-primary mt-2">返回工作台</a></div>';
            }
        },

        _match(pattern, hash) {
            pattern = pattern.replace(/^\//, '');
            if (pattern === hash) return {};
            const pp = pattern.split('/'), hp = hash.split('/');
            if (pp.length !== hp.length) return null;
            const params = {};
            for (let i = 0; i < pp.length; i++) {
                if (pp[i].startsWith(':')) params[pp[i].slice(1)] = hp[i];
                else if (pp[i] !== hp[i]) return null;
            }
            return params;
        },

        navigate(hash) {
            window.location.hash = '#/' + hash;
        }
    };

    window.router = Router;
    console.log('路由管理器已加载');
})();
