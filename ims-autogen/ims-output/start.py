#!/usr/bin/env python3
"""进销存管理系统 (IMS) 启动脚本"""

import os
import sys
import subprocess
import webbrowser


def main():
    print('=' * 50)
    print('  进销存管理系统 (IMS) v1.0 MVP')
    print('  Inventory Management System')
    print('=' * 50)

    # 确保在工作目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # 检查 Python
    if sys.version_info < (3, 9):
        print('❌ 需要 Python 3.9+')
        sys.exit(1)

    # 检查依赖是否安装
    try:
        import flask
        print(f'✅ Flask {flask.__version__}')
    except ImportError:
        print('📦 正在安装依赖...')
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
        print('✅ 依赖安装完成')

    # 启动服务
    print()
    print(f'🚀 正在启动服务...')
    print(f'   本地访问: http://127.0.0.1:5000')
    print(f'   按 Ctrl+C 停止服务')
    print()

    # 自动打开浏览器
    webbrowser.open('http://127.0.0.1:5000')

    # 启动 (使用 backend/app.py)
    os.chdir(os.path.join(script_dir, 'backend'))
    from app import app
    app.run(host='0.0.0.0', port=5000, debug=True)


if __name__ == '__main__':
    main()
