"""统一 JSON 响应格式"""

from flask import jsonify


def success_response(data=None, message='操作成功'):
    """成功响应"""
    resp = {'success': True, 'message': message}
    if data is not None:
        resp['data'] = data
    return jsonify(resp)


def error_response(message='操作失败', code=400):
    """失败响应"""
    return jsonify({'success': False, 'message': message}), code


def paginated_response(items, total, page=1, per_page=20):
    """分页响应"""
    return jsonify({
        'success': True,
        'data': {
            'items': items,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page if per_page > 0 else 0
        },
        'message': '查询成功'
    })
