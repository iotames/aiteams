"""Flask 应用入口"""

import os
from flask import Flask, send_from_directory
from flask_cors import CORS


def create_app():
    """创建 Flask 应用实例"""
    app = Flask(__name__,
                static_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend'),
                static_url_path='')

    # 配置
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ims-dev-secret-key')
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ims.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', f'sqlite:///{db_path}')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['JSON_AS_ASCII'] = False  # 支持中文

    CORS(app)

    # 初始化数据库
    from models import db
    db.init_app(app)

    with app.app_context():
        db.create_all()

    # 注册蓝图
    from routes import all_blueprints
    for bp in all_blueprints:
        app.register_blueprint(bp)

    # ── 静态文件路由 ──
    @app.route('/')
    def index():
        return send_from_directory(app.static_folder, 'index.html')

    @app.route('/js/<path:path>')
    def serve_js(path):
        return send_from_directory(os.path.join(app.static_folder, 'js'), path)

    @app.route('/css/<path:path>')
    def serve_css(path):
        return send_from_directory(os.path.join(app.static_folder, 'css'), path)

    # ── 健康检查 ──
    @app.route('/api/health')
    def health():
        return {'status': 'ok', 'message': 'IMS 服务运行中'}

    return app


# 创建应用实例
app = create_app()


if __name__ == '__main__':
    import webbrowser
    port = int(os.environ.get('PORT', 5000))
    print(f'🚀 进销存管理系统 (IMS) 启动中...')
    print(f'   本地访问: http://127.0.0.1:{port}')
    print(f'   按 Ctrl+C 停止服务')
    webbrowser.open(f'http://127.0.0.1:{port}')
    app.run(host='0.0.0.0', port=port, debug=True)
